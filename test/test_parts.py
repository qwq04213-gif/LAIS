"""설치한 확장·부품 관리: 목록, 하나씩 지우기, 안전 검사."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, os, subprocess, pathlib
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
cn = hub.COMFY / "custom_nodes"; cn.mkdir(parents=True, exist_ok=True)
for n in ("ComfyUI-ReActor", "ComfyUI-Impact-Subpack", "other-pack", "__pycache__"):
    (cn / n).mkdir(exist_ok=True); (cn / n / "a.py").write_bytes(b"x" * 1000)
(cn / "ComfyUI-ReActor" / ".git").mkdir(); (cn / "ComfyUI-ReActor" / ".git" / "obj").write_bytes(b"g"); os.chmod(cn / "ComfyUI-ReActor" / ".git" / "obj", 0o444)
(cn / "readme.txt").write_text("x")
(hub.MODELS / "insightface").mkdir(parents=True, exist_ok=True); (hub.MODELS / "insightface" / "m.onnx").write_bytes(b"i" * 500)
(hub.MODELS / "checkpoints").mkdir(parents=True, exist_ok=True)
r = req("/api/parts")
names = {n["name"]: n for n in r["nodes"]}
assert set(names) == {"ComfyUI-ReActor", "ComfyUI-Impact-Subpack", "other-pack"} and names["ComfyUI-ReActor"]["incomplete"] and names["ComfyUI-ReActor"]["known"] and names["other-pack"]["size"] == 1000; ok("extensions listed with size; __pycache__/files hidden; unfinished install flagged")
assert [m["name"] for m in r["models"] if m["name"] == "insightface"] and not any(m["name"] == "checkpoints" for m in r["models"]); ok("extension model folders listed; managed model folders (checkpoints…) not")
assert not any(p["module"] in ("PIL", "yaml", "einops", "scipy") for p in r["pips"]); ok("ComfyUI core parts never offered")
for bad in ("../x", "", ".git", "__pycache__", "nope", "readme.txt"):
    assert req("/api/parts/delete", {"kind": "node", "name": bad}).get("error"), bad
assert (cn / "other-pack").exists(); ok("path tricks / files / hidden names refused")
e = req("/api/parts/delete", {"kind": "node", "name": "ComfyUI-ReActor"}); assert "밖에서" in e["error"] and (cn / "ComfyUI-ReActor").exists(); ok("refused while ComfyUI runs outside the studio (files would be locked)")
ev = []
class FP:
    args = ["python", "main.py"]
    def terminate(s): ev.append("stop")
    def wait(s, timeout=0): pass
hub.procs.append(FP()); hub.start_engines = lambda: ev.append("start")
d = req("/api/parts/delete", {"kind": "node", "name": "ComfyUI-ReActor"}); assert ev == ["stop", "start"]; ok("studio-started ComfyUI is stopped, then restarted after deleting")
assert d["ok"] and not (cn / "ComfyUI-ReActor").exists() and (cn / "other-pack").exists(); ok("read-only .git files don't block deleting one extension; others untouched")
assert req("/api/parts/delete", {"kind": "model", "name": "checkpoints"}).get("error") and (hub.MODELS / "checkpoints").exists(); ok("model folder delete only from the listed names")
assert req("/api/parts/delete", {"kind": "model", "name": "insightface"})["ok"] and not (hub.MODELS / "insightface").exists(); ok("extension model folder deleted")
calls = []
class R: returncode = 0; stdout = ""; stderr = ""
orig = subprocess.run; hub.subprocess.run = lambda c, **k: (calls.append([str(x) for x in c]) or R())
assert req("/api/parts/delete", {"kind": "pip", "name": "PIL"}).get("error") and req("/api/parts/delete", {"kind": "pip", "name": "evil"}).get("error"); assert not calls; ok("core/unknown pip parts refused")
assert req("/api/parts/delete", {"kind": "pip", "name": "timm"})["ok"] and calls[-1][-3:] == ["uninstall", "-y", "timm"]; ok("pip part uninstalled by name from the fixed list")
assert req("/api/parts/delete", {"kind": "edge"})["ok"] and calls[-1][-1] == "edge-tts"; ok("edge-tts uninstall")
hub.subprocess.run = orig
hub.JOBS["zz"] = {"state": "running"}
assert "진행 중" in req("/api/parts/delete", {"kind": "node", "name": "other-pack"})["error"] and (cn / "other-pack").exists(); del hub.JOBS["zz"]; ok("refused while a job is running")
print("ALL OK")
