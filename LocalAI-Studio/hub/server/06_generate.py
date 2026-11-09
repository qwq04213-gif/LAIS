# 로컬 AI 스튜디오 허브 — 이미지 생성 (SDXL·FLUX 계열·기타 계열) · 업스케일 · 워크플로
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

CN_UNION = {"pose": "openpose", "depth": "depth", "canny": "canny/lineart/anime_lineart/mlsd", "lineart": "canny/lineart/anime_lineart/mlsd"}
CN_PREP = {"canny": ["Canny"], "pose": ["DWPreprocessor", "OpenposePreprocessor"],
           "depth": ["DepthAnythingV2Preprocessor", "DepthAnythingPreprocessor", "Zoe-DepthMapPreprocessor", "MiDaS-DepthMapPreprocessor"],
           "lineart": ["LineArtPreprocessor", "AnimeLineArtPreprocessor"]}


def cn_union(p):
    """쉬운 모드에서 고른 지도 종류 → 통합(union) ControlNet 모델에 알려 줄 값. 통합 모델이 아니거나 노드가 없으면 None."""
    t = CN_UNION.get(str(p.get("cn_type") or ""))
    name = str(p.get("cn_model") or "").lower()
    return t if t and ("union" in name or "promax" in name) and has_node("SetUnionControlNetType") else None


