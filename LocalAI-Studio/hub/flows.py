# -*- coding: utf-8 -*-
"""ComfyUI 그래프(API 형식) 생성기와 사용자 워크플로 분석/적용."""
import copy
import json
import random


class WF:
    def __init__(s):
        s.n, s.i = {}, 0

    def add(s, cls, **inp):
        s.i += 1
        s.n[str(s.i)] = {"class_type": cls, "inputs": inp}
        return str(s.i)


# ───────────────────────── SDXL 계열 공통 ─────────────────────────
def sd_stack(w, q):
    """체크포인트 → (VAE) → LoRA → V-Pred/CFG 재조정/PAG → CLIP skip → 프롬프트 인코딩."""
    ck = w.add("CheckpointLoaderSimple", ckpt_name=q["ckpt"])
    model, clip, vae = [ck, 0], [ck, 1], [ck, 2]
    if q.get("vae"):
        vae = [w.add("VAELoader", vae_name=q["vae"]), 0]
    for name, wt in q.get("loras", []):
        l = w.add("LoraLoader", model=model, clip=clip, lora_name=name, strength_model=wt, strength_clip=wt)
        model, clip = [l, 0], [l, 1]
    if q.get("vpred"):
        model = [w.add("ModelSamplingDiscrete", model=model, sampling="v_prediction", zsnr=True), 0]
    if q.get("rescale"):
        model = [w.add("RescaleCFG", model=model, multiplier=q["rescale"]), 0]
    if q.get("pag"):
        model = [w.add("PerturbedAttentionGuidance", model=model, scale=q["pag"]), 0]
    cs = w.add("CLIPSetLastLayer", clip=clip, stop_at_clip_layer=-q["clip_skip"])
    w.clip = [cs, 0]
    pos = w.add("CLIPTextEncode", text=q["prompt"], clip=[cs, 0])
    neg = w.add("CLIPTextEncode", text=q["negative"], clip=[cs, 0])
    return model, [pos, 0], [neg, 0], vae


def ksampler(w, q, model, pos, neg, lat, denoise=1.0, steps=None):
    return w.add("KSampler", model=model, seed=q["seed"], steps=steps or q["steps"], cfg=q["cfg"],
                 sampler_name=q["sampler"], scheduler=q["scheduler"], positive=pos, negative=neg,
                 latent_image=lat, denoise=denoise)


def wf_gen(q):
    """텍스트→이미지. 옵션: 이미지→이미지(init), ControlNet(cn), 하이레스 픽스(hires)."""
    w = WF()
    model, pos, neg, vae = sd_stack(w, q)
    cn = q.get("cn")
    if cn:
        img = [w.add("LoadImage", image=cn["image"]), 0]
        if cn.get("canny"):
            img = [w.add("Canny", image=img, low_threshold=0.4, high_threshold=0.8), 0]
        loader = w.add("ControlNetLoader", control_net_name=cn["model"])
        ap = w.add("ControlNetApplyAdvanced", positive=pos, negative=neg, control_net=[loader, 0], image=img,
                   strength=cn["strength"], start_percent=cn["start"], end_percent=cn["end"], vae=vae)
        pos, neg = [ap, 0], [ap, 1]
    denoise = 1.0
    if q.get("init"):
        li = w.add("LoadImage", image=q["init"])
        lat, denoise = [w.add("VAEEncode", pixels=[li, 0], vae=vae), 0], q["init_denoise"]
    else:
        lat = [w.add("EmptyLatentImage", width=q["w"], height=q["h"], batch_size=1), 0]
    out = [ksampler(w, q, model, pos, neg, lat, denoise), 0]
    hr = q.get("hires")
    if hr:
        up = w.add("LatentUpscaleBy", samples=out, upscale_method="bislerp", scale_by=hr["scale"])
        out = [ksampler(w, q, model, pos, neg, [up, 0], hr["denoise"], hr["steps"]), 0]
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=out, vae=vae), 0])
    return w.n


