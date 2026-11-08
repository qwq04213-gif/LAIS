"""3.17: Qwen-Image 2.1 이 생성·편집·조명·구도·타일 리파인·대화 실행 모드에 모두 쓰임, Lightning 4단계, 노드·파일 안내, 카탈로그(2511·HiDream·Lumina 없음, MOSS 있음)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17961"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def job2(o):
    jid = post("/api/job", o)["id"]
    for _ in range(600):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def g(): return SUBMITTED[-1]
def cls(c): return [v["inputs"] for v in g().values() if v["class_type"] == c]
def png(w=300, h=200):
    b = io.BytesIO(); Image.new("RGB", (w, h), (10, 120, 200)).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def enc(): return cls("TextEncodeQwenImage21")[0]
# 편집
j = job2({"kind": "edit", "engine": "qwen", "image": png(), "prompt": "make it red", "ref1": png(100, 100)}); assert j["state"] == "done", j
assert cls("UNETLoader")[0]["unet_name"] == "qwen_image_2.1_int8_convrot.safetensors" and cls("CLIPLoader")[0]["type"] == "qwen_image"
assert cls("CLIPLoader")[0]["clip_name"].startswith("qwen3vl_8b") and cls("VAELoader")[0]["vae_name"] == "qwen_image_2.1_vae_bf16.safetensors"
e = enc(); assert "images.image_1" in e and "images.image_2" in e and e["resolution"] == 0 and e["prompt"] == "make it red"
ks = cls("KSampler")[0]; assert ks["latent_image"] == [ks["positive"][0], 2] and ks["negative"][1] == 1 and ks["steps"] == 25 and ks["cfg"] == 1.0
assert not cls("FluxKontextMultiReferenceLatentMethod") and not cls("TextEncodeQwenImageEditPlus")
j = job2({"kind": "edit", "engine": "qwen", "image": png(), "prompt": "make it red", "fast": "on"}); assert j["state"] == "done"
assert cls("LoraLoaderModelOnly")[0]["lora_name"] == "qwen_image_2.1_lightning_4step.safetensors" and cls("KSampler")[0]["steps"] == 4
ok("edit: one 2.1 graph (TextEncodeQwenImage21 + refs, latent from encoder), Lightning 4 steps")
# 생성
j = job2({"kind": "gen", "gengine": "qwenimg", "prompt": "a poster with the word HELLO", "w": 1000, "h": 768}); assert j["state"] == "done", j
lat = cls("EmptySD3LatentImage")[0]; assert (lat["width"], lat["height"]) == (992, 768) and enc()["negative_prompt"] == "" and not [k for k in enc() if k.startswith("images")]
assert cls("KSampler")[0]["steps"] == 25
j = job2({"kind": "gen", "gengine": "qwenimg", "prompt": "cat", "fx_steps": 4}); assert cls("KSampler")[0]["steps"] == 4 and cls("LoraLoaderModelOnly")
ok("generate: same model, empty latent at 32-multiples, ≤8 steps → Lightning")
# 조명 · 구도 · 리파인
j = job2({"kind": "feat", "feature": "relight", "image": png(), "light": "sunset", "dir": "left"}); assert j["state"] == "done", j; assert cls("TextEncodeQwenImage21")
j = job2({"kind": "feat", "feature": "recompose", "mode": "angle", "image": png(), "az": "left", "el": "eye", "dist": "medium"}); assert j["state"] == "done", j
assert "<sks>" not in enc()["prompt"] and "left side" in enc()["prompt"]
j = job2({"kind": "up", "mode": "refine", "rengine": "qwen", "image": png(512, 512), "scale": 2, "rdenoise": 0.4}); assert j["state"] == "done", j
assert cls("VAEEncode") and abs(cls("KSampler")[0]["denoise"] - 0.4) < 1e-6 and cls("TextEncodeQwenImage21")
ok("relight, recompose (angle by words), tile refine all on Qwen-Image 2.1")
# 안내
STATE["missing"].add("TextEncodeQwenImage21"); hub._CAPS["t"] = 0
j = job2({"kind": "edit", "engine": "qwen", "image": png(), "prompt": "x"}); assert j["state"] == "error" and "update_comfyui" in j["error"], j
STATE["missing"].discard("TextEncodeQwenImage21"); hub._CAPS["t"] = 0
(M / "vae/qwen_image_2.1_vae_bf16.safetensors").rename(M / "vae/x.bak")
j = job2({"kind": "edit", "engine": "qwen", "image": png(), "prompt": "x"}); assert j["state"] == "error" and "Qwen-Image 2.1 VAE" in j["error"] and j.get("need") == ["qwen-image"], j
(M / "vae/x.bak").rename(M / "vae/qwen_image_2.1_vae_bf16.safetensors")
ok("old ComfyUI / missing file → clear guidance + download offer")
# MOSS
j = job2({"kind": "gen", "gengine": "moss", "prompt": "x"}); assert j["state"] == "error" and j.get("need") == ["moss-image"], j
for d, f in (("diffusion_models", "moss_image_sft_int8_convrot.safetensors"), ("text_encoders", "qwen3.5_9b_int8_convrot.safetensors"), ("vae", "flux2-vae.safetensors")):
    (M / d / f).write_bytes(b"x")
j = job2({"kind": "gen", "gengine": "moss", "prompt": '{"caption":"poster"}', "w": 1024, "h": 1024}); assert j["state"] == "done", j
c = cls("CLIPLoader")[0]; assert c["type"] == "moss_image" and c["clip_name"].startswith("qwen3.5_9b") and cls("EmptyFlux2LatentImage") and cls("KSampler")[0]["steps"] == 50 and cls("KSampler")[0]["cfg"] == 3.0
L = json.load(urllib.request.urlopen(B + "/api/lists")); assert L["oxmodels"]["moss"] and "moss_image_sft_int8_convrot.safetensors" not in L["fluxmodels"] and "hidream" not in L["oxmodels"]
ok("MOSS-Image: own CLIP type from engine, FLUX.2 latent, 50 steps CFG 3, not mixed into FLUX list")
cat = json.load(open(BASE + "/LocalAI-Studio/hub/models.json", encoding="utf-8")); ids = {m["id"]: m for m in cat["llm"] + cat["image"]}
assert "qwen-edit" not in ids and "qwen-angles" not in ids and not [k for k in ids if "hidream" in k or "lumina" in k]
assert "2.1" in ids["qwen-image"]["files"][0]["url"] and ids["qwen-lightning"]["files"][0]["name"] == "qwen_image_2.1_lightning_4step.safetensors" and "moss-image" in ids
ok("catalog: 2.1 + Lightning + MOSS, no 2511 / HiDream / Lumina")
print("ALL OK")
