"""버전별 변경 사항, 갤러리 날짜 필터/목록, 빠진 파이썬 부품 설치 도우미."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, types, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17892"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
# ── 변경 사항
(hub.ROOT / "README.txt").write_text("﻿제목\r\n=====\r\n\r\n[설치 방법]\r\n  1. 설치\r\n\r\n[2026.10.18.2 새 기능]\r\n  - 첫 항목입니다\r\n    이어지는 줄\r\n  - 둘째\r\n\r\n[2026.10.18.10]\r\n  - 열 번째\r\n\r\n[2026.10.18.9]\r\n  - 아홉 번째\r\n\r\n[문제 해결]\r\n  - 이건 변경 사항이 아니에요\r\n", encoding="utf-8")
c = get("/api/changelog"); vs = [v["version"] for v in c["versions"]]
assert vs == ["2026.10.18.10", "2026.10.18.9", "2026.10.18.2"], vs   # 숫자 순(10 이 9 보다 최신)
v2 = c["versions"][-1]; assert v2["title"] == "새 기능" and v2["items"] == ["첫 항목입니다 이어지는 줄", "둘째"], v2
assert all("변경 사항이 아니에요" not in t for v in c["versions"] for t in v["items"]) and c["current"] == hub.VERSION
ok("changelog: README [버전] sections parsed newest-first (numeric order), wrapped lines joined, other sections ignored")
real = open(BASE + "/LocalAI-Studio/README.txt", encoding="utf-8-sig").read(); (hub.ROOT / "README.txt").write_text(real, encoding="utf-8")
c = get("/api/changelog"); assert c["versions"][0]["version"] == (Path(BASE) / "LocalAI-Studio/VERSION.txt").read_text(encoding="utf-8").strip() and len(c["versions"]) >= 13 and all(v["items"] for v in c["versions"]), [(v["version"], len(v["items"])) for v in c["versions"]]
ok("changelog: the real README yields every released version with items")
# ── 갤러리 날짜
G = hub.OUT / "생성"; G.mkdir(parents=True, exist_ok=True)
def mk(n, d):
    p = G / n; Image.new("RGB", (30, 30), (5, 5, 5)).save(p); t = time.time() - d * 86400; os.utime(p, (t, t))
for n, d in (("a.png", 0), ("b.png", 0), ("c.png", 2), ("d.png", 5)): mk(n, d)
day = lambda d: time.strftime("%Y-%m-%d", time.localtime(time.time() - d * 86400))
r = get("/api/gallery"); assert r["total"] == 4 and r["days"] == [[day(0), 2], [day(2), 1], [day(5), 1]] and all(x["day"] for x in r["items"]), r["days"]
r = get("/api/gallery?date=" + day(2)); assert r["total"] == 1 and r["items"][0]["name"] == "c.png" and r["days"] == [[day(0), 2], [day(2), 1], [day(5), 1]]
assert get("/api/gallery?date=garbage")["total"] == 4 and get("/api/gallery?date=1999-01-01")["total"] == 0
r = get("/api/gallery?q=a.png"); assert r["days"] == [[day(0), 1]]
ok("gallery: day list with counts, date filter, junk date ignored, day list follows the other filters")
# ── 빠진 파이썬 부품
assert hub.pymod_missing("ComfyUI: No module named 'matplotlib'") == {"module": "matplotlib", "pip": "matplotlib"} and hub.pymod_missing("No module named 'cv2'")["pip"] == "opencv-python-headless"
assert hub.pymod_missing("No module named 'evil_pkg'") is None and hub.pymod_missing("전혀 다른 오류") is None; ok("only well-known modules are offered; others are not")
orig = hub.run_wf
def boom(*a, **k): raise RuntimeError("DWPreprocessor: No module named 'matplotlib'")
hub.run_wf = boom
buf = io.BytesIO(); Image.new("RGB", (200, 200), (9, 9, 9)).save(buf, "PNG")
r = post("/api/control/prep", {"image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), "type": "pose"})
assert r["pymod"] == {"module": "matplotlib", "pip": "matplotlib"} and "버튼" in r["error"], r; ok("ControlNet easy mode: a missing module comes back with an install hint")
hub.run_wf = orig
orig_fn = hub.do_feat
def bad(p, J): raise RuntimeError("No module named 'ultralytics'")
hub.do_feat = bad
j = post("/api/job", {"kind": "feat", "feature": "resize", "image": "x"}); 
for _ in range(40):
    jj = get("/api/job/" + j["id"])
    if jj["state"] == "error": break
    time.sleep(0.25)
assert jj["pymod"]["module"] == "ultralytics"; hub.do_feat = orig_fn; ok("a job that fails on a missing module reports it (so the screen can offer the button)")
calls = []
def fake_run(cmd, **kw): calls.append(cmd); return types.SimpleNamespace(returncode=0, stdout="", stderr="")
hub.subprocess.run = fake_run; hub.PY = Path(sys.executable)
assert "error" in post("/api/pymod/install", {"module": "not_allowed; rm -rf"}); assert post("/api/pymod/install", {"module": "matplotlib"}) == {"ok": True}
for _ in range(40):
    s = get("/api/pymod/status")["matplotlib"]
    if s["state"] != "running": break
    time.sleep(0.1)
assert s["state"] == "done" and calls and calls[0][-4:-1] == ["-m", "pip", "install"] or calls[0][3:6] == ["pip", "install", "matplotlib"], (s, calls)
assert "matplotlib" in calls[0] and "-r" not in calls[0]; ok("install runs pip for exactly the allow-listed package in ComfyUI's python; arbitrary names refused")
print("ALL OK")
