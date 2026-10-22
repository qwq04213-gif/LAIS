# 로컬 AI 스튜디오 허브 — 작업: 편집 · 업스케일 공용 · FLUX 공용
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

# ───────────────────────── 작업 (편집 / 생성 / 업스케일 / 워크플로) ─────────────────────────
def qwen_ver(name):
    """Qwen-Image-Edit 파일 이름의 판 번호(2509·2511 …). 번호가 없으면(첫 판) 0."""
    m = re.search(r"(?<!\d)(2[5-9]\d\d)(?!\d)", name or "")
    return int(m.group(1)) if m else 0


def qwen_edit_unet():
    """설치된 Qwen-Image-Edit 중 가장 새 판(2511 > 2509 > 첫 판)."""
    c = [n for n in files("diffusion_models") if "qwen_image_edit" in n.lower()]
    return max(c, key=lambda n: (qwen_ver(n), "fp8" in n.lower()), default=None)


def qwen_fast_lora(unet):
    """편집 모델과 같은 판의 4단계 Lightning LoRA. 판이 다른 LoRA 만 있으면 None(판이 다르면 결과가 깨질 수 있어요)."""
    want = qwen_ver(unet)
    c = [n for n in files("loras") if "lightning" in n.lower() and "qwen" in n.lower() and "edit" in n.lower()] \
        or [n for n in files("loras") if "lightning" in n.lower() and "qwen" in n.lower()]
    same = [n for n in c if qwen_ver(n) == want]
    if same:
        return min(same, key=lambda n: ("4step" not in n.lower(), n))
    return next((n for n in c if not qwen_ver(n)), None) if not want else None


def ref_method_key():
    """FluxKontextMultiReferenceLatentMethod 노드의 고르는 칸 이름(ComfyUI 판마다 달라요)."""
    spec = ((caps()["info"].get("FluxKontextMultiReferenceLatentMethod") or {}).get("input", {}).get("required") or {})
    return next((k for k, v in spec.items() if isinstance(v, list) and v and (v[0] == "COMBO" and "index_timestep_zero" in ((v[1] or {}).get("options") or []) or isinstance(v[0], list) and "index_timestep_zero" in v[0])), "reference_latents_method")


def qwen_params(p, text, tags, J):
    f = dict(unet=qwen_edit_unet(), te=find("text_encoders", "qwen_2.5_vl"),
             vae=find("vae", "qwen_image_vae"))
    for key, field, sub in (("unet", "q_unet", "diffusion_models"), ("te", "q_te", "text_encoders"), ("vae", "q_vae", "vae")):
        if p.get(field) and p[field] in files(sub):   # 화면에서 직접 고른 파일이 우선
            f[key] = p[field]
    if not all(f.values()):
        names = {"unet": "Qwen 모델", "te": "텍스트 인코더", "vae": "VAE"}
        raise RuntimeError("없는 파일: " + ", ".join(names[k] for k, v in f.items() if not v) + ". '설치와 모델' 탭에서 설치하거나, Qwen 설정의 '모델 파일 직접 고르기'에서 골라 주세요.")
    if blocked(text):
        raise ValueError(BLOCK_MSG)
    ver = qwen_ver(f["unet"])
    new_ok = has_node("FluxKontextMultiReferenceLatentMethod") and has_node("TextEncodeQwenImageEditPlus")
    if ver >= 2511 and not new_ok and not p.get("q_unet"):      # 엔진이 옛 판이면 설치된 옛 모델(2509 등)로 대신 그려요
        old = max((n for n in files("diffusion_models") if "qwen_image_edit" in n.lower() and qwen_ver(n) < 2511), key=qwen_ver, default=None)
        if old:
            warn(J, "이 ComfyUI 는 Qwen-Image-Edit 2511 을 아직 못 써서 " + old + " 로 편집했어요. ComfyUI 를 업데이트하면 2511 을 써요.")
            f["unet"], ver = old, qwen_ver(old)
    fast = qwen_fast_lora(f["unet"]) if p.get("fast") else None
    if p.get("fast") and not fast:
        warn(J, f"빠른 모드: 이 편집 모델({ver or '첫 판'})에 맞는 Lightning LoRA 가 없어 보통 속도로 그렸어요. "
                "'설치와 모델'에서 같은 판의 4단계 LoRA 를 받아 주세요.")
    method = None
    if ver >= 2511:      # 2511 공식 워크플로: 조건을 FluxKontextMultiReferenceLatentMethod(index_timestep_zero)로 묶어요
        if not new_ok:
            raise RuntimeError("이 ComfyUI 에는 Qwen-Image-Edit 2511 에 필요한 노드가 없어요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트하거나, Qwen 설정의 '모델 파일 직접 고르기'에서 2509 모델을 골라 주세요.")
        method = ref_method_key()
    loras = ([(fast, 1.0)] if fast else []) + collect_loras(p, tags, J)
    return dict(files=f, loras=loras, prompt=text, seed=seed_of(p), ref_method=method,
                steps=4 if fast else clamp(num(p, "q_steps", 20, int), 1, 100),
                cfg=1.0 if fast else clamp(num(p, "q_cfg", 4.0), 0.0, 20.0),
                sampler=p.get("q_sampler") or "euler", scheduler=p.get("q_scheduler") or "simple",
                shift=clamp(num(p, "q_shift", 3.0), 0.1, 20.0))


