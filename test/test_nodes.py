"""커스텀 노드 도우미: 없는 노드 → 저장소 찾기 → 설치 → ComfyUI 다시 시작."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time
os.environ["TEST_HUB_PORT"] = "17877"
sys.path.insert(0, BASE + "/test")
from mocks import *
import urllib.request
ok = lambda m: print("PASS", m)
def post(path, o):
    r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
hub.PY = Path(sys.executable)
r = post("/api/nodes/sources", {"missing": ["CoolSampler", "CoolLoader", "EvilNode", "Nope"]})
assert len(r["repos"]) == 1 and r["repos"][0]["title"] == "Cool Nodes" and r["repos"][0]["nodes"] == ["CoolSampler", "CoolLoader"] and not r["repos"][0]["installed"], r
assert sorted(r["unknown"]) == ["EvilNode", "Nope"]; ok("missing nodes grouped by repository; unknown / non-GitHub sources are not offered")
assert "error" in post("/api/nodes/install", {"repo": "https://evil.example.com/x/y"}) and "error" in post("/api/nodes/install", {"repo": "http://127.0.0.1:19999/gh/user/Other"}); ok("only repositories from the Manager list are installable")
repo = r["repos"][0]["repo"]; assert post("/api/nodes/install", {"repo": repo}) == {"ok": True}
for _ in range(80):
    st = get("/api/nodes/status")[repo]
    if st["state"] != "running": break
    time.sleep(0.25)
assert st["state"] == "done", st
d = hub.COMFY / "custom_nodes" / "CoolNodes"; assert (d / "__init__.py").is_file() and (d / "requirements.txt").is_file() and "다시 시작" in st["msg"]
assert post("/api/nodes/sources", {"missing": ["CoolSampler"]})["repos"][0]["installed"]; ok("install: zip downloaded, extracted into custom_nodes, requirements step ran, status reported")
assert post("/api/nodes/install", {"repo": repo}) == {"ok": True}; time.sleep(0.6); assert get("/api/nodes/status")[repo]["state"] == "error" and "이미" in get("/api/nodes/status")[repo]["msg"]; ok("already installed -> friendly message")
# 다시 시작: 허브가 띄운 프로세스가 없으면 안내
r = post("/api/engine/restart", {}); assert "스튜디오가 켠 게 아니라서" in r.get("error", ""), r; ok("restart refuses politely when ComfyUI was not started by the studio")
class FP:
    args = ["python", "-s", "x/main.py"]; killed = False
    def terminate(s): s.killed = True
    def wait(s, timeout=0): return 0
fp = FP(); hub.procs.append(fp); started = []; hub.start_engines = lambda: started.append(1)
assert post("/api/engine/restart", {}) == {"ok": True} and fp.killed and started and fp not in hub.procs; ok("restart: stops the studio-launched ComfyUI and starts it again")
# 화면용(UI) 형식 워크플로에 없는 노드가 있어도 설치 도우미가 뜰 수 있게 목록을 돌려줘요
ui = {"nodes": [{"id": 1, "type": "CoolSampler", "mode": 0, "inputs": [], "widgets_values": []}, {"id": 2, "type": "DF_Text", "mode": 0, "inputs": [], "widgets_values": []}, {"id": 3, "type": "Note", "mode": 0}], "links": []}
r = post("/api/wf/analyze", {"graph": json.dumps(ui)}); assert "설치되지 않은 노드" in r["error"] and sorted(r["missing"]) == ["CoolSampler", "DF_Text"], r
assert "Manager" not in r["error"]; src = post("/api/nodes/sources", {"missing": r["missing"]}); assert src["repos"] and "DF_Text" in src["unknown"]; ok("UI-format workflow with missing nodes: analyze returns the names so the install helper can look them up")
print("ALL OK")
