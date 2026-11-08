"""프로그램 다시 시작 / 위치 옮기기 화면."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, tempfile, time
os.environ["TEST_HUB_PORT"] = "17880"
TD = tempfile.mkdtemp(); os.environ["LOCALAPPDATA"] = TD
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
spawned = []; hub.spawn_helper = lambda mode, dst=None: spawned.append((mode, dst))
def fake_exit():
    hub.BOOT = "newboot"          # 새로 켜진 것처럼 보이게
hub._exit_now = fake_exit
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); msgs = []
    pg.on("dialog", lambda d: (msgs.append(d.message), d.accept()))
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.click("nav button[data-v=conf]"); pg.wait_for_timeout(500); pg.click("#cs-nav button[data-pane=app]")
    assert str(hub.ROOT) in pg.inner_text("#app-root"); ok("shows the current install location")
    pg.fill("#app-dest", str(hub.ROOT / "sub")); pg.click("#app-check"); pg.wait_for_timeout(400); assert "안쪽" in pg.inner_text("#app-plan") and pg.locator("#app-go").is_hidden(); ok("invalid target -> reason, no start button")
    pg.click("#app-up"); pg.wait_for_timeout(500); assert pg.input_value("#app-dest") == str(hub.ROOT.parent); t = pg.inner_text("#app-plan"); assert str(hub.ROOT.parent) in t and "다시 켜져요" in t and pg.locator("#app-go").is_visible(); ok("'바깥 폴더로 올리기' fills the parent and shows the plan")
    tgt = str(Path(os.environ["LOCALAPPDATA"]) / "newhome"); pg.fill("#app-dest", tgt); pg.click("#app-check"); pg.wait_for_timeout(400)
    assert "같은 드라이브" in pg.inner_text("#app-plan") or "다른 드라이브" in pg.inner_text("#app-plan")
    pg.click("#app-go"); pg.wait_for_selector("#restarting:not([hidden])", timeout=5000)
    assert spawned and spawned[-1][1] == str(Path(tgt).resolve()), spawned; pg.wait_for_function("location.href && document.querySelector('#restarting')===null || true", timeout=2000)
    pg.wait_for_timeout(5500); ok("move: confirm dialog -> helper started with the destination -> overlay while restarting")
    # 새로 켜진 뒤 자동 새로고침 + 결과 알림
    (Path(TD) / "LocalAI-Studio").mkdir(exist_ok=True); (Path(TD) / "LocalAI-Studio/last-move.json").write_text(json.dumps({"ok": True, "msg": "바깥 폴더로 올렸어요."}), encoding="utf-8")
    pg.reload(); pg.wait_for_timeout(1200); assert "바깥 폴더로 올렸어요" in pg.inner_text("#toast"); ok("after the new start, the result message is shown once")
    # 재시작 버튼 + 작업 중 경고
    hub.JOBS["zz"] = {"state": "running"}; msgs.clear(); spawned.clear()
    pg.click("#restart-app"); pg.wait_for_timeout(800); assert any("진행 중인 작업이 1개" in m for m in msgs) and spawned and spawned[-1][0] == "restart"; ok("restart button asks twice when a job is running, then starts the helper")
    pg.wait_for_selector("#restarting:not([hidden])")
    hub.BOOT = "boot3"; pg.wait_for_timeout(5000); assert pg.evaluate("document.getElementById('restarting').hidden") is True; ok("overlay disappears (page reloads) once the studio comes back with a new boot id")
    b.close()
assert not errs, errs; print("ALL OK")