SCALE_MIN, SCALE_MAX, SIDE_MAX = 0.1, 8.0, 8192


def scale_of(p, default=4.0):
    """배율 칸의 값(예: 2, 1.5, 0.5, '3배')을 숫자로. 1보다 작으면 줄이기예요."""
    raw = str(p.get("scale") if p.get("scale") not in (None, "") else default).strip().lower().replace("배", "").replace("x", "").replace("×", "").replace(",", ".").strip()
    try:
        v = float(raw)
    except ValueError:
        raise ValueError("배율은 숫자로 적어 주세요. (예: 2, 1.5, 0.5)") from None
    if not (SCALE_MIN <= v <= SCALE_MAX):
        raise ValueError(f"배율은 {SCALE_MIN:g} ~ {SCALE_MAX:g} 사이로 적어 주세요. (1보다 작으면 줄여요)")
    return round(v, 3)


def scale_check(size, scale):
    """결과 크기를 (가로, 세로)로 돌려주고, 너무 크거나 작으면 안내해요."""
    out = (max(1, round(size[0] * scale)), max(1, round(size[1] * scale)))
    if max(out) > SIDE_MAX:
        raise ValueError(f"결과가 {SIDE_MAX}px 를 넘어요({out[0]}×{out[1]}). 배율을 낮추거나 더 작은 이미지를 써 주세요.")
    if min(out) < 16:
        raise ValueError(f"결과가 너무 작아져요({out[0]}×{out[1]}). 배율을 키워 주세요.")
    return out


def upscale(img, J, model, scale):
    """scale > 1: 업스케일 모델로 키운 뒤 원하는 배율에 맞춰요(모델이 4배라면 2배·1.5배·6배도 가능). scale <= 1: 모델 없이 줄이기(Lanczos)."""
    scale = float(scale)
    target = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    if scale <= 1.0:
        return img if target == img.size else img.resize(target, RS.LANCZOS)
    model = model or (files("upscale_models") or [None])[0]
    if not model:
        raise RuntimeError("업스케일 모델이 없습니다. '설치와 모델' 탭에서 Real-ESRGAN 을 설치해 주세요.")
    res = run_wf(flows.wf_upscale(model, put_input(img, J)), J)[0]
    return res if res.size == target else res.resize(target, RS.LANCZOS)


FX_DEFAULTS = {"flux": (20, 3.5, 1, "simple"), "chroma": (26, 0, 4, "beta"), "krea2": (8, 0, 1, "simple")}   # 단계, 가이던스, CFG, 스케줄러
FLUX_FAMS = ("flux", "krea2", "chroma")


def fx_sel(p, key="ckpt"):
    """모델 칸 값이 'fx:종류:파일' 이면 (종류, 그 모델에 맞는 단계 수·CFG 를 채운 설정)을, SDXL 체크포인트면 (None, p)를 돌려줘요."""
    fx = re.match(r"fx:(flux|krea2|chroma):(.*)$", str(p.get(key) or ""), re.S)
    if not fx:
        return None, p
    fam = fx.group(1)
    d = FX_DEFAULTS[fam]
    p2 = dict(p, fx_model=fx.group(2), fx_steps=d[0], fx_guidance=d[1], fx_cfg=d[2], fx_scheduler=d[3])
    if fam == "krea2" and re.search("raw", fx.group(2), re.I):
        p2.update(fx_steps=30, fx_cfg=4)
    return fam, p2


