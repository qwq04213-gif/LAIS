"""Krea 2 컨트롤 LoRA: 목록, 그래프, 빠진 확장 안내, 확인해 둔 확장 설치 경로(고정 커밋)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import json, sys, io, base64, urllib.request
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
ok = lambda m: print("PASS", m)
def last(): return SUBMITTED[-1]
def node(wf, c, i=0): return [n for n in wf.values() if n["class_type"] == c][i]["inputs"]
def classes(wf): return [n["class_type"] for n in wf.values()]
def png_url(im):
    b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
(M / "diffusion_models" / "krea2_turbo_fp8_scaled.safetensors").write_bytes(b"x")
(M / "text_encoders" / "qwen3vl_4b_fp8_scaled.safetensors").write_bytes(b"x"); (M / "vae" / "qwen_image_vae.safetensors").write_bytes(b"x")
(M / "loras" / "krea2-depth-control-lora.safetensors").write_bytes(b"x")
L = json.load(urllib.request.urlopen(B + "/api/lists")); assert L["k2control"] == ["krea2-depth-control-lora.safetensors"] and L["k2c_nodes"] is True; ok("control LoRA is recognised in the loras folder; nodes reported as present")
base = {"kind": "gen", "gengine": "krea2", "fx_model": "krea2_turbo_fp8_scaled.safetensors", "prompt": "a woman", "w": "832", "h": "1216", "seed": "3", "cn_image": png_url(Image.new("RGB", (400, 600), (5, 5, 5))), "fx_steps": "8", "fx_cfg": "1"}
job({**base, "cn_model": "krea2-depth-control-lora.safetensors", "cn_strength": "0.9"}); g = last()
ld = node(g, "Krea2ControlLoRALoader"); assert ld["lora_name"] == "krea2-depth-control-lora.safetensors" and ld["strength"] == 0.9
en = node(g, "Krea2ControlImageEncode"); assert en["channel_mode"] == "grayscale" and en["normalize"] == "per_image_minmax" and en["resize"] == "match_latent_size" and en["invert"] is False
ap = [k for k, v in g.items() if v["class_type"] == "Krea2ControlApply"][0]; ks = node(g, "KSampler"); assert ks["model"] == [ap, 0]
lat = [k for k, v in g.items() if v["class_type"] == "EmptyLatentImage"][0]; assert en["latent"] == [lat, 0] and g[node(g, "Krea2ControlApply")["model"][0]]["class_type"] == "Krea2ControlLoRALoader"
assert node(g, "Krea2ControlLoRALoader")["model"] and g[ld["model"][0]]["class_type"] == "UNETLoader"; ok("depth control: UNET → control LoRA → apply (encoded depth map at the latent's size, gray + min-max) → KSampler")
(M / "loras" / "krea2-canny-control.safetensors").write_bytes(b"x")
job({**base, "cn_model": "krea2-canny-control.safetensors", "cn_prep": "canny"}); g = last(); assert node(g, "Krea2ControlImageEncode")["channel_mode"] == "rgb" and "Canny" in classes(g) and node(g, "Krea2ControlLoRALoader")["strength"] == 1.0; ok("non-depth LoRA: rgb, no normalisation, optional canny prep, default strength 1.0")
j = job({**base, "cn_model": "style.safetensors"}, expect_ok=False); assert "컨트롤 LoRA 가 아닌" in j["error"], j; ok("an ordinary LoRA picked as control is refused with an explanation")
STATE["missing"].add("Krea2ControlApply"); hub.caps(True)
j = job({**base, "cn_model": "krea2-depth-control-lora.safetensors"}, expect_ok=False); assert "comfyui-krea2-controlnet" in j["error"] and "설치" in j["error"], j
assert json.load(urllib.request.urlopen(B + "/api/lists"))["k2c_nodes"] is False; ok("missing extension nodes: clear message, lists report it so the screen shows an install button")
src = post("/api/nodes/sources", {"missing": ["Krea2ControlApply"]}); assert src["repos"][0]["repo"] == hub.K2C_REPO and "Krea2" in src["repos"][0]["title"], src; ok("the install source for those nodes is found without the public node list")
job({**base, "cn_model": ""}); assert "Krea2ControlLoRALoader" not in classes(last()); ok("no control selected → plain Krea 2 graph")
# 설치 경로: 확인해 둔 주소만, 확인한 커밋으로 받기
seen = []
class Stop(Exception): pass
orig = urllib.request.urlopen
def fake(url, *a, **k):
    u = url if isinstance(url, str) else url.full_url
    if "github.com" not in u: return orig(url, *a, **k)
    seen.append(u); raise Stop()
urllib.request.urlopen = fake
import time
try:
    assert post("/api/nodes/install", {"repo": hub.K2C_REPO}) == {"ok": True}
    for _ in range(50):
        if seen: break
        time.sleep(0.1)
finally: urllib.request.urlopen = orig
assert seen and seen[0] == hub.K2C_REPO + "/archive/79ebfd3bd80d2180b334dd7ce57f3c9ddaa0848f.zip", seen; ok("install downloads the pinned, reviewed commit (not whatever HEAD is today)")
r = post("/api/nodes/install", {"repo": "https://github.com/evil/pack"}); assert "error" in r; ok("an unknown address is still refused")
print("ALL OK")
