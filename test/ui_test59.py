"""3.12.1: 태그 자동완성 — 결과 전부(내리면 더), 스크롤해도 안 닫힘, 개수 표시, 키보드로 내려가기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17974"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
(TMP / "tags").mkdir(exist_ok=True)
rows = [f'hair style {i},0,{100000 - i},"[패션 > 헤어스타일] 머리 모양 {i}. 키워드: <헤어스타일>, 머리 {i}"' for i in range(450)]
(TMP / "tags" / "kr.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1400, "height": 900}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=gen]"); pg.fill("#f-gen textarea[name=prompt]", "머리"); pg.wait_for_selector("#tagbox:not([hidden]) .ti")
    assert "450" in pg.inner_text("#tagbox .thd"), pg.inner_text("#tagbox .thd"); n0 = pg.locator("#tagbox .ti").count(); assert n0 == 100, n0
    # 스크롤바 끌기처럼: 목록 안을 누른 채 스크롤 → 닫히지 않고 더 불러와요
    bb = pg.locator("#tagbox").bounding_box(); pg.mouse.move(bb["x"] + bb["width"] - 4, bb["y"] + 30); pg.mouse.down()
    for _ in range(12): pg.evaluate("document.querySelector('#tagbox').scrollTop+=2000"); pg.wait_for_timeout(150)
    pg.mouse.up(); pg.wait_for_timeout(300)
    assert pg.locator("#tagbox").is_visible() and pg.locator("#tagbox .ti").count() == 450, pg.locator("#tagbox .ti").count()
    pg.mouse.wheel(0, -500); pg.wait_for_timeout(200); assert pg.locator("#tagbox").is_visible()
    ok("all 450 results reachable by scrolling; box stays open while scrolling / grabbing the scrollbar")
    pg.click("#f-gen textarea[name=prompt]"); pg.fill("#f-gen textarea[name=prompt]", "머리 1"); pg.wait_for_selector("#tagbox:not([hidden]) .ti")
    for _ in range(30): pg.keyboard.press("ArrowDown")
    assert pg.evaluate("(()=>{const b=document.querySelector('#tagbox'),o=b.querySelector('.ti.on').getBoundingClientRect(),r=b.getBoundingClientRect();return o.top>=r.top&&o.bottom<=r.bottom})()")
    pg.keyboard.press("Enter"); assert pg.input_value("#f-gen textarea[name=prompt]").startswith("hair style"), pg.input_value("#f-gen textarea[name=prompt]")
    ok("arrow keys walk down the long list (kept in view) and Enter inserts")
    pg.mouse.click(700, 850); pg.wait_for_timeout(300); assert pg.locator("#tagbox").is_hidden()
    assert not errs, errs
print("ALL OK")
