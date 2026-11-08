"""메모리 부족 자동 안내: 문구 인식, 작업 종류별 팁, 작업 결과에 실림, 메모리 비우기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, time, json, urllib.request
os.environ["TEST_HUB_PORT"] = "17892"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
for m in ("CUDA out of memory. Tried to allocate 2.00 GiB", "torch.OutOfMemoryError: Allocation on device", "Failed to allocate 3GB", "Not enough memory"):
    assert hub.oom_guide(m, {"kind": "gen"}), m
assert hub.oom_guide("No module named 'cv2'", {"kind": "gen"}) is None and hub.oom_guide("", {}) is None and hub.oom_guide(None, None) is None; ok("memory errors recognised, others are not")
g = hub.oom_guide("out of memory", {"kind": "vid"})["tips"]; assert any("프레임" in t for t in g) and "메모리 비우기" in g[-1]
assert any("해상도" in t for t in hub.oom_guide("out of memory", {"kind": "gen"})["tips"])
assert any("보간" in t for t in hub.oom_guide("out of memory", {"kind": "vpost"})["tips"])
assert any("업스케일" in t for t in hub.oom_guide("out of memory", {"kind": "up"})["tips"]); ok("tips depend on the job kind")
orig = hub.do_feat
def bad(p, J): raise RuntimeError("CUDA out of memory")
hub.do_feat = bad
j = post("/api/job", {"kind": "feat", "feature": "resize", "image": "x"})
for _ in range(40):
    jj = get("/api/job/" + j["id"])
    if jj["state"] == "error": break
    time.sleep(0.25)
assert jj["oom"]["tips"] and "pymod" not in jj; hub.do_feat = orig; ok("a failed job carries the guide to the screen")
calls = []
hub.free_comfy = lambda: calls.append("c"); hub.free_ollama = lambda: calls.append("o")
assert post("/api/memory/free", {}) == {"ok": True} and sorted(calls) == ["c", "o"]; ok("memory-free button frees both engines")
print("ALL OK")
