# 로컬 AI 스튜디오 허브 — 사진 기반 구도 바꾸기 · 새 장면 (카메라 각도·화각, 같은 인물로 새 사진, 참고 포즈, 구조만 가져와 새로 그리기)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

ANG_AZ = {"front": "front view", "fr": "front-right quarter view", "right": "right side view", "br": "back-right quarter view", "back": "back view",
          "bl": "back-left quarter view", "left": "left side view", "fl": "front-left quarter view"}
ANG_EL = {"low": "low-angle shot", "eye": "eye-level shot", "elev": "elevated shot", "high": "high-angle shot"}
ANG_DIST = {"close": "close-up", "medium": "medium shot", "wide": "wide shot"}
ANG_KO_AZ = {"front": "the front", "fr": "the front-right (45 degrees)", "right": "the right side (90 degrees)", "br": "behind on the right (135 degrees)",
             "back": "behind", "bl": "behind on the left (225 degrees)", "left": "the left side (270 degrees)", "fl": "the front-left (315 degrees)"}
ANG_NAT_EL = {"low": "from a low angle looking up", "eye": "at eye level", "elev": "from slightly above", "high": "from a high angle looking down"}
ANG_NAT_DIST = {"close": "as a close-up", "medium": "as a medium shot", "wide": "as a wide shot showing more of the surroundings"}
STRUCT_KINDS = ("pose", "depth", "canny", "lineart")


def angle_lora():
    """Qwen-Image 2.1 용 카메라 각도 LoRA 가 있으면 그 파일 이름(2511 용은 2.1 에서 쓸 수 없어 고르지 않아요)."""
    return next((n for n in files("loras") if "angle" in n.lower() and QWEN21_RX.search(n.lower())), None)


def recompose_angle_prompt(p, use_lora):
    az, el, di = p.get("az") or "keep", p.get("el") or "keep", p.get("dist") or "keep"
    if use_lora:
        parts = [ANG_AZ.get(az, "front view"), ANG_EL.get(el, "eye-level shot"), ANG_DIST.get(di, "medium shot")]
        return "<sks> " + " ".join(parts)
    bits = []
    if az in ANG_KO_AZ:
        bits.append(f"show the subject from {ANG_KO_AZ[az]}")
    if el in ANG_NAT_EL:
        bits.append(ANG_NAT_EL[el])
    if di in ANG_NAT_DIST:
        bits.append(ANG_NAT_DIST[di])
    if not bits:
        raise ValueError("바꿀 각도·높이·거리 중 하나는 골라 주세요.")
    return ("Rotate the camera to " + ", ".join(bits) + ". Keep the same person or object, identity, outfit, colors and the same place; "
            "only the camera viewpoint changes.")


def feat_recompose(p, J):
    mode = p.get("mode") if p.get("mode") in ("angle", "scene", "pose", "structure") else "angle"
    extra = str(p.get("extra") or "").strip()[:600]
    if extra and blocked(extra):
        raise ValueError(BLOCK_MSG)
    if mode == "structure":
        return recompose_structure(p, J)
    q = {"kind": "edit", "engine": "qwen", "image": p["image"], "seed": p.get("seed", -1), "q_mp": p.get("q_mp", 1.0)}
    if p.get("fast"):
        q["fast"] = "on"
    note = {}
    if mode == "angle":
        lora = angle_lora() if p.get("use_lora", "on") not in ("", None, "off", False) else None
        text = recompose_angle_prompt(p, bool(lora))
        if lora:
            text += f" <lora:{Path(lora).stem}:{clamp(num(p, 'lora_w', 0.9), 0.3, 1.5)}>"
        if extra:
            text += " " + extra
        note = {"Angle": f'{p.get("az")}/{p.get("el")}/{p.get("dist")}', "AngleLoRA": lora or ""}
    elif mode == "scene":
        scene = str(p.get("scene") or "").strip()[:800]
        if not scene:
            raise ValueError("새 장면을 적어 주세요. 예: 해 질 녘 바닷가에서 웃으며 걷는 모습")
        if blocked(scene):
            raise ValueError(BLOCK_MSG)
        keep = "Keep the identity, face, hairstyle and body shape exactly the same" + (", and the same outfit" if p.get("keep_outfit") else "") + "."
        text = f"Create a new photo of the same person or object from image 1 in a new scene: {scene}. {keep} Natural photo, new composition."
        if extra:
            text += " " + extra
    else:
        if not p.get("pose_ref"):
            raise ValueError("따라 할 포즈가 담긴 참고 사진을 올려 주세요.")
        q["ref1"] = p["pose_ref"]
        text = ("Make the person in image 1 take exactly the same pose and body position as the person in image 2. "
                "Keep the identity, face, hairstyle, outfit and background of image 1; ignore the clothing and face of image 2.")
        if extra:
            text += " " + extra
    q["prompt"] = text
    if re.search("[가-힣]", text):
        q["translate"] = "on"
    out = do_edit(q, J)
    return [(im, {**info, "kind": "recompose", "extra": {**(info.get("extra") or {}), "Mode": mode, **note}}, g) for im, info, g in out]


