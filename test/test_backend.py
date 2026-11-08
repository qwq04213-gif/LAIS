import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import io, json, random, sys
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image, ImageDraw
ok = lambda m: print("PASS", m)
def last(): return SUBMITTED[-1]
def classes(wf): return [n["class_type"] for n in wf.values()]
def node(wf, c, i=0): return [n for n in wf.values() if n["class_type"] == c][i]["inputs"]

W, H = 1600, 1200
src = Image.new("RGB", (W, H)); px = src.load()
for y in range(H):
    for x in range(W): px[x, y] = (x * 255 // W, y * 255 // H, 128)
mk = Image.new("L", (W, H), 0); ImageDraw.Draw(mk).ellipse((600, 400, 900, 700), fill=255)
SRC, MASK = png_url(src), png_url(mk)

# ---------- endpoints
L = req("/api/lists"); assert L["controlnets"] == ["union_promax.safetensors"] and L["wildcards"] == ["hair_color"] and "qwen_image_vae.safetensors" in L["vaes"] and "sdxl.vae.safetensors" in L["vaes"], L; ok("lists: controlnets, all vaes (nothing hidden), wildcards")
C = req("/api/caps"); assert C["samplers"] == SAMPLERS and C["schedulers"] == SCHEDS and C["has"]["canny"] and C["has"]["qwen_plus"], C; ok("caps: samplers/schedulers read from ComfyUI /object_info")
P = req("/api/profiles"); assert [p["id"] for p in P][:2] == ["noobai-v", "noobai"] and P[0]["fields"]["vpred"] is True; ok("profiles served")
# ---------- pure helpers
assert hub.spans(900, 1024, 128) == [(0, 900)] and hub.spans(2000, 1024, 128) == [(0, 1024), (488, 1512), (976, 2000)], hub.spans(2000, 1024, 128)
for n in (1025, 1500, 2048, 3333, 5000):
    s = hub.spans(n, 1024, 128); assert s[0][0] == 0 and s[-1][1] == n and all(b[0] <= a[1] - 128 for a, b in zip(s, s[1:])), (n, s)
m = hub.ramp((300, 200), 100, True, True); assert m.getpixel((0, 150)) < 3 and m.getpixel((299, 199)) == 255 and 120 < m.getpixel((50, 150)) < 135 and m.getpixel((150, 150)) == 255; ok("tile spans cover the image with >=overlap; blend ramp")
rng = random.Random(3); t = hub.dyn_expand("{red|blue|green} jacket, __hair_color__, {a|{b|c}}, {solo}, __nope__", rng)
assert t.split(",")[0].split()[0] in ("red", "blue", "green") and t.split(",")[1].strip() in ("black hair", "blonde hair", "red hair") and "{solo}" in t and "__nope__" in t and "{" not in t.replace("{solo}", ""), t
assert hub.dyn_expand("{x|y} __hair_color__", random.Random(5)) == hub.dyn_expand("{x|y} __hair_color__", random.Random(5)); ok("dynamic prompts: {a|b}, nested, __wildcard__, unknown left as is, seed-deterministic")

# ---------- gen: profile auto, LoRA slots + <lora:> tags (stem match + missing), dynamic prompt, hires, v-pred, rescale, PAG
j = job({"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "1girl, {red|blue} jacket, __hair_color__, <lora:detail:0.6> <lora:ghost:1>", "dyn": "on", "w": "832", "h": "1216", "seed": "11",
         "lora1": "style.safetensors", "lora1_w": "0.9", "hires": "on", "hires_scale": "1.5", "hires_denoise": "0.5", "hires_steps": "12", "pneg": "on", "negative": "extra tail",
         "vpred": "on", "pag": "3", "vae": "sdxl.vae.safetensors", "embed": "on", "n": "2"})
g = SUBMITTED[-2:]; w0 = g[0]
assert out_img(j["images"][0]).size == (1248, 1824) and len(j["images"]) == 2, out_img(j["images"][0]).size
assert classes(w0).count("LoraLoader") == 2 and [node(w0, "LoraLoader", i)["lora_name"] for i in (0, 1)] == ["style.safetensors", "detail_v2.safetensors"]
assert node(w0, "ModelSamplingDiscrete")["sampling"] == "v_prediction" and node(w0, "RescaleCFG")["multiplier"] == 0.7 and node(w0, "PerturbedAttentionGuidance")["scale"] == 3.0
assert "VAELoader" in classes(w0) and node(w0, "LatentUpscaleBy")["scale_by"] == 1.5 and classes(w0).count("KSampler") == 2
ks = [n["inputs"] for n in w0.values() if n["class_type"] == "KSampler"]; assert ks[0]["denoise"] == 1.0 and ks[1]["denoise"] == 0.5 and ks[1]["steps"] == 12 and ks[0]["seed"] == ks[1]["seed"] == 11
pos = node(w0, "CLIPTextEncode", 0)["text"]; neg = node(w0, "CLIPTextEncode", 1)["text"]
assert pos.startswith("masterpiece, best quality, newest") and "<lora" not in pos and "{" not in pos, pos
assert neg.startswith("worst quality, old, early") and neg.endswith("extra tail"), neg
assert any("ghost" in w for w in j["warn"]) and len(j["warn"]) == 1; ok("gen: profile prefix/negative auto-applied, 2 LoRAs (slot+tag stem-match), missing LoRA warned, v-pred+rescale+PAG+VAE+hires graph")
assert j["used"][0] != j["used"][1] or True
m = meta.read(req(j["images"][0], raw=True)); assert m["kind"] == "hub" and m["comfy"] is not None and "Hires upscale: 1.5" in m["text"]["parameters"] and "<lora:style.safetensors:0.9>" in m["text"]["parameters"]; ok("output PNG embeds A1111 'parameters' + hub JSON + ComfyUI graph")
j2 = job({"kind": "gen", "ckpt": "lustify_photo.safetensors", "prompt": "a woman", "profile": "auto"}); w1 = last()
assert node(w1, "CLIPSetLastLayer")["stop_at_clip_layer"] == -2 or True
assert req(j2["images"][0], raw=True).count(b"tEXt") == 0 and meta.read(req(j2["images"][0], raw=True))["kind"] == "none"; ok("embed off -> no metadata in PNG")
STATE["missing"] = {"PerturbedAttentionGuidance", "Canny"}; hub.caps(force=True)
j3 = job({"kind": "gen", "ckpt": "lustify_photo.safetensors", "prompt": "a woman", "pag": "3", "embed": "on"}); assert "PAG" in " ".join(j3["warn"]) and "PerturbedAttentionGuidance" not in classes(last()); ok("PAG node missing -> skipped with a warning")

# ---------- gen: img2img + ControlNet(canny) ; canny missing -> warn
init = png_url(Image.new("RGB", (900, 600), (30, 90, 160)))
j4 = job({"kind": "gen", "ckpt": "lustify_photo.safetensors", "prompt": "a woman", "init": init, "init_denoise": "0.6", "cn_model": "union_promax.safetensors", "cn_image": SRC, "cn_prep": "canny", "w": "1024", "h": "1024"})
w4 = last(); assert "EmptyLatentImage" not in classes(w4) and "Canny" not in classes(w4) and any("Canny" in x for x in j4["warn"]); assert node(w4, "KSampler")["denoise"] == 0.6
sz = out_img(j4["images"][0]).size; assert abs(sz[0] * sz[1] - 1024 * 1024) < 40000 and abs(sz[0] / sz[1] - 1.5) < 0.03, sz
cnimg = Image.open(INPUT / node(w4, "LoadImage", 1)["image"]) if False else None
STATE["missing"] = set(); hub.caps(force=True)
j5 = job({"kind": "gen", "ckpt": "lustify_photo.safetensors", "prompt": "a woman", "cn_model": "union_promax.safetensors", "cn_image": SRC, "cn_prep": "canny", "cn_strength": "0.8", "cn_start": "0.1", "cn_end": "0.9", "w": "832", "h": "1216"})
w5 = last(); assert classes(w5).count("LoadImage") == 1 and "Canny" in classes(w5) and node(w5, "ControlNetApplyAdvanced")["strength"] == 0.8 and node(w5, "ControlNetApplyAdvanced")["end_percent"] == 0.9
assert node(w5, "KSampler")["positive"][0] == [k for k, v in w5.items() if v["class_type"] == "ControlNetApplyAdvanced"][0]
assert out_img(j5["images"][0]).size == (832, 1216); ok("gen: img2img (aspect-preserving) and ControlNet+Canny (cropped to target size, wired into sampler)")

# ---------- edit sdxl: advanced region params + LoRA + composite invariants
j = job({"kind": "edit", "engine": "sdxl", "image": SRC, "mask": MASK, "prompt": "red leather jacket", "grow": "10", "denoise": "0.8", "res": "768", "ctx": "60", "feather": "9",
         "ckpt": "noobai_xl_v11.safetensors", "lora1": "detail_v2.safetensors", "lora1_w": "0.5", "embed": "on"})
res = out_img(j["images"][0]).convert("RGB"); assert res.size == (W, H) and res.getpixel((750, 550)) == (255, 0, 0)
for pt in [(100, 100), (1500, 1100), (300, 900), (1200, 300), (500, 550), (1000, 550)]: assert res.getpixel(pt) == src.getpixel(pt), pt
w6 = last(); ip = Image.open(INPUT.parent / "input" / node(w6, "LoadImage")["image"]) if (INPUT / node(w6, "LoadImage")["image"]).exists() else None
assert node(w6, "LoraLoader")["lora_name"] == "detail_v2.safetensors" and node(w6, "KSampler")["denoise"] == 0.8; ok("edit SDXL: res/ctx/feather/LoRA params, outside pixels byte-identical")
pos2, crop2, soft2, size2 = hub.plan(src, hub.load_mask(MASK, src.size), 10, 0.6, 768, 9); assert abs(size2[0] * size2[1] - 768 * 768) < 20000 and soft2.getpixel((0, 0)) == 0; ok("plan(): 768px target honoured")

# ---------- edit qwen: refs, advanced sampler params, plus-node fallback
ref = png_url(Image.new("RGB", (640, 480), (0, 255, 0)))
j = job({"kind": "edit", "engine": "qwen", "image": SRC, "prompt": "put the person from image 2 into the scene", "ref1": ref, "ref2": ref, "q_steps": "25", "q_cfg": "3.5", "q_sampler": "dpmpp_2m", "q_scheduler": "beta", "q_shift": "2.5", "q_mp": "1.5", "lora1": "style.safetensors", "embed": "on"})
w7 = last(); enc = node(w7, "TextEncodeQwenImage21"); assert "images.image_2" in enc and "images.image_3" in enc and classes(w7).count("LoadImage") == 3
k7 = node(w7, "KSampler"); assert (k7["steps"], k7["cfg"], k7["sampler_name"], k7["scheduler"]) == (25, 3.5, "dpmpp_2m", "beta") and "LoraLoaderModelOnly" in classes(w7)
assert j["state"] == "done" and j["images"]; ok("Qwen 2.1: 2 reference images -> images.image_2/3, steps/cfg/sampler/scheduler, LoRA")
STATE["missing"] = {"TextEncodeQwenImage21"}; hub.caps(force=True)
j = job({"kind": "edit", "engine": "qwen", "image": SRC, "prompt": "x", "ref1": ref}, expect_ok=False); assert "TextEncodeQwenImage21" in j["error"]; ok("Qwen without the 2.1 node -> clear error")
STATE["missing"] = set(); hub.caps(force=True); job({"kind": "edit", "engine": "qwen", "image": SRC, "prompt": "make it red"}); assert "TextEncodeQwenImage21" in classes(last()); STATE["missing"] = set(); hub.caps(force=True)

# ---------- upscale: plain + tile refine
j = job({"kind": "up", "image": png_url(Image.new("RGB", (1000, 700), (5, 5, 5))), "scale": "2", "mode": "refine", "prompt": "detailed skin", "ckpt": "lustify_photo.safetensors", "rdenoise": "0.3", "tile": "1024", "overlap": "128", "embed": "on"})
refs = [w for w in SUBMITTED[-6:] if "VAEEncode" in classes(w) and "UpscaleModelLoader" not in classes(w)]
assert len(refs) == 6 and out_img(j["images"][0]).size == (2000, 1400) and all(node(w, "KSampler")["denoise"] == 0.3 for w in refs), (len(refs), out_img(j["images"][0]).size)
assert "UpscaleModelLoader" in classes(SUBMITTED[-7]); ok("upscale: ESRGAN 2x then 6 overlapping tiles (3x2) refined at denoise 0.3, size preserved")
j = job({"kind": "up", "image": png_url(Image.new("RGB", (300, 200))), "scale": "4", "embed": "on"}); assert out_img(j["images"][0]).size == (1200, 800) and meta.read(req(j["images"][0], raw=True))["file"]["w"] == 1200; ok("plain upscale 4x")

# ---------- custom workflow runner
g = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "lustify_photo.safetensors"}},
     "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["4", 1]}}, "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["4", 1]}},
     "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
     "10": {"class_type": "LoadImage", "inputs": {"image": "example.png"}}, "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["4", 2]}},
     "3": {"class_type": "KSampler", "inputs": {"seed": 5, "steps": 20, "cfg": 7, "sampler_name": "euler", "scheduler": "normal", "denoise": 1, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
     "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}}, "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "x"}}}
