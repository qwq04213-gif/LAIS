# 로컬 AI 스튜디오 허브 — 인체 전용 3D 복원(사진 한 장 → 돌려 볼 수 있는 사람 3D, SiTH)
# 무거운 모델은 별도 프로그램(worker, WSL2 의 자기 파이썬)이 돌리고, 여기서는 사진 준비·진행 표시·사진 붙이기·검사·GLB 저장을 해요.
# 기존 '3D 만들기'(27_m3d.py)와는 따로 도는 새 기능이에요 — 그쪽 코드는 건드리지 않아요.
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

from human3d import contracts as H3K
from human3d import export as h3_export
from human3d import manager as h3_manager
from human3d import mesh_qa as h3_qa
from human3d import preflight as h3_preflight
from human3d import preprocess as h3_pre
from human3d import texture_project as h3_tex
from human3d.worker_client import Client as H3Client, WorkerError as H3WorkerError

H3_DIR = OUT / H3K.OUT_SUB
H3_ID_RX = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
H3_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json", ".glb": "model/gltf-binary", ".log": "text/plain; charset=utf-8",
            ".obj": "text/plain", ".ply": "application/octet-stream"}
_H3_PF = {"t": 0.0, "v": None}


def h3_gpu():
    g = gpu_live()
    return {"used_mb": g["used_mb"], "total_mb": g["total_mb"]} if g else None


def h3_status(deep=False):
    """화면이 처음 열릴 때: 준비 상태·설치 진행·최근 작업."""
    now = time.time()
    if deep or _H3_PF["v"] is None or now - _H3_PF["t"] > 20:
        _H3_PF.update(t=now, v=h3_preflight.check(ROOT, h3_gpu(), deep=deep, log=log))
    return {"preflight": _H3_PF["v"], "install": h3_manager.install_view(), "jobs": h3_list(), "gpu": h3_gpu(),
            "stages": [{"id": s[0], "ko": s[1]} for s in H3K.STAGES], "gpu_hold": gpu_hold_view(), "defaults": H3K.DEFAULT_OPTS, "out": str(H3_DIR)}


def h3_install():
    r = h3_manager.install(ROOT, log=log)
    _H3_PF["v"] = None
    return r


def h3_job_dir(jid):
    if not H3_ID_RX.match(str(jid)):
        raise ValueError("작업을 찾을 수 없어요.")
    d = H3_DIR / jid
    if not d.is_dir():
        raise ValueError("작업을 찾을 수 없어요.")
    return d


def h3_file(jid, rel):
    """작업 폴더 안의 파일만 내줘요(밖으로 나가는 경로는 막아요)."""
    try:
        d = h3_job_dir(jid).resolve()
        fp = (d / urllib.parse.unquote(rel)).resolve()
    except (ValueError, OSError):
        return None
    if d not in fp.parents or not fp.is_file() or fp.suffix.lower() not in H3_TYPES:
        return None
    return fp


def h3_view(jid):
    """작업 하나의 결과 요약(화면용)."""
    d = h3_job_dir(jid)
    rd = lambda k: json.loads((d / H3K.FILES[k]).read_text(encoding="utf-8")) if (d / H3K.FILES[k]).is_file() else None
    url = lambda rel: f"/human3d/file/{jid}/{rel}" if (d / rel).is_file() else None
    meta, qa = rd("meta") or {}, rd("qa")
    views = {v[0]: url(f"result/view_{v[0]}.png") for v in H3K.VIEWS}
    views["observed"] = url("result/view_front_observed.png")
    return {"id": jid, "dir": str(d), "state": meta.get("state"), "meta": meta, "qa": qa, "diagnosis": rd("diagnosis"), "pick": rd("back_pick"),
            "glb": url(H3K.FILES["glb"]), "views": views, "back": url(H3K.FILES["back"]), "square": url(H3K.FILES["square"]), "mask": url(H3K.FILES["mask"]),
            "original": url(H3K.FILES["original"]), "log": url(H3K.FILES["log"])}


def h3_list():
    out = []
    for d in sorted(H3_DIR.iterdir(), reverse=True)[:30] if H3_DIR.is_dir() else []:
        if d.is_dir() and H3_ID_RX.match(d.name):
            st = "?"
            try:
                st = json.loads((d / H3K.FILES["meta"]).read_text(encoding="utf-8")).get("state") or "?"
            except (OSError, ValueError):
                pass
            out.append({"id": d.name, "state": st, "glb": (d / H3K.FILES["glb"]).is_file(), "thumb": f"/human3d/file/{d.name}/result/view_front.png" if (d / "result/view_front.png").is_file() else None})
    return out