def cn_model_for(kind, fam):
    """구조 종류·모델 계열에 맞는 ControlNet 모델 파일(통합 모델 우선)."""
    names = files("controlnet")
    want = (["flux"] if fam == "flux" else [])
    pool = [n for n in names if all(w in n.lower() for w in want)] if want else [n for n in names if "flux" not in n.lower()]
    keys = {"pose": ["union", "promax", "openpose", "pose"], "depth": ["union", "promax", "depth"], "canny": ["union", "promax", "canny"],
            "lineart": ["union", "promax", "lineart", "canny"]}[kind]
    return next((n for k in keys for n in pool if k in n.lower()), None)


def recompose_structure(p, J):
    """사진에서 포즈·깊이·윤곽만 뽑아 그 구도로 새 그림을 그려요(이미지 생성 화면의 모델·설정 사용)."""
    kind = p.get("skind") if p.get("skind") in STRUCT_KINDS else "pose"
    text = str(p.get("prompt") or "").strip()
    if not text:
        raise ValueError("새로 그릴 내용을 적어 주세요. (구도·자세는 올린 사진을 따라가요)")
    gen = p.get("gen") if isinstance(p.get("gen"), dict) else {}
    if not gen:
        raise ValueError("이미지 생성 화면의 설정을 읽지 못했어요. 이미지 생성 화면을 한 번 연 뒤 다시 시도해 주세요.")
    fam = gen.get("gengine") or "sdxl"
    if fam not in ("sdxl", "flux"):
        raise ValueError("구조 따라 그리기는 이미지 생성 화면의 모델 종류가 'SD·SDXL 계열'이나 'FLUX.1·Krea' 일 때 쓸 수 있어요.")
    cn = cn_model_for(kind, fam)
    if not cn:
        raise RuntimeError(f"이 구조({ {'pose': '포즈', 'depth': '깊이', 'canny': '윤곽선', 'lineart': '선화'}[kind] })에 맞는 ControlNet 모델이 없어요. "
                           f"'설치와 모델'에서 {'FLUX ControlNet Union' if fam == 'flux' else 'ControlNet Union SDXL'}을 설치해 주세요.")
    J["msg"] = "사진에서 구조를 뽑는 중"
    r = control_prep({"type": kind, "image": p["image"]})
    if r.get("error"):
        raise RuntimeError(r["error"])
    img = load_img(p["image"])
    g = dict(gen)
    for k in ("init", "init_denoise"):
        g.pop(k, None)
    w0, h0 = img.size
    k = (clamp(num(gen, "w", 1024, int), 256, 2048) * clamp(num(gen, "h", 1024, int), 256, 2048) / (w0 * h0)) ** 0.5
    g.update(kind="gen", prompt=text, cn_image=r["image"], cn_prep="none", cn_type=kind, cn_model=cn, cn_strength=clamp(num(p, "strength", 0.75), 0.1, 1.5),
             w=int(w0 * k) // 16 * 16, h=int(h0 * k) // 16 * 16, n=clamp(num(p, "n", 1, int), 1, 4), seed=p.get("seed", -1))
    if re.search("[가-힣]", text):
        g["translate"] = "on"
    J["msg"] = "같은 구도로 새로 그리는 중"
    out = do_gen(g, J)
    return [(im, {**info, "kind": "recompose", "extra": {**(info.get("extra") or {}), "Mode": "structure", "Structure": kind, "ControlNet": cn}}, gr)
            for im, info, gr in out]
