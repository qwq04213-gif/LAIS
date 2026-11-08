"""FLUX 공용 파일 찾기: 옛 이름 폴더(clip, unet), 흔한 파일 이름, 점검 화면의 FLUX 묶음."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, shutil
os.environ["TEST_HUB_PORT"] = "17908"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
for sub in ("text_encoders", "vae", "diffusion_models"):
    for f in list((M / sub).glob("*")): f.unlink()
assert hub.flux_parts()["t5"] is None and hub.flux_parts()["clip_l"] is None and hub.flux_parts()["vae"] is None; ok("nothing found when nothing is installed")
for d, f in (("clip", "google_t5-v1_1-xxl_encoderonly-fp8_e4m3fn.safetensors"), ("clip", "ViT-L-14-BEST-smooth-GmP-TE-only-HF-format.safetensors"), ("vae", "ae.safetensors"), ("unet", "flux1-dev-fp8.safetensors"), ("unet", "umt5_xxl_ignored_model.safetensors")):
    (M / d).mkdir(exist_ok=True); (M / d / f).write_bytes(b"x")
assert "flux1-dev-fp8.safetensors" in hub.files("diffusion_models") and "ViT-L-14-BEST-smooth-GmP-TE-only-HF-format.safetensors" in hub.files("text_encoders"); ok("files in the old clip/ and unet/ folders are listed like ComfyUI does")
fp = hub.flux_parts(); assert fp["t5"].startswith("google_t5") and fp["clip_l"].startswith("ViT-L") and fp["vae"] == "ae.safetensors", fp; ok("T5, CLIP-L (ViT-L name) and ae VAE are found")
assert hub.mpath("diffusion_models", "flux1-dev-fp8.safetensors") == M / "unet" / "flux1-dev-fp8.safetensors"; fam = hub.model_family("diffusion_models", "flux1-dev-fp8.safetensors"); assert fam[0] in ("flux", "unknown", "chroma"); ok("model info reads the file from the unet folder without crashing")
L = hub.lists(); assert L["flux_ready"] and "flux1-dev-fp8.safetensors" in L["diffusion"]; ok("lists(): flux_ready is true")
for f in (M / "text_encoders").glob("*"): f.unlink()
(M / "clip" / "qwen_2.5_vl_7b_fp8_scaled.safetensors").write_bytes(b"x")
assert hub.flux_parts()["clip_l"] is None or "qwen" not in hub.flux_parts()["clip_l"].lower(); ok("a Qwen encoder is never taken as CLIP-L")
hub.caps(True); r = hub.selfcheck(); g = {x["id"]: x for x in r["groups"]}["flux"]; assert g["rows"][3]["ok"] and g["rows"][1]["ok"] and g["note"]; ok("self-check has a FLUX group that lists what was found")
(M / "vae" / "ae.safetensors").unlink(); r = hub.selfcheck(); g = {x["id"]: x for x in r["groups"]}["flux"]; assert g["rows"][3]["ok"] is False and "ae.safetensors" in g["rows"][3]["detail"]; ok("a missing VAE is named")
print("ALL OK")
