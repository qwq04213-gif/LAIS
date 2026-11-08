import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, os, pathlib, io, threading, time, types, urllib.request, urllib.error, urllib.parse
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
f = hub.swap_file(); f.parent.mkdir(parents=True, exist_ok=True)
if f.exists(): f.unlink()
r = req("/api/faceswap/model"); assert r["file"] is False and r["state"] == ""; ok("status: model file missing")
STATE["missing"].discard("ReActorFaceSwap"); hub.caps(True)
j = job({"kind": "feat", "feature": "faceswap", "image": png_url(Image.new("RGB", (64, 64))), "source": png_url(Image.new("RGB", (64, 64))), "consent": "on"}, expect_ok=False)
assert "모델 받기" in j.get("error", "") or "inswapper" in j.get("error", "") or j.get("state") == "done"; ok("faceswap with no model gives a clear message (or the mock has options)")
DATA = b"M" * (110 << 20)
class Resp(io.BytesIO):
    def __init__(s, d, st=200): super().__init__(d); s.status = st; s.headers = {"Content-Length": str(len(d))}
    def __enter__(s): return s
    def __exit__(s, *a): pass
seen = []
def fake(rq, timeout=0):
    seen.append(rq.headers.get("Range")); return Resp(DATA)
_real = urllib.request.urlopen; hub.urllib = types.SimpleNamespace(request=types.SimpleNamespace(urlopen=fake, Request=urllib.request.Request), error=urllib.error, parse=urllib.parse)
assert req("/api/faceswap/model", {})["ok"]
for _ in range(100):
    if req("/api/faceswap/model")["state"] in ("done", "error"): break
    time.sleep(0.1)
s = req("/api/faceswap/model"); assert s["state"] == "done" and s["file"] and s["size"] == len(DATA) and not f.with_name(f.name + ".part").exists(), s; ok("download completes, .part renamed, status shows file")
assert "이미" in req("/api/faceswap/model", {})["error"]; ok("second click refused (already there)")
f.unlink(); hub.SWAP_JOB.update(state="", msg="")
def bad(rq, timeout=0): raise OSError("no net")
hub.urllib = types.SimpleNamespace(request=types.SimpleNamespace(urlopen=bad, Request=urllib.request.Request), error=urllib.error, parse=urllib.parse); req("/api/faceswap/model", {})
for _ in range(100):
    if req("/api/faceswap/model")["state"] == "error": break
    time.sleep(0.1)
assert "이어서" in req("/api/faceswap/model")["msg"] and not f.exists(); ok("failure → message, no half file treated as installed")
print("ALL OK")
