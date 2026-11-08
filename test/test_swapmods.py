"""얼굴 교체: pip 가 조용히 실패해 onnx 가 빠진 경우를 감지해 채워 넣고, 못 채우면 이유를 알려준다."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, pathlib, subprocess, json
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
hub.PY = pathlib.Path("/fake/python.exe")
orig_exists = pathlib.Path.exists
pathlib.Path.exists = lambda self: True if str(self) == "/fake/python.exe" else orig_exists(self)
hub.HOME = pathlib.Path("/tmp")
state = {"missing": ["onnx", "colour"]}; calls = []
class R:
    def __init__(s, rc=0, out="", err=""): s.returncode, s.stdout, s.stderr = rc, out, err
def fake_run(cmd, **k):
    cmd = [str(c) for c in cmd]; calls.append(cmd)
    if "-c" in cmd: return R(0, json.dumps([m for m in state["missing"]]))
    spec = cmd[cmd.index("install") + 1]
    if spec == "onnx" and state.get("fail"): return R(1, "", "ERROR: No matching distribution found for onnx")
    state["missing"] = [m for m in state["missing"] if hub.REACTOR_MODS[m] != spec]
    return R(0, "ok")
hub.subprocess.run = fake_run
swaps = hub.combo_opts("ReActorFaceSwap", "swap_model")
base = {"kind": "feat", "feature": "faceswap", "image": png_url(Image.new("RGB", (64, 64), (200, 60, 60))), "source": png_url(Image.new("RGB", (64, 64), (60, 200, 60))), "consent": "on"}
j = job(dict(base)); installs = [c[c.index("install") + 1] for c in calls if "install" in c]
assert installs == ["onnx", "colour-science"] and j["state"] == "done", (installs, j); ok("missing onnx/colour are detected and installed before the swap runs")
calls.clear(); state["missing"] = []; job(dict(base)); assert not [c for c in calls if "install" in c]; ok("nothing missing → no pip calls")
calls.clear(); state.update(missing=["onnx"], fail=True); j = job(dict(base), expect_ok=False)
assert j["state"] == "error" and "onnx" in j["error"] and "No matching distribution" in j["error"]; ok("failed install → error names the part and pip's reason")
assert hub.pymod_missing("No module named 'onnx'") == {"module": "onnx", "pip": "onnx"}; ok("generic 'No module named onnx' now offers the install button")

# ── albumentations: cv2 가 이미 있으면 opencv 를 건드리지 않는다 / 파일 잠김(WinError 5)이면 ComfyUI 를 잠시 끄고 재시도
calls.clear(); state.update(missing=["albumentations"], fail=False); state["cv2_ok"] = True
def fake2(cmd, **k):
    cmd = [str(c) for c in cmd]; calls.append(cmd)
    if "-c" in cmd:
        mods = eval(cmd[cmd.index("-c") + 1].split("for m in ")[1].split(" if")[0]); return R(0, json.dumps([m for m in mods if m in state["missing"]]))
    if "--no-deps" in cmd and state.get("lock") and not state.get("stopped"): return R(1, "", "ERROR: Could not install packages due to an OSError: [WinError 5] 액세스가 거부되었습니다: 'cv2.pyd'")
    if "--no-deps" in cmd or "albumentations" in cmd: state["missing"] = []
    return R(0, "ok")
hub.subprocess.run = fake2
rc, out, note = hub.pip_install_one("albumentations")
inst = [c for c in calls if "install" in c]; assert rc == 0 and any("--no-deps" in c and "albucore" in c for c in inst) and not any("opencv-python-headless" in c for c in inst), inst; ok("albumentations installed with --no-deps (opencv/cv2 left alone)")
calls.clear(); state.update(missing=["albumentations"], lock=True, stopped=False)
ev = []
class FP:
    args = ["python", "main.py"]
    def terminate(s): ev.append("stop"); state["stopped"] = True
    def wait(s, timeout=0): pass
hub.procs.append(FP()); hub.start_engines = lambda: ev.append("start")
rc, out, note = hub.pip_install_one("albumentations"); assert rc == 0 and ev == ["stop", "start"] and "껐다" in note, (rc, ev, note); ok("locked file (WinError 5) → studio's ComfyUI stopped, install retried, ComfyUI started again")
hub.procs.clear(); state.update(missing=["albumentations"], lock=True, stopped=False)
rc, out, note = hub.pip_install_one("albumentations"); assert rc and "스튜디오 밖" in note; ok("ComfyUI running outside the studio → clear instruction instead of a vague failure")
print("ALL OK")
