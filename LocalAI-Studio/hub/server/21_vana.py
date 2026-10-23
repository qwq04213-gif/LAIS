# 로컬 AI 스튜디오 허브 — 영상 분석·재편집 (장면·대표 장면·화질·무음·대사·장면 설명 → 하이라이트 계획 → 검토 → 구간 편집)
#                         + 영상 깊이(프레임 간 일관성) · 카메라 움직임 추정
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

import asr_models
import vana
import numpy as np

VANA_DIR = ROOT / "analysis"
VANA_CAP_MAX = 60          # 장면 설명은 이만큼의 샷까지만(오래 걸려서)
VDEPTH_MAX = 360           # 깊이 영상 프레임 수 상한

VANA_SYS_PLAN = """You are a video editor. You get a table of shots (id, time range in seconds, quality flags, a short description and the spoken words).
Choose the shots for a highlight video of about TARGET seconds that fits the user's goal. Prefer shots with speech or action, skip dark/blurry ones.
You may shorten a shot by giving a start/end inside its range. Keep the story order unless the goal says otherwise.
Return JSON only: {"pick":[{"id":0,"start":0.0,"end":3.5,"reason":"short Korean reason"}]}"""


def vana_ff():
    ff = vmix.find_ffmpeg(PY, ROOT)
    if not ff:
        raise RuntimeError("영상 분석에는 ffmpeg 가 필요해요. 설치와 모델 > 내 PC 점검의 [빠진 부품 설치]로 imageio-ffmpeg 를 설치해 주세요.")
    return ff


def vana_path(aid):
    if not re.fullmatch(r"[0-9a-f]{10}", str(aid or "")):
        raise ValueError("분석 결과를 찾을 수 없어요.")
    return VANA_DIR / aid


