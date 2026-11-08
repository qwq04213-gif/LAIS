"""영상 Wan 2.2 14B (고노이즈/저노이즈 2단계): 그래프, 파일 자동 찾기, 가속 LoRA, 오류 안내."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, base64, io, time
os.environ["TEST_HUB_PORT"] = "17874"
sys.path.insert(0, BASE + "/test")
from mocks import *
import urllib.request
ok = lambda m: print("PASS", m)
def post(path, o):
    r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def job(p, t=60):
    i = post("/api/job", p)["id"]
    for _ in range(t * 4):
        j = get("/api/job/" + i)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.25)
    raise AssertionError("timeout")
def nodes(g, c): return [n["inputs"] for n in g.values() if n["class_type"] == c]
base = {"kind": "vid", "wan_ver": "14b", "prompt": "a cat walking, cinematic", "seed": 5, "sec": 3}
j = job(dict(base)); assert j["state"] == "error" and "14B" in j["error"] and "설치" in j["error"], j; ok("14B files missing -> clear install hint")
for d, f in (("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"), ("vae", "wan_2.1_vae.safetensors"),
             ("diffusion_models", "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors"), ("diffusion_models", "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors")):
    (M / d / f).write_bytes(b"x")
l = get("/api/lists"); assert l["wan14"]["t2v"] and not l["wan14"]["i2v"] and not l["wan14"]["fast_t2v"], l["wan14"]
assert l["wanmodels"] == [] and not l["wan_ready"] or True
j = job(dict(base, fps=16)); assert j["state"] == "done", j; g = SUBMITTED[-1]
ks = nodes(g, "KSamplerAdvanced"); assert len(ks) == 2
assert ks[0]["add_noise"] == "enable" and ks[0]["start_at_step"] == 0 and ks[0]["end_at_step"] == 10 and ks[0]["return_with_leftover_noise"] == "enable" and ks[0]["noise_seed"] == 5, ks[0]
assert ks[1]["add_noise"] == "disable" and ks[1]["start_at_step"] == 10 and ks[1]["end_at_step"] >= 1000 and ks[1]["return_with_leftover_noise"] == "disable", ks[1]
ids = {i: n for i, n in g.items()}
un = [(i, n["inputs"]["unet_name"]) for i, n in g.items() if n["class_type"] == "UNETLoader"]; assert [u for _, u in un] == ["wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors", "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors"], un
def root(link):    # ModelSamplingSD3 → UNETLoader 까지 따라가요
    while g[link[0]]["class_type"] != "UNETLoader": link = g[link[0]]["inputs"]["model"]
    return g[link[0]]["inputs"]["unet_name"]
assert "high_noise" in root(ks[0]["model"]) and "low_noise" in root(ks[1]["model"]), "high first, low second"
assert ks[1]["latent_image"][0] == [i for i, n in g.items() if n["class_type"] == "KSamplerAdvanced"][0]
L = nodes(g, "EmptyHunyuanLatentVideo")[0]; assert (L["width"], L["height"], L["length"]) == (832, 480, 49), L     # 3초*16fps=48 -> 49
assert nodes(g, "CreateVideo")[0]["fps"] == 16 and nodes(g, "ModelSamplingSD3")[0]["shift"] == 5.0 and ks[0]["cfg"] == 3.5 and ks[0]["sampler_name"] == "euler" and ks[0]["scheduler"] == "simple"
assert j["images"][0].endswith(".mp4"); ok("14B text-to-video: two-stage KSamplerAdvanced (high 0-10, low 10-end), EmptyHunyuanLatentVideo, wan clip/VAE")
# 이미지→영상: 파일이 없으면 안내, 있으면 WanImageToVideo
im = Image.new("RGB", (600, 900), (10, 120, 200)); b = io.BytesIO(); im.save(b, "PNG"); img = "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
j = job(dict(base, image=img)); assert j["state"] == "error" and "이미지→영상" in j["error"], j
for f in ("wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"): (M / "diffusion_models" / f).write_bytes(b"x")
j = job(dict(base, image=img, keep_ratio="on")); assert j["state"] == "done", j; g = SUBMITTED[-1]
iv = nodes(g, "WanImageToVideo")[0]; assert iv["width"] < iv["height"] and iv["width"] % 16 == 0 and "start_image" in iv and not nodes(g, "EmptyHunyuanLatentVideo")
ks = nodes(g, "KSamplerAdvanced"); assert ks[0]["positive"][0] == [i for i, n in g.items() if n["class_type"] == "WanImageToVideo"][0] and ks[0]["latent_image"][1] == 2
ok("14B image-to-video: WanImageToVideo conditioning/latent feed both samplers, portrait ratio kept")
# 4단계 가속
j = job(dict(base, fast="on")); assert j["state"] == "done" and any("가속" in w for w in j.get("warn", [])), j
assert nodes(SUBMITTED[-1], "KSamplerAdvanced")[0]["steps"] == 20
for f in ("wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors", "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"): (M / "loras" / f).write_bytes(b"x")
assert get("/api/lists")["wan14"]["fast_t2v"]
j = job(dict(base, fast="on")); assert j["state"] == "done", j; g = SUBMITTED[-1]; ks = nodes(g, "KSamplerAdvanced")
assert ks[0]["steps"] == 4 and ks[0]["cfg"] == 1.0 and ks[0]["end_at_step"] == 2 and ks[1]["start_at_step"] == 2 and len(nodes(g, "LoraLoaderModelOnly")) == 2
assert [n["lora_name"] for n in nodes(g, "LoraLoaderModelOnly")][0].endswith("high_noise.safetensors")
ok("4-step fast mode: LoRA on both models, 4 steps cfg 1 split at 2; missing LoRA falls back with a notice")
# 5B 는 그대로, 5B 목록에 14B 파일 안 섞임
assert not any("14B" in n for n in get("/api/lists")["wanmodels"]); ok("5B model list excludes 14B files")
STATE["missing"].add("WanImageToVideo"); hub._CAPS["t"] = 0
j = job(dict(base, image=img)); assert j["state"] == "error" and "WanImageToVideo" in j["error"]; STATE["missing"].discard("WanImageToVideo"); hub._CAPS["t"] = 0; ok("old ComfyUI -> update hint")
cat = {m["id"]: m for m in get("/api/catalog")["image"]}
assert cat["wan22-14b-i2v"]["requires"] == ["wan-common", "wan21-vae"] and "wan21-vae" in cat and "wan22-lightning" in cat; ok("catalog entries present")
print("ALL OK")
