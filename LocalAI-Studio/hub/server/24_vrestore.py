# 로컬 AI 스튜디오 허브 — 영상 복원 (상태 진단 → 고르게 다듬기(ffmpeg) → 조각마다 AI 업스케일·프레임 늘리기(ComfyUI) → 이어 붙이기·원래 소리 → 확인·비교)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

import vrestore

VR_WORK = ROOT / "cache" / "vrestore"
VR_SUB = "영상 복원"
VR_MAX_SIDE = 3840
VR_SCALES = (1.5, 2.0, 3.0, 4.0)


def vr_opts(p):
    """화면 설정 → 정리된 복원 설정."""
    o = {"deint": flag(p, "deint", False), "denoise": p.get("denoise") if p.get("denoise") in vrestore.DENOISE else "off",
         "deflicker": flag(p, "deflicker", False), "color": flag(p, "color", False), "stabilize": flag(p, "stabilize", False),
         "stab_smooth": int(clamp(num(p, "stab_smooth", 20, int), 5, 60)), "sharpen": flag(p, "sharpen", False),
         "upscale": 0.0, "upm": "", "interp": flag(p, "interp", False), "seg": 0.0}
    try:
        sc = float(p.get("upscale") or 0)
    except (TypeError, ValueError):
        sc = 0.0
    if sc in VR_SCALES:
        o["upscale"] = sc
        o["upm"] = str(p.get("upm") or "")
    return o


def vr_analyze(p, J):
    ff = vana_ff()
    src = vmix_src(p.get("video"), vmix.VIDEO_EXT, "영상")
    info = vrestore.probe2(ff, src)
    if not info.get("video"):
        raise ValueError("영상으로 읽을 수 없는 파일이에요.")

    def say(pc, msg):
        check_cancel(J)
        J["msg"], J["progress"] = msg, pc
    rep = vrestore.analyze(ff, src, info, say)
    rep["meta"] = {k: info.get(k) for k in ("dur", "w", "h", "fps", "audio", "acodec", "vcodec", "kbps")}
    rep["name"] = vmix_name(src)
    rep["ups"] = files("upscale_models")
    J["report"] = rep
    J["msg"] = "진단했어요 — 추천 설정을 켜 두었어요"
    return []


def vr_need_nodes(o):
    need = ["LoadVideo", "GetVideoComponents", "CreateVideo", "SaveVideo"]
    if o["upscale"]:
        need += ["ImageScale"] + (list(flows.SEEDVR_NODES) if str(o.get("upm") or "").startswith("SeedVR2") else ["UpscaleModelLoader", "ImageUpscaleWithModel"])
    if o["interp"]:
        need.append("RIFE VFI")
    miss = [n for n in need if caps()["nodes"] and n not in caps()["nodes"]]
    if miss:
        raise RuntimeError("이 ComfyUI 에는 필요한 노드가 없어요: " + ", ".join(miss) + ". " +
                           ("확장 'ComfyUI-Frame-Interpolation' 을(를) 설치하고 ComfyUI 를 다시 시작해 주세요." if "RIFE VFI" in miss else "ComfyUI 를 업데이트해 주세요."))