def wf_inpaint(q, img, msk):
    w = WF()
    model, pos, neg, vae = sd_stack(w, q)
    li = w.add("LoadImage", image=img)
    lm = w.add("LoadImageMask", image=msk, channel="red")
    cn = q.get("cn")
    if cn:   # 칠한 영역 주변 조각에 ControlNet 을 걸어 윤곽·포즈를 유지해요
        cim = [w.add("LoadImage", image=cn["image"]), 0]
        if cn.get("canny"):
            cim = [w.add("Canny", image=cim, low_threshold=0.4, high_threshold=0.8), 0]
        loader = w.add("ControlNetLoader", control_net_name=cn["model"])
        ap = w.add("ControlNetApplyAdvanced", positive=pos, negative=neg, control_net=[loader, 0], image=cim,
                   strength=cn["strength"], start_percent=cn["start"], end_percent=cn["end"], vae=vae)
        pos, neg = [ap, 0], [ap, 1]
    ic = w.add("InpaintModelConditioning", positive=pos, negative=neg, vae=vae,
               pixels=[li, 0], mask=[lm, 0], noise_mask=True)
    dd = w.add("DifferentialDiffusion", model=model)
    k = ksampler(w, q, [dd, 0], [ic, 0], [ic, 1], [ic, 2], q["denoise"])
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=vae), 0])
    return w.n


def wf_outpaint(q, img, pad, feather):
    """이미지 확장(아웃페인팅): 가장자리에 빈 공간을 덧붙이고 그 부분만 새로 그려요."""
    w = WF()
    model, pos, neg, vae = sd_stack(w, q)
    li = w.add("LoadImage", image=img)
    pd = w.add("ImagePadForOutpaint", image=[li, 0], left=pad[0], top=pad[1], right=pad[2], bottom=pad[3], feathering=feather)
    ic = w.add("InpaintModelConditioning", positive=pos, negative=neg, vae=vae, pixels=[pd, 0], mask=[pd, 1], noise_mask=True)
    dd = w.add("DifferentialDiffusion", model=model)
    k = ksampler(w, q, [dd, 0], [ic, 0], [ic, 1], [ic, 2], 1.0)
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=vae), 0])
    return w.n


def wf_regional(q, regions, width, height):
    """영역별 프롬프트: 화면을 나눠(x, y, w, h 는 0~1 비율) 칸마다 다른 내용을 그려요. q['prompt'] 는 전체 공통 문장."""
    w = WF()
    model, pos, neg, vae = sd_stack(w, q)
    cond = pos
    for r in regions:
        enc = w.add("CLIPTextEncode", text=r["text"], clip=w.clip)
        area = w.add("ConditioningSetAreaPercentage", conditioning=[enc, 0], width=r["w"], height=r["h"], x=r["x"], y=r["y"], strength=1.0)
        cond = [w.add("ConditioningCombine", conditioning_1=cond, conditioning_2=[area, 0]), 0]
    lat = [w.add("EmptyLatentImage", width=width, height=height, batch_size=1), 0]
    out = [ksampler(w, q, model, cond, neg, lat, 1.0), 0]
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=out, vae=vae), 0])
    return w.n


def wf_refine(q, img):
    """타일 하나를 낮은 denoise 로 다시 그려 디테일을 살립니다."""
    w = WF()
    model, pos, neg, vae = sd_stack(w, q)
    li = w.add("LoadImage", image=img)
    lat = w.add("VAEEncode", pixels=[li, 0], vae=vae)
    k = ksampler(w, q, model, pos, neg, [lat, 0], q["denoise"])
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=vae), 0])
    return w.n


