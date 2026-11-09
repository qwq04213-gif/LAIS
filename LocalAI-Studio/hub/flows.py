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


def cn_apply(w, cn, pos, neg, vae):
    """ControlNet 한 개를 positive/negative 에 걸어요. cn: model, image, canny(전처리), union(통합 모델의 종류), strength/start/end."""
    img = [w.add("LoadImage", image=cn["image"]), 0]
    if cn.get("canny"):
        img = [w.add("Canny", image=img, low_threshold=0.4, high_threshold=0.8), 0]
    loader = [w.add("ControlNetLoader", control_net_name=cn["model"]), 0]
    if cn.get("union"):      # xinsir union 같은 '여러 종류를 한 모델로' 모델은 지도 종류를 알려 줘야 해요
        loader = [w.add("SetUnionControlNetType", control_net=loader, type=cn["union"]), 0]
    ap = w.add("ControlNetApplyAdvanced", positive=pos, negative=neg, control_net=loader, image=img,
               strength=cn["strength"], start_percent=cn["start"], end_percent=cn["end"], vae=vae)
    return [ap, 0], [ap, 1]


def wf_gen(q):
    """텍스트→이미지. 옵션: 이미지→이미지(init), ControlNet(cn), 하이레스 픽스(hires)."""
    w = WF()
    model, pos, neg, vae = sd_stack(w, q)
    cn = q.get("cn")
    if cn:
        pos, neg = cn_apply(w, cn, pos, neg, vae)
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
        pos, neg = cn_apply(w, cn, pos, neg, vae)
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


def wf_detailer(q, img, passes, fill):
    """얼굴·손 보정(ADetailer 방식): 감지 모델로 부위를 찾아 그 부분만 다시 그려요(Impact Pack 의 FaceDetailer).
    passes: [(감지 모델 이름, 그 부위 프롬프트)], fill(node, given): 노드의 나머지 입력을 /object_info 로 채워 주는 함수."""
    w = WF()
    model, pos, neg, vae = sd_stack(w, q)
    cur = [w.add("LoadImage", image=img), 0]
    for det, text in passes:
        p2 = [w.add("CLIPTextEncode", text=text, clip=w.clip), 0]
        bd = w.add("UltralyticsDetectorProvider", model_name=det)
        ins = fill("FaceDetailer", dict(image=cur, model=model, clip=w.clip, vae=vae, positive=p2, negative=neg,
                                        bbox_detector=[bd, 0], guide_size=768, max_size=1280, seed=q["seed"], steps=q["steps"], cfg=q["cfg"],
                                        sampler_name=q["sampler"], scheduler=q["scheduler"], denoise=q["denoise"],
                                        wildcard=""))
        cur = [w.add("FaceDetailer", **ins), 0]
    w.add("PreviewImage", images=cur)
    return w.n


def wf_faceswap(target, source, swap_model, restore, vis, cf, target_idx, source_idx, fill):
    """얼굴 교체(ReActor): source 사진의 얼굴을 target 사진에 입혀요."""
    w = WF()
    t = w.add("LoadImage", image=target)
    s = w.add("LoadImage", image=source)
    ins = fill("ReActorFaceSwap", dict(enabled=True, input_image=[t, 0], source_image=[s, 0], swap_model=swap_model, face_restore_model=restore,
                                       face_restore_visibility=vis, codeformer_weight=cf, input_faces_index=target_idx, source_faces_index=source_idx))
    r = w.add("ReActorFaceSwap", **ins)
    w.add("PreviewImage", images=[r, 0])
    return w.n


def wf_ipadapter(q, ref, preset, weight_type, weight, width, height, fill):
    """참고 이미지(IPAdapter plus): 스타일 또는 얼굴을 따라 새로 그려요."""
    w = WF()
    model, pos, neg, vae = sd_stack(w, q)
    li = w.add("LoadImage", image=ref)
    ld = w.add("IPAdapterUnifiedLoader", model=model, preset=preset)
    ins = fill("IPAdapter", dict(model=[ld, 0], ipadapter=[ld, 1], image=[li, 0], weight=weight, weight_type=weight_type))
    ip = w.add("IPAdapter", **ins)
    lat = [w.add("EmptyLatentImage", width=width, height=height, batch_size=1), 0]
    k = ksampler(w, q, [ip, 0], pos, neg, lat, 1.0)
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
        if q.get("ckpt_only"):      # checkpoints 폴더의 '모델만' 파일: 체크포인트 로더로 모델만 쓰고 인코더·VAE 는 따로
            unet = w.add("CheckpointLoaderSimple", ckpt_name=q["unet"])
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
    w.clip = [clip, clip_idx]
    enc = w.add("CLIPTextEncode", text=q["prompt"], clip=[clip, clip_idx])
    w.ref_lat = None
    cond = [enc, 0]
    if q.get("redux"):      # FLUX.1 Redux: 참고 이미지의 분위기·구성을 조건으로 더해요 (CLIP Vision + 스타일 모델)
        r = q["redux"]
        cv = w.add("CLIPVisionLoader", clip_name=r["clip_vision"])
        st = w.add("StyleModelLoader", style_model_name=r["style"])
        li = w.add("LoadImage", image=r["image"])
        ce = w.add("CLIPVisionEncode", clip_vision=[cv, 0], image=[li, 0], crop="center")
        cond = [w.add("StyleModelApply", conditioning=cond, style_model=[st, 0], clip_vision_output=[ce, 0], **r.get("extra", {})), 0]
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


def flux_cond(w, q, text):
    """flux_stack 을 만든 뒤, 다른 문장으로 (positive, negative) 를 하나 더 만들어요(부위마다 다른 문장이 필요할 때)."""
    enc = w.add("CLIPTextEncode", text=text, clip=w.clip)
    if q["family"] == "krea2":
        neg = [w.add("CLIPTextEncode", text=q["negative"], clip=w.clip), 0] if q["cfg"] > 1.0 else [w.add("ConditioningZeroOut", conditioning=[enc, 0]), 0]
        return [enc, 0], neg
    if q["family"] == "chroma":
        return [enc, 0], [w.add("CLIPTextEncode", text=q["negative"], clip=w.clip), 0]
    return [w.add("FluxGuidance", conditioning=[enc, 0], guidance=q["guidance"]), 0], [w.add("ConditioningZeroOut", conditioning=[enc, 0]), 0]


