"""시작하기 탭 + 화면별 사용법 안내."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17881"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}); _c = pg; pg = _c.new_page(); pg.add_init_script("localStorage.setItem('ui:scale','1')")
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.click("nav button[data-v=start]"); pg.wait_for_selector("#st-goals .goal"); pg.wait_for_timeout(300)
    assert pg.locator("#st-goals .goal").count() == 13 and pg.locator("#st-fix .fixd").count() == 8
    t = pg.inner_text("#st-ready"); assert "✓" in t and "영상 모델" in t and "✗" in t; ok("start tab: readiness checklist (✓/✗), 8 goals, 8 fix tips")
    g = pg.locator("#st-goals .goal").nth(3); assert "영상 모델" in g.inner_text() and "먼저 준비하러 가기" in g.inner_text(); ok("goal without its models shows what is missing")
    pg.locator("#st-goals .goal").nth(0).locator("summary").click(); assert pg.locator("#st-goals .goal").nth(0).locator("li").count() == 3
    pg.locator("#st-goals .goal", has_text="기록 갤러리").first.locator("button").last.click(); pg.wait_for_timeout(300); assert pg.locator("#v-gal.on").count() == 1; ok("goal button jumps to the right tab")
    # 안내 상자
    pg.click("nav button[data-v=gen]"); assert pg.locator("#v-gen .coach").is_visible() and pg.locator("#v-gen .coach li").count() == 3
    yg = pg.locator("#f-gen button.go").bounding_box()["y"]; assert yg < 120; ok("each tab has a 💡 how-to box in the right column; the form itself is untouched")
    pg.click("#v-gen .coach .cx"); assert pg.locator("#v-gen .coach").is_hidden(); pg.reload(); pg.wait_for_timeout(500); pg.click("nav button[data-v=gen]"); assert pg.locator("#v-gen .coach").is_hidden(); ok("closing a box is remembered")
    pg.click("nav button[data-v=edit]"); assert pg.locator("#v-edit .coach").is_visible()
    pg.click("nav button[data-v=start]"); pg.click("#coach-on"); pg.click("nav button[data-v=edit]"); assert pg.locator("#v-edit .coach").is_hidden(); ok("master switch hides all boxes")
    pg.click("nav button[data-v=start]"); pg.click("#coach-reset"); pg.click("nav button[data-v=gen]"); assert pg.locator("#v-gen .coach").is_visible(); ok("reset shows the closed boxes again")
    pg.click("nav button[data-v=gal]"); assert pg.locator("#v-gal .coach").is_visible() and pg.evaluate("document.querySelector('#v-gal .coach').previousElementSibling.tagName") == "H2"; ok("non-split tabs get the box right under the title")
    pg.screenshot(path=os.environ["TMPDIR"] + "/start.png")
    b.close()
assert not errs, errs; print("ALL OK")
