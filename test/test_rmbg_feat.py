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
# 4.2: 경계 다듬기 — 작은 해상도로 찾은 흐릿한 경계를 사진의 실제 경계에 맞추고, 경계의 배경색을 걷어내요
import numpy as np
sys.path.insert(0, BASE + "/LocalAI-Studio/hub"); import bgremove
W = 1200; pic = Image.new("RGB", (W, W), (30, 60, 220)); ImageDraw.Draw(pic).ellipse((250, 250, 950, 950), fill=(230, 40, 40))
truth = Image.new("L", (W, W), 0); ImageDraw.Draw(truth).ellipse((250, 250, 950, 950), fill=255)
blurry = truth.resize((320, 320), Image.BILINEAR).resize((W, W), Image.LANCZOS)
band = lambda m: int(((np.asarray(m) > 25) & (np.asarray(m) < 230)).sum())
al, col = bgremove.refine(pic, blurry)
assert band(al) < band(blurry) * 0.2, (band(blurry), band(al))
assert np.abs(np.asarray(al, float) - np.asarray(truth, float)).mean() <= np.abs(np.asarray(blurry, float) - np.asarray(truth, float)).mean() + 0.01
semi = (np.asarray(al) > 10) & (np.asarray(al) < 245)
if semi.any(): assert np.asarray(col)[semi][:, 2].mean() < 120                     # 경계에 파란 배경색이 덜 남아요
noisy = Image.fromarray(np.clip(np.asarray(pic, float) + np.random.default_rng(1).normal(0, 35, (W, W, 3)), 0, 255).astype("uint8"))
al2, _ = bgremove.refine(noisy, blurry); assert np.asarray(al2)[:100, :100].max() < 10 and np.asarray(al2)[600, 600] > 245
r0 = bgremove.compose(pic, blurry, refine_edges=False); r1 = bgremove.compose(pic, blurry, (255, 255, 255)); assert r0.mode == "RGBA" and r1.mode == "RGB"
ok("edge refine: blurry band from a low-res model snaps to the real edge, background colour removed from edges, noisy backgrounds stay clean")
# 4.2: '최고(BiRefNet)' — ComfyUI 로 돌려요. 없으면 설치와 모델 목록에서 받기 시작
st = json.load(urllib.request.urlopen(B + "/api/rmbg/status")); assert st["models"]["best"]["comfy"] and not st["models"]["best"]["installed"] and st["default"] == "normal"
cat = json.load(urllib.request.urlopen(B + "/api/catalog")); assert any(m["id"] == "birefnet" and m["files"][0]["dir"] == "background_removal" for m in cat["image"])
started = []; hub.rmbg_install = lambda p: started.append(p.get("key")) or {"ok": True}
j = job({"kind": "feat", "feature": "rmbg", "image": SRC, "rmodel": "best"}); assert j["state"] == "error" and "BiRefNet" in j["error"] and started == ["best"], j
(hub.MODELS / "background_removal").mkdir(exist_ok=True); (hub.MODELS / "background_removal" / "birefnet.safetensors").write_bytes(b"x")
assert json.load(urllib.request.urlopen(B + "/api/rmbg/status"))["default"] == "best"
n0 = len(SUBMITTED)
j = job({"kind": "feat", "feature": "rmbg", "image": SRC}); assert j["state"] == "done", j               # 고르지 않으면 설치된 BiRefNet
g = SUBMITTED[-1]; assert len(SUBMITTED) == n0 + 1 and any(v["class_type"] == "RemoveBackground" for v in g.values())
assert [v["inputs"]["bg_removal_name"] for v in g.values() if v["class_type"] == "LoadBackgroundRemovalModel"] == ["birefnet.safetensors"]
r = Image.open(io.BytesIO(urllib.request.urlopen(B + j["images"][0]).read())); assert r.mode == "RGBA" and r.size == (640, 480)
assert not list((hub.COMFY / "input").glob("hub_*.png"))
ok("best quality (BiRefNet): not installed → download; installed → default, runs on ComfyUI, temp input cleaned")
print("ALL OK")