def wf_detailer_flux(q, img, passes, fill):
    """얼굴·손 보정을 FLUX·Krea 2·Chroma 모델로. FaceDetailer 는 모델·조건만 받으면 되므로 SDXL 과 같은 방식으로 이어 붙여요."""
    w = WF()
    model, _, _, vae = flux_stack(w, q)
    cur = [w.add("LoadImage", image=img), 0]
    for det, text in passes:
        pos, neg = flux_cond(w, q, text)
        bd = w.add("UltralyticsDetectorProvider", model_name=det)
        ins = fill("FaceDetailer", dict(image=cur, model=model, clip=w.clip, vae=vae, positive=pos, negative=neg,
                                        bbox_detector=[bd, 0], guide_size=768, max_size=1280, seed=q["seed"], steps=q["steps"], cfg=q["cfg"],
                                        sampler_name=q["sampler"], scheduler=q["scheduler"], denoise=q["denoise"], wildcard=""))
        cur = [w.add("FaceDetailer", **ins), 0]
    w.add("PreviewImage", images=cur)
    return w.n


def wf_krea2_ref(q, ref, lora, strength, method_key):
    """Krea 2 스타일 참조: 공식 'Image Style Reference' 템플릿과 같은 구성이에요.
    UNET → 스타일 참조 LoRA → ModelSamplingFlux, 참고 이미지는 TextEncodeQwenImageEditPlus 로 조건에 넣고 FluxKontextMultiReferenceLatentMethod 로 묶어요."""
    f, w = q, WF()
    unet = w.add("UNETLoader", unet_name=f["unet"], weight_dtype="default")
    clip = w.add("CLIPLoader", clip_name=f["t5"], type="krea2", device="default")
    vae = w.add("VAELoader", vae_name=f["vae"])
    model = [unet, 0]
    for name, wt in q["loras"]:
        model = [w.add("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=wt), 0]
    model = [w.add("LoraLoaderModelOnly", model=model, lora_name=lora, strength_model=strength), 0]
    model = [w.add("ModelSamplingFlux", model=model, max_shift=1.15, base_shift=0.5, width=q["w"], height=q["h"]), 0]
    li = w.add("LoadImage", image=ref)
    enc = w.add("TextEncodeQwenImageEditPlus", clip=[clip, 0], prompt=q["prompt"], vae=[vae, 0], image1=[li, 0])
    pos = [w.add("FluxKontextMultiReferenceLatentMethod", conditioning=[enc, 0], **{method_key: "index_timestep_zero"}), 0]
    neg = [w.add("ConditioningZeroOut", conditioning=pos), 0]
    lat = [w.add("EmptyLatentImage", width=q["w"], height=q["h"], batch_size=1), 0]
    k = flux_sample(w, q, model, pos, neg, lat, 1.0)
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=[vae, 0]), 0])
    return w.n


def wf_flux(q):
    """FLUX 계열 텍스트→이미지(+이미지→이미지).
    flux  : DualCLIP(clip_l+T5) + FluxGuidance, 네거티브는 ConditioningZeroOut, cfg 1.
    chroma: T5 단독 CLIPLoader(type=chroma) + 실제 네거티브 프롬프트, cfg 사용."""
    w = WF()
    model, pos, neg, vae = flux_stack(w, q)
    if q.get("cn"):      # FLUX.1 dev 계열 ControlNet (Union Pro 2.0 등): positive/negative 에 지도를 걸어요
        pos, neg = cn_apply(w, q["cn"], pos, neg, vae)
    denoise = 1.0
    if q.get("init"):
        li = w.add("LoadImage", image=q["init"])
        lat, denoise = [w.add("VAEEncode", pixels=[li, 0], vae=vae), 0], q["init_denoise"]
    else:
        lat = [w.add("EmptyLatentImage" if q["family"] == "krea2" else "EmptySD3LatentImage", width=q["w"], height=q["h"], batch_size=1), 0]
    base_model = model
    if q.get("k2c"):      # Krea 2 컨트롤 LoRA(깊이·포즈·캐니 등): 확장 노드 Krea2Control* 3개
        c = q["k2c"]
        img = [w.add("LoadImage", image=c["image"]), 0]
        if c.get("canny"):
            img = [w.add("Canny", image=img, low_threshold=0.4, high_threshold=0.8), 0]
        model = [w.add("Krea2ControlLoRALoader", model=model, lora_name=c["lora"], strength=c["strength"]), 0]
        enc = w.add("Krea2ControlImageEncode", control_image=img, vae=vae, resize="match_latent_size", upscale_method="lanczos", crop="center",
                    channel_mode="grayscale" if c.get("depth") else "rgb", normalize="per_image_minmax" if c.get("depth") else "none",
                    invert=False, batch_mode="independent_images", latent=lat)
        model = [w.add("Krea2ControlApply", model=model, control_latent=[enc, 0]), 0]
    k = flux_sample(w, q, model, pos, neg, lat, denoise)
    hr = q.get("hires")
    if hr:      # 하이레스 픽스: 그림으로 풀어 키운 뒤(16의 배수) 다시 넣어 한 번 더 그려요. Krea 2 는 잠재 형식이 달라 그림 단계에서 키우는 게 안전해요
        img = [w.add("VAEDecode", samples=[k, 0], vae=vae), 0]
        if hr.get("model"):
            img = [w.add("ImageUpscaleWithModel", upscale_model=[w.add("UpscaleModelLoader", model_name=hr["model"]), 0], image=img), 0]
        img = [w.add("ImageScale", image=img, upscale_method="lanczos", width=hr["w"], height=hr["h"], crop="disabled"), 0]
        lat2 = [w.add("VAEEncode", pixels=img, vae=vae), 0]
        k = w.add("KSampler", model=base_model, seed=q["seed"], steps=hr["steps"], cfg=q["cfg"], sampler_name=q["sampler"],
                  scheduler=q["scheduler"], positive=pos, negative=neg, latent_image=lat2, denoise=hr["denoise"])
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