def control_prep(p):
    """사진 한 장에서 ControlNet 용 지도(포즈·윤곽선·깊이·선화)를 뽑아 미리보기로 돌려줘요."""
    kind = str(p.get("type") or "")
    if kind not in CN_PREP:
        return {"error": "알 수 없는 종류예요."}
    try:
        img = load_img(p["image"])
    except Exception:
        return {"error": "이미지를 읽을 수 없어요."}
    if max(img.size) > 1536:
        k = 1536 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), RS.LANCZOS)
    try:
        wait_comfy()
    except RuntimeError as e:
        return {"error": str(e)}
    node = next((n for n in CN_PREP[kind] if has_node(n)), None)
    if not node:
        return {"error": "이 ComfyUI 에는 이 지도를 만드는 노드가 없어요." if kind == "canny" else
                "이 지도를 만드는 확장(ComfyUI's ControlNet Auxiliary Preprocessors)이 설치되어 있지 않아요.",
                "missing": CN_PREP[kind][0], "need_pack": kind != "canny"}
    claim("image")
    J = {"id": "prep", "state": "running", "msg": "", "images": [], "tmp": []}
    w = flows.WF()
    li = w.add("LoadImage", image=put_input(img, J))
    ins = {"image": [li, 0]}
    res = clamp(max(img.size) // 64 * 64, 512, 1024)
    inp = (caps()["info"].get(node) or {}).get("input", {}) or {}
    opt = inp.get("optional", {}) or {}
    # 선택 입력(예: 선화의 coarse)도 확장 코드가 kwargs["이름"] 으로 바로 읽는 경우가 있어 기본값을 채워 줘요
    for k, spec in {**opt, **(inp.get("required", {}) or {})}.items():
        if k == "image" or not isinstance(spec, list) or not spec:
            continue
        t, o = spec[0], (spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {})
        if isinstance(t, list):
            if k in opt and k not in (inp.get("required") or {}):
                ins[k] = o["default"] if o.get("default") in t else (t[0] if t else "")
            else:
                ins[k] = "enable" if "enable" in t else (t[0] if t else "")
        elif k == "resolution":
            ins[k] = res
        elif "default" in o:
            ins[k] = o["default"]
        elif t == "BOOLEAN":
            ins[k] = True
    if node == "Canny":
        ins.setdefault("low_threshold", 0.4)
        ins.setdefault("high_threshold", 0.8)
    out = w.add(node, **ins)
    w.add("PreviewImage", images=[out, 0])
    try:
        r = run_wf(w.n, J)[0]
    except RuntimeError as e:
        pm = pymod_missing(e)
        return {"error": f"지도를 만들지 못했어요: {e}" + (" — 아래 버튼으로 빠진 부품을 설치할 수 있어요." if pm else ""), **({"pymod": pm} if pm else {})}
    finally:
        _clean_tmp(J)
    b = io.BytesIO()
    r.save(b, "PNG")
    return {"image": "data:image/png;base64," + base64.b64encode(b.getvalue()).decode(), "node": node, "w": r.width, "h": r.height}


def do_gen(p, J):
    if p.get("gengine") in ("flux", "chroma", "krea2"):
        return do_gen_flux(p, J)
    if p.get("gengine") in OX_FAMS:
        return do_gen_other(p, J)
    base = seed_of(p)
    n = clamp(num(p, "n", 1, int), 1, 8)
    w, h = (clamp(num(p, k, 1024, int) // 8 * 8, 256, 2048) for k in ("w", "h"))
    init = load_img(p["init"]) if p.get("init") else None
    cnimg = load_img(p["cn_image"]) if p.get("cn_image") and p.get("cn_model") else None
    out = []
    for i in range(n):
        rng = random.Random(base + i)
        q = sd(p, *prep(p, J, "tags", rng), J)
        q.update(seed=base + i, w=w, h=h)
        extra = {}
        if init is not None:
            small = fit_area(init, w, h)
            q["init"], q["init_denoise"] = put_input(small, J), clamp(num(p, "init_denoise", 0.7), 0.05, 1.0)
            w0, h0 = small.size
            extra["Denoising strength"] = q["init_denoise"]
        else:
            w0, h0 = w, h
        if cnimg is not None:
            prep_canny = p.get("cn_prep") == "canny"
            if prep_canny and not has_node("Canny"):
                warn(J, "이 ComfyUI 에는 Canny 노드가 없어 전처리 없이 사용했어요.")
                prep_canny = False
            q["cn"] = dict(model=p["cn_model"], image=put_input(cover(cnimg, (w0, h0)), J), canny=prep_canny, union=cn_union(p),
                           strength=clamp(num(p, "cn_strength", 0.7), 0.0, 2.0),
                           start=clamp(num(p, "cn_start", 0.0), 0.0, 1.0), end=clamp(num(p, "cn_end", 1.0), 0.0, 1.0))
            extra["ControlNet"] = f'{p["cn_model"]} {q["cn"]["strength"]}'
        if p.get("hires"):
            q["hires"] = dict(scale=clamp(num(p, "hires_scale", 1.5), 1.0, 3.0),
                              denoise=clamp(num(p, "hires_denoise", 0.5), 0.1, 1.0),
                              steps=clamp(num(p, "hires_steps", 15, int), 1, 100))
            extra.update({"Denoising strength": q["hires"]["denoise"], "Hires upscale": q["hires"]["scale"],
                          "Hires steps": q["hires"]["steps"], "Hires upscaler": "Latent (bislerp)"})
        J["msg"] = f"생성 중 ({i + 1}/{n})"
        J["pi"], J["pn"] = i, n
        g = flows.wf_gen(q)
        try:
            res = run_wf(g, J)[0]
        except Cancelled:
            if out:
                warn(J, f"중단해서 완료된 {len(out)}장만 저장했어요.")
                break
            raise
        out.append((res, info_sd(q, res.size, "gen", **extra), g if not (init is not None or cnimg is not None) else None))
    return out


CHROMA_NEG = "low quality, ugly, unfinished, out of focus, deformed, disfigure, blurry, smudged, restricted palette, flat colors"


def flux_vae():
    return next((n for n in files("vae") if n.lower() in ("ae.safetensors", "flux_ae.safetensors") or n.lower().startswith("ae.") or "flux" in n.lower()), None)


def flux_parts(p=None):
    """FLUX 계열 공용 파일. 자동으로 찾고, 화면에서 직접 고른 파일(fx_vae/fx_t5/fx_clip)이 있으면 그걸 써요."""
    te = files("text_encoders")
    low = lambda n: n.lower()
    is_t5 = lambda n: ("t5" in low(n) or "xxl" in low(n)) and "umt5" not in low(n)
    r = dict(t5=next((n for n in te if "t5xxl" in low(n)), None) or next((n for n in te if is_t5(n)), None),
             clip_l=next((n for n in te if low(n).startswith("clip_l")), None) or next((n for n in te if "clip" in low(n) and not is_t5(n)), None)
             or next((n for n in te if re.search(r"vit-?l|clipl|text_?encoder", low(n)) and not is_t5(n) and "qwen" not in low(n)), None),
             vae=flux_vae() or next((n for n in files("vae") if not re.search(r"qwen|sdxl|wan|sd15|sd_xl", n.lower())), None))
    if p:
        for key, field, sub in (("t5", "fx_t5", "text_encoders"), ("clip_l", "fx_clip", "text_encoders"), ("vae", "fx_vae", "vae")):
            v = p.get(field)
            if v and v in files(sub):
                # 엉뚱한 종류를 골랐으면(예: T5 칸에 Qwen) 무시하고 자동으로 찾아요 — 그대로 쓰면 'meta tensor' 오류가 나요
                if key == "t5" and re.search(r"qwen|umt5|clip|llama|gemma|mistral|vl[_-]?\d|_vl|-vl", low(v)):
                    continue
                if key == "clip_l" and (is_t5(v) or re.search(r"qwen|umt5", low(v))):
                    continue
                r[key] = v
    return r


def krea2_parts(p=None):
    """Krea 2 공용 파일: Qwen3-VL 텍스트 인코더 + Qwen Image VAE. 화면에서 직접 고른 파일(k2_te/k2_vae)이 우선이에요."""
    te, va = files("text_encoders"), files("vae")
    tq = [n for n in te if "qwen3" in n.lower() and not re.search(r"8b|qwen3\.?5", n.lower())]      # Qwen-Image 2.1(8B)·MOSS(3.5 9B) 인코더는 Krea 2 와 맞지 않아요
    vq = [n for n in va if "qwen" in n.lower() and "2.1" not in n and "2_1" not in n]                # Qwen-Image 2.1 VAE 도 달라요
    r = dict(te=next((n for n in tq if "vl" in n.lower() and "4b" in n.lower()), None) or next((n for n in tq if "vl" in n.lower()), None) or next(iter(tq), None),
             vae=next((n for n in vq if "qwen_image_vae" in n.lower()), None) or next(iter(vq), None))
    if p:
        for key, field, lst in (("te", "k2_te", te), ("vae", "k2_vae", va)):
            if p.get(field) and p[field] in lst:
                r[key] = p[field]
    return r


K2C_NODES = ("Krea2ControlLoRALoader", "Krea2ControlImageEncode", "Krea2ControlApply")
K2C_REPO = "https://github.com/facok/comfyui-krea2-controlnet"
# 허브가 직접 확인해 둔 확장(코드를 읽어 네트워크·실행 호출이 없는 것을 확인한 커밋으로 고정). 목록에 없는 주소는 여전히 설치하지 않아요.
SUBPACK_REPO = "https://github.com/ltdrdata/ComfyUI-Impact-Subpack"
REACTOR_REPO = "https://github.com/Gourieff/ComfyUI-ReActor"
KNOWN_PACKS = {REACTOR_REPO: {"ref": "3be5f356fe5b120a7a274d2509c0ecef5d0a7498", "title": "ReActor (얼굴 교체, 안전 필터 포함)", "nodes": ("ReActorFaceSwap",), "install_py": True},
               SUBPACK_REPO: {"ref": "50c7b71a6a224734cc9b21963c6d1926816a97f1", "title": "Impact Subpack (얼굴·손 감지 노드)", "nodes": ("UltralyticsDetectorProvider",)},
               K2C_REPO: {"ref": "79ebfd3bd80d2180b334dd7ce57f3c9ddaa0848f", "title": "Krea2 Control (comfyui-krea2-controlnet)", "nodes": K2C_NODES}}


def k2_control_loras():
    """loras 폴더에서 Krea 2 컨트롤 LoRA(깊이·캐니·포즈 등)로 보이는 파일."""
    return [n for n in files("loras") if re.search(r"control|depth|canny|pose|lineart|normal", n, re.I)]


def flux_setup(p, J, fam):
    """FLUX·Chroma·Krea 2 가 쓸 파일(모델, 텍스트 인코더, VAE)을 찾아서 (파일들, 올인원 여부, 스케줄러)를 돌려줘요."""
    sel = p.get("fx_model") or None
    allin = bool(sel and sel.startswith("ckpt::")) and fam != "krea2"     # 체크포인트 폴더의 올인원 FLUX/Chroma
    if fam == "krea2":
        ct = caps().get("clip_types") or []
        if ct and "krea2" not in ct:
            raise RuntimeError("이 ComfyUI 는 Krea 2 를 아직 지원하지 않아요(버전 0.26.0 이상 필요). ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
        kp = krea2_parts(p)
        f = dict(unet=sel, t5=kp["te"], clip_l=None, vae=kp["vae"])
        miss = [n for n, k in (("Krea 2 모델", "unet"), ("Qwen3-VL 텍스트 인코더", "t5"), ("Qwen Image VAE", "vae")) if not f[k]]
        if miss:
            raise RuntimeError("없는 파일: " + ", ".join(miss) + ". '설치와 모델' 탭에서 설치하거나, 설정의 '모델 파일 직접 고르기'에서 골라 주세요.")
    elif allin:
        sel = sel[6:]
        if sel not in files("checkpoints"):
            raise RuntimeError("선택한 체크포인트 파일을 찾을 수 없어요.")
        if not model_family("checkpoints", sel)[1]:
            # checkpoints 폴더에 있어도 텍스트 인코더·VAE 가 없는 '모델만' 파일이면 공용 파일을 따로 붙여요(모델은 체크포인트 로더로 읽음)
            allin = False
            f = dict(unet=sel, ckpt_only=True, **flux_parts(p))
        else:
            f = dict(unet=sel, t5=None, clip_l=None, vae=None)
    else:
        f = dict(unet=sel, **flux_parts(p))
    if fam != "krea2" and not allin and not all(f[k] for k in (["unet", "t5", "vae"] + (["clip_l"] if fam == "flux" else []))):
        names = {"unet": "FLUX 모델", "t5": "T5 텍스트 인코더", "vae": "VAE", "clip_l": "CLIP-L 텍스트 인코더"}
        miss = [names[k] for k in ["unet", "t5", "vae"] + (["clip_l"] if fam == "flux" else []) if not f[k]]
        raise RuntimeError("없는 파일: " + ", ".join(miss) + ". '설치와 모델' 탭에서 설치하거나, 설정의 '모델 파일 직접 고르기'에서 골라 주세요.")
    sch = p.get("fx_scheduler") or ("beta" if fam == "chroma" else "simple")
    have = caps()["schedulers"]
    if have and sch not in have:
        warn(J, f"이 ComfyUI 에는 스케줄러 '{sch}' 가 없어 simple 로 바꿨어요.")
        sch = "simple"
    return f, allin, sch


def do_gen_flux(p, J):
    """FLUX.1 dev / Krea dev / Chroma / Krea 2 생성(이미지→이미지, LoRA, 다이나믹 프롬프트 지원)."""
    fam = p["gengine"]
    f, allin, sch = flux_setup(p, J, fam)
    base, n = seed_of(p), clamp(num(p, "n", 1, int), 1, 8)
    w, h = (clamp(num(p, k, 1024, int) // 16 * 16, 256, 2048) for k in ("w", "h"))
    init = load_img(p["init"]) if p.get("init") else None
    cnimg = None
    if p.get("cn_model") and p.get("cn_image"):
        if fam == "krea2":      # Krea 2 는 ControlNet 대신 '컨트롤 LoRA' 를 써요(확장 노드 필요)
            if p["cn_model"] not in k2_control_loras():
                raise ValueError("고른 파일은 Krea 2 컨트롤 LoRA 가 아닌 것 같아요. 설치와 모델의 'Krea 2 깊이 컨트롤 LoRA'를 설치하거나 사용 안 함으로 바꿔 주세요.")
            gone = [n for n in K2C_NODES if not has_node(n)]
            if gone:
                raise RuntimeError("Krea 2 컨트롤에는 'comfyui-krea2-controlnet' 확장 노드가 필요해요. 이미지 생성 화면 ControlNet 칸의 [설치] 버튼으로 설치하고 이미지 엔진을 다시 시작해 주세요.")
            cnimg = load_img(p["cn_image"])
        elif fam != "flux":      # Chroma 는 구조가 달라 FLUX.1 용 ControlNet 이 맞지 않아요
            warn(J, "ControlNet 은 FLUX.1·Krea(FLUX.1)·Krea 2 에서만 쓸 수 있어 이번에는 쓰지 않았어요.")
        else:
            if not re.search(r"flux", str(p["cn_model"]), re.I):
                raise ValueError("고른 ControlNet 모델은 FLUX 용이 아닌 것 같아요. 이름에 'FLUX'가 들어간 모델을 고르거나(설치와 모델 → FLUX ControlNet), 사용 안 함으로 바꿔 주세요.")
            if not has_node("ControlNetApplyAdvanced"):
                raise RuntimeError("이 ComfyUI 에는 ControlNet 노드가 없어요. ComfyUI 를 업데이트해 주세요.")
            cnimg = load_img(p["cn_image"])
    out = []
    for i in range(n):
        rng = random.Random(base + i)
        text, tags = prep(p, J, "caption", rng)
        if blocked(text):
            raise ValueError(BLOCK_MSG)
        neg = ""
        if fam == "krea2":
            neg = (p.get("negative") or "").strip()
        elif fam == "chroma":
            neg = (p.get("negative") or "").strip() or CHROMA_NEG
            if flows_sex(text):
                neg += ", child, loli, shota, underage, aged down"
        q = dict(family=fam, allin=allin, **f, loras=collect_loras(p, tags, J), prompt=text, negative=neg, seed=base + i, w=w, h=h,
                 guidance=clamp(num(p, "fx_guidance", 3.5), 0.0, 20.0), steps=clamp(num(p, "fx_steps", 20, int), 1, 100),
                 cfg=clamp(num(p, "fx_cfg", 4.0), 0.0, 20.0) if fam in ("chroma", "krea2") else 1.0,
                 sampler=p.get("fx_sampler") or "euler", scheduler=sch)
        w0, h0 = w, h
        if init is not None:
            small = fit_area(init, w, h)
            q["init"] = put_input(small, J)
            q["init_denoise"] = clamp(num(p, "init_denoise", 0.7), 0.05, 1.0)
            w0, h0 = small.size
        cn_note = None
        if cnimg is not None:
            prep_canny = p.get("cn_prep") == "canny"
            if prep_canny and not has_node("Canny"):
                warn(J, "이 ComfyUI 에는 Canny 노드가 없어 전처리 없이 사용했어요.")
                prep_canny = False
            if fam == "krea2":
                q["k2c"] = dict(lora=p["cn_model"], image=put_input(cover(cnimg, (w0, h0)), J), canny=prep_canny,
                                strength=clamp(num(p, "cn_strength", 1.0), 0.0, 2.0), depth="depth" in p["cn_model"].lower() or p.get("cn_type") == "depth")
                cn_note = f'{p["cn_model"]} {q["k2c"]["strength"]}'
            else:
                q["cn"] = dict(model=p["cn_model"], image=put_input(cover(cnimg, (w0, h0)), J), canny=prep_canny, union=None,
                               strength=clamp(num(p, "cn_strength", 0.7), 0.0, 2.0),
                               start=clamp(num(p, "cn_start", 0.0), 0.0, 1.0), end=clamp(num(p, "cn_end", 1.0), 0.0, 1.0))
                cn_note = f'{p["cn_model"]} {q["cn"]["strength"]}'
        hr_note = {}
        if p.get("hires"):
            sc = clamp(num(p, "hires_scale", 1.5), 1.0, 2.5)
            up = p.get("hires_upm") if p.get("hires_upm") in files("upscale_models") else None
            q["hires"] = dict(scale=sc, w=min(4096, int(round(w0 * sc / 16)) * 16), h=min(4096, int(round(h0 * sc / 16)) * 16), model=up,
                              denoise=clamp(num(p, "hires_denoise", 0.4), 0.05, 1.0), steps=clamp(num(p, "hires_steps", 12, int), 1, 100))
            hr_note = {"Denoising strength": q["hires"]["denoise"], "Hires upscale": sc, "Hires steps": q["hires"]["steps"], "Hires upscaler": up or "Lanczos"}
        J["msg"] = f"생성 중 ({i + 1}/{n})" + (" · 하이레스 픽스 포함" if hr_note else "")
        J["pi"], J["pn"] = i, n
        g = flows.wf_flux(q)
        try:
            res = run_wf(g, J)[0]
        except Cancelled:
            if out:
                warn(J, f"중단해서 완료된 {len(out)}장만 저장했어요.")
                break
            raise
        info = dict(kind="gen-" + fam, prompt=text, negative=neg, steps=q["steps"],
                    cfg=q["guidance"] if fam == "flux" else q["cfg"], sampler=q["sampler"], scheduler=sch, seed=q["seed"],
                    w=res.width, h=res.height, model=f["unet"], loras=[[a, b] for a, b in q["loras"]],
                    extra={"Family": fam, **({"Distilled CFG": q["guidance"]} if fam == "flux" else {}), **({"ControlNet": cn_note} if cn_note else {}), **hr_note})
        out.append((res, info, g if init is None and cnimg is None else None))
    return out


OX_FAMS = ("sd35", "qwenimg", "moss", "zimage", "flux3k")
OX_NAMES = {"sd35": "SD3.5", "qwenimg": "Qwen-Image 2.1", "moss": "MOSS-Image", "zimage": "Z-Image-Turbo", "flux3k": "FLUX 3 Klein"}
# 계열별 기본값: (단계, CFG, 샘플러, 스케줄러, shift)
OX_DEFAULTS = {"sd35": (28, 4.5, "euler", "sgm_uniform", None), "qwenimg": (25, 1.0, "euler", "simple", None),
               "moss": (50, 3.0, "euler", "simple", None), "zimage": (8, 1.0, "res_multistep", "simple", 3.0),
               "flux3k": (16, 1.0, "euler", "simple", None)}
MOSS_RX = re.compile(r"moss[_-]?image")
ZIMAGE_RX = re.compile(r"z[_-]?image")
FLUX3K_RX = re.compile(r"flux[_-]?3.*klein")


def ox_defaults(fam, model):
    if fam == "qwenimg" and "turbo" in (model or "").lower():
        return (8, 1.0, "euler", "simple", None)
    if fam == "flux3k" and "base" in (model or "").lower():       # 원본판: 공식 예시 50단계·CFG 3.5
        return (50, 3.5, "euler", "simple", None)
    return OX_DEFAULTS[fam]


def _pick(lst, *prefs):
    """prefs: 키워드 묶음(튜플)을 앞에서부터 시도해 이름에 모두 들어 있는 첫 파일. 없으면 None."""
    for keys in prefs:
        keys = (keys,) if isinstance(keys, str) else keys
        for n in lst:
            if all(k in n.lower() for k in keys):
                return n
    return None


def moss_te():
    c = [n for n in files("text_encoders") if re.search(r"qwen3\.?5[_-]?9b", n.lower()) and "qwen_image" not in n.lower()]
    return min(c, key=lambda n: (0 if "int8" in n.lower() else 1 if "w4a8" in n.lower() else 2, n), default=None)


def moss_vae():
    va = files("vae")
    return _pick(va, ("flux2", "vae"), ("flux2",))


def moss_ctype():
    """MOSS-Image 텍스트 인코더의 CLIPLoader 종류 이름(ComfyUI 판에 따라 달라서 엔진에 물어봐요)."""
    ct = caps().get("clip_types") or []
    return next((t for t in ct if "moss" in t.lower()), None)


def ctype_of(word):
    """CLIPLoader 종류 이름(ComfyUI 판에 따라 없을 수 있어요)."""
    ct = caps().get("clip_types") or []
    return word if not ct or word in ct else None


def ox_parts(fam):
    """SD3.5·Qwen-Image 2.1·MOSS-Image 가 쓸 텍스트 인코더·VAE 를 폴더에서 찾아요."""
    te = files("text_encoders")
    if fam == "qwenimg":
        return {"te": {"qwen": qwen21_te()}, "vae": qwen21_vae()}
    if fam == "moss":
        return {"te": {"qwen35": moss_te()}, "vae": moss_vae()}
    if fam == "zimage":
        return {"te": {"qwen3": _pick(te, ("qwen_3_4b", "fp8"), "qwen_3_4b", ("qwen3", "4b"))}, "vae": _pick(files("vae"), "ae.safetensors", ("flux", "ae"))}
    if fam == "flux3k":
        return {"te": {"qwen3vl": _pick(te, ("qwen3vl", "4b"), ("qwen3-vl", "4b"))}, "vae": moss_vae()}
    return {"vae": None, "te": {"clip_l": _pick(te, "clip_l"), "clip_g": _pick(te, "clip_g"), "t5": _pick(te, ("t5xxl", "fp8_e4m3fn_scaled"), "t5xxl")}}


def other_models():
    """{'sd35': [...], 'qwenimg': [...], 'moss': [...]} — SD3.5 는 체크포인트 폴더, 나머지는 디퓨전 모델 폴더에서 찾아요."""
    out = {k: [] for k in OX_FAMS}
    for n in files("checkpoints"):
        if model_family("checkpoints", n)[0] == "sd3":
            out["sd35"].append(n)
    out["qwenimg"] = qwen21_unets()
    out["moss"] = sorted((n for n in files("diffusion_models") if MOSS_RX.search(n.lower())), key=lambda n: ("base" in n.lower(), n))
    out["zimage"] = sorted((n for n in files("diffusion_models") if ZIMAGE_RX.search(n.lower())), key=lambda n: ("turbo" not in n.lower(), n))
    out["flux3k"] = sorted((n for n in files("diffusion_models") if FLUX3K_RX.search(n.lower())), key=lambda n: ("base" in n.lower(), n))
    return out


def ox_setup(p, J, fam):
    """고른 모델 파일과 보조 파일을 확인해서 (모델 파일, 텍스트 인코더 dict, VAE) 를 돌려줘요. 빠진 게 있으면 설명과 함께 에러."""
    models = other_models()[fam]
    sel = p.get("fx_model") or (models[0] if models else None)
    if sel and sel.startswith("ckpt::"):
        sel = sel[6:]
    if not sel or sel not in models:
        raise RuntimeError(f"{OX_NAMES[fam]} 모델 파일이 없어요. '설치와 모델' 탭에서 설치해 주세요.")
    parts = ox_parts(fam)
    te, vae = parts["te"], parts["vae"]
    if fam == "sd35":
        _, allin, _ = model_family("checkpoints", sel)
        if allin or "incl_clips" in sel.lower():
            te, vae = {}, None
        elif not all(te.values()):
            raise RuntimeError("SD3.5 텍스트 인코더가 없어요(" + ", ".join(k for k, v in te.items() if not v) + "). '설치와 모델' 탭의 'SD3.5 공용 파일'을 설치해 주세요.")
        if te and not has_node("TripleCLIPLoader"):
            raise RuntimeError("이 ComfyUI 에는 SD3.5 에 필요한 노드(TripleCLIPLoader)가 없어요. ComfyUI 를 업데이트해 주세요.")
    elif fam == "moss":
        miss = ([] if te["qwen35"] else ["텍스트 인코더(Qwen3.5 9B)"]) + ([] if vae else ["FLUX.2 VAE"])
        if miss:
            raise RuntimeError("없는 파일: " + ", ".join(miss) + ". '설치와 모델' 탭에서 'MOSS-Image' 를 설치해 주세요.")
        if not moss_ctype():
            raise RuntimeError("이 ComfyUI 는 MOSS-Image 를 아직 지원하지 않아요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
    elif fam in ("zimage", "flux3k"):
        nm = {"zimage": ("텍스트 인코더(Qwen3 4B)", "VAE(ae.safetensors)", "Z-Image-Turbo", "lumina2"),
              "flux3k": ("텍스트 인코더(Qwen3-VL 4B)", "FLUX.2 VAE", "FLUX 3 Klein", "flux3")}[fam]
        miss = ([] if all(te.values()) else [nm[0]]) + ([] if vae else [nm[1]])
        if miss:
            raise RuntimeError("없는 파일: " + ", ".join(miss) + f". '설치와 모델' 탭에서 '{nm[2]}' 를 설치해 주세요.")
        if not ctype_of(nm[3]) or (fam == "flux3k" and not has_node("EmptyFlux2LatentImage")):
            raise RuntimeError(f"이 ComfyUI 는 {nm[2]} 를 아직 지원하지 않아요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
    return sel, te, vae


def do_gen_qwen(p, J):
    """Qwen-Image 2.1 로 새로 그리기(편집과 같은 모델·인코더). 단계 8 이하로 두면 Lightning LoRA 를 자동으로 써요."""
    models = other_models()["qwenimg"]
    sel = p.get("fx_model") if p.get("fx_model") in models else (models[0] if models else None)
    base, n = seed_of(p), clamp(num(p, "n", 1, int), 1, 8)
    w, h = (clamp(num(p, k, 1024, int) // 32 * 32, 256, 2048) for k in ("w", "h"))
    dsteps, dcfg, dsamp, dsch, _ = ox_defaults("qwenimg", sel)
    steps = clamp(num(p, "fx_steps", dsteps, int), 1, 100)
    out = []
    for i in range(n):
        rng = random.Random(base + i)
        text, tags = prep(p, J, "caption", rng)
        qp = dict(p, q_unet=sel, q_steps=steps, q_cfg=num(p, "fx_cfg", dcfg), q_sampler=p.get("fx_sampler") or dsamp,
                  q_scheduler=p.get("fx_scheduler") or dsch, seed=base + i, fast=steps <= 8 and "turbo" not in (sel or "").lower())
        q = qwen_params(qp, text, tags, J, (p.get("negative") or "").strip())
        if not q["fast"] and steps <= 8:
            q["steps"] = steps
        J["msg"] = f"생성 중 ({i + 1}/{n})"
        J["pi"], J["pn"] = i, n
        g = flows.wf_qwen21(q, (), (w, h))
        try:
            res = run_wf(g, J)[0]
        except Cancelled:
            if out:
                warn(J, f"중단해서 완료된 {len(out)}장만 저장했어요.")
                break
            raise
        info = dict(kind="gen-qwenimg", prompt=text, negative=q["negative"], steps=q["steps"], cfg=q["cfg"], sampler=q["sampler"], scheduler=q["scheduler"],
                    seed=q["seed"], w=res.width, h=res.height, model=q["files"]["unet"], loras=[[a, b] for a, b in q["loras"]],
                    extra={"Family": "qwenimg", "Engine": "Qwen-Image 2.1"})
        out.append((res, info, g))
    return out


def do_gen_other(p, J):
    if p["gengine"] == "qwenimg":
        return do_gen_qwen(p, J)
    """SD3.5 · MOSS-Image 생성(LoRA·다이나믹 프롬프트·번역 지원). 설정 칸은 FLUX 계열과 같은 fx_* 를 써요."""
    fam = p["gengine"]
    sel, te, vae = ox_setup(p, J, fam)
    if fam == "flux3k" and "base" in sel.lower() and num(p, "fx_cfg", 1.0) <= 1.0:     # 원본판을 증류판 설정(CFG 1)으로 그리면 흐려요
        p = dict(p, fx_steps=50, fx_cfg=3.5)
        warn(J, "FLUX 3 Klein 원본판(Base)은 공식 설정인 50단계·CFG 3.5 로 그렸어요. 빠르게는 증류판을 쓰세요.")
    dsteps, dcfg, dsamp, dsch, dshift = ox_defaults(fam, sel)
    base, n = seed_of(p), clamp(num(p, "n", 1, int), 1, 8)
    w, h = (clamp(num(p, k, 1024, int) // 16 * 16, 256, 2048) for k in ("w", "h"))
    sch = p.get("fx_scheduler") or dsch
    have = caps()["schedulers"]
    if have and sch not in have:
        warn(J, f"이 ComfyUI 에는 스케줄러 '{sch}' 가 없어 simple 로 바꿨어요.")
        sch = "simple"
    sampler = p.get("fx_sampler") or dsamp
    if caps()["samplers"] and sampler not in caps()["samplers"]:
        warn(J, f"이 ComfyUI 에는 샘플러 '{sampler}' 가 없어 euler 로 바꿨어요.")
        sampler = "euler"
    out = []
    for i in range(n):
        rng = random.Random(base + i)
        text, tags = prep(p, J, "caption", rng)
        if blocked(text):
            raise ValueError(BLOCK_MSG)
        neg = (p.get("negative") or "").strip()
        q = dict(family=fam, te=te, vae=vae, loras=collect_loras(p, tags, J), prompt=text, negative=neg, seed=base + i, w=w, h=h,
                 steps=clamp(num(p, "fx_steps", dsteps, int), 1, 150), cfg=clamp(num(p, "fx_cfg", dcfg), 0.0, 30.0),
                 sampler=sampler, scheduler=sch, shift=clamp(num(p, "ox_shift", dshift or 3.0), 0.1, 20.0))
        J["msg"] = f"생성 중 ({i + 1}/{n})"
        J["pi"], J["pn"] = i, n
        if fam == "moss":
            q.update(unet=sel, te=te["qwen35"], ctype=moss_ctype(), latent="EmptyFlux2LatentImage" if has_node("EmptyFlux2LatentImage") else "EmptySD3LatentImage")
            g = flows.wf_moss(q)
        elif fam == "zimage":
            q.update(unet=sel, te=te["qwen3"])
            g = flows.wf_zimage(q)
        elif fam == "flux3k":
            q.update(unet=sel, te=te["qwen3vl"])
            g = flows.wf_flux3k(q)
        else:
            q["ckpt"] = sel
            g = flows.wf_other(q)
        try:
            res = run_wf(g, J)[0]
        except Cancelled:
            if out:
                warn(J, f"중단해서 완료된 {len(out)}장만 저장했어요.")
                break
            raise
        info = dict(kind="gen-" + fam, prompt=text, negative=neg, steps=q["steps"], cfg=q["cfg"], sampler=sampler, scheduler=sch,
                    seed=q["seed"], w=res.width, h=res.height, model=sel, loras=[[a, b] for a, b in q["loras"]],
                    extra={"Family": fam})
        out.append((res, info, g))
    return out


ANTI_DUP = "extra eyes, extra faces, multiple faces, duplicate, extra heads, extra limbs, deformed, mutated"


def tile_text(p, J, rng, style, generic):
    """타일 리파인에 쓸 문장. 기본(auto)은 일반 고화질 지시만 써요 — 타일마다 '얼굴·눈' 같은 프롬프트를 그대로 넣으면
    배경 조각에도 눈·얼굴을 그려 넣기 때문이에요. 'mine' 이면 내 프롬프트를 그대로 써요. 반환: (문장, LoRA 태그, 자동 모드 여부)"""
    raw = (p.get("prompt") or "").strip()
    if not raw:
        return generic, [], True
    if p.get("tileprompt") == "mine":
        text, tags = prep(p, J, style, rng)
        return text, tags, False
    if blocked(raw):
        raise ValueError(BLOCK_MSG)
    tags = []

    def grab(m):
        tags.append((m.group(1).strip(), float(m.group(2) or 1)))
        return ""
    LORA_TAG.sub(grab, raw)
    return generic, tags, True


QWEN_REFINE = "Enhance this image: make it sharper with fine natural detail and clean textures. Keep the composition, colors, faces and identity exactly the same."


def refine_tiles(img, q, tile, overlap, J, build=None, mult=8):
    """큰 이미지를 겹치는 타일로 나눠 각각 낮은 denoise 로 다시 그린 뒤 부드럽게 이어 붙입니다."""
    xs, ys = spans(img.width, tile, overlap), spans(img.height, tile, overlap)
    canvas, n, total = img.copy(), 0, len(xs) * len(ys)
    for yi, (y0, y1) in enumerate(ys):
        for xi, (x0, x1) in enumerate(xs):
            n += 1
            check_cancel(J)
            J["msg"] = f"타일 리파인 {n}/{total}"
            J["pi"], J["pn"] = n - 1, total
            t = img.crop((x0, y0, x1, y1))
            s8 = (max(64, round(t.width / mult) * mult), max(64, round(t.height / mult) * mult))
            name = put_input(t.resize(s8, RS.LANCZOS) if s8 != t.size else t, J)
            res = run_wf(build(name) if build else flows.wf_refine(q, name), J)[0]
            if res.size != t.size:
                res = res.resize(t.size, RS.LANCZOS)
            canvas.paste(res, (x0, y0), ramp(t.size, overlap, xi > 0, yi > 0))
    return canvas


def do_up(p, J):
    img = load_img(p["image"])
    scale = scale_of(p)
    scale_check(img.size, scale)
    J["msg"] = "업스케일 중" if scale > 1 else "줄이는 중"
    big = upscale(img, J, p.get("upm"), scale)
    if p.get("mode") != "refine":
        return [(big, dict(kind="upscale", extra={**({"Upscaler": p.get("upm") or "auto"} if scale > 1 else {"Downscale": "Lanczos"}), "Scale": scale}), None)]
    rng = random.Random(num(p, "seed", -1, int))
    fam = p.get("rengine") if p.get("rengine") in ("flux", "chroma", "krea2", "qwen") else "sdxl"
    if fam == "qwen":      # 이미지 편집에 쓰는 Qwen-Image 2.1 로 타일을 다시 그려요
        raw = (p.get("prompt") or "").strip()
        text, tags = prep(p, J, "sentence", rng) if raw else (QWEN_REFINE, [])
        q = qwen_params(p, text, tags, J)
        den = clamp(num(p, "rdenoise", 0.45), 0.05, 0.9)
        if p.get("fast"):          # 4단계용 모델은 일부만 다시 그릴 때 단계가 모자라서 조금 늘려요
            q["steps"] = int(min(12, max(4, round(2.5 / den))))
        q["denoise"], q["resolution"] = den, 0
        tile = clamp(num(p, "tile", 1024, int) // 32 * 32, 512, 1536)
        out = refine_tiles(big, q, tile, clamp(num(p, "overlap", 128, int), 32, tile // 2), J,
                           build=lambda n: flows.wf_qwen21(q, [n], key=qwen21_img_key), mult=32)
        info = dict(kind="upscale-refine", prompt=text, negative="", steps=q["steps"], cfg=q["cfg"], sampler=q["sampler"],
                    scheduler=q["scheduler"], seed=q["seed"], w=out.width, h=out.height, model=q["files"]["unet"],
                    loras=[[n, w] for n, w in q["loras"]], extra={"Family": "qwen", "Denoising strength": den, "Tile": tile})
        return [(out, info, None)]
    if fam != "sdxl":      # 실사 등 FLUX 계열 모델로 타일을 다시 그려요
        f, allin, sch = flux_setup(p, J, fam)
        text, tags, auto = tile_text(p, J, rng, "caption", "high quality photo, sharp focus, fine detail, natural skin texture")
        if blocked(text):
            raise ValueError(BLOCK_MSG)
        neg = (p.get("negative") or "").strip() if fam in ("krea2", "chroma") else ""
        if fam == "chroma" and not neg:
            neg = CHROMA_NEG
        if auto and fam in ("krea2", "chroma"):
            neg = (neg + ", " + ANTI_DUP).strip(", ")
        den = clamp(num(p, "rdenoise", 0.3), 0.05, 0.8)
        q = dict(family=fam, allin=allin, **f, loras=collect_loras(p, tags, J), prompt=text, negative=neg, seed=seed_of(p), w=1024, h=1024,
                 guidance=clamp(num(p, "fx_guidance", 3.5), 0.0, 20.0), steps=clamp(num(p, "fx_steps", 20, int), 1, 100),
                 cfg=clamp(num(p, "fx_cfg", 4.0), 0.0, 20.0) if fam in ("chroma", "krea2") else 1.0,
                 sampler=p.get("fx_sampler") or "euler", scheduler=sch, init_denoise=den)
        tile = clamp(num(p, "tile", 1024, int) // 16 * 16, 512, 1536)
        out = refine_tiles(big, q, tile, clamp(num(p, "overlap", 128, int), 32, tile // 2), J,
                           build=lambda n: flows.wf_flux({**q, "init": n}), mult=16)
        info = dict(kind="upscale-refine", prompt=text, negative=neg, steps=q["steps"], cfg=q["guidance"] if fam == "flux" else q["cfg"],
                    sampler=q["sampler"], scheduler=sch, seed=q["seed"], w=out.width, h=out.height, model=f["unet"],
                    loras=[[a, b] for a, b in q["loras"]], extra={"Family": fam, "Denoising strength": den, "Tile": tile})
        return [(out, info, None)]
    text, tags, auto = tile_text(p, J, rng, "tags", "highly detailed, sharp focus")
    q = sd(p, text, tags, J)
    if auto:      # 배경 조각에 눈·얼굴이 새로 생기는 것을 막는 제외 요소
        q["negative"] = (q["negative"] + ", " + ANTI_DUP).strip(", ")
    q["denoise"] = clamp(num(p, "rdenoise", 0.3), 0.05, 0.8)
    tile = clamp(num(p, "tile", 1024, int) // 8 * 8, 512, 1536)
    out = refine_tiles(big, q, tile, clamp(num(p, "overlap", 128, int), 32, tile // 2), J)
    return [(out, info_sd(q, out.size, "upscale-refine", **{"Denoising strength": q["denoise"], "Tile": tile}), None)]


def do_wf(p, J):
    g = flows.parse_graph(p.get("graph"), caps()["info"])
    g = flows.apply(g, p.get("ov") or {}, lambda data: put_input(load_img(data), J), random)
    txt = " ".join(str(v) for n in g.values() for k, v in n.get("inputs", {}).items()
                   if k in flows.TEXT_KEYS and isinstance(v, str))
    if blocked(txt):
        raise ValueError(BLOCK_MSG)
    have = caps()["nodes"]
    miss = sorted({n["class_type"] for n in g.values() if have and n["class_type"] not in have})
    if miss:
        raise RuntimeError("설치되지 않은 노드가 있어요: " + ", ".join(miss) + " ([워크플로] 탭에서 [분석]을 누르면 설치할 곳을 찾아 줘요)")
    J["msg"] = "워크플로 실행 중"
    return [(im, dict(kind="wf"), g) for im in run_wf(g, J)]
