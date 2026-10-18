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
def flux_stack(w, q):
    """FLUX 계열 모델·텍스트 인코더·VAE·LoRA·프롬프트 인코딩을 만들어 (model, positive, negative, vae) 를 돌려줘요.
    q['ref'] 가 있으면 FLUX Kontext 처럼 그 이미지를 참조 조건으로 걸고, w.ref_lat 에 참조 latent 를 남겨요."""
    if q.get("allin"):       # 텍스트 인코더·VAE 까지 들어 있는 올인원 체크포인트
        ck = w.add("CheckpointLoaderSimple", ckpt_name=q["unet"])
        unet, clip, vae = ck, ck, [ck, 2]
        clip_idx = 1
    else:
        unet = w.add("UNETLoader", unet_name=q["unet"], weight_dtype="default")
        if q["family"] == "krea2":
            clip = w.add("CLIPLoader", clip_name=q["t5"], type="krea2", device="default")
        elif q["family"] == "chroma":
            clip = w.add("CLIPLoader", clip_name=q["t5"], type="chroma", device="default")
        else:
            clip = w.add("DualCLIPLoader", clip_name1=q["clip_l"], clip_name2=q["t5"], type="flux", device="default")
        vae = [w.add("VAELoader", vae_name=q["vae"]), 0]
        clip_idx = 0
    model = [unet, 0]
    for name, wt in q["loras"]:
        model = [w.add("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=wt), 0]
    enc = w.add("CLIPTextEncode", text=q["prompt"], clip=[clip, clip_idx])
    w.ref_lat = None
    cond = [enc, 0]
    if q.get("ref"):
        li = w.add("LoadImage", image=q["ref"])
        sc = w.add("FluxKontextImageScale", image=[li, 0])
        w.ref_lat = [w.add("VAEEncode", pixels=[sc, 0], vae=vae), 0]
        cond = [w.add("ReferenceLatent", conditioning=cond, latent=w.ref_lat), 0]
    if q["family"] == "krea2":      # cfg 1(Turbo)이면 비운 네거티브, 1보다 크면 실제 네거티브
        pos = cond
        neg = [w.add("CLIPTextEncode", text=q["negative"], clip=[clip, clip_idx]), 0] if q["cfg"] > 1.0 else [w.add("ConditioningZeroOut", conditioning=[enc, 0]), 0]
    elif q["family"] == "chroma":
        pos, neg = cond, [w.add("CLIPTextEncode", text=q["negative"], clip=[clip, clip_idx]), 0]
    else:
        neg = [w.add("ConditioningZeroOut", conditioning=[enc, 0]), 0]
        pos = [w.add("FluxGuidance", conditioning=cond, guidance=q["guidance"]), 0]
    return model, pos, neg, vae


def flux_sample(w, q, model, pos, neg, lat, denoise=1.0):
    return w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"],
                 scheduler=q["scheduler"], positive=pos, negative=neg, latent_image=lat, denoise=denoise)


def wf_flux(q):
    """FLUX 계열 텍스트→이미지(+이미지→이미지).
    flux  : DualCLIP(clip_l+T5) + FluxGuidance, 네거티브는 ConditioningZeroOut, cfg 1.
    chroma: T5 단독 CLIPLoader(type=chroma) + 실제 네거티브 프롬프트, cfg 사용."""
    w = WF()
    model, pos, neg, vae = flux_stack(w, q)
    denoise = 1.0
    if q.get("init"):
        li = w.add("LoadImage", image=q["init"])
        lat, denoise = [w.add("VAEEncode", pixels=[li, 0], vae=vae), 0], q["init_denoise"]
    else:
        lat = [w.add("EmptyLatentImage" if q["family"] == "krea2" else "EmptySD3LatentImage", width=q["w"], height=q["h"], batch_size=1), 0]
    k = flux_sample(w, q, model, pos, neg, lat, denoise)
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=vae), 0])
    return w.n


def wf_flux_inpaint(q, img, msk):
    """FLUX·Krea·Chroma 로 칠한 부분만 다시 그리기 (InpaintModelConditioning + DifferentialDiffusion)."""
    w = WF()
    model, pos, neg, vae = flux_stack(w, q)
    li = w.add("LoadImage", image=img)
    lm = w.add("LoadImageMask", image=msk, channel="red")
    ic = w.add("InpaintModelConditioning", positive=pos, negative=neg, vae=vae, pixels=[li, 0], mask=[lm, 0], noise_mask=True)
    dd = w.add("DifferentialDiffusion", model=model)
    k = flux_sample(w, q, [dd, 0], [ic, 0], [ic, 1], [ic, 2], q["denoise"])
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=vae), 0])
    return w.n


