"""모델 계열 판별/수동 지정, 올인원 FLUX, 크기 입력, 출력 폴더 열기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, io, json, struct, sys
sys.path.insert(0, BASE + "/test")
from mocks import *
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import modelinfo
from PIL import Image
ok = lambda m: print("PASS", m)
def st(path, keys):
    meta = {k: {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]} for k in keys}; b = json.dumps(meta).encode()
    Path(path).write_bytes(struct.pack("<Q", len(b)) + b + b"\0\0")
CK, DM = M / "checkpoints", M / "diffusion_models"; DM.mkdir(exist_ok=True)
st(DM / "krea2_unet.safetensors", ["double_blocks.0.img_attn.qkv.weight", "single_blocks.0.linear1.weight", "guidance_in.in_layer.weight"])
st(DM / "mystery_model.safetensors", ["double_blocks.0.a", "single_blocks.0.b", "distilled_guidance_layer.in_proj.weight"])
st(CK / "flux_allinone_fp8.safetensors", ["model.diffusion_model.double_blocks.0.x", "model.diffusion_model.single_blocks.0.y", "text_encoders.t5xxl.x", "vae.decoder.x"])
st(CK / "my_sdxl.safetensors", ["model.diffusion_model.input_blocks.0.0.weight", "conditioner.embedders.1.model.x", "first_stage_model.x"])
st(DM / "sdxl_unet_only.safetensors", ["model.diffusion_model.input_blocks.0.0.weight", "conditioner.embedders.1.x"])
L = req("/api/lists")
assert "krea2_unet.safetensors" in L["krea2models"] and "krea2_unet.safetensors" not in L["fluxmodels"] and "mystery_model.safetensors" in L["chromamodels"] and "mystery_model.safetensors" not in L["fluxmodels"], L
assert "ckpt::flux_allinone_fp8.safetensors" in L["fluxmodels"] and "flux_allinone_fp8.safetensors" not in L["checkpoints"] and "my_sdxl.safetensors" in L["checkpoints"]
assert "sdxl_unet_only.safetensors" not in L["fluxmodels"] + L["chromamodels"]
assert L["families"]["diffusion_models/krea2_unet.safetensors"] == {"family": "krea2", "all_in_one": False, "how": "name"}   # Krea 2 는 FLUX 와 구조가 달라 이름으로 먼저 판단
ok("families read from the safetensors header: FLUX/Chroma/SDXL land in the right tabs; all-in-one FLUX checkpoint listed for the FLUX tab")
# 수동 지정
assert req("/api/family", {"folder": "diffusion_models", "name": "krea2_unet.safetensors", "family": "chroma"})["ok"]
L = req("/api/lists"); assert "krea2_unet.safetensors" in L["chromamodels"] and "krea2_unet.safetensors" not in L["fluxmodels"] and L["families"]["diffusion_models/krea2_unet.safetensors"]["how"] == "manual"
assert req("/api/family", {"folder": "diffusion_models", "name": "krea2_unet.safetensors", "family": "hidden"})["ok"]; assert "krea2_unet.safetensors" not in req("/api/lists")["fluxmodels"]
assert req("/api/family", {"folder": "diffusion_models", "name": "krea2_unet.safetensors", "family": "auto"})["ok"] and "krea2_unet.safetensors" in req("/api/lists")["krea2models"]
assert req("/api/family", {"folder": "diffusion_models", "name": "krea2_unet.safetensors", "family": "flux"})["ok"] and "krea2_unet.safetensors" in req("/api/lists")["fluxmodels"]
assert req("/api/family", {"folder": "diffusion_models", "name": "krea2_unet.safetensors", "family": "auto"})["ok"]
assert "error" in req("/api/family", {"folder": "loras", "name": "x", "family": "flux"}) and "error" in req("/api/family", {"folder": "checkpoints", "name": "../x", "family": "flux"}) and "error" in req("/api/family", {"folder": "checkpoints", "name": "my_sdxl.safetensors", "family": "evil"})
m = req("/api/manage"); e = [x for x in m["folders"]["diffusion_models"] if x["name"] == "krea2_unet.safetensors"][0]; assert e["family"] == "krea2" and e["override"] == "auto"
ok("manual family: move a file between tabs, hide it, reset to auto; bad input refused; manage list shows family info")
# 올인원 FLUX 생성
(M / "vae").mkdir(exist_ok=True)
j = job({"kind": "gen", "gengine": "flux", "fx_model": "ckpt::flux_allinone_fp8.safetensors", "prompt": "a cat", "w": "1000", "h": "1008"}); wf = SUBMITTED[-1]; cls = [n["class_type"] for n in wf.values()]
assert "CheckpointLoaderSimple" in cls and "UNETLoader" not in cls and "DualCLIPLoader" not in cls and "FluxGuidance" in cls
enc = [n for n in wf.values() if n["class_type"] == "CLIPTextEncode"][0]["inputs"]; ck = [k for k, v in wf.items() if v["class_type"] == "CheckpointLoaderSimple"][0]; assert enc["clip"] == [ck, 1]
assert out_img(j["images"][0]).size == (1000, 1008), out_img(j["images"][0]).size
ok("all-in-one FLUX checkpoint: CheckpointLoaderSimple feeds model/CLIP/VAE, FLUX guidance kept, odd sizes rounded to 16")
# 아무 비율
for w, h in ((1000, 600), (777, 1111), (2048, 256)):
    j = job({"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "x", "w": str(w), "h": str(h)}); sz = out_img(j["images"][0]).size; assert sz == (w, h), (sz, w, h)
ok("any width x height works on the server (rounded down to a multiple of 8)")
# 출력 폴더 열기
opened = []; hub.open_folder = lambda p, select=None: opened.append((str(p), str(select) if select else None))
u = j["images"][0]; r = req("/api/open", {"file": u}); assert r["ok"] and opened[-1][0].endswith("생성") and opened[-1][1].endswith(u.rsplit("/", 1)[1]), opened
assert req("/api/open", {"which": "outputs"})["ok"] and opened[-1] == (str(hub.OUT), None)
req("/api/open", {"file": "/out/../../etc/passwd"}); assert str(opened[-1][0]).startswith(str(hub.OUT)), opened[-1]
ok("open-folder: result file -> its own outputs sub-folder with the file selected; plain 'outputs' still works; traversal stays inside outputs")
# ── Krea 2 ──
(M / "text_encoders").mkdir(exist_ok=True); (M / "vae").mkdir(exist_ok=True)
(DM / "krea2_turbo_fp8_scaled.safetensors").write_bytes(b"x"); (DM / "krea2_raw_fp8_scaled.safetensors").write_bytes(b"x")
for n in ("qwen3vl_4b_fp8_scaled.safetensors",): (M / "text_encoders" / n).write_bytes(b"x")
L = req("/api/lists"); assert {"krea2_turbo_fp8_scaled.safetensors", "krea2_raw_fp8_scaled.safetensors"} <= set(L["krea2models"]) and L["krea2_ready"], L["krea2models"]
assert not any("krea2" in x for x in L["fluxmodels"] + L["chromamodels"])
hub.caps(True)
j = job({"kind": "gen", "gengine": "krea2", "fx_model": "krea2_turbo_fp8_scaled.safetensors", "prompt": "a cat", "w": "1000", "h": "1008", "fx_steps": "8", "fx_cfg": "1", "fx_sampler": "euler", "fx_scheduler": "simple"}); wf = SUBMITTED[-1]
byc = lambda c: [n["inputs"] for n in wf.values() if n["class_type"] == c]
assert byc("CLIPLoader")[0]["type"] == "krea2" and byc("CLIPLoader")[0]["clip_name"] == "qwen3vl_4b_fp8_scaled.safetensors" and byc("VAELoader")[0]["vae_name"] == "qwen_image_vae.safetensors"
assert byc("UNETLoader")[0]["unet_name"] == "krea2_turbo_fp8_scaled.safetensors" and "DualCLIPLoader" not in [n["class_type"] for n in wf.values()] and "FluxGuidance" not in [n["class_type"] for n in wf.values()]
assert byc("EmptyLatentImage") and not byc("EmptySD3LatentImage") and byc("ConditioningZeroOut") and byc("KSampler")[0]["steps"] == 8 and byc("KSampler")[0]["cfg"] == 1.0
assert out_img(j["images"][0]).size == (1000, 1008)
ok("Krea 2 Turbo graph: CLIPLoader type krea2 + Qwen3-VL encoder + Qwen VAE, EmptyLatentImage, zeroed negative, 8 steps / cfg 1")
j = job({"kind": "gen", "gengine": "krea2", "fx_model": "krea2_raw_fp8_scaled.safetensors", "prompt": "a cat", "negative": "blurry", "fx_steps": "30", "fx_cfg": "4"}); wf = SUBMITTED[-1]
assert not byc("ConditioningZeroOut") and sorted(n["text"] for n in byc("CLIPTextEncode")) == ["a cat", "blurry"] and byc("KSampler")[0]["cfg"] == 4.0
ok("Krea 2 Raw with CFG > 1 uses a real negative prompt")
j = job({"kind": "gen", "gengine": "krea2", "fx_model": "krea2_turbo_fp8_scaled.safetensors", "prompt": "x", "k2_te": "nope.safetensors"}); assert j["state"] == "done"
os.remove(M / "text_encoders/qwen3vl_4b_fp8_scaled.safetensors")
j = job({"kind": "gen", "gengine": "krea2", "fx_model": "krea2_turbo_fp8_scaled.safetensors", "prompt": "x"}, expect_ok=False); assert j["state"] == "error" and "Qwen3-VL" in j["error"], j
(M / "text_encoders/qwen3vl_4b_fp8_scaled.safetensors").write_bytes(b"x")
STATE["clip_types"] = ["stable_diffusion", "flux"]; hub.caps(True)
j = job({"kind": "gen", "gengine": "krea2", "fx_model": "krea2_turbo_fp8_scaled.safetensors", "prompt": "x"}, expect_ok=False); assert j["state"] == "error" and "0.26" in j["error"] and "update" in j["error"], j
del STATE["clip_types"]; hub.caps(True)
ok("Krea 2: missing text encoder is named; an old ComfyUI without the 'krea2' loader type gets an update instruction instead of the meta-tensor crash")
# 업스케일 디테일 재생성을 FLUX 계열 모델로
src = Image.new("RGB", (200, 150), (90, 120, 200))
n0 = len(SUBMITTED); j = job({"kind": "up", "mode": "refine", "scale": "2", "upm": "RealESRGAN_x4plus.pth", "image": png_url(src), "rengine": "krea2", "fx_model": "krea2_turbo_fp8_scaled.safetensors", "fx_steps": "8", "fx_cfg": "1", "tile": "512", "rdenoise": "0.3", "overlap": "64"})
tiles = SUBMITTED[n0:]; fl = [t for t in tiles if any(n["class_type"] == "UNETLoader" for n in t.values())]
assert fl, "no FLUX-family refine graph"; g = fl[0]; ks = [n["inputs"] for n in g.values() if n["class_type"] == "KSampler"][0]
assert ks["denoise"] == 0.3 and any(n["class_type"] == "VAEEncode" for n in g.values()) and [n["inputs"]["type"] for n in g.values() if n["class_type"] == "CLIPLoader"] == ["krea2"]
ok("upscale 'detail regeneration' can use a Krea 2 / FLUX-family model (tile img2img at low denoise)")
print("FAMILY TESTS PASSED")
