"""Integration test for hub.py using mock ComfyUI / Ollama servers (no network, no GPU)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import base64, io, json, os, sys, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image, ImageDraw

TMP = Path(tempfile.mkdtemp())
os.environ.update(STUDIO_ROOT=str(TMP), HUB_PORT="17860", COMFY_URL="http://127.0.0.1:18188", OLLAMA_URL="http://127.0.0.1:21434")
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import hub  # noqa

M = TMP / "engine/ComfyUI_windows_portable/ComfyUI/models"
for d, f in [("checkpoints", "noob.safetensors"), ("diffusion_models", "qwen_image_2.1_int8_convrot.safetensors"),
             ("text_encoders", "qwen3vl_8b_int8_convrot.safetensors"), ("vae", "qwen_image_2.1_vae_bf16.safetensors"),
             ("loras", "qwen_image_2.1_lightning_4step.safetensors"), ("loras", "style.safetensors"),
             ("upscale_models", "RealESRGAN_x4plus.pth")]:
    (M / d).mkdir(parents=True, exist_ok=True); (M / d / f).write_bytes(b"x")
INPUT = M.parent / "input"; INPUT.mkdir(exist_ok=True)

# ---------- mock ComfyUI ----------
REQ = {"TextEncodeQwenImage21": ["clip", "prompt", "negative_prompt", "resolution"], "CheckpointLoaderSimple": ["ckpt_name"], "LoraLoader": ["model", "clip", "lora_name", "strength_model", "strength_clip"],
       "LoraLoaderModelOnly": ["model", "lora_name", "strength_model"], "CLIPSetLastLayer": ["clip", "stop_at_clip_layer"],
       "CLIPTextEncode": ["text", "clip"], "EmptyLatentImage": ["width", "height", "batch_size"],
       "KSampler": ["model", "seed", "steps", "cfg", "sampler_name", "scheduler", "positive", "negative", "latent_image", "denoise"],
       "VAEDecode": ["samples", "vae"], "VAEEncode": ["pixels", "vae"], "PreviewImage": ["images"], "LoadImage": ["image"],
       "LoadImageMask": ["image", "channel"], "InpaintModelConditioning": ["positive", "negative", "vae", "pixels", "mask", "noise_mask"],
       "DifferentialDiffusion": ["model"], "UNETLoader": ["unet_name", "weight_dtype"], "CLIPLoader": ["clip_name", "type"],
       "VAELoader": ["vae_name"], "ModelSamplingAuraFlow": ["model", "shift"], "CFGNorm": ["model", "strength"],
       "TextEncodeQwenImageEditPlus": ["clip", "prompt", "vae", "image1"], "TextEncodeQwenImageEdit": ["clip", "prompt", "vae", "image"],
       "UpscaleModelLoader": ["model_name"], "ImageUpscaleWithModel": ["upscale_model", "image"], "ImageScaleBy": ["image", "upscale_method", "scale_by"]}
SUBMITTED, HIST, STATE = [], {}, {"qwen_plus": True}

def validate(wf):
    for nid, n in wf.items():
        assert n["class_type"] in REQ, "unknown class " + n["class_type"]
        for k in REQ[n["class_type"]]:
            assert k in n["inputs"], f'{n["class_type"]} missing {k}'
        for k, v in n["inputs"].items():
            if isinstance(v, list):
                assert len(v) == 2 and v[0] in wf, f"bad link {nid}.{k}={v}"
        if n["class_type"] in ("LoadImage", "LoadImageMask"):
            assert (INPUT / n["inputs"]["image"]).exists(), "input file missing"

def out_size(wf):
    cls = {n["class_type"]: n for n in wf.values()}
    if "EmptyLatentImage" in cls:
        i = cls["EmptyLatentImage"]["inputs"]; return i["width"], i["height"]
    w, h = Image.open(INPUT / cls["LoadImage"]["inputs"]["image"]).size
    if "ImageUpscaleWithModel" in cls:
        return (w * 4, h * 4) if "ImageScaleBy" not in cls else (w * 2, h * 2)
    return w, h

class Comfy(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def j(self, o, c=200):
        b = json.dumps(o).encode(); self.send_response(c); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = self.path.split("?")[0]
        if u == "/system_stats": return self.j({})
        if u == "/object_info":
            d = {k: {} for k in ("KSampler", "CLIPLoader", "TextEncodeQwenImageEdit", "TextEncodeQwenImage21")}
            if STATE["qwen_plus"]: d["TextEncodeQwenImageEditPlus"] = {}
            return self.j(d)
        if u.startswith("/object_info/"):
            n = u.split("/")[-1]
            ok = (n != "TextEncodeQwenImageEditPlus" or STATE["qwen_plus"]) and (n != "TextEncodeQwenImage21" or STATE.get("q21", True))
            return self.j({n: {}} if ok else {})
        if u.startswith("/history/"):
            pid = u.split("/")[-1]; h = HIST.get(pid)
            if not h: return self.j({})
            if h["polls"] < 1: h["polls"] += 1; return self.j({})
            return self.j({pid: {"outputs": {"99": {"images": [{"filename": pid + ".png", "subfolder": "", "type": "temp"}]}}, "status": {"status_str": "success", "messages": []}}})
        if u == "/view":
            pid = self.path.split("filename=")[1].split(".png")[0]
            w, h = HIST[pid]["size"]; im = Image.new("RGB", (w, h), (255, 0, 0)); b = io.BytesIO(); im.save(b, "PNG")
            self.send_response(200); self.send_header("Content-Type", "image/png"); self.end_headers(); self.wfile.write(b.getvalue()); return
        self.j({}, 404)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/prompt":
            wf = body["prompt"]
            try: validate(wf)
            except AssertionError as e:
                return self.j({"error": {"message": "Prompt outputs failed validation"}, "node_errors": {"1": {"class_type": "X", "errors": [{"message": str(e), "details": ""}]}}}, 400)
            pid = f"p{len(SUBMITTED)}"; SUBMITTED.append(wf); HIST[pid] = {"polls": 0, "size": out_size(wf)}
            return self.j({"prompt_id": pid, "number": 1, "node_errors": {}})
        if self.path == "/free": STATE["freed"] = STATE.get("freed", 0) + 1; return self.j({})
        self.j({}, 404)

# ---------- mock Ollama ----------
GEN = []
class Ollama(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def j(self, o):
        b = json.dumps(o).encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/version": return self.j({"version": "x"})
        if self.path == "/api/tags": return self.j({"models": [{"name": "testmodel:latest"}]})
        if self.path == "/api/ps": return self.j({"models": [{"name": "testmodel:latest"}]})
        self.j({})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/generate":
            GEN.append(body)
            return self.j({"response": "<think>hm</think>change the jacket to red leather"} if body.get("prompt") else {})
        if self.path == "/api/chat":
            self.send_response(200); self.end_headers()
            for t in ["안녕", "하세요"]: self.wfile.write((json.dumps({"message": {"content": t}, "done": False}) + "\n").encode()); self.wfile.flush()
            return
        if self.path == "/api/pull":
            self.send_response(200); self.end_headers()
            for c in (10, 100): self.wfile.write((json.dumps({"status": "pulling x", "total": 100, "completed": c}) + "\n").encode())
            self.wfile.write(b'{"status":"success"}\n'); return
        self.j({})

# ---------- file server with Range + Content-Disposition ----------
PAYLOAD = os.urandom(3_000_000)
class Files(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/html"):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b"<html>login</html>"); return
        rng = self.headers.get("Range"); start = int(rng.split("=")[1].split("-")[0]) if rng else 0
        data = PAYLOAD[start:]
        self.send_response(206 if rng else 200)
        self.send_header("Content-Length", str(len(data))); self.send_header("Content-Disposition", 'attachment; filename="civitai_style_v2.safetensors"')
        self.end_headers(); self.wfile.write(data)

def serve(h, port):
    s = ThreadingHTTPServer(("127.0.0.1", port), h); threading.Thread(target=s.serve_forever, daemon=True).start(); return s
serve(Comfy, 18188); serve(Ollama, 21434); serve(Files, 19999)
hub.GPU = {"name": "Test GPU", "vram_gb": 12}
srv = ThreadingHTTPServer(("127.0.0.1", 17860), hub.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
threading.Thread(target=hub.worker, daemon=True).start()
B = "http://127.0.0.1:17860"

def req(path, body=None, headers=None, raw=False):
    r = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=60) as f: d = f.read()
    except urllib.error.HTTPError as e:
        d = e.read(); return (e.code, d)
    return d if raw else json.loads(d)

def png_url(im, mode="RGB"):
    b = io.BytesIO(); im.convert(mode).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

def job(p, expect_ok=True):
    r = req("/api/job", p); jid = r["id"]
    for _ in range(120):
        j = req("/api/job/" + jid)
        if j["state"] in ("done", "error"): break
        time.sleep(0.25)
    if expect_ok: assert j["state"] == "done", j
    return j

def fetch_img(url): return Image.open(io.BytesIO(req(url, raw=True))).convert("RGB")

ok = lambda m: print("PASS", m)
# ---- source image + mask
W, H = 1600, 1200
src = Image.new("RGB", (W, H)); px = src.load()
for y in range(H):
    for x in range(0, W): px[x, y] = (x * 255 // W, y * 255 // H, 128)
mk = Image.new("L", (W, H), 0); ImageDraw.Draw(mk).ellipse((600, 400, 900, 700), fill=255)
SRC, MASK = png_url(src), png_url(mk)

# ---- basic endpoints
assert b"<html" in req("/", raw=True)[:200]; ok("index served")
assert req("/api/status")["gpu"]["vram_gb"] == 12; ok("status")
L = req("/api/lists"); assert L["qwen"] and L["checkpoints"] == ["noob.safetensors"] and "style.safetensors" in L["loras"] and L["llm"] == ["testmodel:latest"], L; ok("lists")
C = req("/api/catalog"); inst = {m["id"]: m["installed"] for m in C["llm"] + C["image"]}
assert inst["qwen-image"] and inst["esrgan"] and inst["qwen-lightning"] is True and not inst["noobai"] and not inst["qwen3-8b"], inst; ok("catalog installed flags")
assert req("/", headers={"Origin": "http://evil.example"})[0] == 403; ok("foreign Origin blocked")
assert req("/api/status", headers={"Host": "evil.example"})[0] == 403; ok("foreign Host blocked")

# ---- safety filter
assert hub.blocked("17살 여고생 누드") and hub.blocked("nude schoolgirl") and hub.blocked("a 15 year old naked girl")
assert not hub.blocked("a child playing in the park") and not hub.blocked("18 year old woman nude") and not hub.blocked("성인 여성 누드 사진을 보정해줘"); ok("minor+sexual filter")
body = req("/api/chat", {"messages": [{"role": "user", "content": "nude loli"}]}, raw=True); assert b"error" in body and "미성년".encode() in body; ok("chat blocked")
body = req("/api/chat", {"model": "m", "messages": [{"role": "user", "content": "hi"}]}, raw=True).decode()
txt = "".join(json.loads(l)["message"]["content"] for l in body.splitlines() if l.strip()); assert txt == "안녕하세요", txt; ok("chat streams (NDJSON passthrough)")

# ---- jobs
j = job({"kind": "gen", "prompt": "빨간 재킷을 입은 성인 여성", "translate": "on", "w": "832", "h": "1216", "n": "2", "ckpt": "noob.safetensors", "lora1": "style.safetensors", "seed": "5"})
assert len(j["images"]) == 2 and j["used"][0].endswith("change the jacket to red leather") and fetch_img(j["images"][0]).size == (832, 1216); ok("txt2img x2 + translation (<think> stripped)")
g = SUBMITTED[-1]; assert [n["class_type"] for n in g.values()].count("LoraLoader") == 1; ok("LoRA node wired")

j = job({"kind": "edit", "engine": "sdxl", "image": SRC, "mask": MASK, "prompt": "red leather jacket", "grow": "10", "denoise": "0.9"})
res = fetch_img(j["images"][0]); assert res.size == (W, H)
assert res.getpixel((750, 550)) == (255, 0, 0), res.getpixel((750, 550))          # inside mask -> model output (red)
for pt in [(100, 100), (1500, 1100), (300, 900), (1200, 300), (500, 550), (1000, 550)]:
    assert res.getpixel(pt) == src.getpixel(pt), (pt, res.getpixel(pt), src.getpixel(pt))  # outside untouched, byte-exact
edge = res.getpixel((905, 550)); assert edge != (255, 0, 0) and edge != src.getpixel((905, 550)), edge  # feathered blend zone
ip = [n for n in SUBMITTED[-1].values() if n["class_type"] == "LoadImage"][0]["inputs"]["image"]
ok("SDXL inpaint: crop->model->feathered stitch; outside pixels identical, blend zone present")
assert not list(INPUT.glob("hub_*")), "temp inputs not cleaned"; ok("temp input files cleaned")

j = job({"kind": "edit", "engine": "qwen", "image": SRC, "prompt": "재킷을 빨간색으로", "translate": "on", "fast": "on", "seed": "1"})
q = SUBMITTED[-1]; ks = [n for n in q.values() if n["class_type"] == "KSampler"][0]["inputs"]
assert ks["steps"] == 4 and ks["cfg"] == 1.0 and any(n["class_type"] == "LoraLoaderModelOnly" for n in q.values())
assert any(n["class_type"] == "TextEncodeQwenImage21" for n in q.values())
r = fetch_img(j["images"][0]); assert abs(r.width * r.height - 1_000_000) < 60_000 and r.width % 32 == 0 and r.height % 32 == 0, r.size
ok("Qwen-Image 2.1 edit (Lightning 4-step, ~1MP, /32 dims)")


j = job({"kind": "edit", "engine": "qwen", "image": SRC, "prompt": "make it red", "hires": "on"}); assert fetch_img(j["images"][0]).size == (W, H); ok("Qwen + hires restore -> original size")
j = job({"kind": "edit", "engine": "qwen", "image": SRC, "mask": MASK, "prompt": "make it red", "grow": "6"}); res = fetch_img(j["images"][0])
assert res.size == (W, H) and res.getpixel((750, 550)) == (255, 0, 0) and res.getpixel((100, 100)) == src.getpixel((100, 100)); ok("Qwen + mask: only masked area changes")
j = job({"kind": "up", "image": SRC, "scale": "2", "upm": "RealESRGAN_x4plus.pth"}); assert fetch_img(j["images"][0]).size == (W * 2, H * 2); ok("upscale 2x")
j = job({"kind": "up", "image": png_url(Image.new("RGB", (2300, 100))), "scale": "4"}, expect_ok=False); assert j["state"] == "error" and "8192" in j["error"]; ok("upscale size guard (2300px x4 > 8192)")
j = job({"kind": "gen", "prompt": "nude schoolgirl", "ckpt": "noob.safetensors"}, expect_ok=False); assert j["state"] == "error" and "미성년" in j["error"]; ok("job-level minor filter")
j = job({"kind": "edit", "engine": "sdxl", "image": SRC, "prompt": "x"}, expect_ok=False); assert "마스크" in j["error"]; ok("sdxl without mask -> friendly error")
(M / "diffusion_models/qwen_image_2.1_int8_convrot.safetensors").unlink()
j = job({"kind": "edit", "engine": "qwen", "image": SRC, "prompt": "x"}, expect_ok=False); assert "설치" in j["error"]; ok("missing Qwen model -> friendly error")
assert STATE.get("freed", 0) >= 0; print("INFO comfy /free calls:", STATE.get("freed", 0), "| ollama unload calls:", sum(1 for g in GEN if g.get("keep_alive") == 0))

# ---- install / downloads
def wait_tasks():
    for _ in range(100):
        t = req("/api/install")
        if all(x["state"] in ("done", "error") for x in t): return t
        time.sleep(0.2)
    raise AssertionError("tasks stuck")
r = req("/api/install", {"custom": {"url": "http://127.0.0.1:19999/dl?id=7", "dir": "loras", "token": "KEY"}, "ollama": "huihui_ai/qwen3-abliterated:8b"}); assert r.get("ok")
t = wait_tasks(); assert all(x["state"] == "done" for x in t), t
f = M / "loras/civitai_style_v2.safetensors"; assert f.exists() and f.read_bytes() == PAYLOAD; ok("custom download: Content-Disposition filename + full content")
assert not list((M / "loras").glob("*.part")); assert all("url" not in x and "token" not in x for x in t); ok("no .part leftovers; token not exposed via API")
# resume
f.unlink(); part = M / "loras" / (__import__("hashlib").sha1(b"http://127.0.0.1:19999/dl?id=8").hexdigest()[:12] + ".part"); part.write_bytes(PAYLOAD[:1_000_000])
req("/api/install", {"custom": {"url": "http://127.0.0.1:19999/dl?id=8", "dir": "loras"}}); wait_tasks()
assert (M / "loras/civitai_style_v2.safetensors").read_bytes() == PAYLOAD; ok("resume from partial download")
req("/api/install", {"custom": {"url": "http://127.0.0.1:19999/html", "dir": "loras"}}); t = wait_tasks(); assert t[-1]["state"] == "error" and "웹페이지" in t[-1]["msg"]; ok("HTML login page detected")
req("/api/install", {"custom": {"url": "http://127.0.0.1:19999/x", "dir": "../../evil"}}); assert len(req("/api/install")) == len(t); ok("path traversal in dir rejected")
big = req("/api/install", {"ids": ["qwen3-32b"] * 1}); print("INFO install(ids) ->", big)
print("\nALL TESTS PASSED")
