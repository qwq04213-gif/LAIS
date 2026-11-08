import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import base64, io, json, sys
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from PIL import Image, PngImagePlugin
import meta

def png_with(texts, size=(64, 48), color=(10, 200, 30), itxt=()):
    pi = PngImagePlugin.PngInfo()
    for k, v in texts.items(): pi.add_text(k, v, zip=k in itxt)
    b = io.BytesIO(); Image.new("RGB", size, color).save(b, "PNG", pnginfo=pi); return b.getvalue()

ok = lambda m: print("PASS", m)

# ---- A1111 (Korean prompt => iTXt) with LoRA tag, quoted value containing commas
a = ("masterpiece, 1girl, 붉은 재킷, <lora:detail_v2:0.7>\nNegative prompt: lowres, bad hands\n"
     'Steps: 28, Sampler: DPM++ 2M Karras, CFG scale: 5.5, Seed: 123456, Size: 832x1216, Model hash: abcd, Model: noobai_v11, '
     'Clip skip: 2, Denoising strength: 0.45, Lora hashes: "detail_v2: 1234, other: 5678", Version: v1.10')
r = meta.read(png_with({"parameters": a}))
g = r["gen"]; p = g["params"]
assert r["kind"] == "a1111" and "붉은 재킷" in g["prompt"] and g["negative"] == "lowres, bad hands", r["kind"]
assert (p["steps"], p["cfg"], p["seed"], p["w"], p["h"], p["clip_skip"], p["model"]) == (28, 5.5, 123456, 832, 1216, 2, "noobai_v11"), p
assert p["sampler"] == "dpmpp_2m" and p["scheduler"] == "karras" and p["denoise"] == 0.45 and p["loras"] == [["detail_v2", 0.7]], p
assert g["raw"]["Lora hashes"] == "detail_v2: 1234, other: 5678"
ok("A1111: prompt/negative/params, 'DPM++ 2M Karras' -> dpmpp_2m+karras, LoRA tag, quoted commas")
assert meta.map_sampler("Euler a") == ("euler_ancestral", None) and meta.map_sampler("DPM++ 3M SDE Exponential") == ("dpmpp_3m_sde", "exponential")
assert meta.map_sampler("Euler a", "Karras") == ("euler_ancestral", "karras"); ok("sampler name mapping")

# ---- ComfyUI API graph (+ workflow chunk), with a hires chain and LoRA
graph = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
         "10": {"class_type": "LoraLoader", "inputs": {"model": ["4", 0], "clip": ["4", 1], "lora_name": "style.safetensors", "strength_model": 0.8, "strength_clip": 0.8}},
         "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1536, "batch_size": 1}},
         "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat in a hat", "clip": ["10", 1]}},
         "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["10", 1]}},
         "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1, "model": ["10", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
         "12": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 12, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 0.5, "model": ["10", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["3", 0]}},
         "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0]}}}
r = meta.read(png_with({"prompt": json.dumps(graph), "workflow": json.dumps({"nodes": [], "links": []})}))
g = r["gen"]["params"]
assert r["kind"] == "comfyui" and r["comfy"] == graph and r["gen"]["prompt"] == "a cat in a hat" and r["gen"]["negative"] == "blurry"
assert (g["steps"], g["cfg"], g["seed"], g["sampler"], g["w"], g["h"], g["model"], g["denoise"]) == (20, 7.0, 42, "euler", 1024, 1536, "model.safetensors", 1), g
assert g["loras"] == [["style.safetensors", 0.8]] and "workflow" in r["text"]; ok("ComfyUI: positive/negative traced through LoRA, first-pass sampler chosen, size/model/LoRA")

# ---- NovelAI
c = {"prompt": "1girl, solo", "uc": "lowres", "steps": 28, "scale": 5, "seed": 7, "sampler": "k_euler_ancestral", "width": 832, "height": 1216}
r = meta.read(png_with({"Software": "NovelAI", "Comment": json.dumps(c), "Description": "1girl, solo"}))
assert r["kind"] == "novelai" and r["gen"]["params"]["sampler"] == "euler_ancestral" and r["gen"]["negative"] == "lowres"; ok("NovelAI")

# ---- Character card (v2) in 'chara'
card = {"spec": "chara_card_v2", "data": {"name": "하루", "description": "{{char}}는 카페 주인", "first_mes": "어서 와요, {{user}}!", "tags": ["cafe"], "alternate_greetings": ["안녕"]}}
r = meta.read(png_with({"chara": base64.b64encode(json.dumps(card, ensure_ascii=False).encode()).decode()}))
assert r["kind"] == "card" and r["card"]["name"] == "하루" and "chara" not in r["text"] and r["card"]["alternate_greetings"] == ["안녕"]; ok("character card (chara)")

# ---- zTXt + big text chunk + text after IDAT
big = json.dumps({"x": "y" * 2_000_000})
r = meta.read(png_with({"workflow": big}, itxt=("workflow",)))
assert len(r["text"]["workflow"]) == meta.MAXTXT and "workflow" in r["text_truncated"]; ok("2MB compressed text chunk read, truncated for UI")

# ---- no metadata
r = meta.read(png_with({})); assert r["kind"] == "none" and r["gen"] is None and r["file"]["w"] == 64; ok("plain PNG -> kind none")