def wf_flux_outpaint(q, img, pad, feather):
    w = WF()
    model, pos, neg, vae = flux_stack(w, q)
    li = w.add("LoadImage", image=img)
    pd = w.add("ImagePadForOutpaint", image=[li, 0], left=pad[0], top=pad[1], right=pad[2], bottom=pad[3], feathering=feather)
    ic = w.add("InpaintModelConditioning", positive=pos, negative=neg, vae=vae, pixels=[pd, 0], mask=[pd, 1], noise_mask=True)
    dd = w.add("DifferentialDiffusion", model=model)
    k = flux_sample(w, q, [dd, 0], [ic, 0], [ic, 1], [ic, 2], 1.0)
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=vae), 0])
    return w.n


def wf_kontext(q, img):
    """FLUX Kontext: 말로 지시해 이미지를 고쳐요. q['ref'] 는 쓰지 않고 img 를 참조 이미지로 써요."""
    w = WF()
    model, pos, neg, vae = flux_stack(w, {**q, "ref": img})
    k = flux_sample(w, q, model, pos, neg, w.ref_lat, 1.0)
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
              scheduler=q["scheduler"], positive=[pos, 0], negative=[neg, 0], latent_image=[lat, 0], denoise=q.get("denoise", 1.0))
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=[vae, 0]), 0])
    return w.n


# ───────────────────────── 영상 (Wan 2.2 TI2V 5B) ─────────────────────────
WAN_NEG = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
           "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")


