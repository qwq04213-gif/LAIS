"""4.2: 새 엔진 — LTX-2.5(영상 + 소리), SeedVR2 업스케일, Z-Image-Turbo·FLUX 3 Klein 생성, Depth Anything 3, Stable Audio 3,
MOSS 편집·Qwen 2.1 Turbo 편집. 그래프가 ComfyUI 공식 예시와 같은 짜임인지, 없는 파일 안내, 추천 모델 목록."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17947"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def wait(jid):
    for _ in range(600):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def cls(c, g=None): return [v["inputs"] for v in (g or SUBMITTED[-1]).values() if v["class_type"] == c]
def node(ref, g=None): return (g or SUBMITTED[-1])[ref[0]]["class_type"]
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
def png(w=300, h=200):
    b = io.BytesIO(); Image.new("RGB", (w, h), (10, 120, 200)).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
CAT = {m["id"]: m for k in ("llm", "image") for m in json.loads((Path(BASE) / "LocalAI-Studio/hub/models.json").read_text(encoding="utf-8"))[k]}

# ── LTX-2.5 ──
j = job({"kind": "vid", "wan_ver": "ltx25", "prompt": "a cat walking"}); assert j["state"] == "error" and "LTX-2.5" in j["error"] and j.get("need") == ["ltx25"], j
touch(*[f["dir"] + "/" + f["url"].rsplit("/", 1)[1] for f in CAT["ltx25"]["files"]])
assert json.load(urllib.request.urlopen(B + "/api/lists"))["vidmore"]["ltx25"]
j = job({"kind": "vid", "wan_ver": "ltx25", "prompt": "a cat walking", "size": "1280x720", "sec": "5", "fps": "24", "seed": 3}); assert j["state"] == "done" and j["images"][0].endswith(".mp4"), j
e = cls("EmptyLTXVLatentVideo")[0]; assert (e["width"], e["height"], e["length"]) == (640, 352, 121), e          # 절반 크기(64 배수로 맞춘 1280×704), 5초×24+1
sig = sorted(x["sigmas"] for x in cls("ManualSigmas")); assert sig == ["0.85, 0.7250, 0.4219, 0.0", "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"]
assert all(x["sampler_name"] == "euler_ancestral" for x in cls("KSamplerSelect")) and len(cls("SamplerCustomAdvanced")) == 2 and not cls("LTXVImgToVideoInplace")
assert [x["noise_seed"] for x in cls("RandomNoise")] == [3, 4] and all(x["video_cfg"] == 1.0 for x in cls("LTXVDualCFGGuider"))
assert cls("CLIPLoader")[0]["type"] == "ltxv" and node(cls("CreateVideo")[0]["audio"]) == "LTXVAudioVAEDecode" and cls("LTXVLatentUpsampler")
assert "ltx-2.5" not in json.dumps(json.load(urllib.request.urlopen(B + "/api/lists"))["fluxmodels"])
j = job({"kind": "vid", "wan_ver": "ltx25", "prompt": "a cat walking", "image": png(3000, 1500), "size": "1280x720"}); assert j["state"] == "done", j
ii = cls("LTXVImgToVideoInplace"); assert [x["strength"] for x in ii] == [0.7, 1.0] and node(ii[0]["image"]) == "LTXVPreprocess" and cls("LTXVPreprocess")[0]["img_compression"] == 18
STATE["missing"].add("LTXVDualCFGGuider"); hub._CAPS["t"] = 0
j = job({"kind": "vid", "wan_ver": "ltx25", "prompt": "x"}); assert j["state"] == "error" and "LTXVDualCFGGuider" in j["error"], j
STATE["missing"].discard("LTXVDualCFGGuider"); hub._CAPS["t"] = 0
ok("LTX-2.5: missing files → install hint; official 2-stage graph (half size → latent x2 → refine), sound decoded into the video, start image path")
# ── SeedVR2 ──
assert not any("SeedVR2" in x for x in json.load(urllib.request.urlopen(B + "/api/lists"))["upscalers"])
touch(*[f["dir"] + "/" + f["url"].rsplit("/", 1)[1] for f in CAT["seedvr2"]["files"]], "upscale_models/RealESRGAN_x4plus.pth")
ups = json.load(urllib.request.urlopen(B + "/api/lists"))["upscalers"]; assert "SeedVR2 3B (AI 복원)" in ups and "SeedVR2 7B (AI 복원)" not in ups, ups
j = job({"kind": "up", "image": png(400, 300), "upm": "SeedVR2 3B (AI 복원)", "scale": "2"}); assert j["state"] == "done", j
g = SUBMITTED[-1]; sc = cls("ImageScale")[0]; assert (sc["width"], sc["height"]) == (800, 600) and cls("KSampler")[0]["steps"] == 1 and cls("KSampler")[0]["cfg"] == 1.0
assert node(cls("SeedVR2PostProcessing")[0]["original_resized_images"]) == "ImageScale" and cls("VAEEncodeTiled")[0]["temporal_size"] == 4096
assert cls("UNETLoader")[0]["unet_name"] == "seedvr2_3b_int8_convrot.safetensors" and not cls("UpscaleModelLoader")
j = job({"kind": "up", "image": png(1500, 1000), "upm": "SeedVR2 3B (AI 복원)", "scale": "4"}); assert j["state"] == "done" and any("4096" in w for w in j["warn"]), j
sc = cls("ImageScale")[0]; assert max(sc["width"], sc["height"]) <= 4096
j = job({"kind": "up", "image": png(400, 300), "upm": "SeedVR2 7B (AI 복원)", "scale": "2"}); assert j["state"] == "error" and "SeedVR2 7B" in j["error"] and j.get("need") == ["seedvr2"], j
j = job({"kind": "up", "image": png(400, 300), "upm": "RealESRGAN_x4plus.pth", "scale": "2"}); assert j["state"] == "done" and cls("UpscaleModelLoader")
STATE["missing"].add("SeedVR2Conditioning"); hub._CAPS["t"] = 0
j = job({"kind": "up", "image": png(400, 300), "upm": "SeedVR2 3B (AI 복원)", "scale": "2"}); assert j["state"] == "error" and "SeedVR2Conditioning" in j["error"], j
STATE["missing"].discard("SeedVR2Conditioning"); hub._CAPS["t"] = 0
ok("SeedVR2: listed with the upscale models once installed, official 1-step graph at the target size, 4096px cap, missing 7B/nodes explained, ESRGAN still works")
# ── Z-Image-Turbo · FLUX 3 Klein ──
j = job({"kind": "gen", "gengine": "zimage", "prompt": "a cat"}); assert j["state"] == "error" and "Z-Image-Turbo" in j["error"] and j.get("need") == ["z-image-turbo"], j
touch(*[f["dir"] + "/" + f["url"].rsplit("/", 1)[1] for f in CAT["z-image-turbo"]["files"]])
L = json.load(urllib.request.urlopen(B + "/api/lists")); assert L["oxmodels"]["zimage"] == ["z_image_turbo_int8_convrot.safetensors"] and L["ox_ready"]["zimage"]
assert not any("z_image" in x for x in L["fluxmodels"] + L["chromamodels"])
j = job({"kind": "gen", "gengine": "zimage", "prompt": "a cat", "fx_steps": 8, "fx_cfg": 1, "fx_sampler": "res_multistep", "fx_scheduler": "simple", "w": 1024, "h": 768}); assert j["state"] == "done", j
k = cls("KSampler")[0]; assert (k["steps"], k["cfg"], k["sampler_name"]) == (8, 1.0, "res_multistep") and node(k["negative"]) == "ConditioningZeroOut"
assert cls("ModelSamplingAuraFlow")[0]["shift"] == 3.0 and cls("CLIPLoader")[0]["type"] == "lumina2" and cls("VAELoader")[0]["vae_name"] == "ae.safetensors"
touch(*[f["dir"] + "/" + f["url"].rsplit("/", 1)[1] for f in CAT["flux3-klein"]["files"] + CAT["flux3-klein-base"]["files"]])
L = json.load(urllib.request.urlopen(B + "/api/lists")); assert L["oxmodels"]["flux3k"][0] == "flux3-image-klein-int8-convrot.safetensors" and L["ox_ready"]["flux3k"]
assert not any("flux3" in x for x in L["fluxmodels"])
j = job({"kind": "gen", "gengine": "flux3k", "prompt": "a red fox", "fx_steps": 16, "fx_cfg": 1, "fx_sampler": "euler", "fx_scheduler": "simple"}); assert j["state"] == "done", j
k = cls("KSampler")[0]; assert (k["steps"], k["cfg"]) == (16, 1.0) and cls("CLIPLoader")[0]["type"] == "flux3" and cls("EmptyFlux2LatentImage") and cls("VAELoader")[0]["vae_name"] == "flux2-vae.safetensors"
j = job({"kind": "gen", "gengine": "flux3k", "fx_model": "flux3-image-klein-base-int8-convrot.safetensors", "prompt": "a red fox", "fx_steps": 16, "fx_cfg": 1}); assert j["state"] == "done", j
k = cls("KSampler")[0]; assert (k["steps"], k["cfg"]) == (50, 3.5) and any("50단계" in w for w in j["warn"]), (k, j.get("warn"))
STATE["clip_types"] = ["stable_diffusion", "flux"]; hub._CAPS["t"] = 0
j = job({"kind": "gen", "gengine": "flux3k", "prompt": "x"}); assert j["state"] == "error" and "지원하지 않아요" in j["error"], j
STATE.pop("clip_types"); hub._CAPS["t"] = 0
ok("Z-Image-Turbo / FLUX 3 Klein: official graphs (AuraFlow shift 3 + zeroed negative · flux3 encoder + Flux2 latent), base model gets 50 steps/CFG 3.5, kept out of FLUX lists, old ComfyUI explained")
# ── Depth Anything 3 ──
touch(*[f["dir"] + "/" + f["url"].rsplit("/", 1)[1] for f in CAT["depth-anything-3"]["files"]])
r = post("/api/control/prep", {"type": "depth", "image": png(900, 600)}); assert r.get("node") == "Depth Anything 3" and r["image"].startswith("data:image/png"), r
g = SUBMITTED[-1]; inf = cls("DA3Inference")[0]; assert inf["mode"] == "mono" and inf["resolution"] % 14 == 0 and 504 <= inf["resolution"] <= 1512
rd = cls("DA3Render")[0]; assert rd["output"] == "depth" and rd["output.normalization"] == "v2_style" and cls("LoadDA3Model")[0]["model_name"] == "depth_anything_3_mono_large.safetensors"
STATE["missing"].add("DA3Inference"); hub._CAPS["t"] = 0
r = post("/api/control/prep", {"type": "depth", "image": png()}); assert r.get("node") != "Depth Anything 3", r          # 노드가 없으면 예전 방식(확장 전처리기)
STATE["missing"].discard("DA3Inference"); hub._CAPS["t"] = 0
ok("depth maps prefer Depth Anything 3 (ComfyUI core nodes, mono, v2_style) and fall back to the old preprocessor")
# ── Stable Audio 3 ──
touch("checkpoints/stable_audio_open_1.0.safetensors", "text_encoders/t5_base.safetensors")
j = job({"kind": "music", "mengine": "sfx", "tags": "rain", "sfx_seconds": "90"}); assert j["state"] == "done" and cls("ConditioningStableAudio") and any("47초" in w for w in j["warn"]), j
touch(*[f["dir"] + "/" + f["url"].rsplit("/", 1)[1] for f in CAT["stable-audio-3"]["files"]])
j = job({"kind": "music", "mengine": "sfx", "tags": "rain", "sfx_seconds": "90"}); assert j["state"] == "done", j
k = cls("KSampler")[0]; assert (k["steps"], k["cfg"], k["sampler_name"]) == (8, 1.0, "lcm") and cls("EmptyLatentAudio")[0]["seconds"] == 90.0 and not cls("ConditioningStableAudio")
assert cls("CheckpointLoaderSimple")[0]["ckpt_name"] == "stable_audio_3_medium.safetensors" and cls("CLIPLoader")[0]["clip_name"] == "t5gemma_b_b_ul2.safetensors"
ok("Stable Audio 3: preferred when installed (8 steps lcm, up to 180s), Open 1.0 still works and explains its 47s limit")
# ── Qwen-Image 2.1 Turbo · MOSS 편집 ──
touch(*[f["dir"] + "/" + f["url"].rsplit("/", 1)[1] for f in CAT["qwen-image-turbo"]["files"]])
j = job({"kind": "edit", "engine": "qwen", "image": png(), "prompt": "make it night", "q_unet": "qwen_image_2.1_turbo_int8_convrot.safetensors"}); assert j["state"] == "done", j
assert cls("ManualSigmas")[0]["sigmas"].startswith("1.0, 0.978453") and cls("CFGGuider")[0]["cfg"] == 1.0 and not cls("KSampler")
j = job({"kind": "edit", "engine": "qwen", "image": png(), "prompt": "make it night"}); assert j["state"] == "done" and cls("KSampler") and not cls("ManualSigmas"), j
ok("Qwen-Image 2.1 Turbo edit: official 8-step sigma curve with CFGGuider; the regular model keeps KSampler")
j = job({"kind": "edit", "engine": "moss", "image": png(), "prompt": "black coat"}); assert j["state"] == "error" and "MOSS-Image 편집" in j["error"] and j.get("need")[0] == "moss-image-edit", j
touch(*[f["dir"] + "/" + f["url"].rsplit("/", 1)[1] for f in CAT["moss-image-edit"]["files"]])
j = job({"kind": "edit", "engine": "moss", "image": png(500, 300), "prompt": "black coat"}); assert j["state"] == "done", j
k = cls("KSampler")[0]; assert (k["steps"], k["cfg"], k["scheduler"]) == (30, 4.0, "normal")
te = cls("TextEncodeMOSSImageEdit"); assert len(te) == 2 and te[0]["edit_format"] == "Moss-Image-Edit" and node(te[0]["images.image_0"]) == "LoadImage"
assert cls("SkipLayerGuidanceDiTSimple")[0]["single_layers"] == "22" and cls("LoraLoaderModelOnly")[0]["lora_name"] == "moss_image_edit_lora_rank_64_bf16.safetensors"
lat = cls("EmptyFlux2LatentImage")[0]; assert lat["width"] % 16 == 0 and lat["height"] % 16 == 0 and abs(lat["width"] / lat["height"] - 5 / 3) < 0.05
assert cls("UNETLoader")[0]["unet_name"] == "moss_image_sft_int8_convrot.safetensors" and cls("VAELoader")[0]["vae_name"] == "flux2-vae_small.safetensors"
ok("MOSS-Image edit: official graph (SFT + edit LoRA + SLG 22, 30 steps CFG 4), aspect kept, missing files → install")
print("ALL OK")
