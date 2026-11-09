"""Shared mock ComfyUI / Ollama / file server + hub bootstrap (used by backend and UI tests)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import base64, io, json, os, sys, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image

SLOT = int(os.environ.get("TEST_SLOT", "0"))      # 동시 실행용: 슬롯마다 포트를 1000씩 띄워요
_O = SLOT * 1000
PORT = int(os.environ.get("TEST_HUB_PORT", "17860")) + _O
CP, OP, FP = 18188 + _O, 21434 + _O, 19999 + _O
TMP = Path(tempfile.mkdtemp())
os.environ.update(STUDIO_ROOT=str(TMP), HUB_PORT=str(PORT), COMFY_URL=f"http://127.0.0.1:{CP}", OLLAMA_URL=f"http://127.0.0.1:{OP}",
                  CIVITAI_URL=f"http://127.0.0.1:{FP}/civ", HF_URL=f"http://localhost:{FP}/hf", GITHUB_URL=f"http://127.0.0.1:{FP}/gh",
                  NODEMAP_URL=f"http://127.0.0.1:{FP}/nodemap.json")
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import hub  # noqa
import flows  # noqa
import meta  # noqa

M = TMP / "engine/ComfyUI_windows_portable/ComfyUI/models"
for d, f in ([("checkpoints", "noobai_xl_v11.safetensors"),("checkpoints", "NoobAI-Vpred.safetensors"), ("checkpoints", "lustify_photo.safetensors"),
             ("diffusion_models", "qwen_image_2.1_int8_convrot.safetensors"), ("text_encoders", "qwen3vl_8b_int8_convrot.safetensors"), ("vae", "qwen_image_2.1_vae_bf16.safetensors"), ("text_encoders", "qwen_2.5_vl_7b_fp8_scaled.safetensors"),
             ("vae", "qwen_image_vae.safetensors"), ("vae", "sdxl.vae.safetensors"),
             ("loras", "qwen_image_2.1_lightning_4step.safetensors"), ("loras", "style.safetensors"), ("loras", "detail_v2.safetensors"),
             ("upscale_models", "RealESRGAN_x4plus.pth"), ("controlnet", "union_promax.safetensors"),
             ("diffusion_models", "flux1-krea-dev_fp8_scaled.safetensors"), ("diffusion_models", "Chroma1-HD.safetensors"),
             ("text_encoders", "clip_l.safetensors"), ("text_encoders", "t5xxl_fp8_e4m3fn_scaled.safetensors"), ("vae", "ae.safetensors")]
        + [("loras", f"lora_{c}.safetensors") for c in "abcdefghij"]):
    (M / d).mkdir(parents=True, exist_ok=True); (M / d / f).write_bytes(b"x")
INPUT = M.parent / "input"; INPUT.mkdir(exist_ok=True)
(TMP / "wildcards").mkdir(); (TMP / "wildcards" / "hair_color.txt").write_text("# c\nblack hair\nblonde hair\nred hair\n", encoding="utf-8")


def tiny_glb(w=0.6, h=1.0, d=0.4):
    """가짜 ComfyUI 의 3D 결과: 진짜 GLB 형식의 상자 하나(정점·면·재질·텍스처 그림 포함). 상자 바닥 가운데가 원점이 아님(y -0.5~0.5)."""
    import struct as _st
    xs, ys, zs = (-w / 2, w / 2), (-h / 2, h / 2), (-d / 2, d / 2)
    pos = [(x, y, z) for x in xs for y in ys for z in zs]
    idx = [0, 1, 3, 0, 3, 2, 4, 6, 7, 4, 7, 5, 0, 4, 5, 0, 5, 1, 2, 3, 7, 2, 7, 6, 0, 2, 6, 0, 6, 4, 1, 5, 7, 1, 7, 3]
    pb = b"".join(_st.pack("<3f", *p) for p in pos); ib = b"".join(_st.pack("<H", i) for i in idx) + b"\0\0"
    bi = io.BytesIO(); Image.new("RGB", (4, 4), (200, 50, 50)).save(bi, "PNG"); png = bi.getvalue() + b"\0" * (-len(bi.getvalue()) % 4)
    bin_ = pb + ib + png
    g = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "mesh"}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
         "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}], "textures": [{"source": 0, "sampler": 0}], "samplers": [{}],
         "images": [{"bufferView": 2, "mimeType": "image/png"}], "buffers": [{"byteLength": len(bin_)}],
         "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pb)}, {"buffer": 0, "byteOffset": len(pb), "byteLength": len(idx) * 2},
                         {"buffer": 0, "byteOffset": len(pb) + len(ib), "byteLength": len(bi.getvalue())}],
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": [xs[0], ys[0], zs[0]], "max": [xs[1], ys[1], zs[1]]},
                       {"bufferView": 1, "componentType": 5123, "count": len(idx), "type": "SCALAR"}]}
    js = json.dumps(g).encode(); js += b" " * (-len(js) % 4)
    body = _st.pack("<II", len(js), 0x4E4F534A) + js + _st.pack("<II", len(bin_), 0x004E4942) + bin_
    return _st.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def uv_glb(w=0.75, h=1.0, d=0.5, color=(60, 60, 200), n=12, tex=256):
    """텍스처 좌표가 있는 상자(면마다 n×n 칸, 텍스처는 3×2 칸에 나눠 펼침) — 사진 붙이기 확인용. 앞(+z) 면은 왼쪽 위 칸."""
    import struct as _st
    P, UV, F = [], [], []
    faces = [((0, 0, d / 2), (w, 0, 0), (0, h, 0)), ((0, 0, -d / 2), (-w, 0, 0), (0, h, 0)), ((w / 2, 0, 0), (0, 0, -d), (0, h, 0)),
             ((-w / 2, 0, 0), (0, 0, d), (0, h, 0)), ((0, h / 2, 0), (w, 0, 0), (0, 0, -d)), ((0, -h / 2, 0), (w, 0, 0), (0, 0, d))]
    for k, (c, a, b) in enumerate(faces):
        cu, cv = k % 3, k // 3
        base = len(P)
        for j in range(n + 1):
            for i in range(n + 1):
                s_, t_ = i / n - 0.5, j / n - 0.5
                P.append(tuple(c[q] + a[q] * s_ + b[q] * t_ for q in range(3)))
                UV.append(((cu + 0.05 + 0.9 * i / n) / 3, (cv + 0.05 + 0.9 * (1 - j / n)) / 2))
        for j in range(n):
            for i in range(n):
                q0 = base + j * (n + 1) + i
                F += [(q0, q0 + 1, q0 + n + 2), (q0, q0 + n + 2, q0 + n + 1)]
    bi = io.BytesIO(); (color if isinstance(color, Image.Image) else Image.new("RGB", (tex, tex), color)).save(bi, "PNG"); png = bi.getvalue()
    pb = b"".join(_st.pack("<3f", *p) for p in P); ub = b"".join(_st.pack("<2f", *u) for u in UV); ib = b"".join(_st.pack("<3I", *f) for f in F)
    parts, views, bin_ = [pb, ub, ib, png], [], b""
    for x in parts:
        bin_ += b"\0" * (-len(bin_) % 4); views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(x)}); bin_ += x
    mn = [min(p[q] for p in P) for q in range(3)]; mx = [max(p[q] for p in P) for q in range(3)]
    g = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
         "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}], "textures": [{"source": 0}],
         "images": [{"bufferView": 3, "mimeType": "image/png"}], "buffers": [{"byteLength": len(bin_)}], "bufferViews": views,
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(P), "type": "VEC3", "min": mn, "max": mx},
                       {"bufferView": 1, "componentType": 5126, "count": len(UV), "type": "VEC2"},
                       {"bufferView": 2, "componentType": 5125, "count": len(F) * 3, "type": "SCALAR"}]}
    js = json.dumps(g).encode(); js += b" " * (-len(js) % 4); bin_ += b"\0" * (-len(bin_) % 4)
    body = _st.pack("<II", len(js), 0x4E4F534A) + js + _st.pack("<II", len(bin_), 0x004E4942) + bin_
    return _st.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


REQ = {"CheckpointLoaderSimple": ["ckpt_name"], "LoraLoader": ["model", "clip", "lora_name", "strength_model", "strength_clip"],
       "LoraLoaderModelOnly": ["model", "lora_name", "strength_model"], "CLIPSetLastLayer": ["clip", "stop_at_clip_layer"],
       "CLIPTextEncode": ["text", "clip"], "EmptyLatentImage": ["width", "height", "batch_size"],
       "KSampler": ["model", "seed", "steps", "cfg", "sampler_name", "scheduler", "positive", "negative", "latent_image", "denoise"],
       "VAEDecode": ["samples", "vae"], "VAEEncode": ["pixels", "vae"], "PreviewImage": ["images"], "LoadImage": ["image"],
       "LoadImageMask": ["image", "channel"], "InpaintModelConditioning": ["positive", "negative", "vae", "pixels", "mask", "noise_mask"],
       "DifferentialDiffusion": ["model"], "UNETLoader": ["unet_name", "weight_dtype"], "CLIPLoader": ["clip_name", "type"],
       "VAELoader": ["vae_name"], "ModelSamplingAuraFlow": ["model", "shift"], "CFGNorm": ["model", "strength"],
       "TextEncodeQwenImageEditPlus": ["clip", "prompt", "vae", "image1"], "TextEncodeQwenImageEdit": ["clip", "prompt", "vae", "image"],
       "UpscaleModelLoader": ["model_name"], "ImageUpscaleWithModel": ["upscale_model", "image"], "ImageScaleBy": ["image", "upscale_method", "scale_by"], "ImageScale": ["image", "upscale_method", "width", "height", "crop"],
       "ModelSamplingDiscrete": ["model", "sampling", "zsnr"], "RescaleCFG": ["model", "multiplier"], "PerturbedAttentionGuidance": ["model", "scale"],
       "LatentUpscaleBy": ["samples", "upscale_method", "scale_by"], "ControlNetLoader": ["control_net_name"],
       "ControlNetApplyAdvanced": ["positive", "negative", "control_net", "image", "strength", "start_percent", "end_percent"],
       "Canny": ["image", "low_threshold", "high_threshold"], "SaveImage": ["images"],
       "DualCLIPLoader": ["clip_name1", "clip_name2", "type"], "FluxGuidance": ["conditioning", "guidance"],
       "ConditioningZeroOut": ["conditioning"], "ImagePadForOutpaint": ["image", "left", "top", "right", "bottom", "feathering"],
       "ConditioningSetAreaPercentage": ["conditioning", "width", "height", "x", "y", "strength"], "ConditioningCombine": ["conditioning_1", "conditioning_2"], "EmptySD3LatentImage": ["width", "height", "batch_size"],
       "ReferenceLatent": ["conditioning", "latent"], "FluxKontextImageScale": ["image"],
       "ModelSamplingSD3": ["model", "shift"], "Wan22ImageToVideoLatent": ["vae", "width", "height", "length", "batch_size"],
       "Krea2ControlLoRALoader": ["model", "lora_name", "strength"], "Krea2ControlApply": ["model", "control_latent"],
       "Krea2ControlImageEncode": ["control_image", "vae", "resize", "upscale_method", "crop", "channel_mode", "normalize", "invert", "batch_mode", "latent"],
       "TextEncodeAceStepAudio1.5": ["clip", "tags", "lyrics", "seed", "bpm", "duration", "timesignature", "language", "keyscale", "generate_audio_codes"], "EmptyAceStep1.5LatentAudio": ["seconds", "batch_size"],
       "VAEDecodeAudio": ["samples", "vae"], "SaveAudioAdvanced": ["audio", "filename_prefix", "format"],
       "TripleCLIPLoader": ["clip_name1", "clip_name2", "clip_name3"], "TextEncodeQwenImage21": ["clip", "prompt", "negative_prompt", "resolution"], "EmptyFlux2LatentImage": ["width", "height", "batch_size"], "QuadrupleCLIPLoader": ["clip_name1", "clip_name2", "clip_name3", "clip_name4"],
       "ConditioningStableAudio": ["positive", "negative", "seconds_start", "seconds_total"], "EmptyLatentAudio": ["seconds", "batch_size"],
       "LTXVImgToVideo": ["positive", "negative", "vae", "image", "width", "height", "length", "batch_size", "strength"], "LTXVConditioning": ["positive", "negative", "frame_rate"],
       "LTXVScheduler": ["steps", "max_shift", "base_shift", "stretch", "terminal"], "EmptyLTXVLatentVideo": ["width", "height", "length", "batch_size"],
       "KSamplerSelect": ["sampler_name"], "SamplerCustom": ["model", "add_noise", "noise_seed", "cfg", "positive", "negative", "sampler", "sigmas", "latent_image"],
       "WanVaceToVideo": ["positive", "negative", "vae", "width", "height", "length", "batch_size", "strength"], "TrimVideoLatent": ["samples", "trim_amount"],
       "WanSoundImageToVideo": ["positive", "negative", "vae", "width", "height", "length", "batch_size"], "LoadAudio": ["audio"],
       "AudioEncoderLoader": ["audio_encoder_name"], "AudioEncoderEncode": ["audio_encoder", "audio"],
       "ImageOnlyCheckpointLoader": ["ckpt_name"], "Hunyuan3Dv2Conditioning": ["clip_vision_output"], "EmptyLatentHunyuan3Dv2": ["resolution", "batch_size"],
       "VAEDecodeHunyuan3D": ["samples", "vae", "num_chunks", "octree_resolution"], "VoxelToMesh": ["voxel", "algorithm", "threshold"], "SaveGLB": ["mesh", "filename_prefix"],
       "WanSoundImageToVideoExtend": ["positive", "negative", "vae", "length", "video_latent"], "LatentConcat": ["samples1", "samples2", "dim"],
       "ImageToMask": ["image", "channel"], "ThresholdMask": ["mask", "value"],
       "CreateVideo": ["images", "fps"], "SaveVideo": ["video", "filename_prefix", "format", "codec"],
       "SetUnionControlNetType": ["control_net", "type"], "OpenposePreprocessor": ["image", "detect_hand", "detect_body", "detect_face", "resolution"],
       "DepthAnythingV2Preprocessor": ["image", "ckpt_name", "resolution"],
       "WanImageToVideo": ["positive", "negative", "vae", "width", "height", "length", "batch_size", "start_image"], "EmptyHunyuanLatentVideo": ["width", "height", "length", "batch_size"],
       "KSamplerAdvanced": ["model", "add_noise", "noise_seed", "steps", "cfg", "sampler_name", "scheduler", "positive", "negative", "latent_image", "start_at_step", "end_at_step", "return_with_leftover_noise"],
       "LoadVideo": ["file"], "GetVideoComponents": ["video"], "SaveAnimatedWEBP": ["images", "filename_prefix", "fps", "lossless", "quality", "method"],
       "RIFE VFI": ["ckpt_name", "frames", "clear_cache_after_n_frames", "multiplier", "fast_mode", "ensemble", "scale_factor"],
       "ReActorFaceSwap": ["enabled", "input_image", "swap_model", "facedetection", "face_restore_model", "face_restore_visibility", "codeformer_weight", "detect_gender_input", "detect_gender_source", "input_faces_index", "source_faces_index", "console_log_level"],
       "ModelSamplingFlux": ["model", "max_shift", "base_shift", "width", "height"], "FluxKontextMultiReferenceLatentMethod": ["conditioning", "reference_latents_method"],
       "CLIPVisionLoader": ["clip_name"], "CLIPVisionEncode": ["clip_vision", "image", "crop"], "StyleModelLoader": ["style_model_name"], "StyleModelApply": ["conditioning", "style_model", "clip_vision_output"],
       "UltralyticsDetectorProvider": ["model_name"], "IPAdapterUnifiedLoader": ["model", "preset"],
       "IPAdapter": ["model", "ipadapter", "image", "weight", "weight_type", "start_at", "end_at"],
       "FaceDetailer": ["image", "model", "clip", "vae", "positive", "negative", "bbox_detector", "seed", "steps", "cfg", "sampler_name", "scheduler",
                        "denoise", "guide_size", "max_size", "feather", "bbox_threshold", "bbox_dilation", "bbox_crop_factor", "sam_detection_hint", "wildcard", "cycle"]}
REQ.update({"CFGGuider": ["model", "positive", "negative", "cfg"], "TextEncodeMOSSImageEdit": ["clip", "prompt", "edit_format", "images.image_0"], "SkipLayerGuidanceDiTSimple": ["model"], "ReferenceMultiLatent": ["positive", "resolution"]})
REQ.update({"LoadDA3Model": ["model_name", "weight_dtype"], "DA3Inference": ["da3_model", "image", "resolution", "mode"], "DA3Render": ["da3_geometry", "output"]})
REQ.update({"SeedVR2Preprocess": ["resized_images"], "SeedVR2Conditioning": ["model", "vae_conditioning"],
            "SeedVR2PostProcessing": ["images", "original_resized_images", "color_correction_method"],
            "VAEEncodeTiled": ["pixels", "vae", "tile_size", "overlap", "temporal_size", "temporal_overlap"]})
REQ.update({"LTXVDualCFGGuider": ["model", "positive", "negative", "video_cfg", "audio_cfg"], "LTXVImgToVideoInplace": ["vae", "image", "latent", "strength"],
            "LTXVPreprocess": ["image", "img_compression"], "LTXVEmptyLatentAudio": ["audio_vae", "frames_number", "frame_rate", "batch_size"],
            "LTXVConcatAVLatent": ["video_latent", "audio_latent"], "LTXVSeparateAVLatent": ["av_latent"], "LTXVLatentUpsampler": ["samples", "upscale_model", "vae"],
            "LatentUpscaleModelLoader": ["model_name"], "LTXVAudioVAEDecode": ["samples", "audio_vae"], "ManualSigmas": ["sigmas"],
            "SamplerCustomAdvanced": ["noise", "guider", "sampler", "sigmas", "latent_image"], "RandomNoise": ["noise_seed"],
            "VAEDecodeTiled": ["samples", "vae", "tile_size", "overlap", "temporal_size", "temporal_overlap"]})
REQ.update({"LoadMediaPipeFaceLandmarker": ["model_name"], "MediaPipeFaceLandmarker": ["face_detection_model", "image", "detector_variant", "num_faces"],
            "MediaPipeFaceMask": ["face_landmarks", "regions"], "PreviewAny": ["source"]})
REQ.update({"LoadBackgroundRemovalModel": ["bg_removal_name"], "RemoveBackground": ["bg_removal_model", "image"], "MaskToImage": ["mask"]})
REQ.update({"InvertMask": ["mask"], "ImageCropToMask": ["images", "masks"], "Trellis2Conditioning": ["clip_vision_model", "image"],
            "Pixal3DMultiViewConditioning": ["clip_vision_model", "front"], "Pixal3DConditioning": ["clip_vision_model", "image", "camera_angle_x"], "LoadMoGeModel": ["model_name"], "MoGeInference": ["moge_model", "image"], "MoGeGeometryToFOV": ["moge_geometry"], "EmptyTrellis2LatentStructure": ["batch_size"],
            "VaeDecodeStructureTrellis2": ["samples", "vae", "resolution"], "Trellis2ShapeStage": ["positive", "negative", "voxel"],
            "Trellis2UpsampleStage": ["positive", "negative", "shape_latent", "vae", "target_resolution"], "VaeDecodeShapeTrellis": ["samples", "vae"],
            "Trellis2TextureStage": ["positive", "negative", "shape_latent"], "VaeDecodeTextureTrellis": ["samples", "vae", "shape_subdivides"],
            "RemeshMesh": ["mesh", "resolution", "sign_mode"], "CFGOverride": ["model", "cfg", "start_percent", "end_percent"], "DecimateMesh": ["mesh", "target_face_count"], "MeshSmoothNormals": ["mesh"],
            "UnwrapMesh": ["mesh"], "BakeTextureFromVoxel": ["mesh", "voxel_colors", "texture_size"], "BakeNormalMapFromMesh": ["low_poly", "high_poly"],
            "BakeAmbientOcclusion": ["low_poly", "high_poly"], "ApplyTextureToMesh": ["mesh", "base_color"]})
SUBMITTED, HIST, STATE = [], {}, {"missing": set(), "freed": 0, "slow_from": None, "interrupts": 0, "deleted": [], "ws": False, "seen": [], "ollama_deleted": [], "ws_sent": 0}
SAMPLERS = ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_3m_sde", "uni_pc", "lcm", "res_multistep"]
SCHEDS = ["normal", "karras", "simple", "beta", "sgm_uniform"]

def validate(wf):
    for nid, n in wf.items():
        assert n["class_type"] in REQ, "unknown class " + n["class_type"]
        assert n["class_type"] not in STATE["missing"], "missing node " + n["class_type"]
        for k in REQ[n["class_type"]]:
            assert k in n["inputs"], f'{n["class_type"]} missing {k}'
        for k, v in n["inputs"].items():
            if isinstance(v, list):
                assert len(v) == 2 and v[0] in wf, f"bad link {nid}.{k}={v}"
        if n["class_type"] == "LoadVideo":
            assert (INPUT / n["inputs"]["file"]).exists(), "input video missing"
        if n["class_type"] in ("LoadImage", "LoadImageMask"):
            assert (INPUT / n["inputs"]["image"]).exists(), "input file missing"

def out_size(wf):
    ids = sorted(wf, key=lambda x: [int(p) for p in x.split(":")]); nodes = [wf[i] for i in ids]
    by = lambda c: [n for n in nodes if n["class_type"] == c]
    if by("LoadVideo") or by("EmptyAceStep1.5LatentAudio") or by("EmptyLatentAudio") or by("EmptyLTXVLatentVideo") or by("SaveGLB") or by("WanVaceToVideo") or by("WanSoundImageToVideo") or by("LTXVImgToVideo"): return 64, 64
    for c in ("WanImageToVideo", "EmptyHunyuanLatentVideo"):
        if by(c): i = by(c)[0]["inputs"]; return i["width"], i["height"]
    if by("Wan22ImageToVideoLatent"): i = by("Wan22ImageToVideoLatent")[0]["inputs"]; return i["width"], i["height"]
    if by("EmptyLatentImage") or by("EmptySD3LatentImage") or by("EmptyFlux2LatentImage"):
        i = (by("EmptyLatentImage") or by("EmptySD3LatentImage") or by("EmptyFlux2LatentImage"))[0]["inputs"]; w, h = i["width"], i["height"]
        if by("LatentUpscaleBy"):
            s = by("LatentUpscaleBy")[0]["inputs"]["scale_by"]; w, h = round(w * s / 8) * 8, round(h * s / 8) * 8
        return w, h
    w, h = Image.open(INPUT / by("LoadImage")[0]["inputs"]["image"]).size
    if by("ImagePadForOutpaint"):
        i = by("ImagePadForOutpaint")[0]["inputs"]; return w + i["left"] + i["right"], h + i["top"] + i["bottom"]
    if by("ImageUpscaleWithModel"):
        return (w * 2, h * 2) if by("ImageScaleBy") else (w * 4, h * 4)
    return w, h

WS_CLIENTS = []
def ws_send(obj):
    b = json.dumps(obj).encode(); fr = bytes([0x81]) + (bytes([len(b)]) if len(b) < 126 else bytes([126]) + len(b).to_bytes(2, "big")) + b
    for w in list(WS_CLIENTS):
        try: w.write(fr); w.flush()
        except Exception: WS_CLIENTS.remove(w)
def ws_progress(pid, steps=5, dt=0.35, wf=None):
    if wf:   # 모델을 불러오는 노드 → 샘플러 순으로 실행 중임을 알려요
        ids = sorted(wf, key=lambda x: [int(p) for p in x.split(":")])
        ld = next((i for i in ids if wf[i]["class_type"] in ("CheckpointLoaderSimple", "UNETLoader")), None)
        ks = next((i for i in ids if wf[i]["class_type"] == "KSampler"), None)
        if ld: ws_send({"type": "executing", "data": {"node": ld, "prompt_id": pid}}); time.sleep(STATE.get("load_delay", 0.9))
        if ks: ws_send({"type": "executing", "data": {"node": ks, "prompt_id": pid}})
    for i in range(1, steps + 1):
        time.sleep(dt); ws_send({"type": "progress", "data": {"value": i, "max": steps, "prompt_id": pid}}); STATE["ws_sent"] += 1

class Comfy(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def j(self, o, c=200):
        b = json.dumps(o).encode(); self.send_response(c); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = self.path.split("?")[0]
        if u == "/ws":
            import hashlib as _h
            key = self.headers["Sec-WebSocket-Key"]; acc = base64.b64encode(_h.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            self.send_response(101); self.send_header("Upgrade", "websocket"); self.send_header("Connection", "Upgrade"); self.send_header("Sec-WebSocket-Accept", acc); self.end_headers()
            WS_CLIENTS.append(self.wfile); self.connection.settimeout(None)
            try:
                while True: time.sleep(1)
            except Exception: return
        if u == "/system_stats": return self.j({})
        if u == "/queue":
            run = [[0, pid, {}] for pid, h in HIST.items() if h.get("slow") and not h.get("interrupted")]
            return self.j({"queue_running": run[:1], "queue_pending": run[1:]})
        if u == "/object_info":
            o = {c: {"input": {"required": {}}} for c in REQ if c not in STATE["missing"]}
            o["KSampler"] = {"input": {"required": {"model": ["MODEL"], "seed": ["INT", {"control_after_generate": True}], "steps": ["INT", {}], "cfg": ["FLOAT", {}],
                             "sampler_name": [SAMPLERS], "scheduler": [SCHEDS], "positive": ["CONDITIONING"], "negative": ["CONDITIONING"], "latent_image": ["LATENT"], "denoise": ["FLOAT", {}]}}}
            o["CheckpointLoaderSimple"] = {"input": {"required": {"ckpt_name": [["noobai_xl_v11.safetensors"]]}}}
            o["CLIPTextEncode"] = {"input": {"required": {"text": ["STRING", {"multiline": True}], "clip": ["CLIP"]}}}
            o["EmptyLatentImage"] = {"input": {"required": {"width": ["INT", {}], "height": ["INT", {}], "batch_size": ["INT", {}]}}}
            o["LoadImage"] = {"input": {"required": {"image": [["a.png"], {"image_upload": True}]}}}
            if "OpenposePreprocessor" not in STATE["missing"]: o["OpenposePreprocessor"] = {"input": {"required": {"image": ["IMAGE"], "detect_hand": [["enable", "disable"]], "detect_body": [["enable", "disable"]], "detect_face": [["enable", "disable"]], "resolution": ["INT", {"default": 512}]}}}
            if "DepthAnythingV2Preprocessor" not in STATE["missing"]: o["DepthAnythingV2Preprocessor"] = {"input": {"required": {"image": ["IMAGE"], "ckpt_name": [["depth_anything_v2_vitl.pth", "depth_anything_v2_vitb.pth"]], "resolution": ["INT", {"default": 512}]}}}
            if "ReActorFaceSwap" not in STATE["missing"]: o["ReActorFaceSwap"] = {"input": {"required": {"enabled": ["BOOLEAN", {"default": True}], "input_image": ["IMAGE"], "swap_model": [STATE.get("swaps", ["inswapper_128.onnx"])], "facedetection": [["retinaface_resnet50", "retinaface_mobile0.25", "YOLOv5l", "YOLOv5n"]],
                "face_restore_model": [["none", "GFPGANv1.3.pth", "GFPGANv1.4.pth", "codeformer-v0.1.0.pth", "GPEN-BFR-512.onnx"]], "face_restore_visibility": ["FLOAT", {"default": 1}], "codeformer_weight": ["FLOAT", {"default": 0.5}],
                "detect_gender_input": [["no", "female", "male"], {"default": "no"}], "detect_gender_source": [["no", "female", "male"], {"default": "no"}], "input_faces_index": ["STRING", {"default": "0"}], "source_faces_index": ["STRING", {"default": "0"}], "console_log_level": [[0, 1, 2], {"default": 1}]}}}
            if "UltralyticsDetectorProvider" not in STATE["missing"]: o["UltralyticsDetectorProvider"] = {"input": {"required": {"model_name": [STATE.get("dets", ["bbox/face_yolov8m.pt", "bbox/hand_yolov8s.pt", "segm/person_yolov8m-seg.pt"])]}}}
            if "IPAdapterUnifiedLoader" not in STATE["missing"]: o["IPAdapterUnifiedLoader"] = {"input": {"required": {"model": ["MODEL"], "preset": [["LIGHT - SD1.5 only (low strength)", "STANDARD (medium strength)", "VIT-G (medium strength)", "PLUS (high strength)", "PLUS FACE (portraits)", "FULL FACE - SD1.5 only (portraits stronger)"]]}}}
            if "IPAdapter" not in STATE["missing"]: o["IPAdapter"] = {"input": {"required": {"model": ["MODEL"], "ipadapter": ["IPADAPTER"], "image": ["IMAGE"], "weight": ["FLOAT", {"default": 1.0}], "weight_type": [["linear", "ease in", "style transfer", "composition"]], "start_at": ["FLOAT", {"default": 0.0}], "end_at": ["FLOAT", {"default": 1.0}]}}}
            if "FaceDetailer" not in STATE["missing"]: o["FaceDetailer"] = {"input": {"required": {"image": ["IMAGE"], "model": ["MODEL"], "clip": ["CLIP"], "vae": ["VAE"], "guide_size": ["FLOAT", {"default": 512}], "guide_size_for": ["BOOLEAN", {"default": True}], "max_size": ["FLOAT", {"default": 1024}],
                "seed": ["INT", {}], "steps": ["INT", {"default": 20}], "cfg": ["FLOAT", {"default": 8.0}], "sampler_name": [SAMPLERS], "scheduler": [SCHEDS], "positive": ["CONDITIONING"], "negative": ["CONDITIONING"], "denoise": ["FLOAT", {"default": 0.5}],
                "feather": ["INT", {"default": 5}], "noise_mask": ["BOOLEAN", {"default": True}], "force_inpaint": ["BOOLEAN", {"default": True}], "bbox_threshold": ["FLOAT", {"default": 0.5}], "bbox_dilation": ["INT", {"default": 10}], "bbox_crop_factor": ["FLOAT", {"default": 3.0}],
                "sam_detection_hint": [["center-1", "horizontal-2", "none"]], "sam_dilation": ["INT", {"default": 0}], "sam_threshold": ["FLOAT", {"default": 0.93}], "sam_bbox_expansion": ["INT", {"default": 0}], "sam_mask_hint_threshold": ["FLOAT", {"default": 0.7}], "sam_mask_hint_use_negative": [["False", "Small", "Outter"]],
                "drop_size": ["INT", {"default": 10}], "bbox_detector": ["BBOX_DETECTOR"], "wildcard": ["STRING", {"multiline": True}], "cycle": ["INT", {"default": 1}]}}}
            if "CLIPVisionLoader" not in STATE["missing"]: o["CLIPVisionLoader"] = {"input": {"required": {"clip_name": [STATE.get("clipvis", [])]}}}
            if "StyleModelLoader" not in STATE["missing"]: o["StyleModelLoader"] = {"input": {"required": {"style_model_name": [STATE.get("styles", [])]}}}
            if "StyleModelApply" not in STATE["missing"]: o["StyleModelApply"] = {"input": {"required": {"conditioning": ["CONDITIONING"], "style_model": ["STYLE_MODEL"], "clip_vision_output": ["CLIP_VISION_OUTPUT"], "strength": ["FLOAT", {"default": 1.0}], "strength_type": [["multiply", "attn_bias"]]}}}
            if "FluxKontextMultiReferenceLatentMethod" not in STATE["missing"]: o["FluxKontextMultiReferenceLatentMethod"] = {"input": {"required": {"conditioning": ["CONDITIONING"], "reference_latents_method": [["offset", "index", "uxo/uno", "index_timestep_zero"]]}}}
            o["CLIPLoader"] = {"input": {"required": {"clip_name": [[]], "type": [STATE.get("clip_types", ["stable_diffusion", "flux", "chroma", "krea2", "qwen_image", "wan", "lumina2", "stable_audio", "ltxv", "moss_image", "flux3"])]}}}
            return self.j(o)
        if u.startswith("/history/"):
            pid = u.split("/")[-1]; h = HIST.get(pid)
            if not h: return self.j({})
            if h.get("slow") and not h.get("interrupted"): return self.j({})
            if h["polls"] < 1: h["polls"] += 1; return self.j({})
            if h.get("glb"): return self.j({pid: {"outputs": {"99": {"3d": [{"filename": pid + ".glb", "subfolder": "3d", "type": "output"}]}, **({"98": {"text": [STATE.get("fov_text", "38.5")]}} if h.get("txt") else {})}, "status": {"status_str": "success", "messages": []}}})
            if h.get("audio"): return self.j({pid: {"outputs": {"99": {"audio": [{"filename": pid + ".mp3", "subfolder": "audio", "type": "output"}]}}, "status": {"status_str": "success", "messages": []}}})
            if h.get("webp"): return self.j({pid: {"outputs": {"99": {"images": [{"filename": pid + ".webp", "subfolder": "video", "type": "output"}], "animated": [True]}}, "status": {"status_str": "success", "messages": []}}})
            if h.get("video"): return self.j({pid: {"outputs": {"99": {"images": [{"filename": pid + ".mp4", "subfolder": "video", "type": "output"}], "animated": [True]}}, "status": {"status_str": "success", "messages": []}}})
            return self.j({pid: {"outputs": {"99": {"images": [{"filename": pid + ".png", "subfolder": "", "type": "temp"}]}}, "status": {"status_str": "success", "messages": []}}})
        if u == "/view" and ".glb" in self.path:
            self.send_response(200); self.send_header("Content-Type", "model/gltf-binary"); self.end_headers(); self.wfile.write(STATE.get("glb") or tiny_glb()); return
        if u == "/view" and ".mp3" in self.path:
            self.send_response(200); self.send_header("Content-Type", "audio/mpeg"); self.end_headers(); self.wfile.write(b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(range(256)) * 4); return
        if u == "/view" and ".webp" in self.path:
            self.send_response(200); self.send_header("Content-Type", "image/webp"); self.end_headers(); self.wfile.write(b"RIFF\x00\x00\x00\x00WEBPVP8X"); return
        if u == "/view" and ".mp4" in self.path:
            self.send_response(200); self.send_header("Content-Type", "video/mp4"); self.end_headers(); self.wfile.write(STATE.get("mp4") or b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 8); return
        if u == "/view":
            pid = self.path.split("filename=")[1].split(".png")[0]
            w, h = HIST[pid]["size"]; im = Image.new("RGB", (w, h), (255, 0, 0))
            if HIST[pid].get("face") and STATE.get("face_box"):        # 얼굴 찾기: (그림 크기, 얼굴 상자) → 흰 상자 마스크
                (w, h), box = STATE["face_box"]; im = Image.new("RGB", (w, h), 0); im.paste((255, 255, 255), box)
            b = io.BytesIO(); im.save(b, "PNG")
            self.send_response(200); self.send_header("Content-Type", "image/png"); self.end_headers(); self.wfile.write(b.getvalue()); return
        self.j({}, 404)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/prompt":
            wf = body["prompt"]
            try: validate(wf)
            except AssertionError as e:
                return self.j({"error": {"message": "Prompt outputs failed validation"}, "node_errors": {"1": {"class_type": "X", "errors": [{"message": str(e), "details": ""}]}}}, 400)
            pid = f"p{len(SUBMITTED)}"; SUBMITTED.append(wf)
            HIST[pid] = {"polls": 0, "video": any(n["class_type"] == "SaveVideo" for n in wf.values()), "webp": any(n["class_type"] == "SaveAnimatedWEBP" for n in wf.values()), "audio": any(n["class_type"] == "SaveAudioAdvanced" for n in wf.values()), "glb": any(n["class_type"] == "SaveGLB" for n in wf.values()), "face": any(n["class_type"] == "MediaPipeFaceMask" for n in wf.values()), "txt": any(n["class_type"] == "PreviewAny" for n in wf.values()), "size": out_size(wf), "slow": STATE["slow_from"] is not None and len(SUBMITTED) - 1 >= STATE["slow_from"]}
            if STATE["ws"] and WS_CLIENTS and not HIST[pid]["slow"]: HIST[pid]["polls"] = -14; threading.Thread(target=ws_progress, args=(pid, 5, 0.35, wf), daemon=True).start()
            return self.j({"prompt_id": pid, "number": 1, "node_errors": {}})
        if self.path == "/free": STATE["freed"] += 1; return self.j({})
        if self.path == "/history": return self.j({})
        if self.path == "/interrupt":
            STATE["interrupts"] += 1
            for h in HIST.values():
                if h.get("slow"): h["interrupted"] = True
            return self.j({})
        if self.path == "/queue":
            STATE["deleted"] += body.get("delete", []); return self.j({})
        self.j({}, 404)

GEN = []
class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def j(self, o):
        b = json.dumps(o).encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/version": return self.j({"version": "x"})
        if self.path == "/api/tags": return self.j({"models": [{"name": "testmodel:latest", "size": 5_000_000_000}, {"name": "venice:old", "size": 1}] + [{"name": n, "size": 4_000_000_000} for n in STATE.get("ollama_extra", [])]})
        if self.path == "/api/ps": return self.j({"models": [{"name": "testmodel:latest"}]})
        self.j({})
    def do_DELETE(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        STATE["ollama_deleted"].append(body.get("model"))
        mf = (STATE.get("ollama_manifest") or {}).pop(body.get("model"), None)       # 진짜 Ollama 처럼 목록 파일은 지우고, 조각(blob)은 테스트가 정한 대로 남겨요
        if mf: Path(mf).unlink()
        if body.get("model") in STATE.get("ollama_extra", []): STATE["ollama_extra"].remove(body.get("model"))
        self.j({})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/generate":
            GEN.append(body)
            return self.j({"response": "<think>hm</think>change the jacket to red leather"} if body.get("prompt") else {})
        if self.path == "/api/show":
            return self.j({"capabilities": ["completion"] + (["vision"] if body.get("model") in STATE.get("vision", ()) else []) + ([] if body.get("model") in STATE.get("notools", ()) else ["tools"])})
        if self.path == "/api/chat" and body.get("tools"):
            STATE.setdefault("agentreq", []).append(body)
            rep = STATE.get("agent_replies") or []
            return self.j({"message": rep.pop(0) if rep else {"role": "assistant", "content": "무엇을 할까요?"}})
        if self.path == "/api/chat" and body.get("format"):
            STATE.setdefault("jsonreq", []).append(body)
            rep = STATE.get("json_replies") or []
            return self.j({"message": {"role": "assistant", "content": rep.pop(0) if rep else "{}"}})
        if self.path == "/api/chat" and body.get("stream") is False:
            GEN.append(body); return self.j({"message": {"content": "<think>x</think>1girl, red jacket, rain"}})
        if self.path == "/api/chat":
            STATE.setdefault("chatreq", []).append(body)
            self.send_response(200); self.end_headers()
            for m in [{"thinking": "hmm", "content": ""}, {"content": "안녕"}, {"content": "하세요"}]:
                self.wfile.write((json.dumps({"message": m, "done": False}) + "\n").encode()); self.wfile.flush()
            return
        if self.path == "/api/pull":
            self.send_response(200); self.end_headers()
            for c in (10, 100): self.wfile.write((json.dumps({"status": "pulling x", "total": 100, "completed": c}) + "\n").encode())
            self.wfile.write(b'{"status":"success"}\n'); return
        self.j({})

PAYLOAD = os.urandom(3_000_000)
class Files(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def jj(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        STATE["seen"].append((self.path, self.headers.get("Authorization"), self.headers.get("Host")))
        if self.path == "/nodemap.json":
            return self.jj({f"http://127.0.0.1:{FP}/gh/user/CoolNodes": [["CoolSampler", "CoolLoader"], {"title_aux": "Cool Nodes"}],
                            "https://evil.example.com/x/y": [["EvilNode"], {"title_aux": "Evil"}]})
        if self.path == "/gh/user/CoolNodes/archive/HEAD.zip":
            import zipfile as _z
            bb = io.BytesIO()
            with _z.ZipFile(bb, "w") as z:
                z.writestr("CoolNodes-main/__init__.py", "NODE_CLASS_MAPPINGS={}"); z.writestr("CoolNodes-main/requirements.txt", "# nothing\n")
            d = bb.getvalue(); self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d); return
        if self.path.startswith("/civ/api/v1/models"):
            if "private" in self.path and not self.headers.get("Authorization"): return self.jj({}, 401)
            if "query=weird" in self.path:
                return self.jj({"items": [{"id": 1, "name": "W", "type": "LORA", "nsfw": None, "stats": None, "modelVersions": [{"id": 1, "name": None, "baseModel": None, "images": None, "files": [{"name": "w.safetensors", "sizeKB": None, "type": "Model", "downloadUrl": "http://x/y"}]}]}, {"id": 2, "modelVersions": None}], "metadata": None})
            if "query=html" in self.path:
                self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b"<html>cf</html>"); return
            if "query=" in self.path and "page=" in self.path: return self.jj({"error": "page not allowed with query"}, 400)
            return self.jj({"items": [
                {"id": 11, "name": "Style Pack", "type": "LORA", "nsfw": True, "stats": {"downloadCount": 1234, "thumbsUpCount": 99},
                 "modelVersions": [{"id": 111, "name": "v2", "baseModel": "Illustrious", "downloadUrl": f"http://127.0.0.1:{FP}/civ/api/download/models/111",
                   "images": [{"url": f"http://127.0.0.1:{FP}/img/1.jpg", "nsfwLevel": 4, "type": "image"}],
                   "files": [{"name": "style_pack_v2.safetensors", "sizeKB": 150000, "primary": True, "type": "Model", "downloadUrl": f"http://127.0.0.1:{FP}/civ/api/download/models/111"},
                             {"name": "readme.txt", "sizeKB": 1, "type": "Model"}]}]},
                {"id": 12, "name": "No files", "type": "LORA", "modelVersions": [{"id": 1, "files": []}]}],
                "metadata": {"nextPage": "x", "nextCursor": "CUR1"}})
        if self.path.startswith("/hf/api/models/"):
            return self.jj({"id": "u/r", "gated": False, "tags": ["lora"], "siblings": [{"rfilename": "README.md"}, {"rfilename": "sub/my_lora.safetensors", "size": 52428800}, {"rfilename": "ae.safetensors", "size": 335544320}]})
        if self.path.startswith("/hf/api/models"):
            return self.jj([{"id": "u/r", "downloads": 55, "likes": 3, "tags": ["lora", "x"]}])
        if self.path.startswith("/hf/u/r/resolve"):
            self.send_response(302); self.send_header("Location", f"http://127.0.0.1:{FP}/cdn/f.safetensors"); self.end_headers(); return
        if self.path.startswith("/cdn/"):
            self.send_response(200); self.send_header("Content-Length", "5"); self.send_header("Content-Disposition", 'attachment; filename="f.safetensors"'); self.end_headers(); self.wfile.write(b"12345"); return
        if self.path.startswith("/gated"):
            return self.jj({}, 403)
        if self.path.startswith("/html"):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b"<html>login</html>"); return
        rng = self.headers.get("Range"); start = int(rng.split("=")[1].split("-")[0]) if rng else 0
        data = PAYLOAD[start:]
        self.send_response(206 if rng else 200)
        self.send_header("Content-Length", str(len(data))); self.send_header("Content-Disposition", 'attachment; filename="civitai_style_v2.safetensors"')
        self.end_headers(); self.wfile.write(data)

def serve(h, port):
    s = ThreadingHTTPServer(("127.0.0.1", port), h); threading.Thread(target=s.serve_forever, daemon=True).start(); return s
serve(Comfy, CP); serve(Ollama, OP); serve(Files, FP)
hub.GPU = {"name": "Test GPU", "vram_gb": 12}
srv = ThreadingHTTPServer(("127.0.0.1", PORT), hub.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
threading.Thread(target=hub.worker, daemon=True).start(); hub.ws_start()
B = f"http://127.0.0.1:{PORT}"

def req(path, body=None, headers=None, raw=False):
    r = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=60) as f: d = f.read()
    except urllib.error.HTTPError as e:
        return (e.code, e.read())
    return d if raw else json.loads(d)

def png_url(im, mode="RGB"):
    b = io.BytesIO(); im.convert(mode).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

def job(p, expect_ok=True):
    r = req("/api/job", p); jid = r["id"]
    for _ in range(240):
        j = req("/api/job/" + jid)
        if j["state"] in ("done", "error"): break
        time.sleep(0.25)
    if expect_ok: assert j["state"] == "done", j
    return j

def out_img(url): return Image.open(io.BytesIO(req(url, raw=True)))