def vr_run(p, J):
    ff = vana_ff()
    src = vmix_src(p.get("video"), vmix.VIDEO_EXT, "영상")
    info = vrestore.probe2(ff, src)
    dur, W, H, fps = float(info.get("dur") or 0), int(info.get("w") or 0), int(info.get("h") or 0), float(info.get("fps") or 24)
    if not info.get("video") or dur <= 0 or not W:
        raise ValueError("영상으로 읽을 수 없는 파일이에요.")
    o = vr_opts(p)
    ai = bool(o["upscale"] or o["interp"])
    if not ai and not any(o[k] and o[k] != "off" for k in ("deint", "denoise", "deflicker", "color", "stabilize", "sharpen")):
        raise ValueError("고칠 항목을 하나 이상 골라 주세요.")
    q = {"fps": round(fps, 3), "interp": o["interp"]}
    if o["upscale"] and seedvr_of(o["upm"]):          # SeedVR2 로 복원하며 키우기
        q["seedvr"] = seedvr_of(o["upm"])
        q["model"] = o["upm"]
        k = min(o["upscale"], VR_MAX_SIDE / max(W, H))
        if k < o["upscale"]:
            warn(J, f"결과가 너무 커지지 않게 긴 쪽 {VR_MAX_SIDE}px 까지만 키웠어요.")
        q["w"], q["h"] = vrestore.even(W * k), vrestore.even(H * k)
    elif o["upscale"]:
        ups = files("upscale_models")
        q["model"] = o["upm"] if o["upm"] in ups else (ups or [None])[0]
        if not q["model"]:
            raise RuntimeError("업스케일 모델이 없어요. '설치와 모델' 탭에서 업스케일 모델을 설치해 주세요.")
        k = min(o["upscale"], VR_MAX_SIDE / max(W, H))
        if k < o["upscale"]:
            warn(J, f"결과가 너무 커지지 않게 긴 쪽 {VR_MAX_SIDE}px 까지만 키웠어요.")
        q["w"], q["h"] = vrestore.even(W * k), vrestore.even(H * k)
    if ai:
        vr_need_nodes(o)
        if o["interp"] and fps > 30:
            warn(J, f"이미 초당 {fps:.0f}장이라 프레임을 늘려도 차이가 작아요.")
        frames = vrestore.chunk_frames(W, H, (8 if q.get("seedvr") else vrestore.model_scale(q.get("model"))) if o["upscale"] else 1, o["interp"])
        o["seg"] = round(max(0.5, frames / max(fps, 1)), 3)
    key = vrestore.opts_key(src, {**o, "model": q.get("model"), "w": q.get("w")})
    work = VR_WORK / key
    work.mkdir(parents=True, exist_ok=True)
    resumed = (work / "pre.mp4").is_file() and (work / "pre.ok").is_file()

    def say(pc, msg, base=0.0, span=1.0):
        if J.get("cancel"):
            raise Cancelled("사용자가 중단했어요.")
        J["msg"], J["progress"] = msg, base + span * pc
    span_pre = 0.3 if ai else 0.9
    used = []
    try:
        if resumed:
            used = json.loads((work / "pre.ok").read_text(encoding="utf-8"))
            J["msg"] = "지난번에 다듬어 둔 파일로 이어서 해요"
        else:
            used = vrestore.prepass(ff, src, o, info, work, o["seg"], lambda pc, m: say(pc, m, 0.0, span_pre), lambda: J.get("cancel"))
            (work / "pre.ok").write_text(json.dumps(used, ensure_ascii=False), encoding="utf-8")
        parts = [work / "pre.mp4"]
        if ai:
            chunks = vrestore.split(ff, work / "pre.mp4", o["seg"], work / "chunks")
            (work / "done").mkdir(exist_ok=True)
            (COMFY / "input").mkdir(parents=True, exist_ok=True)
            parts, skipped = [], 0
            for i, c in enumerate(chunks):
                dst = work / "done" / ("o" + c.name[1:])
                parts.append(dst)
                if dst.is_file() and dst.stat().st_size > 0:
                    skipped += 1
                    continue
                check_cancel(J)
                J["msg"], J["progress"] = f"AI 처리 중 — 조각 {i + 1}/{len(chunks)}", span_pre + 0.6 * i / len(chunks)
                name = f"hub_{uuid.uuid4().hex[:10]}.mp4"
                shutil.copyfile(c, COMFY / "input" / name)
                J["tmp"].append(COMFY / "input" / name)
                res = run_wf(flows.wf_vrestore({**q, "file": name}), J, raw=True)
                if not res:
                    raise RuntimeError(f"조각 {i + 1} 의 결과 영상을 받지 못했어요.")
                (work / "done" / (dst.name + ".part")).write_bytes(res[0][1])
                (work / "done" / (dst.name + ".part")).replace(dst)
                _clean_tmp(J)
            if skipped:
                warn(J, f"끝나 있던 조각 {skipped}개는 다시 하지 않고 이어서 했어요.")
            used += ([f"AI 업스케일 {q['w']}×{q['h']} ({q['model']})"] if o["upscale"] else []) + (["프레임 2배(RIFE)"] if o["interp"] else [])
        J["msg"], J["progress"] = "이어 붙이고 원래 소리 넣는 중", 0.92
        out = work / "restored.mp4"
        vrestore.finish(ff, parts, src, info, out, work)
        J["msg"] = "소리·길이 확인 중"
        ver = vrestore.verify(ff, info, out, src)
    except Cancelled:
        raise
    except InterruptedError as e:
        raise Cancelled(str(e)) from None
    except Exception as e:
        raise RuntimeError(f"{e} (다시 실행하면 끝난 단계부터 이어서 해요)") from None
    J["verify"] = ver
    if not ver["ok"]:
        warn(J, ver["msg"])
    final = VR_WORK / f"out_{uuid.uuid4().hex[:8]}.mp4"
    shutil.move(str(out), final)
    cmp_img = None
    try:
        cmp_img = vrestore.compare_image(ff, src, final, dur * 0.5)
    except Exception:  # noqa: BLE001
        cmp_img = None
    shutil.rmtree(work, ignore_errors=True)
    info_ = {"kind": "vrestore", "file": vmix_name(src), "steps": used, "verify": ver, "_sub": VR_SUB}
    J["msg"] = "복원했어요 — " + ", ".join(used) + " · " + ver["msg"]
    items = [(final, info_, ".mp4")]
    if cmp_img is not None:
        items.append((cmp_img, {"kind": "vrestore", "op": "compare", "file": vmix_name(src), "_sub": VR_SUB}, None))
    return items


def do_vrestore(p, J):
    fn = {"analyze": vr_analyze, "run": vr_run}.get(p.get("op") or "run")
    if not fn:
        raise ValueError("알 수 없는 복원 작업이에요.")
    return fn(p, J)