def flux_q(p, J, fam, text, tags, seed, w=1024, h=1024):
    """FLUX·Krea 2·Chroma 생성 그래프에 넘길 설정 한 벌(생성·편집·확장·업스케일이 같이 써요)."""
    f, allin, sch = flux_setup(p, J, fam)
    neg = ""
    if fam == "krea2":
        neg = (p.get("negative") or "").strip()
    elif fam == "chroma":
        neg = (p.get("negative") or "").strip() or CHROMA_NEG
        if flows_sex(text):
            neg += ", child, loli, shota, underage, aged down"
    return dict(family=fam, allin=allin, **f, loras=collect_loras(p, tags, J), prompt=text, negative=neg, seed=seed, w=w, h=h,
                guidance=clamp(num(p, "fx_guidance", 3.5), 0.0, 20.0), steps=clamp(num(p, "fx_steps", 20, int), 1, 100),
                cfg=clamp(num(p, "fx_cfg", 4.0), 0.0, 20.0) if fam in ("chroma", "krea2") else 1.0,
                sampler=p.get("fx_sampler") or "euler", scheduler=sch)


def flux_info(q, res, kind, **extra):
    fam = q["family"]
    return dict(kind=kind, prompt=q["prompt"], negative=q["negative"], steps=q["steps"], cfg=q["guidance"] if fam == "flux" else q["cfg"],
                sampler=q["sampler"], scheduler=q["scheduler"], seed=q["seed"], w=res.width, h=res.height, model=q["unet"],
                loras=[[a, b] for a, b in q["loras"]],
                extra={"Family": fam, **({"Distilled CFG": q["guidance"]} if fam == "flux" else {}), **extra})


def edit_flux(p, J, img, mask, grow, feather, rng):
    """FLUX·Krea 2·Chroma 로 편집. 칠한 영역은 인페인트, FLUX Kontext 모델이면 말로 지시하는 편집."""
    fam = p.get("fengine") if p.get("fengine") in FLUX_FAMS else "flux"
    text, tags = prep(p, J, "caption", rng)
    q = flux_q(p, J, fam, text, tags, seed_of(p))
    kontext = fam == "flux" and "kontext" in (p.get("fx_model") or "").lower()
    if kontext:
        if not has_node("ReferenceLatent") or not has_node("FluxKontextImageScale"):
            raise RuntimeError("FLUX Kontext 편집에는 ReferenceLatent·FluxKontextImageScale 노드가 필요해요. ComfyUI 를 업데이트해 주세요.")
        small = img.resize(qsize(img.size, 1.0), RS.LANCZOS)
        J["msg"] = "편집 중"
        res = run_wf(flows.wf_kontext(q, put_input(small, J)), J)[0]
        res = res.resize(img.size, RS.LANCZOS)
        if mask:
            res = Image.composite(res, img, grow_feather(mask, grow, feather))
        return [(res, flux_info(q, res, "edit-flux", Kontext=True), None)]
    if not mask:
        raise ValueError("칠해서 고치는 방식이에요. 편집할 영역을 마스크로 칠하거나 [선택 도구]로 골라 주세요. (말로만 지시해서 고치려면 Qwen-Image-Edit 이나 FLUX Kontext 모델을 쓰세요.)")
    q["denoise"] = clamp(num(p, "fx_edn", num(p, "fx_denoise", 0.6)), 0.1, 1.0)     # 기본 0.6: 1.0 이면 칠한 곳을 원본과 상관없이 통째로 새로 그려요
    pos, crop, soft, size = plan(img, mask, grow, clamp(num(p, "ctx", 35.0), 5, 200) / 100,
                                 clamp(num(p, "res", 1024, int), 512, 2048), feather, mult=16)
    a = put_input(crop.resize(size, RS.LANCZOS), J)
    b = put_input(soft.resize(size, RS.BILINEAR), J)
    J["msg"] = "인페인트 생성 중"
    out = finish(img, pos, crop, soft, run_wf(flows.wf_flux_inpaint(q, a, b), J)[0])
    return [(out, flux_info(q, out, "edit-flux", **{"Denoising strength": q["denoise"], "Mask grow": grow}), None)]


