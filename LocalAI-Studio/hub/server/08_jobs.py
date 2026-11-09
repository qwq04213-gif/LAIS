# 로컬 AI 스튜디오 허브 — 영상 소리·자막 · 작업 실행 · 작업 대기열
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

# ───────────────────── 영상에 소리 · 자막 넣기 ─────────────────────
VMIX_DIR = ROOT / "cache" / "vmix"
VMIX_MAX = 500 << 20


def vmix_src(ref, exts, what):
    """작업에 쓸 파일: 결과 폴더의 파일(/out/…) 또는 올려 둔 파일(up:아이디)."""
    ref = str(ref or "")
    f = None
    if ref.startswith("/out/"):
        f = out_path(ref[5:])
    elif re.fullmatch(r"up:[0-9a-f]{12}", ref):
        f = next((x for x in sorted(VMIX_DIR.glob(ref[3:] + ".*")) if x.suffix.lower() in exts), None)
    if not f or f.suffix.lower() not in exts or not f.is_file():
        raise ValueError(f"{what} 파일을 찾을 수 없어요. 목록에서 다시 골라 주세요.")
    return f


def vmix_name(f):
    """올려 둔 파일이면 원래 이름을, 아니면 파일 이름을."""
    try:
        return (f.with_suffix(".nm")).read_text(encoding="utf-8").strip() or f.name
    except OSError:
        return f.name


def flag(p, k, d=True):
    v = p.get(k, d)
    return v not in (False, 0, "0", "", "false", "False", "off", None)