# ───────────────────────── Qwen-Image 2.1 (생성·편집 하나로) ─────────────────────────
def wf_qwen21(q, imgs=(), size=None, key=None):
    """Qwen-Image 2.1: UNET(+LoRA·Lightning) + Qwen3-VL 8B(CLIPLoader type=qwen_image) + 2.1 VAE.
    TextEncodeQwenImage21 이 프롬프트·부정 프롬프트·참고 사진(최대 16장)을 한 번에 조건으로 만들어요.
    imgs 가 있으면 편집(잠재 = 첫 사진 크기, denoise<1 이면 첫 사진을 인코딩해 일부만 다시 그리기), 없으면 size(w, h) 로 새로 그려요."""
    f, w = q["files"], WF()
    key = key or (lambda i: f"images.image_{i}")
    unet = w.add("UNETLoader", unet_name=f["unet"], weight_dtype="default")
    clip = w.add("CLIPLoader", clip_name=f["te"], type="qwen_image", device="default")
    vae = w.add("VAELoader", vae_name=f["vae"])
    model = [unet, 0]
    for name, wt in q["loras"]:
        model = [w.add("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=wt), 0]
    lis = [w.add("LoadImage", image=x) for x in imgs]
    enc = w.add("TextEncodeQwenImage21", clip=[clip, 0], prompt=q["prompt"], negative_prompt=q.get("negative") or "", vae=[vae, 0],
                resolution=int(q.get("resolution", 1024)), **{key(i + 1): [li, 0] for i, li in enumerate(lis)})
    den = float(q.get("denoise", 1.0))
    if not lis:
        lat = [w.add("EmptySD3LatentImage", width=size[0], height=size[1], batch_size=1), 0]
    elif den < 1.0:
        lat = [w.add("VAEEncode", pixels=[lis[0], 0], vae=[vae, 0]), 0]
    else:
        lat = [enc, 2]
    k = w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"],
              scheduler=q["scheduler"], positive=[enc, 0], negative=[enc, 1], latent_image=lat, denoise=den)
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=[vae, 0]), 0])
    return w.n


# ───────────────────────── MOSS-Image (배치 지정·긴 글자) ─────────────────────────
def wf_moss(q):
    """MOSS-Image 5B: UNET + Qwen3.5-9B(CLIPLoader, type=q['ctype']) + FLUX.2 VAE. 프롬프트는 문장·태그·배치 JSON 모두 돼요."""
    w = WF()
    model = [w.add("UNETLoader", unet_name=q["unet"], weight_dtype="default"), 0]
    for name, wt in q.get("loras", []):
        model = [w.add("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=wt), 0]
    clip = [w.add("CLIPLoader", clip_name=q["te"], type=q["ctype"], device="default"), 0]
    vae = [w.add("VAELoader", vae_name=q["vae"]), 0]
    pos = [w.add("CLIPTextEncode", text=q["prompt"], clip=clip), 0]
    neg = [w.add("CLIPTextEncode", text=q["negative"], clip=clip), 0]
    lat = [w.add(q.get("latent") or "EmptySD3LatentImage", width=q["w"], height=q["h"], batch_size=1), 0]
    k = w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"],
              scheduler=q["scheduler"], positive=pos, negative=neg, latent_image=lat, denoise=1.0)
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=vae), 0])
    return w.n


# ───────────────────────── 영상 (Wan 2.2 TI2V 5B) ─────────────────────────
WAN_NEG = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
           "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")