# ───────────────────────── FLUX 계열 (FLUX.1 dev / Krea dev / Chroma) ─────────────────────────
def wf_flux(q):
    """FLUX 계열 텍스트→이미지(+이미지→이미지).
    flux  : DualCLIP(clip_l+T5) + FluxGuidance, 네거티브는 ConditioningZeroOut, cfg 1.
    chroma: T5 단독 CLIPLoader(type=chroma) + 실제 네거티브 프롬프트, cfg 사용."""
    w = WF()
    unet = w.add("UNETLoader", unet_name=q["unet"], weight_dtype="default")
    if q["family"] == "chroma":
        clip = w.add("CLIPLoader", clip_name=q["t5"], type="chroma", device="default")
    else:
        clip = w.add("DualCLIPLoader", clip_name1=q["clip_l"], clip_name2=q["t5"], type="flux", device="default")
    vae = [w.add("VAELoader", vae_name=q["vae"]), 0]
    model = [unet, 0]
    for name, wt in q["loras"]:
        model = [w.add("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=wt), 0]
    enc = w.add("CLIPTextEncode", text=q["prompt"], clip=[clip, 0])
    if q["family"] == "chroma":
        pos, neg = [enc, 0], [w.add("CLIPTextEncode", text=q["negative"], clip=[clip, 0]), 0]
    else:
        neg = [w.add("ConditioningZeroOut", conditioning=[enc, 0]), 0]
        pos = [w.add("FluxGuidance", conditioning=[enc, 0], guidance=q["guidance"]), 0]
    denoise = 1.0
    if q.get("init"):
        li = w.add("LoadImage", image=q["init"])
        lat, denoise = [w.add("VAEEncode", pixels=[li, 0], vae=vae), 0], q["init_denoise"]
    else:
        lat = [w.add("EmptySD3LatentImage", width=q["w"], height=q["h"], batch_size=1), 0]
    k = w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"],
              scheduler=q["scheduler"], positive=pos, negative=neg, latent_image=lat, denoise=denoise)
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=vae), 0])
    return w.n


# ───────────────────────── Qwen-Image-Edit ─────────────────────────
def wf_qwen(q, img, refs, plus):
    f, w = q["files"], WF()
    unet = w.add("UNETLoader", unet_name=f["unet"], weight_dtype="default")
    clip = w.add("CLIPLoader", clip_name=f["te"], type="qwen_image", device="default")
    vae = w.add("VAELoader", vae_name=f["vae"])
    li = w.add("LoadImage", image=img)
    model = [unet, 0]
    for name, wt in q["loras"]:
        model = [w.add("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=wt), 0]
    model = [w.add("ModelSamplingAuraFlow", model=model, shift=q["shift"]), 0]
    model = [w.add("CFGNorm", model=model, strength=1.0), 0]
    extra = {f"image{i + 2}": [w.add("LoadImage", image=r), 0] for i, r in enumerate(refs)}

    def enc(text):
        if plus:
            return w.add("TextEncodeQwenImageEditPlus", clip=[clip, 0], prompt=text, vae=[vae, 0], image1=[li, 0], **extra)
        return w.add("TextEncodeQwenImageEdit", clip=[clip, 0], prompt=text, vae=[vae, 0], image=[li, 0])

    pos, neg = enc(q["prompt"]), enc("")
    lat = w.add("VAEEncode", pixels=[li, 0], vae=[vae, 0])
    k = w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"],
              scheduler=q["scheduler"], positive=[pos, 0], negative=[neg, 0], latent_image=[lat, 0], denoise=1.0)
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=[vae, 0]), 0])
    return w.n


def wf_upscale(model, img, half):
    w = WF()
    li = w.add("LoadImage", image=img)
    um = w.add("UpscaleModelLoader", model_name=model)
    out = [w.add("ImageUpscaleWithModel", upscale_model=[um, 0], image=[li, 0]), 0]
    if half:
        out = [w.add("ImageScaleBy", image=out, upscale_method="lanczos", scale_by=0.5), 0]
    w.add("PreviewImage", images=out)
    return w.n


# ───────────────────────── 사용자 워크플로(API 형식) 분석 / 적용 ─────────────────────────
TEXT_KEYS = ("text", "prompt", "text_g", "text_l")
IMG_CLASSES = ("LoadImage", "LoadImageMask", "LoadImageOutput")
SEED_KEYS = ("seed", "noise_seed")


def parse_graph(obj):
    if isinstance(obj, (str, bytes)):
        try:
            obj = json.loads(obj)
        except ValueError:
            raise ValueError("JSON 형식이 올바르지 않아요. ComfyUI 에서 'Save (API Format)'으로 저장한 내용을 그대로 붙여 넣어 주세요.") from None
    if isinstance(obj, dict) and isinstance(obj.get("prompt"), dict) and "class_type" not in obj:
        obj = obj["prompt"]  # {"prompt": {...}} 형태의 API 요청 본문도 허용
    if isinstance(obj, dict) and "nodes" in obj and "links" in obj:
        raise ValueError("ComfyUI 화면용(UI) 워크플로예요. 설정에서 개발자 모드를 켠 뒤 'Save (API Format)'으로 저장한 파일이 필요해요.")
    g = {str(k): v for k, v in obj.items() if isinstance(v, dict) and "class_type" in v} if isinstance(obj, dict) else {}
    if not g:
        raise ValueError("노드를 찾지 못했어요. 'Save (API Format)'으로 저장한 JSON 인지 확인해 주세요.")
    return g


