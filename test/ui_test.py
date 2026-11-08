"""Integration test for hub.py using mock ComfyUI / Ollama servers (no network, no GPU)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import base64, io, json, os, sys, tempfile, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image, ImageDraw

TMP = Path(tempfile.mkdtemp())
os.environ.update(STUDIO_ROOT=str(TMP), HUB_PORT="17861", COMFY_URL="http://127.0.0.1:18188", OLLAMA_URL="http://127.0.0.1:21434")
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import hub  # noqa

M = TMP / "engine/ComfyUI_windows_portable/ComfyUI/models"
for d, f in [("checkpoints", "noob.safetensors"), ("diffusion_models", "qwen_image_edit_2509_fp8_e4m3fn.safetensors"),
             ("text_encoders", "qwen_2.5_vl_7b_fp8_scaled.safetensors"), ("vae", "qwen_image_vae.safetensors"),
             ("loras", "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors"), ("loras", "style.safetensors"),
             ("upscale_models", "RealESRGAN_x4plus.pth")]:
    (M / d).mkdir(parents=True, exist_ok=True); (M / d / f).write_bytes(b"x")
INPUT = M.parent / "input"; INPUT.mkdir(exist_ok=True)

# ---------- mock ComfyUI ----------
REQ = {"CheckpointLoaderSimple": ["ckpt_name"], "LoraLoader": ["model", "clip", "lora_name", "strength_model", "strength_clip"],
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
        if u.startswith("/object_info/"):
            n = u.split("/")[-1]
            ok = n != "TextEncodeQwenImageEditPlus" or STATE["qwen_plus"]
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
srv = ThreadingHTTPServer(("127.0.0.1", 17861), hub.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
threading.Thread(target=hub.worker, daemon=True).start()

import base64, io
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
SH = Path("/tmp/shots"); SH.mkdir(exist_ok=True)
im = Image.new("RGB", (1200, 800)); px = im.load()
for y in range(800):
    for x in range(1200): px[x, y] = (40 + x // 8, 90 + y // 8, 160 - x // 12)
ImageDraw.Draw(im).ellipse((420, 220, 780, 620), fill=(230, 190, 160))
im.save("/tmp/shots/sample.png")

errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1360, "height": 860})
    pg.on("console", lambda m: errs.append(("console", m.text)) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
    pg.goto("http://127.0.0.1:17861/"); pg.wait_for_timeout(600)
    # --- no first-run consent dialog any more (3.17)
    assert pg.locator("#ack").count() == 0; print("PASS no consent dialog")
    pg.screenshot(path=str(SH / "1_chat_empty.png"))
    # --- chat
    pg.wait_for_function("document.querySelectorAll('#llm option').length>0")
    pg.fill("#msg", "안녕! 자기소개 해줘"); pg.press("#msg", "Enter"); pg.wait_for_timeout(900)
    log = pg.inner_text("#log"); assert "안녕! 자기소개 해줘" in log and "안녕하세요" in log, log
    pg.click("#send") if False else None
    print("PASS chat send + streamed reply:", repr(log[:60]))
    pg.fill("#msg", "nude loli"); pg.press("#msg", "Enter"); pg.wait_for_timeout(700)
    assert pg.locator("#cerr").is_visible() and "미성년자" in pg.inner_text("#cerr")
    assert "nude loli" not in pg.inner_text("#log") and pg.input_value("#msg") == "nude loli"
    pg.fill("#msg", "다음 질문이야"); pg.press("#msg", "Enter"); pg.wait_for_timeout(900)
    assert "다음 질문이야" in pg.inner_text("#log") and pg.locator("#cerr").is_hidden()
    print("PASS blocked turn removed from history; next normal message is NOT blocked")
    pg.screenshot(path=str(SH / "2_chat.png"))
    # --- edit view
    pg.click("nav button[data-v=edit]"); pg.wait_for_timeout(300)
    assert pg.locator("#f-edit .sdxl").first.is_hidden() and pg.locator("#f-edit .qwen").first.is_visible(); print("PASS qwen mode hides SDXL-only fields")
    pg.screenshot(path=str(SH / "3_edit_empty.png"))
    pg.set_input_files("#v-edit .drop input[type=file]", "/tmp/shots/sample.png"); pg.wait_for_selector("#v-edit .work:not([hidden])")
    pg.wait_for_function("document.querySelector('#v-edit canvas').width>100")
    cv = pg.locator("#v-edit canvas"); bb = cv.bounding_box(); print("canvas px:", cv.evaluate("c=>[c.width,c.height]"), "css box:", [round(bb['width']), round(bb['height'])])
    assert pg.evaluate("IV.edit.hasMask()") is False
    cx, cy = bb["x"] + bb["width"] * 0.5, bb["y"] + bb["height"] * 0.5
    pg.mouse.move(cx - 60, cy - 40); pg.mouse.down()
    for i in range(12): pg.mouse.move(cx - 60 + i * 11, cy - 40 + (i % 4) * 14)
    ring_visible = pg.locator("#v-edit .ring").evaluate("r=>getComputedStyle(r).display")
    pg.mouse.up(); assert ring_visible == "block", ring_visible
    assert pg.evaluate("IV.edit.hasMask()") is True; print("PASS mask painting + brush ring")
    m = pg.evaluate("IV.edit.maskData()"); mi = Image.open(io.BytesIO(base64.b64decode(m.split(',')[1]))).convert("RGB")
    r = mi.getchannel("R"); white = sum(1 for v in r.getdata() if v > 127); assert white > 500 and mi.size == tuple(cv.evaluate("c=>[c.width,c.height]")), (white, mi.size)
    print("PASS exported mask:", mi.size, "white px:", white)
    assert pg.locator("#f-edit [name=translate]").is_checked() is False
    pg.select_option("#f-edit [name=engine]", "sdxl"); pg.wait_for_timeout(200)
    assert pg.locator("#f-edit [name=translate]").is_checked() is True; print("PASS translate default: off for Qwen, on for SDXL")
    assert pg.locator("#f-edit .qwen").first.is_hidden() and pg.locator("#f-edit .sdxl").first.is_visible(); print("PASS engine toggle -> SDXL fields")
    pg.fill("#f-edit [name=prompt]", "검은 실크 가운"); pg.screenshot(path=str(SH / "4_edit_mask.png"))
    pg.click("#f-edit .go"); pg.wait_for_selector("#v-edit .batch figure img", timeout=20000)
    pg.wait_for_function("document.querySelector('#v-edit .batch figure img').naturalWidth>0")
    nat = pg.locator("#v-edit .batch figure img").first.evaluate("i=>[i.naturalWidth,i.naturalHeight]"); assert nat == [1200, 800], nat
    assert "사용된 프롬프트" in pg.inner_text("#v-edit .batch"); print("PASS edit result rendered, size", nat, "+ translated-prompt note")
    top = pg.locator("#v-edit .batch figure img").first.bounding_box()["y"]; assert 0 <= top < 860, top; print("PASS result scrolled into view (y=%d)" % top)
    pg.screenshot(path=str(SH / "5_edit_result.png"), full_page=False)
    # chain: send result back as input
    pg.click("#v-edit .batch button[data-to=edit]"); pg.wait_for_timeout(500)
    assert pg.evaluate("IV.edit.img").startswith("data:image/png"); assert pg.evaluate("IV.edit.hasMask()") is False; print("PASS 'continue editing' reloads result as input and clears mask")
    # no-mask sdxl -> friendly message
    pg.click("#f-edit .go"); assert "칠해" in pg.inner_text("#v-edit .jobbar .st"); print("PASS sdxl without mask -> inline message")
    # --- gen
    pg.click("nav button[data-v=gen]"); pg.fill("#f-gen [name=prompt]", "1girl, red jacket"); pg.click("#f-gen .go")
    pg.wait_for_selector("#v-gen .batch figure img", timeout=20000); print("PASS gen result rendered")
    # --- upscale
    pg.click("nav button[data-v=up]"); pg.set_input_files("#v-up input[type=file]", "/tmp/shots/sample.png"); pg.fill("#f-up [name=scale]", "2")
    pg.click("#f-up .go"); pg.wait_for_selector("#v-up .batch figure img", timeout=20000)
    nat = pg.locator("#v-up .batch figure img").first.evaluate("i=>new Promise(r=>{if(i.naturalWidth)return r([i.naturalWidth,i.naturalHeight]);i.onload=()=>r([i.naturalWidth,i.naturalHeight])})"); assert nat == [2400, 1600], nat
    print("PASS upscale result", nat)
    # --- setup
    pg.click("nav button[data-v=setup]"); pg.wait_for_selector("#cat-llm .item"); pg.wait_for_timeout(300)
    rows = pg.locator("#v-setup .item").count(); print("catalog rows:", rows)
    assert pg.locator("#v-setup .item", has_text="Real-ESRGAN x4plus").first.inner_text().find("설치됨") >= 0
    pg.click("#rec"); chk = pg.evaluate("[...document.querySelectorAll('#v-setup .item input:checked')].map(i=>i.value)"); print("12GB GPU recommendation:", chk)
    assert "qwen3-14b" in chk and "noobai" in chk and "esrgan" not in chk  # esrgan already installed -> disabled
    pg.screenshot(path=str(SH / "6_setup.png"), full_page=True)
    # (주소로 직접 받기는 다운로드 탭으로 옮겼고 ui_test4 에서 검사해요)
    b.close()
print("page errors:", errs)
assert not errs, errs
print("\nUI TESTS PASSED")