# ---- JPEG with EXIF (camera + GPS + A1111 UserComment)
im = Image.new("RGB", (80, 60), (200, 50, 50)); ex = Image.Exif()
ex[0x010F], ex[0x0110], ex[0x0112] = "Canon", "EOS R5", 1
ifd = ex.get_ifd(0x8769); ifd[0x9286] = b"UNICODE\x00" + "a red cat\nNegative prompt: blur\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 5, Size: 80x60, Model: m".encode("utf-16-be")
gps = ex.get_ifd(0x8825); gps[1], gps[2], gps[3], gps[4] = "N", (37.0, 33.0, 36.0), "E", (126.0, 58.0, 48.0)
b = io.BytesIO(); im.save(b, "JPEG", exif=ex, quality=92); jpg = b.getvalue()
r = meta.read(jpg); rows = dict(r["exif"])
assert rows["Make"] == "Canon" and r["gps"] == {"lat": 37.56, "lon": 126.98}, (rows, r["gps"])
assert r["kind"] == "a1111" and r["gen"]["prompt"] == "a red cat" and r["gen"]["params"]["sampler"] == "euler_ancestral"; ok("JPEG EXIF: camera, GPS decimal (37.56, 126.98), UserComment A1111 params")

# ---- strip: JPEG lossless (scan data identical), PNG lossless (pixels identical), orientation fallback, WebP
out, ext, note = meta.strip(jpg); r2 = meta.read(out)
assert ext == "jpg" and r2["gps"] is None and not r2["exif"] and r2["kind"] == "none"
assert Image.open(io.BytesIO(out)).tobytes() == Image.open(io.BytesIO(jpg)).tobytes() and out[-2:] == b"\xff\xd9"; ok("strip JPEG: EXIF+GPS gone, pixels identical (lossless)")
src = png_with({"parameters": a, "prompt": json.dumps(graph)}, color=(1, 2, 3))
out, ext, _ = meta.strip(src); assert meta.png_texts(out) == {} and Image.open(io.BytesIO(out)).tobytes() == Image.open(io.BytesIO(src)).tobytes() and ext == "png"; ok("strip PNG: text chunks gone, pixels identical")
ex2 = Image.Exif(); ex2[0x0112] = 6; b = io.BytesIO(); Image.new("RGB", (40, 20), (9, 9, 9)).save(b, "JPEG", exif=ex2)
out, ext, note = meta.strip(b.getvalue()); assert Image.open(io.BytesIO(out)).size == (20, 40) and "회전" in note; ok("strip JPEG with rotation: orientation baked in")
b = io.BytesIO(); Image.new("RGB", (10, 10)).save(b, "WEBP", exif=ex); out, ext, _ = meta.strip(b.getvalue()); assert ext == "webp" and not meta.read(out)["exif"]; ok("strip WebP")

# ---- writing: our own output round-trips
info = dict(prompt="red jacket, 1girl", negative="lowres", steps=28, cfg=5.0, sampler="euler_ancestral", scheduler="normal", seed=99, w=832, h=1216, model="noob.safetensors", clip_skip=2,
            loras=[["detail.safetensors", 0.7]], extra={"Hires upscale": 1.5})
b = io.BytesIO(); Image.new("RGB", (8, 8)).save(b, "PNG", pnginfo=meta.pnginfo(info, graph)); r = meta.read(b.getvalue())
p = r["gen"]["params"]; assert r["kind"] == "hub" and r["gen"]["prompt"].startswith("red jacket") and p["sampler"] == "euler_ancestral" and p["scheduler"] == "normal"
assert (p["steps"], p["seed"], p["w"], p["h"], p["model"], p["clip_skip"]) == (28, 99, 832, 1216, "noob.safetensors", 2) and p["loras"] == [["detail.safetensors", 0.7]] and r["comfy"] == graph
assert "Euler a" in r["text"]["parameters"] and "Hires upscale: 1.5" in r["text"]["parameters"]; ok("own output: A1111-compatible 'parameters' + hub JSON + ComfyUI graph round-trip")
info2 = dict(kind="gen-krea2", prompt="a cat", negative="", steps=8, cfg=1.0, sampler="euler", scheduler="simple", seed=5, w=1024, h=1024, model="krea2_turbo_fp8_scaled.safetensors", loras=[["x.safetensors", 0.8]], extra={"Family": "krea2"})
b = io.BytesIO(); Image.new("RGB", (8, 8)).save(b, "PNG", pnginfo=meta.pnginfo(info2)); r = meta.read(b.getvalue()); p = r["gen"]["params"]
assert p["family"] == "krea2" and p["loras"] == [["x.safetensors", 0.8]] and r["gen"]["prompt"] == "a cat" and "<lora" not in r["gen"]["prompt"] and p["model"].startswith("krea2")
g2 = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": "k.safetensors"}}, "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "q", "type": "krea2"}}, "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}},
      "4": {"class_type": "KSampler", "inputs": {"steps": 8, "cfg": 1, "sampler_name": "euler", "scheduler": "simple", "seed": 3, "denoise": 1, "positive": ["5", 0], "negative": ["5", 0]}}, "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "hi"}}}
c = meta.comfy_norm(g2)["params"]; assert c["family"] == "krea2" and c["vae"] == "v.safetensors" and c["model"] == "k.safetensors"
ok("hub JSON keeps family/model/LoRAs for every engine (info -> gen restore); ComfyUI graphs report family and VAE")
print("\nMETA TESTS PASSED")