def h3_cut(img, J):
    """사람 마스크: 기존 LAIS 배경 지우기를 그대로 써요(이미 투명 배경이면 그대로)."""
    if img.mode == "RGBA" and (np.asarray(img.getchannel("A")) < 16).mean() > 0.05:
        return img
    key = rmbg_default()
    if not rmbg_ready(key):
        r = rmbg_install({"key": key})
        if r.get("error"):
            raise RuntimeError(r["error"])
        raise RuntimeError(f"사람만 오려 내려면 배경 지우기 모델(약 {bgremove.MODELS[key]['mb']}MB)이 필요해서 받기 시작했어요. 다 받으면(설치와 모델 → 내려받기) 다시 눌러 주세요.")
    return rmbg_cut(key, img.convert("RGB"), None, J)


def h3_meta_update(d, **kw):
    f = d / H3K.FILES["meta"]
    try:
        m = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except ValueError:
        m = {}
    m.update(kw)
    f.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return m


def h3_finish(d, J, opts, step):
    """worker 가 만든 엔진 원본 → 사진 화소 붙이기 → 검사·4방향 그림 → GLB. 엔진 원본 파일은 고치지 않아요."""
    src = d / H3K.FILES["engine_ply"] if (d / H3K.FILES["engine_ply"]).is_file() else d / H3K.FILES["engine_obj"]
    if not src.is_file():
        raise RuntimeError("엔진이 메시 파일을 만들지 못했어요. 작업 폴더의 job.log 를 확인해 주세요.")
    mesh = h3_export.read_mesh(src)
    square = Image.open(d / H3K.FILES["square"]).convert("RGBA")
    notes, stats = [], {}
    step("project", 0.1)
    if opts.get("project_photo", True):
        frame = json.loads((d / H3K.FILES["frame"]).read_text(encoding="utf-8")) if (d / H3K.FILES["frame"]).is_file() else None
        orig = Image.open(d / H3K.FILES["rgba"]).convert("RGBA") if frame and (d / H3K.FILES["rgba"]).is_file() else None
        C, obs, stats = h3_tex.project_front(mesh, square, orig, frame)
        mesh = h3_export.Mesh(mesh.V, mesh.F, C, obs)
    (d / "result").mkdir(exist_ok=True)
    step("qa", 0.05)
    pose = h3_pre.load_openpose(d / H3K.FILES["keypoints"])
    smplx = None
    try:
        smplx = h3_export.read_obj(d / H3K.FILES["smplx_obj"]) if (d / H3K.FILES["smplx_obj"]).is_file() else None
    except Exception as e:  # noqa: BLE001
        notes.append(f"SMPL-X 몸을 읽지 못해 '몸 맞추기' 비교는 뺐어요: {e}")
    rep = h3_qa.inspect(mesh, square, pose, smplx, mesh.obs)
    rep["projection"] = stats
    step("qa", 0.6)
    rep["views"] = h3_qa.renders(mesh, d / "result", 768, tint=mesh.obs)
    if mesh.obs is not None:
        Image.open(d / "result" / "view_front_observed.png").save(d / H3K.FILES["texture"])
    step("export", 0.1)
    out = mesh
    if rep["topology"].get("inverted"):              # 안팎이 뒤집힌 메시는 GLB 에서만 면 방향을 바로잡아요(꼭짓점·면 수는 그대로, 엔진 원본 파일은 그대로)
        out = h3_export.Mesh(mesh.V, mesh.F[:, ::-1], mesh.C, mesh.obs)
        notes.append("면 방향이 뒤집혀 있어서 GLB 에서는 바로잡았어요(엔진 원본 파일은 그대로예요).")
    size = h3_export.write_glb(d / H3K.FILES["glb"], out, "human", extras={"generator": "LAIS human3d", "observed": "_OBSERVED: 1 = 원본 사진에서 가져온 색, 0 = AI 추정"})
    rep["glb"] = {"bytes": size, "vertices": int(len(out.V)), "faces": int(len(out.F)), "remesh": False, "decimate": False}
    rep["notes"] = notes
    h3_qa.save(rep, d / H3K.FILES["qa"])
    return rep