def do_edit(p, J):
    img = load_img(p["image"])
    mask = load_mask(p.get("mask"), img.size)
    grow = clamp(num(p, "grow", 8, int), 0, 128)
    rng = random.Random(num(p, "seed", -1, int))
    feather = clamp(num(p, "feather", 0, int), 0, 200) or None
    if p.get("engine") == "flux":
        return edit_flux(p, J, img, mask, grow, feather, rng)
    if p.get("engine") == "sdxl":
        if not mask:
            raise ValueError("편집할 영역을 마스크로 칠해 주세요.")
        q = sd(p, *prep(p, J, "tags", rng), J)
        pos, crop, soft, size = plan(img, mask, grow, clamp(num(p, "ctx", 35.0), 5, 200) / 100,
                                     clamp(num(p, "res", 1024, int), 512, 2048), feather)
        a = put_input(crop.resize(size, RS.LANCZOS), J)
        b = put_input(soft.resize(size, RS.BILINEAR), J)
        extra = {"Denoising strength": q["denoise"], "Mask grow": grow}
        if p.get("cn_model"):
            own = bool(p.get("cn_image"))
            src = load_img(p["cn_image"]).resize(img.size, RS.LANCZOS) if own else img   # 올린 제어 이미지는 원본 크기에 맞춰 같은 구역을 잘라 써요
            cc = src.crop((pos[0], pos[1], pos[0] + crop.width, pos[1] + crop.height)).resize(size, RS.LANCZOS)
            canny = p.get("cn_prep") == "canny" or not own
            if canny and not has_node("Canny"):
                warn(J, "이 ComfyUI 에는 Canny 노드가 없어 전처리 없이 사용했어요.")
                canny = False
            q["cn"] = dict(model=p["cn_model"], image=put_input(cc, J), canny=canny, union=cn_union(p),
                           strength=clamp(num(p, "cn_strength", 0.7), 0.0, 2.0),
                           start=clamp(num(p, "cn_start", 0.0), 0.0, 1.0), end=clamp(num(p, "cn_end", 1.0), 0.0, 1.0))
            extra["ControlNet"] = f'{p["cn_model"]} {q["cn"]["strength"]}'
        J["msg"] = "인페인트 생성 중"
        out = finish(img, pos, crop, soft, run_wf(flows.wf_inpaint(q, a, b), J)[0])
        return [(out, info_sd(q, out.size, "edit-sdxl", **extra), None)]
    text, tags = prep(p, J, "sentence", rng)
    q = qwen_params(p, text, tags, J)
    plus = has_node("TextEncodeQwenImageEditPlus")
    refs = [load_img(p[k]) for k in ("ref1", "ref2") if p.get(k)]
    if refs and not plus:
        raise RuntimeError("참조 이미지는 TextEncodeQwenImageEditPlus 노드가 필요해요. ComfyUI 를 업데이트해 주세요.")
    small = img.resize(qsize(img.size, clamp(num(p, "q_mp", 1.0), 0.3, 2.5)), RS.LANCZOS)
    wf = flows.wf_qwen(q, put_input(small, J), [put_input(r.resize(qsize(r.size), RS.LANCZOS), J) for r in refs], plus)
    J["msg"] = "편집 중"
    res = run_wf(wf, J)[0]
    if mask:  # 칠한 영역만 바꾸고 나머지는 원본 100% 유지
        res = Image.composite(res.resize(img.size, RS.LANCZOS), img, grow_feather(mask, grow, feather))
    elif p.get("hires") and files("upscale_models") and img.width * img.height > 1.3 * res.width * res.height:
        J["msg"] = "원본 해상도로 복원 중"
        res = upscale(res, J, None, 4).resize(img.size, RS.LANCZOS)
    info = dict(kind="edit-qwen", prompt=q["prompt"], negative="", steps=q["steps"], cfg=q["cfg"], sampler=q["sampler"],
                scheduler=q["scheduler"], seed=q["seed"], w=res.width, h=res.height, model=q["files"]["unet"],
                loras=[[n, w] for n, w in q["loras"]], extra={"Shift": q["shift"], "Refs": len(refs)})
    return [(res, info, None)]