def vana_load(aid):
    try:
        return json.loads((vana_path(aid) / "data.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("분석 결과를 찾을 수 없어요.") from None


def vana_save(A):
    d = vana_path(A["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "data.tmp").write_text(json.dumps(A, ensure_ascii=False), encoding="utf-8")
    (d / "data.tmp").replace(d / "data.json")


def vana_caption(model, img_path):
    """대표 장면 한 장 → 한국어 한 문장(이미지를 볼 수 있는 대화 모델)."""
    b64 = base64.b64encode(Path(img_path).read_bytes()).decode()
    body = {"model": model, "stream": False, "think": False, "options": {"temperature": 0.2},
            "messages": [{"role": "user", "content": "이 영상 장면을 한국어 한 문장(40자 안쪽)으로 설명해. 누가·무엇을·어디서만.", "images": [b64]}]}
    try:
        r = http(OLLAMA + "/api/chat", body, 180)
    except urllib.error.HTTPError:
        body.pop("think")
        r = http(OLLAMA + "/api/chat", body, 180)
    return re.sub(r"<think>.*?</think>", "", (r.get("message") or {}).get("content") or "", flags=re.S).strip()[:120]


def vana_analyze(p, J):
    ff = vana_ff()
    src = vmix_src(p.get("video"), vmix.VIDEO_EXT, "분석할 영상")
    info = vmix.probe(ff, src)
    dur = float(info.get("dur") or 0)
    if not info.get("video") or dur <= 0:
        raise ValueError("영상으로 읽을 수 없는 파일이에요.")
    aid = uuid.uuid4().hex[:10]
    d = vana_path(aid)
    d.mkdir(parents=True, exist_ok=True)
    A = {"id": aid, "t": time.time(), "src": str(p.get("video")), "name": vmix_name(src), "meta": info, "shots": [], "silences": [], "speech": [],
         "notes": [], "plan": []}
    J["msg"], J["progress"] = "장면이 바뀌는 곳을 찾는 중", 0.03
    thr = clamp(num(p, "sens", 0.32), 0.1, 0.8)
    shots = vana.scenes(ff, src, dur, thr)
    for i, (a, b) in enumerate(shots):
        check_cancel(J)
        J["msg"], J["progress"] = f"대표 장면 뽑는 중 {i + 1}/{len(shots)}", 0.05 + 0.3 * (i + 1) / len(shots)
        th = d / f"s{i:03d}.jpg"
        q, flags = ({}, [])
        if vana.frame(ff, src, (a + b) / 2, th):
            q, flags = vana.quality(Image.open(th))
        A["shots"].append({"id": i, "start": round(a, 3), "end": round(b, 3), "thumb": th.name, "q": q, "flags": flags, "caption": "", "text": ""})
    if info.get("audio"):
        J["msg"], J["progress"] = "무음 구간 찾는 중", 0.37
        A["silences"] = vana.silences(ff, src)
        if flag(p, "asr", False):
            if not asr_models.installed(ROOT):
                A["notes"].append("대사 받아쓰기 엔진이 없어 대사는 건너뛰었어요.")
            else:
                wav = d / "audio.wav"
                vana.extract_audio(ff, src, wav)
                free_comfy()
                free_ollama()
                STATE["last"] = None

                def say(pc, msg):
                    J["msg"], J["progress"] = msg, 0.4 + 0.35 * pc
                A["speech"] = asr_models.transcribe(ROOT, wav, p.get("asr_model") or "turbo", p.get("lang") or "", ff, say, lambda: J.get("cancel"))
                wav.unlink(missing_ok=True)
    else:
        A["notes"].append("소리가 없는 영상이에요.")
    for s in A["shots"]:
        s["text"] = " ".join(c["text"] for c in A["speech"] if c["e"] > s["start"] and c["s"] < s["end"])[:600]
        s["silent"] = round(sum(max(0.0, min(s["end"], e) - max(s["start"], b)) for b, e in A["silences"]), 2)
    vm = str(p.get("vision") or "")
    if vm:
        n = min(len(A["shots"]), VANA_CAP_MAX)
        if llm_needs_room(vm):
            free_comfy()
        STATE["last"] = "chat"
        for i, s in enumerate(A["shots"][:n]):
            check_cancel(J)
            J["msg"], J["progress"] = f"장면 설명 쓰는 중 {i + 1}/{n}", 0.76 + 0.22 * (i + 1) / n
            try:
                s["caption"] = vana_caption(vm, d / s["thumb"])
            except Exception as e:  # noqa: BLE001
                A["notes"].append(f"장면 설명을 쓰지 못했어요: {e}")
                break
        if len(A["shots"]) > n:
            A["notes"].append(f"장면 설명은 앞쪽 {n}개 샷만 했어요.")
    vana_save(A)
    J["vana"] = aid
    J["msg"] = f"분석했어요 — 샷 {len(A['shots'])}개" + (f", 대사 {len(A['speech'])}줄" if A["speech"] else "")
    return []


def vana_vdepth(p, J):
    """영상 → 깊이 영상: 프레임마다 깊이를 추정한 뒤 영상 전체 기준으로 밝기를 맞추고 앞뒤 프레임과 섞어 깜빡임을 줄여요."""
    ff = vana_ff()
    src = vmix_src(p.get("video"), vmix.VIDEO_EXT, "영상")
    info = vmix.probe(ff, src)
    dur = float(info.get("dur") or 0)
    fps = clamp(num(p, "fps", 12, int), 4, 30)
    sec = min(dur, VDEPTH_MAX / fps)
    work = ROOT / "cache" / "vdepth" / uuid.uuid4().hex[:8]
    try:
        J["msg"] = "프레임 뽑는 중"
        fs = vana.frames(ff, src, fps, clamp(num(p, "width", 512, int), 256, 1024), work, 0.0, sec)
        if not fs:
            raise ValueError("프레임을 뽑지 못했어요.")
        ds = []
        for i, f in enumerate(fs):
            check_cancel(J)
            J["msg"], J["progress"] = f"깊이 추정 중 {i + 1}/{len(fs)}", 0.05 + 0.75 * (i + 1) / len(fs)
            b64 = "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()
            r = control_prep({"type": "depth", "image": b64})
            if r.get("error"):
                raise RuntimeError(r["error"])
            im = Image.open(io.BytesIO(base64.b64decode(r["image"].split(",", 1)[1]))).convert("L")
            ds.append(im.resize(Image.open(f).size, RS.BICUBIC))
        raw = depthfx.flicker(ds)
        sm = clamp(num(p, "smooth", 60), 0, 95) / 100
        ds = depthfx.stabilize_depth(ds, sm)
        after = depthfx.flicker(ds)
        color = p.get("look") == "color"
        frames_ = (depthfx.colorize(x) if color else x.convert("RGB") for x in ds)
        data = _encode_frames(frames_, fps, J, len(ds), "깊이 영상 만드는 중")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if sec < dur - 0.05:
        warn(J, f"깊이 영상은 앞쪽 {sec:.0f}초({VDEPTH_MAX}프레임)까지만 만들었어요. 초당 장면 수를 낮추면 더 길게 만들 수 있어요.")
    J["msg"] = f"깜빡임 {raw:.1f} → {after:.1f} (낮을수록 안정)"
    return [(data, {"kind": "video-depth", "source": vmix_name(src), "fps": fps, "smooth": sm, "flicker_before": round(raw, 2),
                    "flicker_after": round(after, 2), "note": DEPTH_NOTE, "_sub": DEPTH_SUB}, ".mp4")]


def vana_camera(p, J):
    """영상 → 카메라 움직임(화면 2D: 좌우·상하 이동, 확대·축소) 추정 → .json + 경로 그림. 패럴랙스 영상에 그대로 쓸 수 있어요."""
    ff = vana_ff()
    src = vmix_src(p.get("video"), vmix.VIDEO_EXT, "영상")
    info = vmix.probe(ff, src)
    work = ROOT / "cache" / "vcam" / uuid.uuid4().hex[:8]
    try:
        J["msg"] = "프레임 뽑는 중"
        fs = vana.frames(ff, src, 8, 320, work, 0.0, min(float(info.get("dur") or 0), 120.0))
        if len(fs) < 2:
            raise ValueError("영상이 너무 짧아요.")
        imgs = [Image.open(f).convert("L") for f in fs]
        J["msg"], J["progress"] = "움직임 계산 중", 0.5
        tr = depthfx.camera_track(imgs)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    data = {"kind": "camera-2d", "note": "화면 위 움직임(2D) 추정 — 실제 3D 카메라 위치·회전이 아니에요", "source": vmix_name(src), "fps": 8, "track": tr}
    chart = depthfx.track_chart(tr)
    info2 = {"kind": "camera-2d", "prompt": "", "source": vmix_name(src), "note": data["note"]}
    return [(json.dumps(data, ensure_ascii=False).encode("utf-8"), {"kind": "camera-2d", "source": vmix_name(src)}, ".camera.json"), (chart, info2, None)]


def vana_cam3d(p, J):
    """영상 → 3D 카메라 경로(특징점 매칭으로 회전·이동 추정) + 깊이를 그 경로에 맞춰 쌓은 점 구름(.glb).
    카메라 한 대라 거리 단위는 모르는 '상대 크기'예요. 깊이도 AI 추정이라 점 구름은 대략적인 모양이에요."""
    try:
        import cv2  # noqa: F401
    except ImportError:
        raise RuntimeError("3D 카메라 추정에는 파이썬 부품 opencv 가 필요해요. (No module named 'cv2')") from None
    ff = vana_ff()
    src = vmix_src(p.get("video"), vmix.VIDEO_EXT, "영상")
    info = vmix.probe(ff, src)
    fps = clamp(num(p, "fps", 4, int), 2, 10)
    sec = min(float(info.get("dur") or 0), 90 / fps)
    work = ROOT / "cache" / "vcam3d" / uuid.uuid4().hex[:8]
    out = []
    try:
        J["msg"] = "프레임 뽑는 중"
        fs = vana.frames(ff, src, fps, 480, work, 0.0, sec)
        if len(fs) < 3:
            raise ValueError("영상이 너무 짧아요(1초 이상 필요해요).")
        frames_ = [Image.open(f).convert("RGB") for f in fs]
        J["msg"], J["progress"] = "카메라 움직임 계산 중(특징점 매칭)", 0.1
        poses, foc, warns = depthfx.vo_track(frames_, clamp(num(p, "fov", 60), 20, 120))
        for w in warns:
            warn(J, w)
        rows = depthfx.pose_rows(poses, fps)
        data = {"kind": "camera-3d", "note": "카메라 한 대로 추정한 상대 경로 — 회전·방향은 대략 맞지만 거리 단위(m)는 알 수 없어요", "source": vmix_name(src),
                "fps": fps, "focal_px": round(foc, 1), "width": frames_[0].width, "height": frames_[0].height, "frames": rows}
        out.append((json.dumps(data, ensure_ascii=False).encode("utf-8"), {"kind": "camera-3d", "source": vmix_name(src)}, ".camera3d.json"))
        out.append((depthfx.pose_chart(rows), {"kind": "camera-3d", "prompt": "", "source": vmix_name(src), "note": data["note"]}, None))
        if flag(p, "cloud", True):
            keys = list(range(0, len(frames_), max(1, len(frames_) // 24)))
            Ps, Cs = [], []
            span = float(np.median([np.linalg.norm(x["t"]) for x in poses[1:]] or [1.0])) or 1.0
            for n, i in enumerate(keys):
                check_cancel(J)
                J["msg"], J["progress"] = f"깊이로 점 구름 쌓는 중 {n + 1}/{len(keys)}", 0.2 + 0.75 * (n + 1) / len(keys)
                b = io.BytesIO()
                frames_[i].save(b, "PNG")
                r = control_prep({"type": "depth", "image": "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()})
                if r.get("error"):
                    warn(J, "깊이 추정이 안 돼서 점 구름은 만들지 못했어요: " + r["error"][:160])
                    Ps = []
                    break
                d = Image.open(io.BytesIO(base64.b64decode(r["image"].split(",", 1)[1]))).convert("L")
                P_, C_ = depthfx.cloud_points(frames_[i], d, poses[i], foc, step=5, scale=2.0 / span)
                Ps.append(P_)
                Cs.append(C_)
            if Ps:
                P_, C_ = np.concatenate(Ps), np.concatenate(Cs)
                if len(P_) > 400000:
                    sel = np.random.default_rng(0).choice(len(P_), 400000, replace=False)
                    P_, C_ = P_[sel], C_[sel]
                out.append((depthfx.points_glb(P_, C_), {"kind": "pointcloud", "source": vmix_name(src), "points": int(len(P_)),
                                                          "note": "AI 깊이 + 추정 카메라로 쌓은 대략적인 점 구름(정밀 3D 복원 아님)"}, ".glb"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    J["msg"] = f"카메라 {len(rows)}개 위치 추정" + ("" if len(out) < 3 else " · 점 구름 만듦")
    return out


def do_vana(p, J):
    op = p.get("op") or "analyze"
    fn = {"analyze": vana_analyze, "vdepth": vana_vdepth, "camera": vana_camera, "cam3d": vana_cam3d}.get(op)
    if not fn:
        raise ValueError("알 수 없는 분석이에요.")
    return fn(p, J)


def vana_view(aid):
    A = vana_load(aid)
    A["src_ok"] = True
    try:
        vmix_src(A["src"], vmix.VIDEO_EXT, "영상")
    except ValueError:
        A["src_ok"] = False
    return A


def vana_list():
    rows = []
    try:
        ds = sorted((d for d in VANA_DIR.iterdir() if (d / "data.json").is_file()), key=lambda d: d.stat().st_mtime, reverse=True)[:30]
    except OSError:
        ds = []
    for d in ds:
        try:
            A = json.loads((d / "data.json").read_text(encoding="utf-8"))
            rows.append({"id": A["id"], "name": A.get("name", ""), "t": A["t"], "shots": len(A["shots"]), "dur": round(A["meta"].get("dur", 0), 1)})
        except (OSError, ValueError, KeyError):
            continue
    return {"items": rows}


def vana_thumb(aid, name):
    if not re.fullmatch(r"s\d{3}\.jpg", name or ""):
        return None
    f = vana_path(aid) / name
    return f if f.is_file() else None


def vana_plan(p):
    """하이라이트 계획: mode=ai(대화 모델이 고르고 이유를 적어요) · auto(점수로). 실행 전에 화면에서 고치고 승인해요."""
    A = vana_load(p.get("id"))
    target = clamp(num(p, "target", 60.0), 3.0, 1800.0)
    shots = A["shots"]
    if p.get("mode") == "ai":
        goal = str(p.get("goal") or "").strip()[:500]
        if goal and blocked(goal):
            return {"error": BLOCK_MSG}
        rows = [f'{s["id"]} | {s["start"]:.1f}-{s["end"]:.1f}s | {",".join(s["flags"]) or "ok"} | {s["caption"][:80]} | {s["text"][:160]}' for s in shots]
        ask = (VANA_SYS_PLAN.replace("TARGET", f"{target:.0f}"), f"goal: {goal or '가장 중요한 장면 위주의 하이라이트'}\ntarget seconds: {target:.0f}\nshots (id | time | flags | description | speech):\n" + "\n".join(rows))
        r = llm_json(str(p.get("model") or ""), ask[0], ask[1], 0.3)
        by = {s["id"]: s for s in shots}
        pick = []
        for x in (r.get("pick") if isinstance(r, dict) else None) or []:
            try:
                s = by[int(x.get("id"))]
            except (TypeError, ValueError, KeyError):
                continue
            a = clamp(float(x.get("start", s["start"]) or s["start"]), s["start"], s["end"])
            b = clamp(float(x.get("end", s["end"]) or s["end"]), s["start"], s["end"])
            if b - a < 0.5:
                a, b = s["start"], s["end"]
            pick.append({"id": s["id"], "start": round(a, 3), "end": round(b, 3), "reason": str(x.get("reason") or "")[:120]})
        if not pick:
            return {"error": "도우미 모델이 구간을 고르지 못했어요. [자동으로 고르기]를 쓰거나 목표를 바꿔 보세요."}
        total, keep = 0.0, []
        for x in pick:                              # 목표보다 많이 길면 뒤쪽은 빼요
            if total > target * 1.25:
                break
            keep.append(x)
            total += x["end"] - x["start"]
        pick = keep
    else:
        pick = vana.auto_pick(shots, target, A["speech"])
    A["plan"] = [{**x, "on": True} for x in pick]
    A["plan_goal"], A["plan_target"], A["plan_mode"] = str(p.get("goal") or ""), target, p.get("mode") or "auto"
    vana_save(A)
    return {"plan": A["plan"], "total": round(sum(x["end"] - x["start"] for x in pick), 2)}


def vana_render(p):
    """검토한 구간으로 새 영상 만들기 — 작업 대기열로(영상 편집 작업)."""
    A = vana_load(p.get("id"))
    segs = []
    for x in p.get("segs") or []:
        try:
            a, b = float(x["start"]), float(x["end"])
        except (KeyError, TypeError, ValueError):
            return {"error": "구간 값이 올바르지 않아요."}
        dur = float(A["meta"].get("dur") or 0)
        if not (0 <= a < b <= dur + 0.05):
            return {"error": f"구간이 영상 길이(0~{dur:.1f}초)를 벗어나요: {a:.1f}~{b:.1f}"}
        segs.append([round(a, 3), round(b, 3)])
    if not segs:
        return {"error": "남길 구간을 하나 이상 골라 주세요."}
    if len(segs) > 120:
        return {"error": "구간은 120개까지 쓸 수 있어요."}
    J = submit_job({"kind": "vedit", "op": "cutlist", "file": A["src"], "segs": segs, "vana": A["id"], "drop_silence": bool(p.get("drop_silence")),
                    "subs": p.get("subs") if p.get("subs") in ("burn", "srt") else ""}, label=f"하이라이트 만들기 · {A.get('name', '')[:30]}", view="vana")
    return {"ok": True, "job": J["id"]}


def vedit_cutlist(p, J, ff, work):
    """영상 분석의 구간표대로 잘라 이어 붙이기(+무음 빼기, 자막 입히기/저장)."""
    src = vmix_src(p.get("file"), vmix.VIDEO_EXT, "영상")
    info = vmix.probe(ff, src)
    segs = [(float(a), float(b)) for a, b in (p.get("segs") or [])]
    A = None
    try:
        A = vana_load(p.get("vana")) if p.get("vana") else None
    except ValueError:
        A = None
    if p.get("drop_silence") and A and A.get("silences"):
        segs = vana.minus(segs, [(a, b) for a, b in A["silences"]])
    J["msg"] = f"구간 {len(segs)}개를 잘라 잇는 중"
    out = work / "cut.mp4"
    total = vana.cut_concat(ff, src, segs, out, bool(info.get("audio")))
    info_ = {"kind": "vedit", "op": "highlight", "file": vmix_name(src), "segments": [[round(a, 2), round(b, 2)] for a, b in segs], "seconds": round(total, 2)}
    subs = vana.remap_subs(A["speech"], segs) if A and A.get("speech") and p.get("subs") else []
    srt = vmix.to_srt(subs) if subs else ""
    if subs and p.get("subs") == "burn":
        J["msg"] = "자막 입히는 중"
        job = dict(video=out, audio=None, amode="replace", vol=1.0, ovol=1.0, delay=0.0, fit="video", fade=False, subs=srt, size=5.5, pos="bottom",
                   color="#ffffff", outline=True, bg=False)
        res = vmix.make(ff, job, work / "subs", lambda m, pc=None: J.update(msg=m), lambda: J.get("cancel"))
        data = res["out"].read_bytes()
    else:
        data = out.read_bytes()
    if p.get("subs") and A and not A.get("speech"):
        warn(J, "받아쓴 대사가 없어 자막은 넣지 못했어요. 분석할 때 '대사 받아쓰기'를 켜 주세요.")
    if srt:
        info_["_extra"] = {".srt": srt}
    return [(data, info_, ".mp4")]