# ───────────────────────── SD3.5 ─────────────────────────
def wf_other(q):
    """SD3.5 텍스트→이미지. q: family, ckpt, te(dict, 비면 체크포인트 내장), vae, loras, prompt, negative, seed, w, h, steps, cfg, sampler, scheduler."""
    w = WF()
    te = q.get("te") or {}
    ck = w.add("CheckpointLoaderSimple", ckpt_name=q["ckpt"])
    model, vae = [ck, 0], [ck, 2]
    if te:
        clip_ref = [w.add("TripleCLIPLoader", clip_name1=te["clip_l"], clip_name2=te["clip_g"], clip_name3=te["t5"]), 0]
    else:
        clip_ref = [ck, 1]
    if q.get("vae"):
        vae = [w.add("VAELoader", vae_name=q["vae"]), 0]
    for name, wt in q.get("loras", []):
        model = [w.add("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=wt), 0]
    pos = [w.add("CLIPTextEncode", text=q["prompt"], clip=clip_ref), 0]
    neg = [w.add("CLIPTextEncode", text=q["negative"], clip=clip_ref), 0]
    lat = [w.add("EmptySD3LatentImage", width=q["w"], height=q["h"], batch_size=1), 0]
    k = w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"],
              scheduler=q["scheduler"], positive=pos, negative=neg, latent_image=lat, denoise=1.0)
    w.add("PreviewImage", images=[w.add("VAEDecode", samples=[k, 0], vae=vae), 0])
    return w.n


def wf_music(q):
    """ACE-Step 1.5 올인원 체크포인트로 음악 만들기: 글(태그·가사) → 소리 잠재 → 샘플링 → 소리로 풀기 → 저장.
    q: ckpt, tags, lyrics, seed, seconds, bpm, timesig, language, keyscale, steps, cfg, sampler, scheduler, fmt(mp3/flac), codes"""
    w = WF()
    ck = w.add("CheckpointLoaderSimple", ckpt_name=q["ckpt"])
    pos = w.add("TextEncodeAceStepAudio1.5", clip=[ck, 1], tags=q["tags"], lyrics=q["lyrics"], seed=q["seed"], bpm=q["bpm"], duration=q["seconds"],
                timesignature=q["timesig"], language=q["language"], keyscale=q["keyscale"], generate_audio_codes=q["codes"], cfg_scale=2.0,
                temperature=0.85, top_p=0.9, top_k=0, min_p=0.0)
    neg = w.add("ConditioningZeroOut", conditioning=[pos, 0])
    lat = w.add("EmptyAceStep1.5LatentAudio", seconds=q["seconds"], batch_size=1)
    k = w.add("KSampler", model=[ck, 0], seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"], scheduler=q["scheduler"],
              positive=[pos, 0], negative=[neg, 0], latent_image=[lat, 0], denoise=1.0)
    dec = w.add("VAEDecodeAudio", samples=[k, 0], vae=[ck, 2])
    fmt = {"format": "flac"} if q.get("fmt") == "flac" else {"format": "mp3", "format.quality": "V0"}
    w.add("SaveAudioAdvanced", audio=[dec, 0], filename_prefix="audio/hub", **fmt)
    return w.n


def wf_sfx(q):
    """Stable Audio Open 1.0: 체크포인트(모델·VAE) + T5-base 인코더 → 효과음. q: ckpt, te, prompt, negative, seed, seconds, steps, cfg, sampler, scheduler, fmt"""
    w = WF()
    ck = w.add("CheckpointLoaderSimple", ckpt_name=q["ckpt"])
    clip = w.add("CLIPLoader", clip_name=q["te"], type="stable_audio", device="default")
    pos = w.add("CLIPTextEncode", text=q["prompt"], clip=[clip, 0])
    neg = w.add("CLIPTextEncode", text=q["negative"], clip=[clip, 0])
    cond = w.add("ConditioningStableAudio", positive=[pos, 0], negative=[neg, 0], seconds_start=0.0, seconds_total=q["seconds"])
    lat = w.add("EmptyLatentAudio", seconds=q["seconds"], batch_size=1)
    k = w.add("KSampler", model=[ck, 0], seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"], scheduler=q["scheduler"],
              positive=[cond, 0], negative=[cond, 1], latent_image=[lat, 0], denoise=1.0)
    dec = w.add("VAEDecodeAudio", samples=[k, 0], vae=[ck, 2])
    fmt = {"format": "flac"} if q.get("fmt") == "flac" else {"format": "mp3", "format.quality": "V0"}
    w.add("SaveAudioAdvanced", audio=[dec, 0], filename_prefix="audio/hub", **fmt)
    return w.n


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


def _save_video(w, img, fps, audio=None):
    vin = dict(images=img, fps=fps)
    if audio:
        vin["audio"] = audio
    vid = w.add("CreateVideo", **vin)
    w.add("SaveVideo", video=[vid, 0], filename_prefix="video/hub", format="auto", codec="auto")


def wf_ltx(q, start=None):
    """LTX-Video(빠른 영상): 체크포인트 + T5(ltxv) → 글→영상 또는 이미지→영상. q: ckpt, te, prompt, negative, seed, w, h, frames, fps, steps, cfg"""
    w = WF()
    ck = w.add("CheckpointLoaderSimple", ckpt_name=q["ckpt"])
    clip = w.add("CLIPLoader", clip_name=q["te"], type="ltxv", device="default")
    pos = [w.add("CLIPTextEncode", text=q["prompt"], clip=[clip, 0]), 0]
    neg = [w.add("CLIPTextEncode", text=q["negative"], clip=[clip, 0]), 0]
    if start:
        im = w.add("LoadImage", image=start)
        i2v = w.add("LTXVImgToVideo", positive=pos, negative=neg, vae=[ck, 2], image=[im, 0], width=q["w"], height=q["h"],
                    length=q["frames"], batch_size=1, strength=1.0)
        pos, neg, lat = [i2v, 0], [i2v, 1], [i2v, 2]
    else:
        lat = [w.add("EmptyLTXVLatentVideo", width=q["w"], height=q["h"], length=q["frames"], batch_size=1), 0]
    cond = w.add("LTXVConditioning", positive=pos, negative=neg, frame_rate=float(q["fps"]))
    sig = w.add("LTXVScheduler", steps=q["steps"], max_shift=2.05, base_shift=0.95, stretch=True, terminal=0.1, latent=lat)
    smp = w.add("KSamplerSelect", sampler_name="euler")
    k = w.add("SamplerCustom", model=[ck, 0], add_noise=True, noise_seed=q["seed"], cfg=q["cfg"], positive=[cond, 0], negative=[cond, 1],
              sampler=[smp, 0], sigmas=[sig, 0], latent_image=lat)
    _save_video(w, [w.add("VAEDecode", samples=[k, 0], vae=[ck, 2]), 0], q["fps"])
    return w.n


def _wan21_base(w, q):
    unet = w.add("UNETLoader", unet_name=q["unet"], weight_dtype="default")
    clip = w.add("CLIPLoader", clip_name=q["te"], type="wan", device="default")
    vae = w.add("VAELoader", vae_name=q["vae"])
    model = [w.add("ModelSamplingSD3", model=[unet, 0], shift=q.get("shift", 8.0)), 0]
    pos = [w.add("CLIPTextEncode", text=q["prompt"], clip=[clip, 0]), 0]
    neg = [w.add("CLIPTextEncode", text=q["negative"], clip=[clip, 0]), 0]
    return model, [vae, 0], pos, neg


def wf_vace(q, ref):
    """Wan VACE: 참고 이미지(사람·사물·스타일)를 유지하며 글대로 영상. ref = 입력 이미지 파일명."""
    w = WF()
    model, vae, pos, neg = _wan21_base(w, q)
    li = w.add("LoadImage", image=ref)
    v = w.add("WanVaceToVideo", positive=pos, negative=neg, vae=vae, width=q["w"], height=q["h"], length=q["frames"], batch_size=1,
              strength=q.get("strength", 1.0), reference_image=[li, 0])
    k = w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"], scheduler=q["scheduler"],
              positive=[v, 0], negative=[v, 1], latent_image=[v, 2], denoise=1.0)
    tr = w.add("TrimVideoLatent", samples=[k, 0], trim_amount=[v, 3])      # 참고 이미지 몫으로 붙은 앞 프레임을 잘라요
    _save_video(w, [w.add("VAEDecode", samples=[tr, 0], vae=vae), 0], q["fps"])
    return w.n