def do_human3d(p, J):
    """사진 한 장 → 인체 3D. 결과는 outputs/3D-human/<작업 id>/ 에 단계별로 남아요(실패해도 지우지 않아요)."""
    opts = H3K.clean_opts(p.get("opts"))
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = H3_DIR / jid
    d.mkdir(parents=True, exist_ok=True)
    info = J["human3d"] = {"id": jid, "dir": str(d), "stage": "preprocess", "stage_ko": H3K.STAGE_KO["preprocess"], "stages": [], "notes": [], "checks": [], "vram": None}
    hublog = open(d / "hub.log", "a", encoding="utf-8")

    def note(t):
        hublog.write(time.strftime("%H:%M:%S ") + t + "\n")
        hublog.flush()

    def step(stage, frac, msg=None):
        info["stage"], info["stage_ko"] = stage, H3K.STAGE_KO[stage]
        J["progress"], J["msg"] = H3K.overall(stage, frac), msg or H3K.STAGE_KO[stage]
        check_cancel(J)

    t0 = time.time()
    held = False
    try:
        step("preprocess", 0.05)
        raw = base64.b64decode(str(p["image"]).split(",", 1)[-1])
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
        alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if alpha else "RGB")
        rgba = h3_cut(im, J).convert("RGBA")
        info["checks"] = h3_pre.body_checks(rgba)
        if any(c["level"] == "bad" for c in info["checks"]):
            raise RuntimeError(next(c["text"] for c in info["checks"] if c["level"] == "bad"))
        _, frame = h3_pre.save_inputs(d, raw, im, rgba)
        h3_meta_update(d, id=jid, state="running", opts=opts, input={"size": list(im.size), "frame": frame, "checks": info["checks"]}, created=time.strftime("%Y-%m-%d %H:%M:%S"))
        note(f"입력 {im.size} → 정사각형 {frame['size']} (사람 키 비율 {frame['ratio']})")
        step("preprocess", 0.6, "인체 3D 프로그램 준비 중")
        pf = h3_preflight.check(ROOT, h3_gpu(), deep=True, log=log)
        _H3_PF.update(t=time.time(), v=pf)
        info["gender"] = opts["gender"]
        gd = pf.get("genders")
        want = "neutral" if opts["gender"] == "auto" else opts["gender"]
        if pf["ready"] and gd is not None and not gd.get(want):      # 고른 성별의 몸 모델이 없으면 다른 성별로 바꾸지 않고 여기서 멈춰요
            raise RuntimeError(f"SMPL-X {H3K.GENDER_KO[want]} 몸 모델 파일(SMPLX_{want.upper()}.npz)이 없어요" + (" ('자동'은 중립 모델을 써요)" if opts["gender"] == "auto" else "") +
                               ". 다른 성별 모델로 바꿔 쓰지 않아요 — 파일을 넣거나 다른 성별을 골라 주세요.")
        if not pf["ready"]:
            miss = [c for c in pf["checks"] if not c["ok"] and not c.get("info") and c["id"] not in ("gpu", "w_vram", "w_vram_free", "w_smplx")]
            raise RuntimeError("인체 3D 를 돌릴 준비가 안 됐어요 — " + " / ".join(c["text"] + (f" ({c['fix']})" if c.get("fix") else "") for c in miss[:3]))
        # 그래픽카드 혼자 쓰기: 이미지·영상 작업은 이 작업이 대기열을 잡고 있어서 못 돌고, 대화(Ollama)는 여기서 막아요.
        # 답을 만들고 있는 대화가 있으면 끝날 때까지 기다린 뒤, Ollama·ComfyUI 가 올려 둔 모델을 내려요. 끝나면(완료·중단·실패) finally 에서 꼭 풀어요.
        step("preprocess", 0.8, "그래픽카드 비우는 중")
        gpu_exclusive_begin("human3d", "인체 3D", owner=J["id"], should_stop=lambda: J.get("cancel"),
                            on_wait=lambda n: J.update(msg="진행 중인 대화가 끝나기를 기다리는 중"))
        held = True
        info["gpu_hold"] = True
        note(f"그래픽카드 혼자 쓰기 시작 (Ollama 에 남은 모델: {ollama_loaded() or '없음'})")
        cl = H3Client(h3_manager.STATE["port"])
        try:
            wj = cl.submit(h3_manager.job_path(d), opts)
        except H3WorkerError as e:
            raise RuntimeError(str(e)) from None
        wid, st = wj["id"], None
        note(f"worker 작업 {wid} 시작")
        fails = 0
        while True:
            if J.get("cancel"):
                try:
                    cl.cancel(wid)
                except H3WorkerError:
                    pass
            try:
                st, fails = cl.status(wid), 0
            except H3WorkerError as e:
                fails += 1
                if fails > 15:
                    raise RuntimeError(f"인체 3D 프로그램(worker)이 응답하지 않아요: {e}") from None
                time.sleep(1)
                continue
            if st.get("stage") in H3K.STAGE_KO:
                info["stage"], info["stage_ko"] = st["stage"], H3K.STAGE_KO[st["stage"]]
                J["progress"] = H3K.overall(st["stage"], st.get("stage_progress") or 0)
                J["msg"] = H3K.STAGE_KO[st["stage"]] + (f" — {st['msg']}" if st.get("msg") and st["msg"] not in ("시작", "대기 중") else "")
            info.update(stages=st.get("stages") or [], notes=st.get("notes") or [], grid=(st.get("opts") or {}).get("grid"), chunk=(st.get("opts") or {}).get("chunk"), retries=st.get("retries", 0), attempts=st.get("attempts") or [],
                        vram={"now_mb": st.get("vram_now_mb"), "peak_mb": st.get("vram_peak_mb"), "total_mb": st.get("vram_total_mb")})
            if st["state"] in ("done", "error", "cancelled"):
                break
            time.sleep(0.5 if os.environ.get("HUMAN3D_WORKER_CMD") else 1.0)
        if st["state"] == "cancelled":
            raise Cancelled("사용자가 중단했어요. 지금까지 만든 중간 결과는 작업 폴더에 남아 있어요.")
        if st["state"] == "error":
            e = st.get("error") or {}
            info["error"] = e
            raise RuntimeError(f"{H3K.STAGE_KO.get(e.get('stage'), e.get('stage') or '')} 단계에서 멈췄어요 — {H3K.ERRORS.get(e.get('code'), '')} {e.get('msg') or ''} (자세한 진단: {d / H3K.FILES['diagnosis']})".replace("  ", " "))
        gj = d / "smplx" / "gender.json"
        try:
            info["gender_used"] = json.loads(gj.read_text(encoding="utf-8")) if gj.is_file() else None
        except ValueError:
            info["gender_used"] = None
        if not (info["gender_used"] or {}).get("applied"):     # 몸 맞추기가 성별을 적용했다는 기록이 없으면 '적용됨'으로 치지 않아요
            raise RuntimeError("몸 맞추기 단계가 어떤 성별의 몸 모델을 썼는지 기록하지 않았어요. 성별이 적용됐는지 확인할 수 없어 결과를 내지 않았어요(작업 폴더는 그대로 있어요).")
        rep = h3_finish(d, J, st.get("opts") or opts, step)
        final_grid = (st.get("opts") or opts).get("grid") or opts["grid"]
        info["low_detail"] = final_grid < opts["grid"]         # 메모리가 모자라 격자를 낮춰 만들었는지
        if info["low_detail"]:
            info["low_detail_text"] = f"그래픽카드 메모리가 모자라 형태 복원 격자를 {opts['grid']} → {final_grid} 로 낮춰 만들었어요. 형상(주름·손가락·얼굴 굴곡)이 덜 세밀해요."
        info["qa"] = {"pass": rep["pass"], "warnings": rep["warnings"], "problems": rep["problems"], "silhouette": rep.get("silhouette"), "topology": {k: rep["topology"].get(k) for k in
                      ("vertices", "faces", "components", "big_holes", "boundary_edges", "inverted", "degenerate_faces")}}
        info["views"] = {k: f"/human3d/file/{jid}/result/{v}" for k, v in rep["views"].items()}
        info["glb"] = f"/human3d/file/{jid}/{H3K.FILES['glb']}"
        info["verified"] = bool(pf.get("verified"))
        h3_meta_update(d, state="done", hub_seconds=round(time.time() - t0, 1), qa_pass=rep["pass"], glb=H3K.FILES["glb"], requested_grid=opts["grid"], final_grid=final_grid, gender=opts["gender"], gender_used=info["gender_used"],
                       low_detail=info["low_detail"], low_detail_text=info.get("low_detail_text"))
        J["images"].append(info["glb"])
        J["msg"] = ("인체 3D 를 만들었어요." if rep["pass"] else "만들었지만 검사에서 문제가 보여요 — 아래 검사 결과를 확인해 주세요.") + (f" (격자 {final_grid} — 형상이 덜 세밀해요)" if info["low_detail"] else "")
        step("export", 1.0, J["msg"])
        note("끝: " + J["msg"])
    except Cancelled:
        h3_meta_update(d, state="cancelled")
        raise
    except Exception as e:
        h3_meta_update(d, state="error", hub_error=str(e))
        note("실패: " + str(e))
        raise
    finally:
        if held:
            gpu_exclusive_end("human3d", J["id"])
            info["gpu_hold"] = False
        hublog.close()
    return []
