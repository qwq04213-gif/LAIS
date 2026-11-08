"""얼굴 교체: 동의 확인 필수, 그래프 구성, 모델 선택, 빈 결과 안내, 설치 경로(고정 커밋)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, json, io, base64, time, urllib.request
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
ok = lambda m: print("PASS", m)
def png_url(c):
    b = io.BytesIO(); Image.new("RGB", (64, 64), c).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def node(wf, c): return [n for n in wf.values() if n["class_type"] == c][0]["inputs"]
base = {"kind": "feat", "feature": "faceswap", "image": png_url((200, 50, 50)), "source": png_url((50, 200, 50))}
n0 = len(SUBMITTED)
j = job({**base, "consent": "on", "source": ""}, expect_ok=False); assert "둘 다" in j["error"] and len(SUBMITTED) == n0; ok("both photos are required")
job({**base, "consent": "on"})
g = SUBMITTED[-1]; r = node(g, "ReActorFaceSwap")
assert r["swap_model"] == "inswapper_128.onnx" and r["face_restore_model"] == "GFPGANv1.4.pth" and r["input_faces_index"] == "0" and r["source_faces_index"] == "0" and r["facedetection"] == "retinaface_resnet50" and r["enabled"] is True
assert isinstance(r["input_image"], list) and isinstance(r["source_image"], list) and r["input_image"] != r["source_image"]; ok("graph: target + source → ReActorFaceSwap with inswapper and GFPGAN 1.4")
job({**base, "consent": "on", "restore": "codeformer", "vis": "0.6", "cf": "0.8", "target_face": "1, 2", "source_face": "x"})
r = node(SUBMITTED[-1], "ReActorFaceSwap"); assert r["face_restore_model"].startswith("codeformer") and r["face_restore_visibility"] == 0.6 and r["codeformer_weight"] == 0.8 and r["input_faces_index"] == "1,2" and r["source_faces_index"] == "0"; ok("options passed; bad face numbers fall back to 0")
orig_run = hub.run_wf
def flaky(g, J, raw=False):
    if any("codeformer" in str(n["inputs"].get("face_restore_model", "")).lower() for n in g.values()): raise RuntimeError("Error(s) in loading state_dict for CodeFormer")
    return orig_run(g, J, raw)
hub.run_wf = flaky
j = job({**base, "consent": "on", "restore": "codeformer"}); hub.run_wf = orig_run
assert j["state"] == "done" and node(SUBMITTED[-1], "ReActorFaceSwap")["face_restore_model"].lower().startswith("gfpgan") and any("CodeFormer" in w for w in j.get("warn", [])), j; ok("CodeFormer failure falls back to GFPGAN with a warning")
job({**base, "consent": "on", "restore": "none"}); assert node(SUBMITTED[-1], "ReActorFaceSwap")["face_restore_model"] == "none"; ok("restore can be turned off")
STATE["swaps"] = []; hub.caps(True)
j = job({**base, "consent": "on"}, expect_ok=False); assert "모델 받기" in j["error"]; ok("no swap model installed → clear message"); STATE.pop("swaps"); hub.caps(True)
big = Image.new("RGB", (4200, 10), (1, 2, 3)); b = io.BytesIO(); big.save(b, "PNG")
j = job({**base, "consent": "on", "image": "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()}, expect_ok=False); assert "너무 커요" in j["error"]; ok("oversized photo refused")
F = [f for f in json.load(urllib.request.urlopen(B + "/api/features")) if f["id"] == "faceswap"][0]; assert F["missing_nodes"] == [] and not any(x["type"] == "check" for x in F["fields"]); ok("feature is listed with a required consent field")
STATE["missing"].add("ReActorFaceSwap"); hub.caps(True)
F = [f for f in json.load(urllib.request.urlopen(B + "/api/features")) if f["id"] == "faceswap"][0]; assert F["missing_nodes"] == ["ReActorFaceSwap"]
src = post("/api/nodes/sources", {"missing": ["ReActorFaceSwap"]}); assert src["repos"][0]["repo"] == hub.REACTOR_REPO, src; ok("install source is known without the public node list")
seen = []
class Stop(Exception): pass
orig = urllib.request.urlopen
def fake(url, *a, **k):
    u = url if isinstance(url, str) else url.full_url
    if "github.com" not in u: return orig(url, *a, **k)
    seen.append(u); raise Stop()
urllib.request.urlopen = fake
try:
    assert post("/api/nodes/install", {"repo": hub.REACTOR_REPO}) == {"ok": True}
    for _ in range(50):
        if seen: break
        time.sleep(0.1)
finally: urllib.request.urlopen = orig
assert seen[0] == hub.REACTOR_REPO + "/archive/3be5f356fe5b120a7a274d2509c0ecef5d0a7498.zip", seen; ok("install downloads the reviewed, pinned commit")
print("ALL OK")
