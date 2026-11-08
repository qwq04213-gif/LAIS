"""설정 > 프로그램 관리: 업데이트 파일 올리기 → 미리보기 → 적용 → 다시 시작 버튼."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, shutil, subprocess
from pathlib import Path
os.environ["TEST_HUB_PORT"] = "17904"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
W = TMP / "upd2"; shutil.rmtree(W, ignore_errors=True); (W / "t/hub/web").mkdir(parents=True)
(W / "t/hub/hub.py").write_text("x=2\n"); (W / "t/VERSION.txt").write_text("2.0"); (W / "t/hub/web/app.js").write_text("//2")
(W / "n.txt").write_text("화면에서 적용\n", encoding="utf-8")
subprocess.run([sys.executable, BASE + "/release-tools/build_update.py", "--tree", str(W / "t"), "--out", str(W / "o"), "--notes", str(W / "n.txt"), "--history", str(W / "h.json")], check=True, capture_output=True)
bat = next((W / "o").glob("*.bat"))
(hub.ROOT / "hub").mkdir(exist_ok=True); (hub.ROOT / "hub" / "hub.py").write_text("x=1\n"); (hub.ROOT / "VERSION.txt").write_text("2026.10.18.24"); hub.VERSION = "2026.10.18.24"
errs = []; restarted = []
hub.app_restart = lambda p: (restarted.append(1), {"ok": True})[1]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1100}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="conf"]'); pg.wait_for_timeout(300)
    pg.click("#cs-nav button[data-pane=app]")
    pg.set_input_files("#upd-file", str(W / "n.txt")); pg.wait_for_selector("#upd-out .warn"); assert ".bat" in pg.inner_text("#upd-out"); ok("a non-.bat file is turned away politely")
    pg.set_input_files("#upd-file", str(bat)); pg.wait_for_selector("#upd-go")
    t = pg.inner_text("#upd-out"); assert "2.0" in t and "2026.10.18.24" in t and "화면에서 적용" in t and "바뀔 파일" in t; ok("preview shows versions, notes and the file count")
    pg.screenshot(path="/tmp/tt/upd.png")
    assert (hub.ROOT / "hub" / "hub.py").read_text() == "x=1\n"; pg.click("#upd-go"); pg.wait_for_selector("#upd-rs", timeout=15000)
    assert (hub.ROOT / "hub" / "hub.py").read_text() == "x=2\n" and "적용했어요" in pg.inner_text("#upd-out"); ok("[적용하기] replaces the files and offers a restart")
    pg.click("#upd-rs"); pg.wait_for_timeout(500); ok("restart button is wired to the app restart")
    assert not errs, errs
    b.close()
print("ALL OK")