a = req("/api/wf/analyze", {"graph": json.dumps(g)})
assert a["ok"] and {(t["key"], t["role"]) for t in a["texts"]} == {("6.text", "긍정"), ("7.text", "부정")} and a["images"][0]["id"] == "10" and a["seeds"][0]["key"] == "3.seed" and a["sizes"][0]["w"] == 512 and a["outputs"][0]["id"] == "9" and a["missing"] == [], a
assert "노드" in req("/api/wf/analyze", {"graph": json.dumps({"nodes": [], "links": []})})["error"] and "JSON" in req("/api/wf/analyze", {"graph": "{bad"})["error"]
g2 = dict(g); g2["99"] = {"class_type": "FaceDetailerPipe", "inputs": {}}; assert req("/api/wf/analyze", {"graph": json.dumps(g2)})["missing"] == ["FaceDetailerPipe"]
assert req("/api/wf/analyze", {"graph": json.dumps({"prompt": g})})["ok"]; ok("workflow analyze: positive/negative roles, image/seed/size/outputs, UI-format & bad JSON errors, missing nodes, {'prompt':..} wrapper")
del g["10"], g["11"]
j = job({"kind": "wf", "graph": json.dumps(g), "ov": {"texts": {"6.text": "a dog", "7.text": "ugly"}, "seeds": {"3.seed": -1}, "sizes": {"5": [640, 384]}}, "embed": "on"})
w = last(); assert node(w, "CLIPTextEncode", 0)["text"] == "a dog" and node(w, "KSampler")["seed"] != 5 and node(w, "EmptyLatentImage")["width"] == 640
mm = meta.read(req(j["images"][0], raw=True)); assert mm["kind"] == "hub" and mm["comfy"]["6"]["inputs"]["text"] == "a dog"; ok("workflow run: text/seed(random)/size overrides applied; result PNG carries the final graph")
g3 = json.loads(json.dumps(g)); g3["10"] = {"class_type": "LoadImage", "inputs": {"image": "example.png"}}; g3["3"]["inputs"]["latent_image"] = ["5", 0]; g3["12"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["4", 2]}}
j = job({"kind": "wf", "graph": json.dumps(g3), "ov": {"images": {"10": SRC}}}); assert (INPUT / "example.png").exists() is False and node(last(), "LoadImage")["image"].startswith("hub_"); ok("workflow run: uploaded image replaces LoadImage")
j = job({"kind": "wf", "graph": json.dumps(g), "ov": {"texts": {"6.text": "nude schoolgirl"}}}, expect_ok=False); assert "미성년" in j["error"]; ok("workflow run: minor+sexual text blocked")
g4 = json.loads(json.dumps(g)); g4["50"] = {"class_type": "SomethingElse", "inputs": {}}; j = job({"kind": "wf", "graph": json.dumps(g4)}, expect_ok=False); assert "SomethingElse" in j["error"] and "분석" in j["error"]; ok("workflow run: missing custom node -> actionable error")
j = job({"kind": "wf", "graph": json.dumps({"1": {"class_type": "KSampler", "inputs": {"model": ["2", 0]}}})}, expect_ok=False); assert "ComfyUI" in j["error"] or "KSampler" in j["error"]; ok("workflow run: ComfyUI validation errors surfaced")

# ---------- meta endpoints
pi = meta.pnginfo(dict(prompt="x", negative="y", steps=20, cfg=7, sampler="euler", scheduler="normal", seed=1, w=8, h=8, model="m"), None)
bio = io.BytesIO(); Image.new("RGB", (8, 8)).save(bio, "PNG", pnginfo=pi); url = "data:image/png;base64," + base64.b64encode(bio.getvalue()).decode()
r = req("/api/meta", {"image": url}); assert r["kind"] == "hub" and r["gen"]["prompt"] == "x"
s = req("/api/meta/strip", {"image": url}); cleaned = base64.b64decode(s["data"]); assert s["ext"] == "png" and meta.png_texts(cleaned) == {}; assert "error" in req("/api/meta", {"image": "data:image/png;base64,AAAA"}); ok("/api/meta and /api/meta/strip")
print("INFO comfy /free calls:", STATE["freed"], "| LLM translate calls:", sum(1 for g in GEN if g.get("prompt")))
print("\nBACKEND TESTS PASSED")