def wf_video(q, start=None):
    """Wan 2.2 5B: 글→영상, start(입력 이미지 파일명)가 있으면 그 이미지에서 시작하는 이미지→영상. 결과는 SaveVideo(mp4)."""
    w = WF()
    unet = w.add("UNETLoader", unet_name=q["unet"], weight_dtype="default")
    clip = w.add("CLIPLoader", clip_name=q["te"], type="wan", device="default")
    vae = w.add("VAELoader", vae_name=q["vae"])
    model = [unet, 0]
    for name, wt in q.get("loras", []):
        model = [w.add("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=wt), 0]
    model = [w.add("ModelSamplingSD3", model=model, shift=q["shift"]), 0]
    pos = w.add("CLIPTextEncode", text=q["prompt"], clip=[clip, 0])
    neg = w.add("CLIPTextEncode", text=q["negative"], clip=[clip, 0])
    lat_in = dict(vae=[vae, 0], width=q["w"], height=q["h"], length=q["frames"], batch_size=1)
    if start:
        lat_in["start_image"] = [w.add("LoadImage", image=start), 0]
    lat = w.add("Wan22ImageToVideoLatent", **lat_in)
    k = w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"],
              scheduler=q["scheduler"], positive=[pos, 0], negative=[neg, 0], latent_image=[lat, 0], denoise=1.0)
    img = w.add("VAEDecode", samples=[k, 0], vae=[vae, 0])
    vid = w.add("CreateVideo", images=[img, 0], fps=q["fps"])
    w.add("SaveVideo", video=[vid, 0], filename_prefix="video/hub", format="auto", codec="auto")
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


def parse_graph(obj, info=None):
    """API 형식이면 그대로, 화면용(UI) 형식이면 info(/object_info)로 변환해요."""
    if isinstance(obj, (str, bytes)):
        try:
            obj = json.loads(obj)
        except ValueError:
            raise ValueError("JSON 형식이 올바르지 않아요. ComfyUI 에서 'Save (API Format)'으로 저장한 내용을 그대로 붙여 넣어 주세요.") from None
    if isinstance(obj, dict) and isinstance(obj.get("prompt"), dict) and "class_type" not in obj:
        obj = obj["prompt"]  # {"prompt": {...}} 형태의 API 요청 본문도 허용
    if isinstance(obj, dict) and "nodes" in obj and "links" in obj:
        if not info:
            raise ValueError("화면용(UI) 워크플로를 바꾸려면 이미지 엔진(ComfyUI)이 켜져 있어야 해요. 잠시 뒤 다시 시도해 주세요.")
        return ui_to_api(obj, info)
    g = {str(k): v for k, v in obj.items() if isinstance(v, dict) and "class_type" in v} if isinstance(obj, dict) else {}
    if not g:
        raise ValueError("노드를 찾지 못했어요. 'Save (API Format)'으로 저장한 JSON 인지 확인해 주세요.")
    return g


# ───────────────────────── ComfyUI 화면용(UI) 워크플로 → API 형식 변환 ─────────────────────────
_PRIM = ("INT", "FLOAT", "STRING", "BOOLEAN")
_SKIP_TYPES = {"Note", "MarkdownNote", "Group"}


def _widget_names(spec):
    """object_info 의 입력 정의에서 '화면 위젯으로 나오는 입력' 이름을 순서대로 돌려줘요 (연결용 입력은 빼요)."""
    out = []
    for sec in ("required", "optional"):
        for name, d in (spec.get("input", {}).get(sec) or {}).items():
            t = d[0] if isinstance(d, (list, tuple)) and d else d
            opts = d[1] if isinstance(d, (list, tuple)) and len(d) > 1 and isinstance(d[1], dict) else {}
            if isinstance(t, list) or t in _PRIM or opts.get("image_upload") or opts.get("video_upload") or opts.get("audio_upload"):
                extra = bool(opts.get("control_after_generate")) or name in ("seed", "noise_seed") \
                    or bool(opts.get("image_upload") or opts.get("video_upload") or opts.get("audio_upload"))
                out.append((name, extra))
    return out


def ui_to_api(ui, info):
    """화면용 워크플로(nodes/links)를 API 형식으로 바꿔요. info 는 ComfyUI 의 /object_info 응답이에요.
    Reroute·PrimitiveNode 는 값/연결을 바로 이어 주고, 끈 노드(mode 2)는 빼고, 우회 노드(mode 4)는 같은 종류의 입력으로 건너뛰어요."""
    if ui.get("definitions", {}).get("subgraphs"):
        raise ValueError("서브그래프(묶음 노드)가 들어 있는 워크플로예요. ComfyUI 에서 서브그래프를 풀거나 'Save (API Format)'으로 저장해 주세요.")
    nodes = {str(n["id"]): n for n in ui.get("nodes", []) if isinstance(n, dict) and "id" in n}
    links = {}
    for l in ui.get("links", []):
        if isinstance(l, (list, tuple)) and len(l) >= 5:
            links[l[0]] = (str(l[1]), l[2])
        elif isinstance(l, dict):
            links[l["id"]] = (str(l["origin_id"]), l["origin_slot"])
    unknown = sorted({n["type"] for n in nodes.values() if n.get("type") not in info and n.get("type") not in _SKIP_TYPES
                      and n.get("type") not in ("Reroute", "PrimitiveNode") and n.get("mode") not in (2,)})
    if unknown:
        raise ValueError("설치되지 않은 노드가 있어요: " + ", ".join(unknown) + " (ComfyUI 고급 화면의 Manager 에서 설치한 뒤 다시 시도해 주세요)")

    def resolve(ref, depth=0):
        """(노드번호, 슬롯) 이 Reroute/우회/Primitive 이면 실제 출발점이나 값으로 따라가요. 반환: ('link', id, slot) 또는 ('val', 값)."""
        nid, slot = ref
        n = nodes.get(nid)
        if n is None or depth > 40:
            return None
        t = n.get("type")
        if t == "PrimitiveNode":
            v = n.get("widgets_values") or [None]
            return ("val", v[0])
        if t == "Reroute" or n.get("mode") == 4:
            ins = [i for i in n.get("inputs", []) if i.get("link") is not None]
            if t != "Reroute":     # 우회: 출력과 같은 종류의 입력을 찾아요
                outs = n.get("outputs", [])
                want = outs[slot].get("type") if slot < len(outs) else None
                ins = [i for i in ins if i.get("type") == want] or ins
            if not ins or ins[0]["link"] not in links:
                return None
            return resolve(links[ins[0]["link"]], depth + 1)
        return ("link", nid, slot)

    g = {}
    for nid, n in nodes.items():
        t = n.get("type")
        if t in _SKIP_TYPES or t in ("Reroute", "PrimitiveNode") or n.get("mode") in (2, 4) or t not in info:
            continue
        spec = info[t]
        wn = _widget_names(spec)
        vals = list(n.get("widgets_values") or []) if not isinstance(n.get("widgets_values"), dict) else n["widgets_values"]
        inp = {}
        if isinstance(vals, dict):
            inp.update(vals)
        else:
            k = 0
            for name, extra in wn:
                if k < len(vals):
                    inp[name] = vals[k]
                k += 2 if extra else 1
        for i in n.get("inputs", []):
            lid = i.get("link")
            if lid is None or lid not in links:
                continue
            r = resolve(links[lid])
            if r is None:
                continue
            inp[i["name"]] = r[1] if r[0] == "val" else [r[1], r[2]]
            if r[0] == "val":
                inp[i["name"]] = r[1]
        g[nid] = {"class_type": t, "inputs": inp}
    for nid in list(g):      # 끊어진 연결(빠진 노드를 가리킴)은 지워요
        for k, v in list(g[nid]["inputs"].items()):
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0] not in g:
                del g[nid]["inputs"][k]
    if not g:
        raise ValueError("실행할 수 있는 노드를 찾지 못했어요.")
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
