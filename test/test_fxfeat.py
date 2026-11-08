"""2.3: 업스케일 임의 배율·줄이기, 얼굴·손 보정과 참고 이미지 그리기를 FLUX.1 · Krea 2 · Chroma 모델로."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import io, os, sys, json, base64, urllib.request
os.environ["TEST_HUB_PORT"] = "17930"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
ok = lambda m: print("PASS", m)
def png_url(im):
    b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def classes(wf): return [n["class_type"] for n in wf.values()]
def nodes(wf, c): return [n["inputs"] for n in wf.values() if n["class_type"] == c]
def idof(wf, c): return [k for k, v in wf.items() if v["class_type"] == c]
def last(): return SUBMITTED[-1]

# ───────────── 1. 업스케일: 임의 배율, 줄이기 ─────────────
src = png_url(Image.new("RGB", (300, 200), (50, 60, 70)))
for sc, want in (("2", (600, 400)), ("1.5", (450, 300)), ("2.5", (750, 500)), ("6", (1800, 1200)), ("4", (1200, 800)), ("3배", (900, 600)), ("1,5", (450, 300))):
    n0 = len(SUBMITTED); j = job({"kind": "up", "image": src, "scale": sc, "upm": "RealESRGAN_x4plus.pth"})
    assert out_img(j["images"][0]).size == want and len(SUBMITTED) == n0 + 1, (sc, out_img(j["images"][0]).size)
    assert "ImageScaleBy" not in classes(last()), "scaling to the wanted size is done by the hub, not by a fixed 0.5 node"
ok("upscale: any factor (2, 1.5, 2.5, 6, 3배, 1,5) gives exactly that size; the model graph is the same for all")
n0 = len(SUBMITTED); j = job({"kind": "up", "image": src, "scale": "0.5", "embed": "on"})
assert out_img(j["images"][0]).size == (150, 100) and len(SUBMITTED) == n0, "downscale must not use ComfyUI"
side = meta.read(req(j["images"][0], raw=True)); assert side["file"]["w"] == 150, side
ok("downscale (0.5): done without ComfyUI or any upscale model, size halved")
j = job({"kind": "up", "image": src, "scale": "1"}); assert out_img(j["images"][0]).size == (300, 200); ok("1x leaves the size unchanged")
j = job({"kind": "up", "image": src, "scale": "0.33"}); assert out_img(j["images"][0]).size == (99, 66); ok("odd factors round to whole pixels")
for bad, msg in (("abc", "숫자"), ("0", "사이"), ("0.05", "사이"), ("9", "사이"), ("-2", "사이")):
    j = job({"kind": "up", "image": src, "scale": bad}, expect_ok=False); assert j["state"] == "error" and msg in j["error"], (bad, j)
ok("bad factors (text, 0, <0.1, >8, negative) get a clear message")
j = job({"kind": "up", "image": png_url(Image.new("RGB", (1200, 900))), "scale": "8"}, expect_ok=False); assert j["state"] == "error" and "8192" in j["error"], j
j = job({"kind": "up", "image": png_url(Image.new("RGB", (100, 12))), "scale": "0.5"}, expect_ok=False); assert j["state"] == "error" and "너무 작아" in j["error"], j
ok("too-large and too-small results are refused with the resulting size")
# 모델이 없어도 줄이기는 된다
hub_files = hub.files
hub.files = lambda sub: [] if sub == "upscale_models" else hub_files(sub)
j = job({"kind": "up", "image": src, "scale": "0.5"}); assert out_img(j["images"][0]).size == (150, 100)
j = job({"kind": "up", "image": src, "scale": "2"}, expect_ok=False); assert j["state"] == "error" and "업스케일 모델" in j["error"], j
hub.files = hub_files
ok("without an upscale model: shrinking works, enlarging explains what to install")
# 일괄 처리
from pathlib import Path
SRCD = TMP / "bphotos"; SRCD.mkdir(); Image.new("RGB", (400, 300), (9, 9, 9)).save(SRCD / "a.png")
def run_batch(o):
    r = req("/api/job", {"kind": "batch", **o}); import time as _t
    for _ in range(240):
        j = req("/api/job/" + r["id"])
        if j["state"] in ("done", "error", "cancelled"): return j
        _t.sleep(0.25)
n0 = len(SUBMITTED); j = run_batch({"op": "upscale", "folder": str(SRCD), "scale": "0.5"}); outs = list((hub.OUT / "일괄").glob("a_축소x0.5*.png"))
assert j["state"] == "done" and j["batch"]["ok"] == 1 and outs and Image.open(outs[0]).size == (200, 150) and len(SUBMITTED) == n0, j
j = run_batch({"op": "upscale", "folder": str(SRCD), "scale": "1.5"}); outs = list((hub.OUT / "일괄").glob("a_업스케일x1.5*.png")); assert j["state"] == "done" and outs and Image.open(outs[0]).size == (600, 450), j
ok("batch: shrinking (no engine) and a fractional enlarge both name files by factor and give the right size")

# ───────────────── 2. 얼굴·손 보정: FLUX.1 · Krea 2 · Chroma ─────────────────
(M / "diffusion_models" / "krea2_turbo_fp8_scaled.safetensors").write_bytes(b"x")
(M / "text_encoders" / "qwen3vl_4b_fp8_scaled.safetensors").write_bytes(b"x")
(M / "diffusion_models" / "flux1-kontext-dev_fp8.safetensors").write_bytes(b"x")
img = png_url(Image.new("RGB", (640, 480), (120, 80, 60)))
det = {"kind": "feat", "feature": "detailer", "image": img, "target": "both", "denoise": "0.35", "prompt": "blue eyes", "seed": "5"}
for sel, fam, steps, cfg in (("fx:flux:flux1-krea-dev_fp8_scaled.safetensors", "flux", 20, 1.0), ("fx:krea2:krea2_turbo_fp8_scaled.safetensors", "krea2", 8, 1.0), ("fx:chroma:Chroma1-HD.safetensors", "chroma", 26, 4.0)):
    j = job({**det, "ckpt": sel}); wf = last()
    fd = nodes(wf, "FaceDetailer"); assert len(fd) == 2 and "CheckpointLoaderSimple" not in classes(wf), (sel, classes(wf))
    assert all(abs(n["denoise"] - 0.35) < 1e-6 and n["steps"] == steps and n["cfg"] == cfg and n["seed"] == 5 for n in fd), (sel, fd[0])
    assert fd[1]["image"][0] == [k for k, v in wf.items() if v["class_type"] == "FaceDetailer"][0] and idof(wf, "UNETLoader"), "passes chained, model is a UNET"
    assert [n["model_name"] for n in nodes(wf, "UltralyticsDetectorProvider")] == ["bbox/face_yolov8m.pt", "bbox/hand_yolov8s.pt"]
    texts = [n["text"] for n in nodes(wf, "CLIPTextEncode")]; assert any("detailed face" in t and "blue eyes" in t for t in texts) and any("detailed hands" in t for t in texts), texts
    ids = set(wf)
    assert all(n["clip"][0] in ids and n["positive"][0] in ids and n["negative"][0] in ids and n["model"][0] in ids for n in fd)
    if fam == "flux":
        assert len(idof(wf, "FluxGuidance")) >= 2 and wf[fd[0]["negative"][0]]["class_type"] == "ConditioningZeroOut" and wf[fd[0]["positive"][0]]["class_type"] == "FluxGuidance", "FLUX: guidance on positive, zero-out negative, one conditioning per part"
        assert fd[0]["positive"] != fd[1]["positive"]
    if fam == "chroma":
        ng = wf[fd[0]["negative"][0]]; assert ng["class_type"] == "CLIPTextEncode" and ng["inputs"]["text"].strip(), "Chroma uses a real negative prompt"
    if fam == "krea2":
        assert nodes(wf, "CLIPLoader")[0]["type"] == "krea2"
    ok(f"detailer with {fam}: two FaceDetailer passes chained on a {fam} UNET stack, steps {steps} / cfg {cfg}, conditioning per part")
j = job({**det, "ckpt": "noobai_xl_v11.safetensors", "target": "face"}); assert "CheckpointLoaderSimple" in classes(last()); ok("detailer still works with an SDXL checkpoint")
j = job({**det, "ckpt": "fx:flux:flux1-krea-dev_fp8_scaled.safetensors", "target": "hand"}); assert len(nodes(last(), "FaceDetailer")) == 1; ok("detailer: single part with a FLUX model")
F = {f["id"]: f for f in req("/api/features")}
assert F["detailer"]["needs"]["lists"] == ["anymodels"] and [x for x in F["detailer"]["fields"] if x["name"] == "ckpt"][0]["list"] == "models"; ok("detailer model list now offers every model family")

# ───────────────── 3. 참고 이미지 그리기: SDXL 외 모델 ─────────────────
ref = png_url(Image.new("RGB", (512, 768), (200, 100, 50)))
rb = {"kind": "feat", "feature": "ipadapter", "image": ref, "prompt": "a woman standing on a city street", "mode": "style", "weight": "0.6", "w": "832", "h": "1216", "seed": "7"}
# (a) Krea 2
j = job({**rb, "ckpt": "fx:krea2:krea2_turbo_fp8_scaled.safetensors"}, expect_ok=False); assert j["state"] == "error" and "스타일 참조" in j["error"] and "설치" in j["error"], j
(M / "loras" / "krea2_style_reference.safetensors").write_bytes(b"x")
j = job({**rb, "ckpt": "fx:krea2:krea2_turbo_fp8_scaled.safetensors", "kweight": "0.9"}); wf = last()
assert "IPAdapter" not in classes(wf) and "CheckpointLoaderSimple" not in classes(wf)
lo = nodes(wf, "LoraLoaderModelOnly"); assert len(lo) == 1 and lo[0]["lora_name"] == "krea2_style_reference.safetensors" and lo[0]["strength_model"] == 0.9, lo
ms = nodes(wf, "ModelSamplingFlux")[0]; assert (ms["max_shift"], ms["base_shift"], ms["width"], ms["height"]) == (1.15, 0.5, 832, 1216), ms
te = nodes(wf, "TextEncodeQwenImageEditPlus")[0]; assert wf[te["clip"][0]]["class_type"] == "CLIPLoader" and wf[te["image1"][0]]["class_type"] == "LoadImage" and "city street" in te["prompt"], te
rm = nodes(wf, "FluxKontextMultiReferenceLatentMethod")[0]; assert rm["reference_latents_method"] == "index_timestep_zero" and wf[rm["conditioning"][0]]["class_type"] == "TextEncodeQwenImageEditPlus"
ks = nodes(wf, "KSampler")[0]; assert (ks["steps"], ks["cfg"], ks["denoise"], ks["sampler_name"], ks["scheduler"]) == (8, 1.0, 1.0, "euler", "simple") and wf[ks["model"][0]]["class_type"] == "ModelSamplingFlux"
assert wf[ks["negative"][0]]["class_type"] == "ConditioningZeroOut" and wf[ks["latent_image"][0]]["inputs"]["width"] == 832
assert wf[ms["model"][0]]["class_type"] == "LoraLoaderModelOnly" and wf[lo[0]["model"][0]]["class_type"] == "UNETLoader"
assert out_img(j["images"][0]).size == (832, 1216); ok("Krea 2 reference: UNET → style-reference LoRA → ModelSamplingFlux, reference through TextEncodeQwenImageEditPlus + multi-reference method, 8 steps, zero-out negative")
j = job({**rb, "ckpt": "fx:krea2:krea2_turbo_fp8_scaled.safetensors", "mode": "face"}); assert any("얼굴" in w for w in (j.get("warn") or [])), j; ok("Krea 2 face mode explains it uses style reference")
STATE["missing"].add("FluxKontextMultiReferenceLatentMethod"); hub.caps(force=True)
j = job({**rb, "ckpt": "fx:krea2:krea2_turbo_fp8_scaled.safetensors"}, expect_ok=False); assert "FluxKontextMultiReferenceLatentMethod" in j["error"] and "업데이트" in j["error"], j
STATE["missing"].discard("FluxKontextMultiReferenceLatentMethod"); hub.caps(force=True); ok("Krea 2 reference with an old ComfyUI: clear update message")
# (b) FLUX.1 + Redux
j = job({**rb, "ckpt": "fx:flux:flux1-krea-dev_fp8_scaled.safetensors"}, expect_ok=False); assert j["state"] == "error" and "Redux" in j["error"] and "sigclip" in j["error"], j
STATE["clipvis"] = ["sigclip_vision_patch14_384.safetensors"]; STATE["styles"] = ["flux1-redux-dev.safetensors"]; hub.caps(force=True)
j = job({**rb, "ckpt": "fx:flux:flux1-krea-dev_fp8_scaled.safetensors"}); wf = last()
assert "IPAdapter" not in classes(wf) and nodes(wf, "CLIPVisionLoader")[0]["clip_name"] == "sigclip_vision_patch14_384.safetensors" and nodes(wf, "StyleModelLoader")[0]["style_model_name"] == "flux1-redux-dev.safetensors"
sa = nodes(wf, "StyleModelApply")[0]; assert sa["strength"] == 0.6 and sa["strength_type"] == "multiply" and wf[sa["clip_vision_output"][0]]["class_type"] == "CLIPVisionEncode" and wf[sa["conditioning"][0]]["class_type"] == "CLIPTextEncode", sa
fg = nodes(wf, "FluxGuidance")[0]; assert wf[fg["conditioning"][0]]["class_type"] == "StyleModelApply", "Redux conditioning goes through FluxGuidance"
assert nodes(wf, "EmptySD3LatentImage")[0]["width"] == 832 and nodes(wf, "KSampler")[0]["denoise"] == 1.0 and "ReferenceLatent" not in classes(wf)
assert out_img(j["images"][0]).size == (832, 1216); ok("FLUX.1 reference: Redux (CLIP Vision encode → StyleModelApply → FluxGuidance), strength from the slider")
j = job({**rb, "ckpt": "fx:flux:flux1-krea-dev_fp8_scaled.safetensors", "mode": "face"}); assert any("Kontext" in w for w in (j.get("warn") or [])), j; ok("plain FLUX.1 face mode warns that Kontext follows faces better")
# (c) FLUX Kontext: 참고 이미지를 조건으로
j = job({**rb, "ckpt": "fx:flux:flux1-kontext-dev_fp8.safetensors", "mode": "face"}); wf = last()
assert "StyleModelApply" not in classes(wf) and idof(wf, "ReferenceLatent") and idof(wf, "FluxKontextImageScale")
assert nodes(wf, "EmptySD3LatentImage")[0]["width"] == 832 and nodes(wf, "KSampler")[0]["denoise"] == 1.0
t = [n["text"] for n in nodes(wf, "CLIPTextEncode")][0]; assert "same person" in t and "city street" in t, t
j = job({**rb, "ckpt": "fx:flux:flux1-kontext-dev_fp8.safetensors", "mode": "style"}); assert "art style" in [n["text"] for n in nodes(last(), "CLIPTextEncode")][0]
ok("FLUX Kontext reference: reference image as ReferenceLatent on an empty canvas at the chosen size; face/style wording added to the prompt")
# (d) Chroma, SDXL
j = job({**rb, "ckpt": "fx:chroma:Chroma1-HD.safetensors"}, expect_ok=False); assert j["state"] == "error" and "Chroma" in j["error"]; ok("Chroma is refused with an explanation")
f = [x for x in F["ipadapter"]["fields"] if x["name"] == "ckpt"][0]; assert f["list"] == "models" and f["exclude"] == ["chroma"] and F["ipadapter"]["needs"]["lists"] == ["anymodels"] and F["ipadapter"]["needs"].get("alt"); ok("feature spec: model list without Chroma, IPAdapter-extension note")
# IPAdapter 확장이 없어도 FLUX·Krea 2 는 막히지 않고, SDXL 만 막힘
STATE["missing"].update({"IPAdapter", "IPAdapterUnifiedLoader"}); hub.caps(force=True)
job({**rb, "ckpt": "fx:krea2:krea2_turbo_fp8_scaled.safetensors"}); job({**rb, "ckpt": "fx:flux:flux1-kontext-dev_fp8.safetensors"})
j = job({**rb, "ckpt": "noobai_xl_v11.safetensors"}, expect_ok=False); assert j["state"] == "error" and "IPAdapter" in j["error"], j
STATE["missing"] -= {"IPAdapter", "IPAdapterUnifiedLoader"}; hub.caps(force=True)
ok("without the IPAdapter extension FLUX/Krea 2 still run; SDXL gets the install message")
j = job({**rb, "ckpt": "noobai_xl_v11.safetensors"}); assert "IPAdapter" in classes(last()); ok("SDXL IP-Adapter path unchanged")

# ───────────────── 4. 카탈로그 ─────────────────
cat = {m["id"]: m for m in req("/api/catalog")["image"]}
r = cat["flux-redux"]; assert [f["dir"] for f in r["files"]] == ["clip_vision", "style_models"] and "HuggingFace" in r["desc"]
k = cat["krea2-style-reference"]; assert k["files"][0]["dir"] == "loras" and k["files"][0]["url"].endswith("krea2_style_reference.safetensors")
assert "style_models" in hub.FOLDERS; ok("catalog has FLUX.1 Redux (CLIP Vision + style model, gated note) and the Krea 2 style-reference LoRA; style_models is an allowed folder")
print("ALL OK")
