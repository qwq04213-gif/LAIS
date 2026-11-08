"""앱 안에서 update.bat 적용: 실제 build_update.py 로 만든 파일을 올려 미리보기 → 적용 → 백업/로그/버전 확인, 잘못된 파일 거절, 옛 버전 거절, 날짜식<번호식 정렬."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, shutil, subprocess, base64
from pathlib import Path
os.environ["TEST_HUB_PORT"] = "17903"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
TOOLS = Path(BASE + "/release-tools"); W = TMP / "upd"; shutil.rmtree(W, ignore_errors=True); W.mkdir()
def mk(tree, ver, hubsrc, extra=None):
    (tree / "hub" / "web").mkdir(parents=True, exist_ok=True)
    (tree / "hub" / "hub.py").write_text(hubsrc, encoding="utf-8"); (tree / "VERSION.txt").write_text(ver, encoding="utf-8"); (tree / "hub" / "web" / "app.js").write_text("// " + ver, encoding="utf-8")
    for k, v in (extra or {}).items(): (tree / k).write_text(v, encoding="utf-8")
def build(tree, name):
    n = W / (name + ".txt"); n.write_text("새 기능 하나\n두 번째 기능\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(TOOLS / "build_update.py"), "--tree", str(tree), "--out", str(W / ("o" + name)), "--notes", str(n), "--history", str(W / "h.json")], capture_output=True, text=True); assert r.returncode == 0, r.stderr
    return next((W / ("o" + name)).glob("*.bat")).read_bytes().decode("ascii")
old = Path(hub.ROOT); (old / "hub").mkdir(exist_ok=True)
saved = {f: (old / f).read_bytes() if (old / f).exists() else None for f in ("hub/hub.py", "VERSION.txt")}
(old / "hub" / "hub.py").write_text("x = 1\n", encoding="utf-8"); (old / "VERSION.txt").write_text("2026.10.18.24", encoding="utf-8")
(old / "hub" / "web").mkdir(exist_ok=True); (old / "hub" / "web" / "app.js").write_text("// old", encoding="utf-8")
hub.VERSION = "2026.10.18.24"
new = W / "new"; mk(new, "2.0", "x = 2\n"); bat = build(new, "a")
r = hub.update_inspect({"text": bat}); assert r.get("ok") and r["from"] == "2026.10.18.24" and r["to"] == "2.0" and r["changes"] >= 2 and "새 기능 하나" in r["notes"] and not r["older"] and not r["same"], r
assert (old / "hub" / "hub.py").read_text() == "x = 1\n" and not (old / "backup").exists(); ok("preview lists the changes and touches nothing")
assert "2.0" in r["log"] and "교체" in r["log"]; ok("preview log shows what would be replaced")
bad = hub.update_inspect({"text": "echo hi\r\n"}); assert "업데이트 파일이 아니에요" in bad["error"]; ok("a random .bat is refused")
trunc = hub.update_inspect({"text": bat[:len(bat) // 2]}); assert trunc.get("error"); ok("a cut-off file is refused")
assert hub.update_apply({"token": "nope"}).get("error"); ok("apply needs the token from a preview")
a = hub.update_apply({"token": r["token"]}); assert a["ok"] and a["code"] == 0, a
assert (old / "hub" / "hub.py").read_text() == "x = 2\n" and (old / "VERSION.txt").read_text().strip() == "2.0" and (old / "hub" / "web" / "app.js").read_text() == "// 2.0"; ok("files replaced and VERSION updated")
bk = list((old / "backup").iterdir()); assert bk and (bk[0] / "_restore.json").is_file() and (bk[0] / "hub" / "hub.py").read_text() == "x = 1\n"; ok("previous files backed up first (rollback.bat can use it)")
assert "업데이트가 끝났어요" in (old / "logs" / "update.log").read_text(encoding="utf-8"); ok("update.log written")
assert hub.update_apply({"token": r["token"]}).get("error"); ok("a token works only once")
hub.VERSION = "2.0"
r2 = hub.update_inspect({"text": bat}); assert r2["same"], r2; ok("same file again says it is already up to date")
older = W / "older"; mk(older, "2026.10.18.25", "x = 0\n"); b_old = build(older, "b")
r3 = hub.update_inspect({"text": b_old}); assert r3["older"] and r3["code"] == 3, r3; ok("an older (date-style) update is refused, because 2.0 counts as newer")
assert (old / "hub" / "hub.py").read_text() == "x = 2\n"
a3 = hub.update_apply({"token": hub.update_inspect({"text": b_old, "force": True})["token"], "force": True}); assert a3["ok"] and (old / "VERSION.txt").read_text().strip() == "2026.10.18.25"; ok("forced rollback-style apply works only when asked")
assert hub.vkey("2.0") > hub.vkey("2026.10.18.24") and hub.vkey("2.0.1") > hub.vkey("2.0") and hub.vkey("2.10") > hub.vkey("2.9") and hub.vkey("2026.10.18.24") > hub.vkey("2026.10.18.9"); ok("version ordering: 2.0.1 > 2.0 > date-style")
rx = hub.VER_RX; assert rx.match("[2.0] 큰 업데이트") and rx.match("[2.0.1] 고침") and rx.match("[2026.10.18.24] x") and not rx.match("[설치 방법]"); ok("README sections accept new version numbers")
for f, d in saved.items():
    if d is not None: (old / f).write_bytes(d)
print("ALL OK")
