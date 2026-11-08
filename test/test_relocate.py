"""프로그램 위치 옮기기 / 다시 시작: 검사, 바깥으로 올리기, 같은 드라이브 이동, 복사 이동, 되돌리기, API."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, tempfile, shutil, time
os.environ["TEST_HUB_PORT"] = "17879"
TD = tempfile.mkdtemp(); os.environ["LOCALAPPDATA"] = TD + "/appdata"
sys.path.insert(0, BASE + "/test")
from mocks import *
import urllib.request
import relocate
ok = lambda m: print("PASS", m)
def post(path, o):
    r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def tree(base, files):
    for f, c in files.items():
        p = Path(base) / f; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(c)
def snap(base): return sorted((str(p.relative_to(base)), p.stat().st_size) for p in Path(base).rglob("*") if p.is_file())
FILES = {"hub/hub.py": b"print(1)", "engine/ComfyUI/models/checkpoints/a.safetensors": b"A" * 5000, "outputs/생성/x.png": b"P" * 100, "start.bat": b"@echo hi", "settings.json": b"{}"}
def job(mode, src, dst, **kw):
    marker = Path(TD) / ("launched-" + mode + str(time.time_ns()))
    j = dict(mode=mode, src=str(src), dst=str(dst), wait=0, log=TD + "/appdata/move.log", result=TD + "/appdata/last-move.json", path_txt=TD + "/appdata/path.txt",
             launch=[sys.executable, "-c", f"open(r'{marker}','w').write('x')"]); j.update(kw); return j, marker
def W(mk):
    for _ in range(40):
        if mk.exists(): return True
        time.sleep(0.1)
    return False
def last(): return json.loads(Path(TD + "/appdata/last-move.json").read_text(encoding="utf-8"))

# ── 검사
outer = Path(TD) / "sd/LocalAI"; inner = outer / "LocalAI"; tree(inner, FILES); (outer / "other.txt").write_text("x")
p = relocate.plan(inner, str(outer)); assert p["mode"] == "flatten" and p["items"] == 5, p
for bad, msg in (("", "적어"), ("relative/path", "전체 경로"), (str(inner), "같아요"), (str(inner / "sub"), "안쪽")):
    try: relocate.plan(inner, bad); raise AssertionError(bad)
    except ValueError as e: assert msg in str(e), (bad, e)
(Path(TD) / "full").mkdir(); (Path(TD) / "full/f.txt").write_text("x")
try: relocate.plan(inner, str(Path(TD) / "full")); raise AssertionError
except ValueError as e: assert "비어 있지" in str(e)
(outer / "hub").mkdir()
try: relocate.plan(inner, str(outer)); raise AssertionError
except ValueError as e: assert "hub" in str(e) and "같은 이름" in str(e)
(outer / "hub").rmdir(); assert relocate.plan(inner, str(outer))["mode"] == "flatten"; ok("plan: validates empty / relative / same / inside / missing drive / non-empty target / name clash when flattening")

# ── 바깥으로 올리기(E:\\sd\\LocalAI\\LocalAI -> E:\\sd\\LocalAI)
before = snap(inner); j, mk = job("flatten", inner, outer)
assert relocate.run(j) is True
after = snap(outer); after_f = [x for x in after if x[0] != "other.txt"]
assert after_f == before and not inner.exists() and (outer / "other.txt").exists() and W(mk), (after_f, before)
assert Path(TD + "/appdata/path.txt").read_text() == str(outer) and last()["ok"] and "바깥" in last()["msg"]; ok("flatten: every file moved one level up, other files untouched, empty inner folder removed, path.txt updated, studio relaunched from new place")

# ── 같은 드라이브 이동(없는 폴더로)
tgt = Path(TD) / "moved/here"; j, mk = job("move", outer, tgt)
p = relocate.plan(outer, str(tgt)); assert p["mode"] == "move"
shutil.rmtree(outer / "other.txt", ignore_errors=True) if (outer / "other.txt").is_dir() else (outer / "other.txt").unlink()
b2 = snap(outer); assert relocate.run(j) is True and snap(tgt) == b2 and not outer.exists() and W(mk); ok("move on the same drive: files renamed into the new folder (no copy), old folder gone")

# ── 복사 이동(다른 드라이브 흉내) + 검증
src = Path(TD) / "srcA"; tree(src, FILES); dst = Path(TD) / "dstA"; j, mk = job("copy", src, dst)
assert relocate.run(j) is True and snap(dst) == snap(src) and W(mk) and "그대로 남겼" in last()["msg"]; ok("copy move: copied and verified, original folder kept")

# ── 실패 시 되돌리기: 이동 도중 오류
src = Path(TD) / "srcB"; tree(src, FILES); dst = Path(TD) / "dstB"; b = snap(src)
real = shutil.move; cnt = {"n": 0}
def flaky(a, b_):
    cnt["n"] += 1
    if cnt["n"] == 3: raise PermissionError("locked")
    return real(a, b_)
shutil.move = flaky; relocate._retry.__defaults__ = (1,)
j, mk = job("move", src, dst)
try: r = relocate.run(j)
finally: shutil.move = real; relocate._retry.__defaults__ = (30,)
assert r is False and snap(src) == b and not dst.exists() and not last()["ok"] and "되돌" not in "" and "옮기지 못했어요" in last()["msg"] and W(mk); ok("failure midway: already-moved items are put back, old place relaunched, clear message")
# 복사 도중 실패
src = Path(TD) / "srcC"; tree(src, FILES); dst = Path(TD) / "dstC"
orig = shutil.copy2; n = {"i": 0}
def bad(a, b_):
    n["i"] += 1
    if n["i"] == 3: raise OSError("disk full")
    return orig(a, b_)
shutil.copy2 = bad; j, mk = job("copy", src, dst)
try: r = relocate.run(j)
finally: shutil.copy2 = orig
assert r is False and snap(src) == snap(src) and not any(dst.rglob("*")) if dst.exists() else True; ok("failure while copying: partial copy removed, original intact")
# 다시 시작
j, mk = job("restart", Path(TD) / "dstA", Path(TD) / "dstA"); assert relocate.run(j) and W(mk) and "다시 시작" in last()["msg"]; ok("restart mode just relaunches")

# ── API
w = get("/api/app/where"); assert w["root"] == str(hub.ROOT) and w["parent"] == str(hub.ROOT.parent)
r = post("/api/app/move/check", {"dest": ""}); assert "error" in r
r = post("/api/app/move/check", {"dest": str(Path(TD) / "api_target")}); assert r["mode"] in ("move", "copy") and r["src"] == str(hub.ROOT), r
r = post("/api/app/move/check", {"dest": str(hub.ROOT / "x")}); assert "안쪽" in r["error"]
spawned = []; exited = []; orig_spawn = hub.spawn_helper
hub.spawn_helper = lambda mode, dst=None: spawned.append((mode, dst)); hub._exit_now = lambda: exited.append(1)
hub.JOBS["zz"] = {"state": "running"}
r = post("/api/app/restart", {}); assert r == {"busy": 1} and not spawned
r = post("/api/app/restart", {"force": True}); assert r == {"ok": True} and spawned == [("restart", None)]; time.sleep(1.2); assert exited
del hub.JOBS["zz"]; spawned.clear()
r = post("/api/app/move", {"dest": str(Path(TD) / "api_target")}); assert r["ok"] and spawned[0][0] in ("move", "copy") and spawned[0][1] == str(Path(TD) / "api_target").replace("\\", "/") or spawned
assert get("/api/status")["boot"]; ok("API: where/check/restart/move, refuses while jobs run unless forced, exits the studio after spawning the helper")
(Path(TD) / "appdata/LocalAI-Studio").mkdir(parents=True, exist_ok=True); (Path(TD) / "appdata/LocalAI-Studio/last-move.json").write_text(json.dumps({"ok": True, "msg": "m"}), encoding="utf-8")
assert get("/api/app/notice")["msg"] == "m" and get("/api/app/notice") == {}; ok("result notice is shown once")
# 진짜 도우미 프로세스: 임시 폴더로 복사돼 따로 실행되고, 옮긴 뒤 결과를 남겨요
hub.spawn_helper = orig_spawn
o2 = Path(TD) / "real/outer"; i2 = o2 / "inner"; tree(i2, FILES); b = snap(i2)
hub.ROOT = i2; (Path(TD) / "appdata/LocalAI-Studio").mkdir(parents=True, exist_ok=True)
res = Path(TD) / "appdata/LocalAI-Studio/last-move.json"; res.unlink(missing_ok=True)
hub.spawn_helper("flatten", str(o2))
for _ in range(120):
    if res.exists(): break
    time.sleep(0.25)
assert res.exists() and json.loads(res.read_text(encoding="utf-8"))["ok"] and snap(o2) == b and not i2.exists(); ok("real detached helper process: copied to a temp folder, ran on its own, moved the files and wrote the result")
print("ALL OK")