def do_vmix(p, J):
    """영상에 소리(음성·음악)와 자막을 합쳐 새 영상으로. 결과: [(바이트, 정보, 확장자)]"""
    video = vmix_src(p.get("video"), vmix.VIDEO_EXT, "영상")
    audio = vmix_src(p.get("audio"), vmix.AUDIO_EXT, "소리") if p.get("audio") else None
    subs = str(p.get("subs") or "").strip()[:20000]
    if not audio and not subs:
        raise ValueError("넣을 소리나 자막을 하나 이상 골라 주세요.")
    if subs and blocked(subs):
        raise ValueError(BLOCK_MSG)
    ff = vmix.find_ffmpeg(PY, ROOT)
    if not ff:
        raise RuntimeError("영상을 합치려면 ffmpeg 가 필요해요. 아래 [빠진 부품 설치] 버튼으로 imageio-ffmpeg 를 설치해 주세요. (No module named 'imageio_ffmpeg')")
    job = dict(video=video, audio=audio, amode="mix" if p.get("amode") == "mix" else "replace", vol=clamp(num(p, "vol", 100, int), 0, 300) / 100,
               ovol=clamp(num(p, "ovol", 100, int), 0, 300) / 100, delay=clamp(num(p, "delay", 0, float), 0, 600), fit="audio" if p.get("fit") == "audio" else "video",
               fade=flag(p, "fade"), subs=subs, size=clamp(num(p, "sub_size", 5.5, float), 2, 15), pos=p.get("sub_pos") if p.get("sub_pos") in ("top", "middle", "bottom") else "bottom",
               color=p.get("sub_color") or "#ffffff", outline=flag(p, "sub_outline"), bg=flag(p, "sub_bg", False))
    work = VMIX_DIR / ("job-" + uuid.uuid4().hex[:8])

    def say(m, pc=None):
        J["msg"] = m
        if pc is not None:
            J["progress"] = pc
    try:
        res = vmix.make(ff, job, work, say, lambda: J.get("cancel"))
        data = res["out"].read_bytes()
    except vmix.Cancelled as e:
        raise Cancelled(str(e))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for w in res["warn"]:
        warn(J, w)
    try:
        base = json.loads(Path(str(video) + ".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        base = {}
    info = dict(base, kind="vid", post="소리·자막", source=vmix_name(video))
    if audio:
        info["audio"] = vmix_name(audio)
    if subs:
        info["subs"] = subs[:2000]
        info.setdefault("prompt", subs.splitlines()[0][:200])
    if res["srt"] and flag(p, "save_srt", False):
        info["_extra"] = {".srt": res["srt"]}
    return [(data, info, ".mp4")]


def vmix_list():
    """영상·소리 고르기 목록(결과 폴더). 소리는 음성·음악, 음성은 만들 때 쓴 글도 같이 줘요."""
    def rows(sub, exts, limit=150):
        d, out = OUT / sub, []
        for f in out_files(d, exts) if d.is_dir() else []:
            try:
                out.append((f.stat().st_mtime, f))
            except OSError:
                continue
        out.sort(key=lambda r: r[0], reverse=True)
        res = []
        for mt, f in out[:limit]:
            try:
                meta_ = json.loads(Path(str(f) + ".json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta_ = {}
            res.append({"url": "/out/" + "/".join(urllib.parse.quote(x) for x in f.relative_to(OUT).parts), "name": f.name, "kind": sub, "time": int(mt),
                        "text": str(meta_.get("text") or meta_.get("prompt") or "")[:3000]})
        return res
    return {"videos": sorted(rows(OUT_SUB["vid"], vmix.VIDEO_EXT) + rows(OUT_SUB["vrestore"], vmix.VIDEO_EXT) + rows(OUT_SUB["audio"], vmix.VIDEO_EXT), key=lambda x: -x["time"])[:200],
            "audios": sorted(rows(OUT_SUB["tts"], vmix.AUDIO_EXT) + rows(OUT_SUB["music"], vmix.AUDIO_EXT) + rows(OUT_SUB["audio"], vmix.AUDIO_EXT), key=lambda x: -x["time"])[:200],
            "ffmpeg": bool(vmix.find_ffmpeg(PY, ROOT))}


def vmix_upload(h):
    """내 컴퓨터의 영상·소리 파일을 받아 cache/vmix 에 둬요(본문이 파일 그대로)."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    kind, name = (q.get("kind") or [""])[0], Path((q.get("name") or ["file"])[0]).name
    ext = Path(name).suffix.lower()
    if ext not in (vmix.VIDEO_EXT if kind == "video" else vmix.AUDIO_EXT if kind == "audio" else ()):
        return {"error": "이 파일 형식은 쓸 수 없어요. " + ("영상은 mp4 · webm · mov · mkv" if kind == "video" else "소리는 wav · mp3 · m4a · ogg · flac") + " 파일을 올려 주세요."}
    n = int(h.headers.get("Content-Length") or 0)
    if n <= 0 or n > VMIX_MAX:
        return {"error": "파일이 너무 커요(500MB 이하만 올릴 수 있어요)."}
    VMIX_DIR.mkdir(parents=True, exist_ok=True)
    for f in VMIX_DIR.glob("*"):                      # 사흘 지난 올린 파일은 정리
        try:
            if f.is_file() and re.fullmatch(r"[0-9a-f]{12}", f.stem) and time.time() - f.stat().st_mtime > 3 * 86400:
                f.unlink()
        except OSError:
            pass
    uid = uuid.uuid4().hex[:12]
    dest = VMIX_DIR / (uid + ext)
    left = n
    with open(dest, "wb") as fh:
        while left:
            chunk = h.rfile.read(min(1 << 20, left))
            if not chunk:
                break
            fh.write(chunk)
            left -= len(chunk)
    if left:
        dest.unlink(missing_ok=True)
        return {"error": "파일을 끝까지 받지 못했어요. 다시 올려 주세요."}
    (VMIX_DIR / (uid + ".nm")).write_text(name, encoding="utf-8")
    return {"ok": True, "id": "up:" + uid, "name": name, "kind": kind}


def job_thread(J, p):
    try:
        J["state"], J["msg"] = "running", "엔진 준비 중"
        if p["kind"] in ("tts", "vmix") or (p["kind"] == "vedit" and p.get("op") in ("concat", "trim", "cutlist")) or (p["kind"] == "vana" and p.get("op") not in ("vdepth", "cam3d")) or p["kind"] == "audio" or (p["kind"] == "m3d" and p.get("op") == "prep") or (p["kind"] == "lora" and not (p.get("op") == "augment" and p.get("mode") == "ai")) \
                or (p["kind"] == "vrestore" and not (p.get("op") == "run" and (vr_opts(p)["upscale"] or vr_opts(p)["interp"]))):
            pass                                          # 음성 만들기·영상 소리/자막 넣기는 ComfyUI 를 쓰지 않아요
        elif (p["kind"] == "feat" and p.get("feature") in ("resize", "color", "rmbg")) or (p["kind"] == "vpost" and p.get("op") == "gif"):
            pass                                          # 크기·색 보정·배경 지우기는 ComfyUI 없이 바로 처리해요
        elif (p["kind"] == "batch" and (p.get("op") != "upscale" or scale_of(p) <= 1.0)) or (p["kind"] == "up" and p.get("mode") != "refine" and scale_of(p) <= 1.0):
            pass                                          # 일괄 처리의 배경 지우기·크기 변경, 줄이기(1배 이하)는 ComfyUI 가 필요 없어요
        else:
            wait_comfy()
            claim("image")
        items = {"edit": do_edit, "gen": do_gen, "up": do_up, "wf": do_wf, "feat": do_feat, "vid": do_vid, "vpost": do_vpost, "vmix": do_vmix, "vedit": do_vedit, "music": do_music, "tts": do_tts, "batch": do_batch, "vana": do_vana, "lora": do_lora, "vrestore": do_vrestore, "audio": do_audio, "m3d": do_m3d}[p["kind"]](p, J)
        sub = OUT_SUB["vid"] if p["kind"] in ("vpost", "vmix", "vedit", "vana") else OUT_SUB.get(p["kind"], "기타")
        stamp, embed = time.strftime("%Y%m%d-%H%M%S"), bool(p.get("embed"))
        jdir = job_dir_name(stamp, J.get("out_label") or "")         # 작업 한 번 = 폴더 하나(사용자 요청 — 결과 폴더가 너무 어지러워서)
        for i, (im, info, graph) in enumerate(items):
            dsub0 = info.pop("_sub", None) or sub if isinstance(info, dict) else sub      # 깊이 맵처럼 따로 모아 두는 결과는 자기 폴더로
            dsub = dsub0 + "/" + jdir
            (OUT / dsub).mkdir(parents=True, exist_ok=True)
            if p["kind"] in ("vid", "vpost", "vmix", "vedit", "music", "tts") or isinstance(im, (bytes, bytearray, Path)):      # 영상·음악: 받은 파일을 그대로 저장하고, 설정은 옆에 .json 으로 남겨요
                name = f'{stamp}-{uuid.uuid4().hex[:4]}-{p["kind"] if p["kind"] in ("music", "tts", "audio", "m3d") else "m3d" if graph in (".glb", ".zip") else "vid"}-{i}{graph}'
                if isinstance(im, Path):                      # 큰 결과(복원한 영상 등)는 메모리에 올리지 않고 파일을 옮겨요
                    shutil.move(str(im), OUT / dsub / name)
                    try:
                        im.parent.rmdir()
                    except OSError:
                        pass
                else:
                    (OUT / dsub / name).write_bytes(im)
                (OUT / dsub / (name + ".json")).write_text(json.dumps({k: v for k, v in info.items() if k != "_extra"}, ensure_ascii=False), encoding="utf-8")
                for xext, xdata in (info.get("_extra") or {}).items():      # 자막 파일(.srt) 같은 덧붙이는 파일
                    (OUT / dsub / (Path(name).stem + xext)).write_text(xdata, encoding="utf-8")
                J["images"].append("/out/" + urllib.parse.quote(dsub0) + "/" + urllib.parse.quote(jdir) + "/" + name)
                J.setdefault("used", []).append(info.get("prompt", ""))
                continue
            if p["kind"] == "gen" and not p.get("init"):      # 모델은 8·16 배수 크기로만 그려서, 입력한 정확한 크기와 조금 다르면 그 크기로 맞춰 저장해요
                try:
                    rw, rh = int(float(p.get("w"))), int(float(p.get("h")))
                    if (rw, rh) != im.size and 64 <= rw <= 4096 and 64 <= rh <= 4096 and abs(rw - im.width) <= 32 and abs(rh - im.height) <= 32:
                        im = im.resize((rw, rh), RS.LANCZOS)
                except (TypeError, ValueError):
                    pass
            name = f'{stamp}-{uuid.uuid4().hex[:4]}-{"depth" if dsub0 == DEPTH_SUB else p["kind"]}-{i}.png'
            im.save(OUT / dsub / name, "PNG", pnginfo=meta.pnginfo(info, graph) if embed else None)
            J["images"].append("/out/" + urllib.parse.quote(dsub0) + "/" + urllib.parse.quote(jdir) + "/" + name)
            J.setdefault("used", []).append(info.get("prompt", ""))
        J["state"], J["progress"] = "done", 1.0
    except Cancelled as e:
        J["state"], J["error"] = "cancelled", str(e)
        if p["kind"] == "batch" and J.get("images"):
            J["msg"] = f"중단했어요. 지금까지 {len(J['images'])}장은 저장돼 있어요."
    except Exception as e:
        J["state"], J["error"] = "error", str(e) or e.__class__.__name__
        nd = need_ids(J["error"], p)
        if nd:
            J["need"] = nd
        if pymod_missing(J["error"]):
            J["pymod"] = pymod_missing(J["error"])
        og = oom_guide(J["error"], p)
        if og:
            J["oom"] = og
        log("[작업 오류]", J["error"])
    finally:
        _clean_tmp(J)
        if p.get("stage"):      # 올려 둔 파일은 내가 만든 임시 사본이라 끝나면 정리해요
            shutil.rmtree(BATCH_IN / str(p["stage"]), ignore_errors=True)


def _clean_tmp(J):
    for f in J["tmp"]:
        try:
            f.unlink()
        except OSError:
            pass
    J["tmp"].clear()


# ───────────────────────── 작업 대기열 ─────────────────────────
QUEUE, QP = [], {}
_QCV = threading.Condition()
_QW = {"t": None, "eta": None}
KIND_NAME = {"vedit": "영상 편집", "edit": "이미지 편집", "gen": "이미지 생성", "up": "업스케일", "wf": "워크플로", "feat": "기능", "vid": "영상 만들기", "vpost": "영상 다듬기", "vmix": "영상 소리·자막", "music": "음악 만들기", "tts": "음성 만들기", "batch": "일괄 처리", "vana": "영상 분석", "lora": "LoRA 만들기", "vrestore": "영상 복원", "audio": "소리 분리·복원", "m3d": "3D 만들기"}
DONE_STATES = ("done", "error", "cancelled")


def job_label(p):
    k = p.get("kind")
    name = KIND_NAME.get(k, "작업")
    if k == "batch":
        return f"{name} · {BATCH_OPS.get(p.get('op'), '')} ({p.get('count', 0)}장)"
    if k == "feat":
        name = next((f["title"] for f in FEATURES if f["id"] == p.get("feature")), name)
    txt = " ".join(str(p.get("prompt") or "").split())
    return name + (f" · {txt[:36]}{'…' if len(txt) > 36 else ''}" if txt else "")


NEED_RULES = [      # 작업 오류 글 → 바로 받을 추천 모델(models.json 의 id). 함께 필요한 공용 파일은 받을 때 같이 받아요.
    (r"체크포인트가 없", ["noobai", "sdxl-vae-fix"]), (r"업스케일 모델이 없", ["esrgan"]), (r"감지 모델이 없", ["adetailer"]),
    (r"Krea 2 스타일 참조", ["krea2-style-reference"]), (r"Krea 2 깊이 컨트롤", ["krea2-depth-control"]),
    (r"Stable Audio 3|T5Gemma", ["stable-audio-3"]), (r"Stable Audio|T5-base", ["stable-audio-open"]), (r"ACE-Step", ["ace-step-15-turbo"]), (r"4단계 가속 LoRA", ["wan22-lightning"]),
    (r"TRELLIS\.2", ["trellis2"]), (r"Pixal3D", ["pixal3d-mv"]), (r"LTX-2\.5", ["ltx25"]), (r"SeedVR2", ["seedvr2"]), (r"Z-Image-Turbo", ["z-image-turbo"]), (r"Depth Anything 3", ["depth-anything-3"]), (r"FLUX 3 Klein", ["flux3-klein"]), (r"LTX-Video", ["ltx-video"]), (r"Wan VACE", ["wan-vace"]), (r"S2V", ["wan-s2v"]),
    (r"Wan 2\.2 14B 이미지", ["wan22-14b-i2v"]), (r"Wan 2\.2 14B 글", ["wan22-14b-t2v"]), (r"'Wan 2\.2 영상'", ["wan22-ti2v-5b"]),
    (r"SD3\.5", ["sd35-medium"]), (r"MOSS-Image 편집", ["moss-image-edit"]), (r"MOSS-Image", ["moss-image"]), (r"Qwen-Image 2\.1", ["qwen-image"]),
    (r"Lightning LoRA", ["qwen-lightning"]),
    (r"이미지를 볼 수 있는 대화 모델", ["qwen25vl-7b"]), (r"기반 모델\(체크포인트\)", ["noobai"]), (r"FLUX ControlNet Union", ["controlnet-flux-union"]), (r"ControlNet Union SDXL", ["controlnet-union"]), (r"도우미로 쓸 대화 모델|도구 호출", ["qwen35-9b"]),
]
NEED_FAM = {"flux": ["krea-dev"], "chroma": ["chroma-hd"], "krea2": ["krea2-turbo"]}


def need_ids(err, p=None):
    """'설치와 모델에서 설치해 주세요' 같은 오류일 때 바로 받을 수 있는 추천 모델 id 목록(최대 3개)."""
    err = str(err or "")
    if "설치" not in err or "ffmpeg" in err or "부품" in err or "확장" in err or "노드" in err:
        return []
    known = {m["id"] for m in CATALOG["llm"] + CATALOG["image"]}
    out = []
    if (p or {}).get("kind") == "gen" and "없는 파일" in err:
        out += NEED_FAM.get((p or {}).get("gengine"), [])
    for rx, ids in NEED_RULES:
        if re.search(rx, err):
            out += ids
    return [i for i in dict.fromkeys(out) if i in known][:3]


def submit_job(p, **extra):
    """작업 하나를 만들어 대기열에 넣어요(화면의 /api/job 과 대화 실행 모드가 같이 써요)."""
    if len(JOBS) > 50:
        for k, v in list(JOBS.items()):
            if v.get("state") in DONE_STATES:
                del JOBS[k]
                break
    J = {"id": uuid.uuid4().hex[:10], "state": "queued", "msg": "대기 중", "elapsed": 0, "images": [], "tmp": [], **extra}
    JOBS[J["id"]] = J
    J["feature"] = str(p.get("feature") or "")[:40]
    enqueue(J, p)
    return J


HIST_FILE = LOGS / "job-history.jsonl"
HIST_MAX = 4 << 20


def job_history_add(J):
    """끝난 작업을 logs\\job-history.jsonl 에 한 줄씩 남겨요(프로그램을 다시 켜도 남아요. 4MB 를 넘으면 한 번 옮겨 두고 새로 써요)."""
    try:
        LOGS.mkdir(exist_ok=True)
        if HIST_FILE.is_file() and HIST_FILE.stat().st_size > HIST_MAX:
            HIST_FILE.replace(HIST_FILE.with_suffix(".old.jsonl"))
        row = {k: J.get(k) for k in ("id", "kind", "label", "feature", "state", "error", "t_add", "t_start", "t_end", "images", "warn", "agent")}
        with open(HIST_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in row.items() if v not in (None, "", [])}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def enqueue(J, p):
    J["kind"], J["label"], J["t_add"] = p["kind"], J.get("label") or job_label(p), time.time()
    with _QCV:
        QP[J["id"]] = p
        QUEUE.append(J["id"])
        _QCV.notify_all()
        if not (_QW["t"] and _QW["t"].is_alive()):
            _QW["t"] = threading.Thread(target=job_worker, daemon=True)
            _QW["t"].start()
        if not (_QW["eta"] and _QW["eta"].is_alive()):
            _QW["eta"] = threading.Thread(target=eta_loop, daemon=True)
            _QW["eta"].start()


# ───────────────────────── 남은 시간 (모든 작업을 한 곳에서 같은 방법으로) ─────────────────────────
# 예전에는 그리는 단계(그래프) 하나만 보고 어림해서, 여러 장·여러 단계 작업이나 화면마다 값이 제각각이었어요.
# 이제는 작업 전체 진행률(0~1)이 늘어나는 속도로만 어림해요: 처음부터의 평균 속도와 최근 속도를 반씩 섞고,
# 표시 값은 1초마다 줄어들면서 새 어림값 쪽으로 조금씩 따라가서 튀지 않아요. 진행이 멈추면 최근 속도가 느려져 남은 시간이 늘어나요.
ETA_MIN_T = 8          # 진행이 시작되고 이만큼(초) 지나야
ETA_MIN_P = 0.02       # 그리고 진행률이 이만큼 늘어야 보여 줘요(그 전엔 어림이 부정확해요)


ETA_FILE = ROOT / "eta_history.json"     # 작업 종류별 '진행률 → 걸린 시간 비율' 곡선(최근 5번) — 남은 시간 어림에 써요
ETA_CK = [round(0.05 * i, 2) for i in range(1, 20)]      # 0.05, 0.10, … 0.95
_ETA_H = {"d": None}


def eta_key(p):
    """작업 진행 모양이 비슷한 것끼리 묶는 이름(크기·단계 수는 빼요 — 곡선의 '모양'만 쓰니까요)."""
    k = [str(p.get("kind") or "")]
    for n in ("op", "feature", "mode", "engine", "gengine", "fengine", "wan_ver"):
        if p.get(n):
            k.append(f"{n}={p.get(n)}")
    for n in ("hires", "refine", "blender", "photo", "upscale", "interp", "fill"):
        if p.get(n) not in (None, "", False, 0, "0"):
            k.append(n)
    return "|".join(k)[:200]


def _eta_hist():
    if _ETA_H["d"] is None:
        try:
            d = json.loads(ETA_FILE.read_text(encoding="utf-8"))
            _ETA_H["d"] = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            _ETA_H["d"] = {}
    return _ETA_H["d"]


def eta_learn(J):
    """끝난 작업의 진행 곡선을 기억해요(진행률 0.05 칸마다 '그때까지 걸린 시간 ÷ 전체 시간')."""
    try:
        key, pts, t0, t1 = J.get("_eta_key"), (J.get("_eta") or {}).get("all") or [], J.get("t_start"), J.get("t_end")
        if not key or J.get("state") != "done" or t0 is None or t1 is None or t1 - t0 < 10 or len(pts) < 3:
            return
        T = t1 - t0
        curve = []
        for c in ETA_CK:
            t = next((q[0] for q in pts if q[1] >= c), None)
            if t is None:
                return
            curve.append(round(min(1.0, (t - t0) / T), 4))
        d = _eta_hist()
        d[key] = ([curve] + [x for x in d.get(key, []) if isinstance(x, list) and len(x) == len(ETA_CK)])[:5]
        if len(d) > 300:
            for k in list(d)[:len(d) - 300]:
                d.pop(k, None)
        ETA_FILE.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    except Exception:  # noqa: BLE001 — 남은 시간은 덤이라 실패해도 작업에는 영향 없어요
        pass


def eta_from_hist(J, p, now, t_reach=None):
    """지난번 같은 종류 작업의 곡선으로 남은 시간 어림 → 초 또는 None.
    t_reach: 지금 진행률에 처음 닿은 때 — 진행률이 한동안 멈춰 있어도(마무리 단계) 그때 기준으로 전체 시간을 어림해요."""
    cs = _eta_hist().get(J.get("_eta_key") or "")
    if not cs or J.get("t_start") is None or p < ETA_CK[0] * 0.5:
        return None
    f_ck = [sum(c[i] for c in cs) / len(cs) for i in range(len(ETA_CK))]
    xs, ys = [0.0] + ETA_CK + [1.0], [0.0] + f_ck + [1.0]
    i = next(k for k in range(1, len(xs)) if p <= xs[k])
    f = ys[i - 1] + (ys[i] - ys[i - 1]) * (p - xs[i - 1]) / max(1e-9, xs[i] - xs[i - 1])
    e = (t_reach or now) - J["t_start"]
    if f < 0.03 or e < 3:
        return None
    return max(0.0, e / f - (now - J["t_start"]))


def eta_update(J, now=None):
    """J["eta"](초, 모르면 None)·J["elapsed"](작업 시작부터 초)를 새로 정해요."""
    now = now or time.time()
    if J.get("t_start") is not None:
        J["elapsed"] = int(now - J["t_start"])
    E = J.setdefault("_eta", {"pts": []})
    pts, p = E["pts"], J.get("progress")
    if J.get("state") != "running" or not isinstance(p, (int, float)) or J.get("pest") or p >= 1:
        J["eta"] = None
        return None
    if not pts and (p <= 0 or J.get("phase") in ("load", "wait")):     # 첫 모델 불러오기는 빼고 재요
        J["eta"] = None
        return None
    al = E.setdefault("all", [])                       # 작업 전체 곡선(끝나면 eta_learn 이 기억해요)
    if not al or p > al[-1][1]:
        al.append((now, p))
    if pts and p < pts[-1][1] - 1e-6:                  # 진행률이 뒤로 가면 처음부터 다시 재요
        pts.clear()
        E.pop("v", None)
    if not pts or p != pts[-1][1] or now - pts[-1][0] >= 5:
        pts.append((now, p))
        if len(pts) > 800:
            del pts[1:200]
    t0, p0 = pts[0]
    rate = None
    if now - t0 >= ETA_MIN_T and p - p0 >= ETA_MIN_P:
        r_all = (p - p0) / (now - t0)                  # 처음부터 평균 속도
        win = max(20.0, 0.3 * (now - t0))
        ref = next((q for q in pts if q[0] >= now - win), pts[-1])
        r_win = (p - ref[1]) / (now - ref[0]) if now - ref[0] >= 5 else r_all     # 최근 속도
        r = 0.5 * r_all + 0.5 * r_win
        rate = (1 - p) / r if r > 1e-9 else None
    hist = eta_from_hist(J, p, now, al[-1][0]) if p - p0 >= 0.01 or now - t0 >= ETA_MIN_T else None
    if hist is not None and rate is not None:          # 지난번 같은 작업의 진행 모양을 더 믿어요(속도가 바뀌는 단계·마무리 시간을 알아서)
        w = 0.85 if len(_eta_hist().get(J.get("_eta_key") or "", [])) >= 2 else 0.75
        raw = w * hist + (1 - w) * rate
    else:
        raw = hist if hist is not None else rate
    if raw is None:
        J["eta"] = None
        return None
    prev = E.get("v")
    if prev:
        pred = max(0.0, prev[0] - (now - prev[1]))      # 지난번 값에서 흐른 시간만큼 빼고
        a = 0.5 if abs(raw - pred) > 0.5 * max(pred, 20) else 0.15
        raw = pred + a * (raw - pred)                   # 새 어림값 쪽으로 조금씩
    E["v"] = (raw, now)
    J["eta"] = int(round(raw))
    return J["eta"]


def eta_loop():
    while True:
        time.sleep(1)
        try:
            now = time.time()
            for J in list(JOBS.values()):
                if J.get("state") == "running":
                    eta_update(J, now)
        except Exception:  # noqa: BLE001
            pass


LAST_MODEL = {"key": None}      # 방금 돌린 작업이 쓴 모델(다음 작업이 같은 모델이면 다시 안 불러도 돼요)
SAME_LOOK = 6                   # 앞에서부터 이만큼 안에서만 같은 모델 작업을 찾아요
SAME_SKIP_MAX = 2               # 한 작업이 이 횟수보다 더 밀리지는 않아요


def model_key(p):
    """이 작업이 쓰는 모델을 나타내는 값. 모델을 알 수 없는 작업(음성·일괄 처리·워크플로 등)은 None."""
    k = p.get("kind")
    if k not in ("gen", "edit", "feat", "up", "vid"):
        return None
    vals = tuple(str(p.get(n)) for n in ("engine", "gengine", "rengine", "fengine", "ckpt", "model", "fx_model", "rmodel", "upm", "wan_ver") if p.get(n))
    return (k, vals) if vals else None


def pick_next():
    """대기열에서 다음에 돌릴 위치. 기본은 맨 앞이에요. 방금 돌린 것과 같은 모델을 쓰는 작업이 바로 뒤쪽(앞 6개 안)에 있으면 그걸 먼저 해서
    모델을 다시 불러오는 시간을 아껴요. 직접 순서를 바꾼 작업과 이미 두 번 밀린 작업은 건너뛰지 않아요. (대기열 잠금을 쥔 채로 불러요)"""
    last = LAST_MODEL["key"]
    if last is None or len(QUEUE) < 2:
        return 0
    front = QP.get(QUEUE[0])
    if front is None or model_key(front) in (None, last):
        return 0
    for i in range(1, min(len(QUEUE), SAME_LOOK)):
        pi = QP.get(QUEUE[i])
        if pi is not None and model_key(pi) == last:
            before = [JOBS.get(j) for j in QUEUE[:i]]
            if any(J is None or J.get("pin") or J.get("skipped", 0) >= SAME_SKIP_MAX for J in before):
                return 0
            for J in before:
                J["skipped"] = J.get("skipped", 0) + 1
            return i
    return 0


def job_worker():
    """대기열 맨 앞 작업부터 하나씩 실행해요(엔진은 어차피 한 번에 하나만 그리니까, 순서를 바꾸거나 빼기 쉽게 한 줄로 세워요).
    다만 같은 모델을 쓰는 작업이 곧 뒤에 있으면 먼저 해서 모델을 다시 불러오는 시간을 줄여요(pick_next)."""
    while True:
        with _QCV:
            while not QUEUE:
                _QCV.wait()
            i = pick_next()
            jid = QUEUE.pop(i)
            p = QP.pop(jid, None)
            if i and jid in JOBS:
                JOBS[jid]["msg"] = "같은 모델이라 먼저 해요"
        J = JOBS.get(jid)
        if not J or p is None or J.get("state") != "queued":
            continue
        if J.get("cancel"):
            J["state"], J["error"] = "cancelled", "사용자가 중단했어요."
            continue
        try:
            J["t_start"] = time.time()
            J["_eta_key"] = eta_key(p)
            mk = model_key(p)
            J["model_desc"] = " · ".join(mk[1]) if mk else ""
            job_thread(J, p)
            if mk is not None:
                LAST_MODEL["key"] = mk
        except BaseException as e:  # noqa: BLE001
            J["state"], J["error"] = "error", repr(e)
            log("[대기열 오류]", repr(e))
        J["t_end"] = time.time()
        J["eta"] = None
        eta_learn(J)
        J.pop("_eta", None)
        job_history_add(J)
        STATE["idle_since"] = time.time()


def queue_cancel(J):
    J["cancel"] = True
    if J.get("state") == "queued":
        with _QCV:
            if J["id"] in QUEUE:
                QUEUE.remove(J["id"])
                QP.pop(J["id"], None)
        J["state"], J["error"] = "cancelled", "사용자가 중단했어요."
    elif J.get("pid"):
        threading.Thread(target=comfy_cancel, args=(J["pid"],), daemon=True).start()


def queue_cancel_all():
    """대기 중·실행 중인 작업을 모두 멈춰요. ComfyUI 대기열도 비우고 지금 그리는 것도 중단시킨 뒤, 불러 둔 모델을 내려 VRAM 을 비워요."""
    n = 0
    for J in list(JOBS.values()):
        if J.get("state") in ("queued", "running"):
            queue_cancel(J)
            n += 1

    def comfy_all():
        for path, body in (("/queue", {"clear": True}), ("/interrupt", {})):
            try:
                http(CUI + path, body, 5)
            except Exception:  # noqa: BLE001
                pass
        for _ in range(40):      # 그리던 게 실제로 멈출 때까지 잠깐 기다렸다가(최대 20초) 메모리를 비워요 — 실행 중에는 ComfyUI 가 모델을 못 내려요
            try:
                if not http(CUI + "/queue", timeout=5).get("queue_running"):
                    break
            except Exception:  # noqa: BLE001
                break
            time.sleep(0.5)
        try:
            memory_free()      # ComfyUI 모델·캐시와 Ollama 대화 모델을 내려 VRAM 을 비워요
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=comfy_all, daemon=True).start()
    return {"ok": True, "n": n}


def queue_move(p):
    to = p.get("to")
    with _QCV:
        if p.get("id") not in QUEUE:
            return {"error": "이미 시작했거나 끝난 작업이에요."}
        i = QUEUE.index(p["id"])
        j = {"up": max(0, i - 1), "down": min(len(QUEUE) - 1, i + 1), "top": 0, "bottom": len(QUEUE) - 1}.get(to)
        if j is None:
            return {"error": "알 수 없는 동작"}
        QUEUE.insert(j, QUEUE.pop(i))
        if JOBS.get(p["id"]):
            JOBS[p["id"]]["pin"] = True       # 직접 옮긴 순서는 그대로 지켜요
    return {"ok": True}


def _qrow(J, pos=0):
    return {"id": J["id"], "kind": J.get("kind"), "label": J.get("label") or "작업", "state": J["state"], "pos": pos,
            "msg": J.get("msg", ""), "progress": J.get("progress"), "error": str(J.get("error") or "")[:200],
            "images": len(J.get("images") or []), "t_end": J.get("t_end"), "feature": J.get("feature") or "",
            "model": J.get("model_desc") or "", "eta": J.get("eta"), "view": J.get("view") or "", "xp": J.get("xp") or ""}


def queue_view():
    run = [_qrow(J) for J in list(JOBS.values()) if J.get("state") == "running"]
    wait = [_qrow(JOBS[i], n + 1) for n, i in enumerate(list(QUEUE)) if i in JOBS]
    fin = [_qrow(J) for J in list(JOBS.values()) if J.get("state") in DONE_STATES and J.get("label")][-8:][::-1]
    return {"running": len(run), "queued": len(wait), "items": run + wait + fin}
