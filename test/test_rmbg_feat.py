"""기타 기능 '배경 지우기': 모델 없으면 받기 시작, 진짜 u2netp 모델로 투명/색 배경, 테두리 자르기, ComfyUI 없이 실행."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, shutil, urllib.request
os.environ["TEST_HUB_PORT"] = "17953"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import ImageDraw
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def job(o):
    jid = post("/api/job", o)["id"]
    for _ in range(600):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
im = Image.new("RGB", (640, 480), (40, 140, 40)); ImageDraw.Draw(im).ellipse((220, 140, 420, 340), fill=(230, 60, 60))
b = io.BytesIO(); im.save(b, "PNG"); SRC = "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
hub.rmbg_install = lambda p: {"ok": True, "started": p.get("key")}
j = job({"kind": "feat", "feature": "rmbg", "image": SRC, "rmodel": "fast"}); assert j["state"] == "error" and "받기 시작" in j["error"], j; ok("no model → starts the download and says so")
(hub.MODELS / "rmbg").mkdir(exist_ok=True); shutil.copy(BASE + "/rmbg-test/u2netp.onnx", hub.MODELS / "rmbg" / "u2netp.onnx")
n0 = len(SUBMITTED); STATE["down"] = True if "down" in STATE else None
j = job({"kind": "feat", "feature": "rmbg", "image": SRC, "rmodel": "fast"}); assert j["state"] == "done", j
r = Image.open(io.BytesIO(urllib.request.urlopen(B + j["images"][0]).read())); assert r.mode == "RGBA" and r.size == (640, 480)
a = r.getchannel("A"); assert a.getpixel((320, 240)) > 200 and a.getpixel((5, 5)) < 30 and len(SUBMITTED) == n0; ok("transparent PNG with the real model, no ComfyUI job")
j = job({"kind": "feat", "feature": "rmbg", "image": SRC, "rmodel": "fast", "bg": "custom", "bgcolor": "#0000ff", "crop": "on"}); r = Image.open(io.BytesIO(urllib.request.urlopen(B + j["images"][0]).read()))
assert r.mode == "RGB" and r.getpixel((320, 240))[0] > 150 and j["state"] == "done"
j = job({"kind": "feat", "feature": "rmbg", "image": SRC, "rmodel": "fast", "crop": "on"}); r = Image.open(io.BytesIO(urllib.request.urlopen(B + j["images"][0]).read()))
assert r.mode == "RGBA" and r.width < 400 and r.height < 320, r.size; ok("custom colour background; crop trims to the subject")
print("ALL OK")