def _upstream_text(g, ref):
    out, queue, seen = [], [ref], set()
    while queue and len(seen) < 60:
        r = queue.pop(0)
        if not (isinstance(r, list) and len(r) == 2) or str(r[0]) in seen or str(r[0]) not in g:
            continue
        seen.add(str(r[0]))
        ins = g[str(r[0])].get("inputs", {})
        keys = [k for k in TEXT_KEYS if isinstance(ins.get(k), str)]
        if keys:
            out.append((str(r[0]), keys[0]))
            continue
        queue += [v for v in ins.values() if isinstance(v, list)]
    return out


def analyze(g, available=None):
    roles = {}
    for n in g.values():
        ins = n.get("inputs", {})
        for role, key in (("긍정", "positive"), ("부정", "negative")):
            if isinstance(ins.get(key), list):
                for nid, k in _upstream_text(g, ins[key]):
                    roles[f"{nid}.{k}"] = role
    texts, images, seeds, sizes, outputs = [], [], [], [], []
    for nid, n in sorted(g.items(), key=lambda kv: (len(kv[0]), kv[0])):
        c, ins = n["class_type"], n.get("inputs", {})
        for k in TEXT_KEYS:
            if isinstance(ins.get(k), str):
                texts.append({"key": f"{nid}.{k}", "id": nid, "class": c, "role": roles.get(f"{nid}.{k}", ""), "value": ins[k]})
        if c in IMG_CLASSES:
            images.append({"id": nid, "class": c, "value": ins.get("image", "")})
        for k in SEED_KEYS:
            if isinstance(ins.get(k), (int, float)):
                seeds.append({"key": f"{nid}.{k}", "id": nid, "class": c, "value": int(ins[k])})
        if "width" in ins and "height" in ins and isinstance(ins["width"], int) and isinstance(ins["height"], int) \
                and c.startswith("Empty"):
            sizes.append({"id": nid, "class": c, "w": ins["width"], "h": ins["height"]})
        if c in ("SaveImage", "PreviewImage") or c.startswith("Save"):
            outputs.append({"id": nid, "class": c})
    missing = sorted({n["class_type"] for n in g.values() if available and n["class_type"] not in available})
    return {"nodes": len(g), "texts": texts, "images": images, "seeds": seeds, "sizes": sizes, "outputs": outputs,
            "missing": missing}


def apply(g, ov, save_image, rng=random):
    """덮어쓸 값(ov)을 적용한 새 그래프를 돌려줍니다. save_image(dataURL)->ComfyUI input 파일명."""
    g = copy.deepcopy(g)
    for k, v in (ov.get("texts") or {}).items():
        nid, key = k.split(".", 1)
        if nid in g and key in g[nid]["inputs"]:
            g[nid]["inputs"][key] = str(v)
    if ov.get("rand"):
        for n in g.values():
            for k in SEED_KEYS:
                if isinstance(n.get("inputs", {}).get(k), (int, float)):
                    n["inputs"][k] = rng.randint(0, 2**32 - 1)
    for k, v in (ov.get("seeds") or {}).items():
        nid, key = k.split(".", 1)
        if nid in g and key in g[nid]["inputs"]:
            v = int(v)
            g[nid]["inputs"][key] = v if v >= 0 else rng.randint(0, 2**32 - 1)
    for nid, data in (ov.get("images") or {}).items():
        if nid in g and data:
            g[nid]["inputs"]["image"] = save_image(data)
    for nid, wh in (ov.get("sizes") or {}).items():
        if nid in g:
            g[nid]["inputs"]["width"], g[nid]["inputs"]["height"] = int(wh[0]), int(wh[1])
    return g
