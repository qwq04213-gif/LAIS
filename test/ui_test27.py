"""갤러리 두 장 비교: 정확히 2장 선택 시에만 버튼, 슬라이더 비교로 열림."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, time
os.environ["TEST_HUB_PORT"] = "17891"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
G = hub.OUT / "생성"; G.mkdir(parents=True, exist_ok=True)
for i, n in enumerate(("a.png", "b.png", "c.png")): Image.new("RGB", (60, 40), (i * 80, 20, 20)).save(G / n)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1300, "height": 900}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=gal]"); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length==3")
    assert pg.locator("#gal-cmp").is_hidden()
    ts = pg.locator("#gal-grid .gt"); ts.nth(0).hover(); ts.nth(0).locator("[data-pick]").check(); assert pg.locator("#gal-cmp").is_hidden()
    ts.nth(1).click(); assert pg.locator("#gal-cmp").is_visible(); ok("button appears only with exactly two picked")
    ts.nth(2).click(); assert pg.locator("#gal-cmp").is_hidden(); ts.nth(2).click(); ok("hidden again with three")
    pg.click("#gal-cmp"); pg.wait_for_selector("#lb:not([hidden])"); pg.wait_for_function("document.querySelector('#lb-split') && !document.querySelector('#lb-before').hidden", timeout=5000)
    assert pg.evaluate("document.querySelector('#lb-img').src!=document.querySelector('#lb-before').src"); ok("opens lightbox in overlay-slider compare with two different images")
    print("page errors:", errs); assert not errs
print("ALL OK")