def wf_vace_extend(q, control, mask):
    """Wan VACE 로 영상 뒤 이어 그리기: control = 앞은 원본 마지막 장면·뒤는 회색인 영상, mask = 그대로 둘 곳 검정·새로 그릴 곳 흰색."""
    w = WF()
    model, vae, pos, neg = _wan21_base(w, q)
    cv = w.add("GetVideoComponents", video=[w.add("LoadVideo", file=control), 0])
    mv = w.add("GetVideoComponents", video=[w.add("LoadVideo", file=mask), 0])
    mk = w.add("ThresholdMask", mask=[w.add("ImageToMask", image=[mv, 0], channel="red"), 0], value=0.5)
    v = w.add("WanVaceToVideo", positive=pos, negative=neg, vae=vae, width=q["w"], height=q["h"], length=q["frames"], batch_size=1,
              strength=1.0, control_video=[cv, 0], control_masks=[mk, 0])
    k = w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"], scheduler=q["scheduler"],
              positive=[v, 0], negative=[v, 1], latent_image=[v, 2], denoise=1.0)
    tr = w.add("TrimVideoLatent", samples=[k, 0], trim_amount=[v, 3])
    _save_video(w, [w.add("VAEDecode", samples=[tr, 0], vae=vae), 0], q["fps"])
    return w.n


def wf_s2v(q, ref, audio):
    """Wan 2.2 S2V: 사진 한 장 + 목소리(소리 파일) → 말하는 영상(입 모양 맞춤). audio = 입력 폴더의 소리 파일 이름."""
    w = WF()
    model, vae, pos, neg = _wan21_base(w, q)
    if q.get("lora"):      # 빠른 모드: 4단계 가속 LoRA
        model = [w.add("LoraLoaderModelOnly", model=model, lora_name=q["lora"], strength_model=1.0), 0]
    au = w.add("LoadAudio", audio=audio)
    enc = w.add("AudioEncoderLoader", audio_encoder_name=q["audio_encoder"])
    ao = w.add("AudioEncoderEncode", audio_encoder=[enc, 0], audio=[au, 0])
    li = w.add("LoadImage", image=ref)
    v = w.add("WanSoundImageToVideo", positive=pos, negative=neg, vae=vae, width=q["w"], height=q["h"], length=q["frames"], batch_size=1,
              audio_encoder_output=[ao, 0], ref_image=[li, 0])
    k = w.add("KSampler", model=model, seed=q["seed"], steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"], scheduler=q["scheduler"],
              positive=[v, 0], negative=[v, 1], latent_image=[v, 2], denoise=1.0)
    acc = [k, 0]
    for i in range(1, q.get("chunks", 1)):      # 긴 목소리: 앞부분 영상에 이어서 약 5초씩 더 그리고 시간축으로 붙여요
        e = w.add("WanSoundImageToVideoExtend", positive=pos, negative=neg, vae=vae, length=q["frames"], video_latent=acc,
                  audio_encoder_output=[ao, 0], ref_image=[li, 0])
        ke = w.add("KSampler", model=model, seed=q["seed"] + i, steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"], scheduler=q["scheduler"],
                   positive=[e, 0], negative=[e, 1], latent_image=[e, 2], denoise=1.0)
        acc = [w.add("LatentConcat", samples1=acc, samples2=[ke, 0], dim="t"), 0]
    _save_video(w, [w.add("VAEDecode", samples=acc, vae=vae), 0], q["fps"], audio=[au, 0])
    return w.n


