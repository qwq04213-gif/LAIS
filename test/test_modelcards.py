"""LoRA 정보 카드(트리거 단어 등)와 모델 목록 API."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, struct, io
os.environ["TEST_HUB_PORT"] = "17882"
sys.path.insert(0, BASE + "/test")
from mocks import *
import urllib.request, urllib.parse
ok = lambda m: print("PASS", m)
def get(path): return json.load(urllib.request.urlopen(B + path))
def st(path, keys, md=None):
    meta = {k: {"dtype": "F16", "shape": [4, 8], "data_offsets": [0, 2]} for k in keys}
    if md: meta["__metadata__"] = md
    b = json.dumps(meta).encode(); Path(path).write_bytes(struct.pack("<Q", len(b)) + b + b"\0\0")
L = M / "loras"
st(L / "kohya_style.safetensors", ["lora_unet_x.lora_down.weight", "lora_te2_y.lora_down.weight"],
   {"ss_output_name": "My Style", "ss_base_model_version": "sdxl_base_v1-0", "ss_network_dim": "32", "ss_network_alpha": "16", "ss_num_train_images": "120", "ss_epoch": "8",
    "ss_tag_frequency": json.dumps({"10_data": {"1girl": 100, "red jacket": 80, "solo": 120, "mystyle": 120, "bad": "x"}, "20_b": {"1girl": 5}})})
st(L / "spec.safetensors", ["lora_unet_single_blocks_0_linear1.lora_down.weight"], {"modelspec.title": "Flux Thing", "modelspec.trigger_phrase": "tok, ohwx style", "modelspec.description": "desc"})
st(L / "bare.safetensors", ["a.lora_down.weight"])
Image.new("RGB", (900, 600), (0, 200, 0)).save(L / "kohya_style.preview.png")
d = {c["name"]: c for c in get("/api/models/cards?kind=loras")["items"]}
k = d["kohya_style.safetensors"]; assert k["title"] == "My Style" and k["family"] == "sdxl" and k["dim"] == "32" and k["alpha"] == "16" and k["images"] == "120" and k["epochs"] == "8", k
assert k["tags"] == ["solo", "mystyle", "1girl", "red jacket"], k["tags"]; assert "red jacket" in k["tags"] and k["preview"] is True and k["size_mb"] >= 0
s = d["spec.safetensors"]; assert s["trigger"] == ["tok", "ohwx style"] and s["title"] == "Flux Thing" and s["family"] == "flux" and s["description"] == "desc" and s["preview"] is False, s
b = d["bare.safetensors"]; assert b["trigger"] == [] and b["tags"] == [] and b["title"] == ""; assert "lora_a.safetensors" in d  # 가짜 1바이트 파일도 깨지지 않음
ok("cards: kohya metadata (title/base/dim/alpha/images/epochs, top tags), modelspec trigger phrase, bare files, broken files don't crash")
r = urllib.request.urlopen(B + "/mprev/loras/" + urllib.parse.quote("kohya_style.safetensors")); im = Image.open(io.BytesIO(r.read())); assert r.headers["Content-Type"] == "image/jpeg" and im.width == 320; ok("preview image next to the file is served as a thumbnail")
for bad in ("/mprev/loras/spec.safetensors", "/mprev/etc/passwd", "/mprev/loras/..%2F..%2Fx"):
    try: urllib.request.urlopen(B + bad); raise AssertionError(bad)
    except urllib.error.HTTPError as e: assert e.code == 404
ck = get("/api/models/cards?kind=checkpoints")["items"]; assert any(c["name"] == "noobai_xl_v11.safetensors" and c["dir"] == "checkpoints" for c in ck) and any(c["dir"] == "diffusion_models" for c in ck); ok("checkpoint / diffusion model list with family and size")
print("ALL OK")
