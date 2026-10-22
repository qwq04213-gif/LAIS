# 로컬 AI 스튜디오 허브 — 영상 편집 (이어 붙이기 · 자르기 · AI 로 이어 그리기)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

import vedit

VEDIT_NODES = ("LoadVideo", "GetVideoComponents", "ImageToMask", "ThresholdMask", "WanVaceToVideo", "TrimVideoLatent", "CreateVideo", "SaveVideo")


def _vedit_ff():
    ff = vmix.find_ffmpeg(PY, ROOT)
    if not ff:
        raise RuntimeError("영상 편집에는 ffmpeg 가 필요해요. 설치와 모델 > 내 PC 점검의 [빠진 부품 설치]로 imageio-ffmpeg 를 설치해 주세요.")
    return ff


def do_vedit(p, J):
    """영상 편집. op: concat(여러 개 이어 붙이기) / trim(구간 자르기) / extend(Wan VACE 로 뒤를 이어 그리기). 결과: [(바이트, 정보, 확장자)]"""
    op, ff = p.get("op"), _vedit_ff()
    work = ROOT / "cache" / "vedit" / uuid.uuid4().hex[:10]
    work.mkdir(parents=True, exist_ok=True)
    out = work / "out.mp4"
    try:
        if op == "concat":
            refs = [r for r in (p.get("files") or []) if r][:20]
            srcs = [vmix_src(r, vmix.VIDEO_EXT, f"{i + 1}번째 영상") for i, r in enumerate(refs)]
            J["msg"] = f"영상 {len(srcs)}개 이어 붙이는 중"
            dur = vedit.concat(ff, srcs, out, fade=clamp(num(p, "fade", 0.0), 0.0, 2.0))
            info = dict(kind="vedit", op="concat", files=[s.name for s in srcs], seconds=round(dur, 2))
        elif op == "trim":
            src = vmix_src(p.get("file"), vmix.VIDEO_EXT, "자를 영상")
            J["msg"] = "영상 자르는 중"
            dur = vedit.trim(ff, src, out, num(p, "start", 0.0), p.get("end"))
            info = dict(kind="vedit", op="trim", file=src.name, start=num(p, "start", 0.0), seconds=round(dur, 2))
        elif op == "extend":
            return vedit_extend(p, J, ff, work)
        elif op == "cutlist":
            return vedit_cutlist(p, J, ff, work)
        else:
            raise ValueError("알 수 없는 영상 편집이에요.")
        return [(out.read_bytes(), info, ".mp4")]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def vedit_extend(p, J, ff, work):
    """올린 영상의 마지막 1초를 그대로 두고 그 뒤를 Wan VACE 로 이어 그린 다음, 원본 뒤에 붙여 한 영상으로 돌려줘요."""
    gone = [n for n in VEDIT_NODES if not has_node(n)]
    if gone:
        raise RuntimeError(f"이 ComfyUI 에는 영상 이어 그리기에 필요한 노드({', '.join(gone)})가 없어요. ComfyUI 를 업데이트해 주세요.")
    unet = vace_model()
    te, vae = _pick(files("text_encoders"), "umt5"), _pick(files("vae"), "wan_2.1_vae", "wan2.1", ("wan", "2.1"))
    miss = [n for n, v in (("Wan VACE 모델", unet), ("UMT5 텍스트 인코더", te), ("Wan 2.1 VAE", vae)) if not v]
    if miss:
        raise RuntimeError("없는 파일: " + ", ".join(miss) + ". '설치와 모델' > 영상에서 'Wan VACE'를 설치해 주세요.")
    src = vmix_src(p.get("file"), vmix.VIDEO_EXT, "이어 그릴 영상")
    text = (p.get("prompt") or "").strip() or "continue the scene naturally, same subject, same camera motion"
    if blocked(text):
        raise ValueError(BLOCK_MSG)
    fps, ctx = 16, 16
    new = clamp(int(round(clamp(num(p, "sec", 3.0), 1.0, 5.0) * fps)), 16, 80)
    J["msg"] = "원본의 마지막 장면을 읽는 중"
    inp = vedit.extend_inputs(ff, src, work, ctx=ctx, new=new, fps=fps)
    names = []
    for k in ("control", "mask"):
        nm = f"hub_{uuid.uuid4().hex[:10]}_{k}.mp4"
        (COMFY / "input").mkdir(parents=True, exist_ok=True)
        shutil.copy(inp[k], COMFY / "input" / nm)
        J["tmp"].append(COMFY / "input" / nm)
        names.append(nm)
    q = dict(unet=unet, te=te, vae=vae, prompt=text, negative=(p.get("negative") or "").strip() or flows.WAN_NEG, seed=seed_of(p),
             w=inp["w"], h=inp["h"], frames=inp["length"], fps=fps, steps=clamp(num(p, "steps", 20, int), 1, 60), cfg=clamp(num(p, "cfg", 5.0), 1.0, 20.0),
             sampler="uni_pc" if "uni_pc" in (caps()["samplers"] or ["uni_pc"]) else "euler", scheduler="simple", shift=8.0)
    J["msg"] = f"뒤를 이어 그리는 중 ({inp['w']}×{inp['h']}, {inp['length']}장면) — 몇 분 걸릴 수 있어요"
    res = run_wf(flows.wf_vace_extend(q, names[0], names[1]), J, raw=True)
    gen = work / "gen.mp4"
    gen.write_bytes(res[0][1])
    tail = work / "tail.mp4"
    J["msg"] = "원본 뒤에 붙이는 중"
    vedit.trim(ff, gen, tail, ctx / fps, None)                       # 원본에서 가져온 앞부분(그대로 둔 장면)은 빼고
    out = work / "out.mp4"
    dur = vedit.concat(ff, [src, tail], out, size=(vedit.even(inp["src_info"]["w"]), vedit.even(inp["src_info"]["h"])), fps=inp["src_info"].get("fps"))
    info = dict(kind="vedit", op="extend", file=src.name, prompt=text, seed=q["seed"], added=round(new / fps, 2), seconds=round(dur, 2), model=unet)
    return [(out.read_bytes(), info, ".mp4")]