def wf_trellis(q):
    """사진 → 게임용 3D(GLB). TRELLIS.2(사진 한 장) 또는 Pixal3D 멀티뷰(앞·왼쪽·뒤·오른쪽).
    ComfyUI 공식 예시(3d_pixal3d_trellis2_image_to_model)와 같은 설정이에요:
    구조(희소 복셀, shift 5) → 모양 512(20단계) → 1024~1536 으로 한 번 더 → 재질(PBR) →
    닫힌 몸체로 다시 짜기(solid) → 면 줄이기 → UV 펴기 → 색·금속·거칠기·노멀·AO 굽기 → 텍스처 입힌 GLB.
    구조·모양 단계는 원본처럼 가이드(cfg 7.5)를 앞쪽 단계에만 걸고(CFGOverride) 세기를 눌러 줘요(RescaleCFG) —
    빠지면 형체가 뭉개져요.
    q: files{model, dino, svae, tvae}, views{front[, left, back, right]}(LoadImage 이름, 배경 지운 RGBA — framed 면 이미 맞춘 검은 배경 정사각형), multiview, framed, seed,
       steps(ss, shape, tex), cfg(ss, shape, tex), res(512·1024·1536), remesh(0=안 함, 다시 짜기 해상도), faces, tex"""
    w, f = WF(), q["files"]
    model = [w.add("UNETLoader", unet_name=f["model"], weight_dtype="default"), 0]
    cv = [w.add("CLIPVisionLoader", clip_name=f["dino"]), 0]
    sv = [w.add("VAELoader", vae_name=f["svae"]), 0]
    tv = [w.add("VAELoader", vae_name=f["tvae"]), 0]
    # 원본 TRELLIS.2 의 guidance_interval·guidance_rescale·rescale_t 와 같게
    co = q.get("cfg_override", True)                  # 예전 ComfyUI 에는 CFGOverride 가 없어요(그때는 빼고 만들어요)
    m_ss = [w.add("CFGOverride", model=model, cfg=1.0, start_percent=0.667, end_percent=1.0), 0] if co else model
    m_ss = [w.add("RescaleCFG", model=m_ss, multiplier=0.7), 0]
    m_ss = [w.add("ModelSamplingSD3", model=m_ss, shift=5.0), 0]
    m_sh = [w.add("CFGOverride", model=model, cfg=1.0, start_percent=0.769, end_percent=1.0), 0] if co else model
    m_sh = [w.add("RescaleCFG", model=m_sh, multiplier=0.5), 0]
    pad = 1.1 if q.get("multiview") else 1.0         # 노드 설명: TRELLIS.2 는 1.0, Pixal3D 는 1.1

    def prep(name):                                   # 배경을 지운 사진 → 물체만 가운데로 잘라 정사각형(검은 배경)
        li = w.add("LoadImage", image=name)
        if q.get("framed"):                           # 허브가 이미 같은 배율로 맞춘 정사각형(멀티뷰)
            return [li, 0]
        m = w.add("InvertMask", mask=[li, 1])         # LoadImage 마스크는 투명한 곳이 1 이라 뒤집어요
        return [w.add("ImageCropToMask", images=[li, 0], masks=[m, 0], width=1024, height=1024, pad_factor=pad, grow_mask=0,
                      background="#000000"), 0]
    v = q["views"]
    if q.get("multiview"):
        cond = w.add("Pixal3DMultiViewConditioning", clip_vision_model=cv, fov=20.0, **{k: prep(n) for k, n in v.items() if n})
    else:
        cond = w.add("Trellis2Conditioning", clip_vision_model=cv, image=prep(v["front"]))
    pos, neg = [cond, 0], [cond, 1]
    st, cf = q["steps"], q["cfg"]

    def ks(m_, p_, n_, lat, steps, cfg, i, sch="normal"):
        return [w.add("KSampler", model=m_, seed=q["seed"] + i, steps=steps, cfg=cfg, sampler_name="euler", scheduler=sch,
                      positive=p_, negative=n_, latent_image=lat, denoise=1.0), 0]
    ss = ks(m_ss, pos, neg, [w.add("EmptyTrellis2LatentStructure", batch_size=1), 0], st[0], cf[0], 0)
    vox = [w.add("VaeDecodeStructureTrellis2", samples=ss, vae=sv, resolution="32"), 0]
    sh = w.add("Trellis2ShapeStage", positive=pos, negative=neg, voxel=vox)
    shape = ks(m_sh, [sh, 0], [sh, 1], [sh, 2], st[1], cf[1], 1)
    tpos, tneg = [sh, 0], [sh, 1]
    if int(q.get("res", 1024)) > 512:
        up = w.add("Trellis2UpsampleStage", positive=[sh, 0], negative=[sh, 1], shape_latent=shape, vae=sv, target_resolution=int(q["res"]))
        shape = ks(m_sh, [up, 0], [up, 1], [up, 2], st[3] if len(st) > 3 else 12, cf[1], 2, "simple")
        tpos, tneg = [up, 0], [up, 1]
    dec = w.add("VaeDecodeShapeTrellis", samples=shape, vae=sv)
    dense = [dec, 0]
    tx = w.add("Trellis2TextureStage", positive=tpos, negative=tneg, shape_latent=shape)
    tex = ks(model, [tx, 0], [tx, 1], [tx, 2], st[2], cf[2], 3)
    col = [w.add("VaeDecodeTextureTrellis", samples=tex, vae=tv, shape_subdivides=[dec, 1]), 0]
    hi = dense
    if q.get("remesh"):                               # 닫힌 몸체로 다시 짜기(udf 는 안팎 두 겹 껍질이 생겨요)
        hi = [w.add("RemeshMesh", mesh=dense, resolution=int(q["remesh"]), sign_mode="solid", band=1.0, project_back=0.0, fix_poles=False,
                    smooth_iters=20, drop_small_components=0.01, precluster_max_verts=20000000,
                    **{"sign_mode.fill": 20.0, "sign_mode.qef": False}), 0]
        # 예전 ComfyUI(선택지에 solid 가 없음)용 대신 값 — udf 는 안팎 두 겹이 생겨서 안쪽 껍질을 지워요(hub 의 wf_fit 이 골라요)
        g = w.n[hi[0]]
        g["_alt"] = {"sign_mode": [("udf", {"sign_mode.qef": False, "sign_mode.drop_inverted_components": True,
                                            "sign_mode.drop_enclosed_components": False})]}
    low = [w.add("DecimateMesh", mesh=hi, target_face_count=int(q["faces"]), placement_mode="midpoint"), 0]
    low = [w.add("MeshSmoothNormals", mesh=low, crease_angle=180.0), 0]
    low = [w.add("UnwrapMesh", mesh=low, segmenter="pec", resolution=int(q["tex"]), padding=1, weld_distance=0.0002), 0]
    bt = w.add("BakeTextureFromVoxel", mesh=low, voxel_colors=col, texture_size=int(q["tex"]), reference_mesh=dense)
    nm = w.add("BakeNormalMapFromMesh", low_poly=low, high_poly=hi, resolution=int(q["tex"]), cage_distance=0.05, ignore_backfaces=True)
    ao = w.add("BakeAmbientOcclusion", low_poly=low, high_poly=hi, resolution=min(int(q["tex"]), 2048), samples=64, max_distance=0.71,
               strength=1.0, bias=0.01)
    fin = w.add("ApplyTextureToMesh", mesh=low, base_color=[bt, 0], metallic=[bt, 1], roughness=[bt, 2], occlusion=[ao, 0], normal_map=[nm, 0])
    fin = w.add("MeshSmoothNormals", mesh=[fin, 0], crease_angle=180.0)
    w.add("SaveGLB", mesh=[fin, 0], filename_prefix="3d/hub3d")
    return w.n


def wf_vpost(op, q):
    """만든 영상 다듬기: 영상을 불러와 프레임으로 풀고(GetVideoComponents) → 보간(RIFE)·업스케일·WebP 저장.
    op: interp(프레임 2배) / upscale(업스케일 모델) / webp(움직이는 WebP)"""
    w = WF()
    vid = w.add("LoadVideo", file=q["file"])
    comp = w.add("GetVideoComponents", video=[vid, 0])
    img, fps = [comp, 0], [comp, 2]
    if op == "interp":
        img = [w.add("RIFE VFI", ckpt_name=q.get("ckpt") or "rife47.pth", frames=img, clear_cache_after_n_frames=10, multiplier=2,
                     fast_mode=True, ensemble=True, scale_factor=1.0), 0]
        fps = q["fps"] * 2
    elif op == "upscale":
        m = w.add("UpscaleModelLoader", model_name=q["model"])
        img = [w.add("ImageUpscaleWithModel", upscale_model=[m, 0], image=img), 0]
    if op == "webp":
        w.add("SaveAnimatedWEBP", images=img, filename_prefix="video/hub", fps=fps, lossless=False, quality=88, method="default")
    else:
        out = w.add("CreateVideo", images=img, fps=fps)
        w.add("SaveVideo", video=[out, 0], filename_prefix="video/hub", format="auto", codec="auto")
    return w.n


