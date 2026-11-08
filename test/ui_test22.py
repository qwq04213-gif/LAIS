"""태그 자동완성: 제안 표시, 키보드 선택, 클릭, 끄기, 비대상 칸 제외."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17897"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 1000}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="gen"]'); ta = pg.locator("#f-gen textarea[name=prompt]"); ta.click()
    ta.type("1girl, blue ha", delay=20); pg.wait_for_selector("#tagbox:not([hidden]) .ti"); n = pg.locator("#tagbox .ti").count()
    assert 1 <= n <= 8 and "blue hair" in pg.inner_text("#tagbox"); ok("typing a segment shows <=8 suggestions with category")
    pg.screenshot(path="/tmp/tt/tag1.png")
    pg.keyboard.press("ArrowDown"); pg.keyboard.press("Enter")
    v = ta.input_value(); assert v.startswith("1girl, blue hair") and v.endswith(", ") and pg.locator("#tagbox").is_hidden(), v; ok("arrow + Enter inserts the tag and a comma, box closes")
    ta.type("long_ha", delay=20); pg.wait_for_selector("#tagbox:not([hidden]) .ti"); pg.keyboard.press("Tab")
    assert "long hair, " in ta.input_value(); ok("Tab accepts the first suggestion")
    ta.type("bro", delay=20); pg.wait_for_selector("#tagbox:not([hidden]) .ti"); pg.keyboard.press("Escape"); assert pg.locator("#tagbox").is_hidden(); ok("Esc closes")
    ta.fill(""); ta.type("blue ha", delay=20); pg.wait_for_selector("#tagbox:not([hidden]) .ti"); pg.locator("#tagbox .ti").first.dispatch_event("mousedown")
    assert ta.input_value().startswith("blue ha") and ta.input_value().endswith(", ") and ta.input_value() != "blue ha"; ok("click inserts")
    ta.fill("a quiet day at the beach. blue ha"); ta.press("End"); ta.type("i", delay=20); pg.wait_for_timeout(500); assert pg.locator("#tagbox").is_hidden(); ok("long sentence text does not trigger suggestions")
    ta.fill(""); ta.type("mid", delay=20); pg.wait_for_selector("#tagbox:not([hidden])"); ta.press("Home"); ta.press("Shift+End")
    pg.click('nav button[data-v="vid"]'); vt = pg.locator("#f-vid textarea[name=prompt]"); vt.click(); vt.type("blue ha", delay=20); pg.wait_for_timeout(500); assert pg.locator("#tagbox").is_hidden(); ok("video scene box is excluded")
    pg.click('nav button[data-v="conf"]'); pg.click("#cs-nav button[data-pane=input]"); pg.uncheck("#tag-on")
    pg.click('nav button[data-v="gen"]'); ta.fill(""); ta.type("blue ha", delay=20); pg.wait_for_timeout(500); assert pg.locator("#tagbox").is_hidden(); ok("can be switched off")
    pg.reload(); pg.wait_for_timeout(500); pg.click('nav button[data-v="conf"]'); pg.click("#cs-nav button[data-pane=input]"); assert not pg.is_checked("#tag-on"); ok("off state is remembered")
    pg.click('nav button[data-v="conf"]'); pg.click("#cs-nav button[data-pane=input]"); pg.locator("#fold-input").screenshot(path="/tmp/tt/tag2.png")
    b.close()
assert not errs, errs
print("ALL OK")
