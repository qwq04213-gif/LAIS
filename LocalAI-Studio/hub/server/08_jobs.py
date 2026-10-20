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
    return {"videos": rows(OUT_SUB["vid"], vmix.VIDEO_EXT), "audios": sorted(rows(OUT_SUB["tts"], vmix.AUDIO_EXT) + rows(OUT_SUB["music"], vmix.AUDIO_EXT), key=lambda x: -x["time"])[:200],
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
        if p["kind"] in ("tts", "vmix"):
            pass                                          # 음성 만들기·영상 소리/자막 넣기는 ComfyUI 를 쓰지 않아요
        elif (p["kind"] == "feat" and p.get("feature") in ("resize", "color", "rmbg")) or (p["kind"] == "vpost" and p.get("op") == "gif"):
            pass                                          # 크기·색 보정·배경 지우기는 ComfyUI 없이 바로 처리해요
        elif (p["kind"] == "batch" and (p.get("op") != "upscale" or scale_of(p) <= 1.0)) or (p["kind"] == "up" and p.get("mode") != "refine" and scale_of(p) <= 1.0):
            pass                                          # 일괄 처리의 배경 지우기·크기 변경, 줄이기(1배 이하)는 ComfyUI 가 필요 없어요
        else:
            wait_comfy()
            claim("image")
        items = {"edit": do_edit, "gen": do_gen, "up": do_up, "wf": do_wf, "feat": do_feat, "vid": do_vid, "vpost": do_vpost, "vmix": do_vmix, "music": do_music, "tts": do_tts, "batch": do_batch}[p["kind"]](p, J)
        sub = OUT_SUB["vid"] if p["kind"] in ("vpost", "vmix") else OUT_SUB.get(p["kind"], "기타")
        (OUT / sub).mkdir(parents=True, exist_ok=True)
        stamp, embed = time.strftime("%Y%m%d-%H%M%S"), bool(p.get("embed"))
        for i, (im, info, graph) in enumerate(items):
            if p["kind"] in ("vid", "vpost", "vmix", "music", "tts") or isinstance(im, (bytes, bytearray)):      # 영상·음악: 받은 파일을 그대로 저장하고, 설정은 옆에 .json 으로 남겨요
                name = f'{stamp}-{uuid.uuid4().hex[:4]}-{p["kind"] if p["kind"] in ("music", "tts") else "vid"}-{i}{graph}'
                (OUT / sub / name).write_bytes(im)
                (OUT / sub / (name + ".json")).write_text(json.dumps({k: v for k, v in info.items() if k != "_extra"}, ensure_ascii=False), encoding="utf-8")
                for xext, xdata in (info.get("_extra") or {}).items():      # 자막 파일(.srt) 같은 덧붙이는 파일
                    (OUT / sub / (Path(name).stem + xext)).write_text(xdata, encoding="utf-8")
                J["images"].append("/out/" + urllib.parse.quote(sub) + "/" + name)
                J.setdefault("used", []).append(info.get("prompt", ""))
                continue
            if p["kind"] == "gen" and not p.get("init"):      # 모델은 8·16 배수 크기로만 그려서, 입력한 정확한 크기와 조금 다르면 그 크기로 맞춰 저장해요
                try:
                    rw, rh = int(float(p.get("w"))), int(float(p.get("h")))
                    if (rw, rh) != im.size and 64 <= rw <= 4096 and 64 <= rh <= 4096 and abs(rw - im.width) <= 32 and abs(rh - im.height) <= 32:
                        im = im.resize((rw, rh), RS.LANCZOS)
                except (TypeError, ValueError):
                    pass
            name = f'{stamp}-{uuid.uuid4().hex[:4]}-{p["kind"]}-{i}.png'
            im.save(OUT / sub / name, "PNG", pnginfo=meta.pnginfo(info, graph) if embed else None)
            J["images"].append("/out/" + urllib.parse.quote(sub) + "/" + name)
            J.setdefault("used", []).append(info.get("prompt", ""))
        J["state"], J["progress"] = "done", 1.0
    except Cancelled as e:
        J["state"], J["error"] = "cancelled", str(e)
        if p["kind"] == "batch" and J.get("images"):
            J["msg"] = f"중단했어요. 지금까지 {len(J['images'])}장은 저장돼 있어요."
    except Exception as e:
        J["state"], J["error"] = "error", str(e) or e.__class__.__name__
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
_QW = {"t": None}
KIND_NAME = {"edit": "이미지 편집", "gen": "이미지 생성", "up": "업스케일", "wf": "워크플로", "feat": "기능", "vid": "영상 만들기", "vpost": "영상 다듬기", "vmix": "영상 소리·자막", "music": "음악 만들기", "tts": "음성 만들기", "batch": "일괄 처리"}
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


def enqueue(J, p):
    J["kind"], J["label"], J["t_add"] = p["kind"], job_label(p), time.time()
    with _QCV:
        QP[J["id"]] = p
        QUEUE.append(J["id"])
        _QCV.notify_all()
        if not (_QW["t"] and _QW["t"].is_alive()):
            _QW["t"] = threading.Thread(target=job_worker, daemon=True)
            _QW["t"].start()


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
            mk = model_key(p)
            job_thread(J, p)
            if mk is not None:
                LAST_MODEL["key"] = mk
        except BaseException as e:  # noqa: BLE001
            J["state"], J["error"] = "error", repr(e)
            log("[대기열 오류]", repr(e))
        J["t_end"] = time.time()
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
            "images": len(J.get("images") or []), "t_end": J.get("t_end"), "feature": J.get("feature") or ""}


def queue_view():
    run = [_qrow(J) for J in list(JOBS.values()) if J.get("state") == "running"]
    wait = [_qrow(JOBS[i], n + 1) for n, i in enumerate(list(QUEUE)) if i in JOBS]
    fin = [_qrow(J) for J in list(JOBS.values()) if J.get("state") in DONE_STATES and J.get("label")][-8:][::-1]
    return {"running": len(run), "queued": len(wait), "items": run + wait + fin}
