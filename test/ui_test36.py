"""얼굴 교체 화면: 동의 칸이 없으면 막고, 확장이 없으면 설치 버튼, 있으면 만들기 가능."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17899"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
STATE["missing"].add("ReActorFaceSwap"); hub.caps(True)
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_timeout(600)
    pg.evaluate("document.querySelector('nav button[data-f=\"faceswap\"]').click()"); pg.wait_for_selector("#feat-form .ninst", timeout=8000)
    assert "ReActor" in pg.inner_text("#feat-form .feat-nodes") and pg.locator("#feat-form .consent").count() == 0; ok("missing extension → install button; no consent box")
    STATE["missing"].discard("ReActorFaceSwap"); hub.caps(True)
    pg.click('nav button[data-v="gen"]'); pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_timeout(500)
    pg.evaluate("document.querySelector('nav button[data-f=\"faceswap\"]').click()"); pg.wait_for_timeout(400)
    assert pg.locator("#feat-form .ninst").count() == 0; ok("extension present → no install box")
    pg.click("#feat-form .go"); assert "이미지" in pg.inner_text("#v-feat .jobbar .st"); ok("no photos → asked to upload")
    import io
    from PIL import Image
    for c, nm in (((200, 60, 60), "a.png"), ((60, 200, 60), "b.png")):
        Image.new("RGB", (64, 64), c).save("/tmp/tt/" + nm)
    ins = pg.locator("#feat-form .mini[data-img] input[type=file]"); ins.nth(0).set_input_files("/tmp/tt/a.png"); ins.nth(1).set_input_files("/tmp/tt/b.png"); pg.wait_for_timeout(500)
    pg.click("#feat-form .go"); pg.wait_for_timeout(300); assert "동의" not in pg.inner_text("#v-feat"); ok("no consent step any more")
    pg.wait_for_selector("#v-feat .res img", timeout=20000); ok("result image appears")
    pg.screenshot(path="/tmp/tt/faceswap.png")
    b.close()
assert not errs, errs
print("ALL OK")