def wf_vrestore(q):
    """영상 복원 조각 하나: 불러와 프레임으로 풀고 → (업스케일 모델 → 목표 크기로 맞추기) → (RIFE 로 프레임 2배) → 소리 없이 저장."""
    w = WF()
    vid = w.add("LoadVideo", file=q["file"])
    comp = w.add("GetVideoComponents", video=[vid, 0])
    img, fps = [comp, 0], q["fps"]
    if q.get("model"):
        m = w.add("UpscaleModelLoader", model_name=q["model"])
        img = [w.add("ImageUpscaleWithModel", upscale_model=[m, 0], image=img), 0]
        img = [w.add("ImageScale", image=img, upscale_method="lanczos", width=q["w"], height=q["h"], crop="disabled"), 0]
    if q.get("interp"):
        img = [w.add("RIFE VFI", ckpt_name=q.get("ckpt") or "rife47.pth", frames=img, clear_cache_after_n_frames=10, multiplier=2,
                     fast_mode=True, ensemble=True, scale_factor=1.0), 0]
        fps = fps * 2
    out = w.add("CreateVideo", images=img, fps=fps)
    w.add("SaveVideo", video=[out, 0], filename_prefix="video/restore", format="auto", codec="auto")
    return w.n


def wf_video14(q, start=None):
    """Wan 2.2 14B: 고노이즈 모델이 앞 단계(큰 구도·움직임)를, 저노이즈 모델이 뒷 단계(디테일)를 맡는 2단계 샘플링.
    start 가 있으면 이미지→영상(WanImageToVideo), 없으면 글→영상(EmptyHunyuanLatentVideo)."""
    w = WF()
    clip = w.add("CLIPLoader", clip_name=q["te"], type="wan", device="default")
    vae = w.add("VAELoader", vae_name=q["vae"])
    models = []
    for key, lkey in (("high", "lora_high"), ("low", "lora_low")):
        m = [w.add("UNETLoader", unet_name=q[key], weight_dtype="default"), 0]
        if q.get(lkey):      # 4단계 가속(LightX2V) LoRA
            m = [w.add("LoraLoaderModelOnly", model=m, lora_name=q[lkey], strength_model=1.0), 0]
        models.append([w.add("ModelSamplingSD3", model=m, shift=q["shift"]), 0])
    pos = [w.add("CLIPTextEncode", text=q["prompt"], clip=[clip, 0]), 0]
    neg = [w.add("CLIPTextEncode", text=q["negative"], clip=[clip, 0]), 0]
    if start:
        iv = w.add("WanImageToVideo", positive=pos, negative=neg, vae=[vae, 0], width=q["w"], height=q["h"], length=q["frames"],
                   batch_size=1, start_image=[w.add("LoadImage", image=start), 0])
        pos, neg, lat = [iv, 0], [iv, 1], [iv, 2]
    else:
        lat = [w.add("EmptyHunyuanLatentVideo", width=q["w"], height=q["h"], length=q["frames"], batch_size=1), 0]
    common = dict(steps=q["steps"], cfg=q["cfg"], sampler_name=q["sampler"], scheduler=q["scheduler"], positive=pos, negative=neg)
    k1 = w.add("KSamplerAdvanced", model=models[0], add_noise="enable", noise_seed=q["seed"], latent_image=lat,
               start_at_step=0, end_at_step=q["split"], return_with_leftover_noise="enable", **common)
    k2 = w.add("KSamplerAdvanced", model=models[1], add_noise="disable", noise_seed=0, latent_image=[k1, 0],
               start_at_step=q["split"], end_at_step=10000, return_with_leftover_noise="disable", **common)
    img = w.add("VAEDecode", samples=[k2, 0], vae=[vae, 0])
    vid = w.add("CreateVideo", images=[img, 0], fps=q["fps"])
    w.add("SaveVideo", video=[vid, 0], filename_prefix="video/hub", format="auto", codec="auto")
    return w.n


def wf_upscale(model, img):
    """업스케일 모델로 키워요(모델 고유 배율). 원하는 배율에 맞추는 건 허브가 받은 뒤에 해요."""
    w = WF()
    li = w.add("LoadImage", image=img)
    um = w.add("UpscaleModelLoader", model_name=model)
    out = [w.add("ImageUpscaleWithModel", upscale_model=[um, 0], image=[li, 0]), 0]
    w.add("PreviewImage", images=out)
    return w.n


# ───────────────────────── 사용자 워크플로(API 형식) 분석 / 적용 ─────────────────────────
TEXT_KEYS = ("text", "prompt", "text_g", "text_l")
IMG_CLASSES = ("LoadImage", "LoadImageMask", "LoadImageOutput")
SEED_KEYS = ("seed", "noise_seed")


class MissingNodes(ValueError):
    """워크플로에 이 ComfyUI 에 없는 노드가 있어요. .nodes 에 노드 이름 목록이 들어 있어요."""
    def __init__(self, nodes, msg):
        super().__init__(msg)
        self.nodes = list(nodes)


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


def _norm_links(links):
    out = []
    for l in links or []:
        if isinstance(l, (list, tuple)) and len(l) >= 5:
            out.append({"id": l[0], "origin_id": l[1], "origin_slot": l[2], "target_id": l[3], "target_slot": l[4]})
        elif isinstance(l, dict) and "id" in l:
            out.append({"id": l["id"], "origin_id": l.get("origin_id"), "origin_slot": l.get("origin_slot", 0),
                        "target_id": l.get("target_id"), "target_slot": l.get("target_slot", 0)})
    return out


