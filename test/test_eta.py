"""4.4.1: 남은 시간 — 작업 전체 진행률로 한 곳에서(eta_update), 지난번 같은 종류 작업의 진행 곡선 기억(eta_learn),
모든 화면이 같은 표시(fmtEta·fmtEl), 그리기 단계 글에 남은 시간을 따로 붙이지 않음."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, urllib.request
os.environ["TEST_HUB_PORT"] = "17980"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))


def run(key, prog, T, learn=False):
    """가짜 작업을 1초씩 흘려 보며 남은 시간 어림 → (진행 15% 뒤 평균 상대 오차, 처음 보인 때, 값들)"""
    J = {"state": "running", "t_start": 1000.0, "_eta_key": key}
    errs, first, seen = [], None, []
    for t in range(1, T + 1):
        p, ph = prog(t); J["progress"], J["phase"] = p, ph
        e = hub.eta_update(J, 1000.0 + t)
        assert J["elapsed"] == t
        seen.append(e)
        if e is not None:
            first = first or t
            if t > T * 0.15:
                errs.append(abs(e - (T - t)) / max(T - t, 30))
    if learn:
        J["state"], J["t_end"] = "done", 1000.0 + T
        hub.eta_learn(J)
    return sum(errs) / max(1, len(errs)), first, seen


hub.ETA_FILE.unlink(missing_ok=True); hub._ETA_H["d"] = None
even = lambda t: (0.0, "load") if t < 30 else (min(0.97, (t - 30) / 270), "gen")
err, first, seen = run("even", even, 300)
assert err < 0.05 and 30 < first <= 45, (err, first)
assert all(seen[i] is None for i in range(29))                                         # 모델 불러오는 동안은 안 보여요
steps = [abs(seen[i + 1] - seen[i]) for i in range(60, 280) if seen[i] is not None and seen[i + 1] is not None]
assert max(steps) <= 3, max(steps)                                                     # 1초에 3초 넘게 튀지 않아요
ok("steady job: ETA within 5%, hidden while loading, counts down smoothly")

four = lambda t: (0.0, "load") if t < 15 else (min(0.99, int((t - 15) / 60) / 4 + ((t - 15) / 60 % 1) * 0.97 / 4), "gen")
err, *_ = run("four", four, 255); assert err < 0.06, err
ok("4 images in a row (progress per image): whole-job ETA within 6%")

def tail(t):                                                                           # 3D: 그리기 뒤 오래 멈춤(굽기·Blender)
    if t < 30: return 0.0, "load"
    if t < 330: return 0.95 * (t - 30) / 300, "gen"
    return 0.95, "gen"
e1, *_ = run("m3d|blender", tail, 450, learn=True)
e2, *_ = run("m3d|blender", lambda t: tail(t / 1.5), 675, learn=True)
e3, *_ = run("m3d|blender", lambda t: tail(t / 0.8), 360)
assert e1 > 0.3 and e2 < 0.2 and e3 < 0.2, (e1, e2, e3)
d = json.loads(hub.ETA_FILE.read_text(encoding="utf-8")); assert len(d["m3d|blender"]) == 2 and len(d["m3d|blender"][0]) == 19
ok(f"slow finishing step: first time {e1:.0%} off, with remembered progress curve {e2:.0%}/{e3:.0%} (bigger/smaller job of the same kind)")

J = {"state": "running", "t_start": 1000.0, "progress": 0.4, "pest": True}
assert hub.eta_update(J, 1100.0) is None and J["elapsed"] == 100
ok("time-guessed progress (no live steps) shows no ETA")

assert hub.eta_key({"kind": "gen", "engine": "flux", "hires": True, "steps": 30, "w": 1024}) == "gen|engine=flux|hires"
assert hub.eta_key({"kind": "m3d", "op": "build", "blender": "", "photo": True}) == "m3d|op=build|photo"
ok("progress-curve key: kind + mode + on/off options (not sizes or steps)")

# 서버: 실행 중인 작업은 1초마다 남은 시간·걸린 시간이 새로 매겨져요. 그리기 글에는 남은 시간을 붙이지 않아요
src = (Path(BASE) / "LocalAI-Studio/hub/server/03_comfy.py").read_text(encoding="utf-8")
assert "남은 시간 약" not in src and "fmt_eta" not in src
STATE["slow_from"] = len(SUBMITTED)
jid = post("/api/job", {"kind": "gen", "prompt": "a cat", "width": 512, "height": 512})["id"]
for _ in range(60):
    j = get("/api/job/" + jid)
    if j["state"] == "running" and j.get("elapsed", 0) >= 2: break
    time.sleep(0.2)
assert j["state"] == "running" and j["elapsed"] >= 2, j
post("/api/job/cancel", {"id": jid}); STATE["slow_from"] = None
for _ in range(50):
    if get("/api/job/" + jid)["state"] != "running": break
    time.sleep(0.2)
assert hub.JOBS[jid].get("eta") is None and "_eta" not in hub.JOBS[jid]
F = {"id": "fake-eta", "kind": "gen", "label": "가짜", "state": "running", "t_add": time.time(), "t_start": time.time(), "progress": 0.0, "phase": "gen", "msg": "", "images": []}
hub.JOBS["fake-eta"] = F                                           # 진행률을 직접 올리는 가짜 실행 작업(1초마다 남은 시간이 매겨져요)
for k in range(14):
    F["progress"] = 0.05 * (k + 1); time.sleep(1)
j = get("/api/job/fake-eta"); assert isinstance(j.get("eta"), int) and 0 < j["eta"] < 120 and j["elapsed"] >= 13, j
q = get("/api/queue"); assert next(r for r in q["items"] if r["id"] == "fake-eta")["eta"] == F["eta"]
F["state"] = "done"; del hub.JOBS["fake-eta"]
ok("running job gets eta/elapsed every second (same value in job status and queue), cleared when it ends")

# 화면: 같은 표시 함수
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B); pg.wait_for_timeout(800)
    got = pg.evaluate("[5,40,74,95,600,3599,3600,5400,7260].map(fmtEta)")
    assert got == ["곧 끝나요", "약 40초", "약 70초", "약 2분", "약 10분", "약 1시간", "약 1시간", "약 1시간 30분", "약 2시간 1분"], got
    assert pg.evaluate("[fmtEl(42),fmtEl(125),fmtEl(3720)]") == ["42초", "2분 5초", "1시간 2분"]
    assert pg.evaluate("etaTxt({state:'running',eta:300})") == " · 남은 시간 약 5분" and pg.evaluate("etaTxt({state:'queued',eta:300})") == "" and pg.evaluate("etaTxt({eta:null})") == ""
    js = "".join(f.read_text(encoding="utf-8") for f in sorted((Path(BASE) / "LocalAI-Studio/hub/web/js").glob("*.js")))
    assert js.count("const fmtEta") + js.count("function fmtEta") == 1 and "초 경과" not in js and "초째" not in js
    assert not errs, errs
    br.close()
ok("one ETA/elapsed format for every screen (image, queue, monitor, chat steps, LoRA, video tools, 3D)")
print("ALL OK")
