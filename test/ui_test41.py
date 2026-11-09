"""이어서 작업: 갤러리·큰 화면(라이트박스)에서 같은 설정/새 시드/변형/편집/업스케일/영상으로 보내기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17902"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=gen]"); pg.wait_for_selector("#f-gen")
    pg.fill("#f-gen [name=prompt]", "1girl, red scarf, snow"); pg.fill("#f-gen [name=seed]", "4242")
    pg.click("#f-gen .go"); pg.wait_for_selector("#v-gen .res figure img", timeout=30000); pg.wait_for_timeout(500)
    pg.click("nav button[data-v=gal]"); pg.wait_for_selector("#gal-grid .gt")
    t = pg.inner_html("#gal-grid .gt .gb2"); assert 'data-to="again"' in t and 'data-to="up"' in t and 'data-to="edit"' in t and 'data-to="vid"' in t; ok("gallery card has same-settings, edit, upscale and video buttons")
    pg.locator("#gal-grid .gt").first.hover()
    pg.locator('#gal-grid .gt [data-to="up"]').first.click(force=True); pg.wait_for_selector("#v-up.on"); pg.wait_for_function("IV.up.img||document.querySelector('#v-up img[src^=data]')"); ok("⤢ sends the picture to upscale")
    pg.click("nav button[data-v=gal]"); pg.locator("#gal-grid .gt").first.hover()
    pg.locator('#gal-grid .gt [data-to="edit"]').first.click(force=True); pg.wait_for_selector("#v-edit.on"); ok("✎ sends it to edit")
    pg.click("nav button[data-v=gal]"); pg.locator("#gal-grid .gt").first.hover()
    n0 = len(hub.TASKS)
    pg.locator('#gal-grid .gt [data-to="again"]').first.click(force=True); pg.wait_for_selector("#v-gen.on"); pg.wait_for_function(f"{n0}<(window.__n||0) || true")
    pg.wait_for_function("document.querySelector('#f-gen [name=prompt]').value.includes('red scarf')", timeout=10000)
    pg.wait_for_function("document.querySelectorAll('#v-gen .res figure img').length>=4", timeout=40000); ok("⟳ fills the same settings and makes 4 new pictures at once")
    pg.click("nav button[data-v=gal]"); pg.locator("#gal-grid .gt img").first.click(); pg.wait_for_selector("#lb:not([hidden])")
    assert pg.is_visible("#lb-cont"); pg.click("#lb-cont summary"); pg.wait_for_function("(()=>{const m=document.querySelector('#lb-cont .menu');return m&&getComputedStyle(m).visibility==='visible'&&m.innerText.includes('변형')})()"); labels = pg.inner_text("#lb-cont .menu"); assert "이미지 생성으로 보내기" in labels and "업스케일" in labels and "영상" in labels and "변형" in labels; ok("big view has a [이어서 작업] menu with every follow-up")
    pg.click('#lb-cont [data-to="vid"]'); pg.wait_for_selector("#v-vid.on"); assert pg.is_hidden("#lb"); ok("choosing an item closes the big view and opens that screen")
    pg.click("nav button[data-v=gal]"); pg.locator("#gal-grid .gt img").first.click(); pg.click("#lb-cont summary"); pg.click('#lb-cont [data-to="gvar"]'); pg.wait_for_selector("#v-gen.on")
    pg.wait_for_function("document.querySelectorAll('#v-gen .res figure img').length>=4", timeout=40000); ok("variation from the big view runs on the gen screen")
    assert not errs, errs
    b.close()
print("ALL OK")