def flatten_subgraphs(ui):
    """서브그래프(묶음 노드)를 풀어서 안에 든 노드를 바깥 그래프에 그대로 펼쳐요(중첩도 풀어요).
    펼쳐진 노드 번호는 '묶음번호:안쪽번호' 이고, 묶음 바깥에서 들어오던 값·연결은 안쪽 노드에 직접 이어 줘요.
    묶음 노드에서 바깥으로 꺼내 둔 값(위젯)은 안쪽 노드의 같은 위젯 값으로 넣고(_ovr), 끈/우회한 묶음은 안쪽 노드도 같은 상태로 둬요."""
    subs = {str(s.get("id")): s for s in (ui.get("definitions") or {}).get("subgraphs", []) if isinstance(s, dict)}
    nodes = [dict(n) for n in ui.get("nodes", []) if isinstance(n, dict) and "id" in n]
    links = _norm_links(ui.get("links"))
    for _ in range(12):
        inst = [n for n in nodes if str(n.get("type")) in subs]
        if not inst:
            break
        for I in inst:
            sg, pre = subs[str(I["type"])], f"{I['id']}:"
            byid = {l["id"]: l for l in links}
            ins = I.get("inputs") or []
            wv = list(I.get("widgets_values") or []) if isinstance(I.get("widgets_values"), list) else []
            outer, wvals, k = {}, {}, 0          # 바깥 연결 / 연결 없는 위젯 입력의 값
            for slot, i in enumerate(ins):
                lid = i.get("link")
                if lid is not None and lid in byid:
                    outer[slot] = byid[lid]
                elif i.get("widget") and k < len(wv):
                    wvals[slot] = wv[k]
                if i.get("widget"):
                    k += 1
            new_nodes = []
            for N in sg.get("nodes", []):
                if not isinstance(N, dict) or "id" not in N:
                    continue
                c = copy.deepcopy(N)
                c["id"] = pre + str(N["id"])
                for i in c.get("inputs") or []:
                    if i.get("link") is not None:
                        i["link"] = pre + str(i["link"])
                for o in c.get("outputs") or []:
                    if isinstance(o.get("links"), list):
                        o["links"] = [pre + str(x) for x in o["links"]]
                if I.get("mode") in (2, 4):
                    c["mode"] = I["mode"]
                c["_ovr"] = dict(c.get("_ovr") or {})
                new_nodes.append(c)
            nmap = {str(c["id"]): c for c in new_nodes}
            pw = (I.get("properties") or {}).get("proxyWidgets")
            if isinstance(pw, list) and wv and not any(i.get("widget") for i in ins):
                for idx, pair in enumerate(pw):
                    if isinstance(pair, (list, tuple)) and len(pair) == 2 and idx < len(wv) and str(pair[0]) not in ("-1", "-10"):
                        t = nmap.get(pre + str(pair[0]))
                        if t is not None:
                            t["_ovr"][pair[1]] = wv[idx]
            out_map, new_links = {}, []
            for L in sg.get("links", []):
                if not isinstance(L, dict):
                    continue
                o_id, t_id = L.get("origin_id"), L.get("target_id")
                if t_id == -20:                      # 묶음의 출력 → 바깥에서 이 출력을 쓰는 연결의 출발점
                    out_map[L.get("target_slot", 0)] = (L.get("origin_id"), L.get("origin_slot", 0), L)
                    continue
                tgt = nmap.get(pre + str(t_id))
                if tgt is None:
                    continue
                if o_id == -10:                      # 묶음의 입력 → 바깥에서 들어오던 연결 또는 위젯 값
                    slot = L.get("origin_slot", 0)
                    ol = outer.get(slot)
                    tname = None
                    for ti in tgt.get("inputs") or []:
                        if ti.get("link") == pre + str(L["id"]):
                            tname = ti.get("name")
                            if ol is None:
                                ti["link"] = None
                    if ol is not None:
                        new_links.append({"id": pre + str(L["id"]), "origin_id": ol["origin_id"], "origin_slot": ol["origin_slot"],
                                          "target_id": tgt["id"], "target_slot": L.get("target_slot", 0)})
                    elif slot in wvals and tname:
                        tgt["_ovr"][tname] = wvals[slot]
                else:
                    new_links.append({"id": pre + str(L["id"]), "origin_id": pre + str(o_id), "origin_slot": L.get("origin_slot", 0),
                                      "target_id": tgt["id"], "target_slot": L.get("target_slot", 0)})
            keep = []
            for l in links:
                if l["target_id"] == I["id"]:
                    continue                          # 이 묶음으로 들어가던 연결은 안쪽에 다시 이었어요
                if l["origin_id"] == I["id"]:
                    m = out_map.get(l["origin_slot"])
                    if m is None:
                        continue
                    oid, osl, src = m
                    if oid == -10:                    # 입력이 곧바로 출력으로 지나가는 경우
                        ol = outer.get(osl)
                        if ol is None:
                            continue
                        l = dict(l, origin_id=ol["origin_id"], origin_slot=ol["origin_slot"])
                    else:
                        l = dict(l, origin_id=pre + str(oid), origin_slot=osl)
                keep.append(l)
            nodes = [n for n in nodes if n is not I] + new_nodes
            links = keep + new_links
    out = {k: v for k, v in ui.items() if k not in ("nodes", "links")}
    out["nodes"], out["links"] = nodes, links
    return out


def ui_to_api(ui, info):
    """화면용 워크플로(nodes/links)를 API 형식으로 바꿔요. info 는 ComfyUI 의 /object_info 응답이에요.
    Reroute·PrimitiveNode 는 값/연결을 바로 이어 주고, 끈 노드(mode 2)는 빼고, 우회 노드(mode 4)는 같은 종류의 입력으로 건너뛰어요."""
    if (ui.get("definitions") or {}).get("subgraphs"):
        ui = flatten_subgraphs(ui)
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
        raise MissingNodes(unknown, "설치되지 않은 노드가 있어요: " + ", ".join(unknown))

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
        for k2, v2 in (n.get("_ovr") or {}).items():
            inp[k2] = v2
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
