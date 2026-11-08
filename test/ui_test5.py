"""3차 UI: 마법봉·배경·반전·얼굴 자동 선택, 표정 칩, 편집 ControlNet 칸."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17864"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image, ImageDraw
import skimage.data as skd
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
SP = Path(os.environ["TMPDIR"]) / "shots5"; SP.mkdir(exist_ok=True)
sq = Image.new("RGB", (600, 400), (30, 60, 200)); ImageDraw.Draw(sq).rectangle((200, 100, 400, 300), fill=(220, 40, 40)); sq.save(SP / "sq.png")
Image.fromarray(skd.astronaut()).save(SP / "astro.png")
import fake_sam
errs = []
JS = """(()=>{const cv=document.querySelector('#v-edit canvas'),d=cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;
 const at=(x,y)=>d[((y*cv.width+x)|0)*4+3]>40;const sx=cv.width/%d,sy=cv.height/%d;return {inSq:at(300*sx,200*sy),out:at(50*sx,50*sy),corner:at(5,5)}})()"""
import time
calls = lambda: len(fake_sam.FakeDec.calls)
def wait_call(n0):
    for _ in range(200):
        if calls() > n0: break
        time.sleep(0.1)
    pg_.wait_for_timeout(400)
with sync_playwright() as p:
    b = p.chromium.launch(); pg = pg_ = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.click("nav button[data-v=edit]"); pg.set_input_files("#v-edit .drop input[type=file]", str(SP / "sq.png")); pg.wait_for_selector("#v-edit .work:not([hidden])"); pg.wait_for_timeout(300)
    # 설치 전: 선택 도구 대신 설치 버튼, 배경은 색 기반 대체 동작
    assert pg.locator("#v-edit .sam-install").is_visible() and not pg.locator("#v-edit .wand").is_visible(); ok("before install: install button shown, selection tool hidden")
    box = pg.locator("#v-edit canvas").first.bounding_box()
    pg.click("#v-edit .am-bg"); pg.wait_for_timeout(300); r = pg.evaluate(JS % (600, 400)); assert r["out"] and not r["inSq"], r
    pg.click("#v-edit .am-inv"); pg.wait_for_timeout(200); r = pg.evaluate(JS % (600, 400)); assert r["inSq"] and not r["out"], r; ok("background + invert work even before install (colour fallback)")
    pg.click("#v-edit .clr")
    # 설치
    def fake_install(t):
        for n in (hub.sam.ENCODER, hub.sam.DECODER): (hub.MODELS / "sam" / n).write_bytes(b"0" * 2_000_000)
        t["msg"] = "완료"
    hub.sam_run_install = fake_install; hub.SAM["factory"] = fake_sam.factory; hub.SAM["engine"] = None; hub.sam.have_ort = lambda: True
    (hub.MODELS / "sam").mkdir(exist_ok=True)
    pg.click("#v-edit .sam-install"); pg.wait_for_selector("#v-edit .wand", state="visible", timeout=20000); assert not pg.locator("#v-edit .sam-install").is_visible(); ok("install button -> tool appears when the task finishes")
    # 선택 도구
    box = pg.locator("#v-edit canvas").first.bounding_box()
    pg.check("#v-edit .wand"); assert "sel" in pg.get_attribute("#v-edit .stage", "class")
    pg.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5); pg.wait_for_function("document.querySelector('#v-edit .jobbar .st').textContent.includes('선택했어요')", timeout=20000)
    r = pg.evaluate(JS % (600, 400)); assert r["inSq"] and not r["out"], r; ok("selection tool: one click selects the whole clicked object")
    N0 = calls(); pg.mouse.click(box["x"] + box["width"] * 0.1, box["y"] + box["height"] * 0.1); wait_call(N0); pg.wait_for_timeout(200)
    r = pg.evaluate(JS % (600, 400)); assert r["inSq"] and r["out"], r; ok("a second click adds to the selection")
    pg.click("#v-edit .am-undo"); pg.wait_for_timeout(200); r = pg.evaluate(JS % (600, 400)); assert r["inSq"] and not r["out"], r; ok("undo removes the last click's selection")
    pg.check("#v-edit .erase"); N0 = calls(); pg.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5); wait_call(N0); pg.wait_for_timeout(200)
    assert not pg.evaluate(JS % (600, 400))["inSq"]; pg.uncheck("#v-edit .erase"); ok("eraser + tool deselects the clicked object")
    pg.click("#v-edit .clr"); pg.uncheck("#v-edit .wand")
    pg.click("#v-edit .am-bg"); pg.wait_for_function("document.querySelector('#v-edit .jobbar .st').textContent.includes('배경을 선택했어요')", timeout=20000); r = pg.evaluate(JS % (600, 400)); assert r["out"] and not r["inSq"], r
    pg.click("#v-edit .am-inv"); pg.wait_for_timeout(200); r = pg.evaluate(JS % (600, 400)); assert r["inSq"] and not r["out"], r; ok("background via SAM corner clicks, then invert gives the subject")
    pg.click("#v-edit .clr")
    assert pg.locator("#v-edit .am-face").count() == 0 and pg.locator("#v-edit .tol").count() == 0; ok("face button and old colour sliders are gone")
    pg.click("#v-edit .swap"); pg.set_input_files("#v-edit .drop input[type=file]", str(SP / "astro.png")); pg.wait_for_selector("#v-edit .work:not([hidden])"); pg.wait_for_timeout(300)
    # 표정 칩
    pg.select_option("#f-edit select[name=engine]", "sdxl"); pg.fill("#f-edit textarea[name=prompt]", "1girl, red hair")
    pg.click(".exprs .chip:has-text('웃음')"); v1 = pg.input_value("#f-edit textarea[name=prompt]"); assert "smile" in v1 and v1.startswith("1girl, red hair")
    pg.click(".exprs .chip:has-text('화남')"); v2 = pg.input_value("#f-edit textarea[name=prompt]"); assert "angry" in v2 and "smile" not in v2 and v2.startswith("1girl, red hair"), v2
    assert float(pg.input_value("#f-edit input[name=denoise]")) <= 0.55; ok("expression chips replace each other, keep the user's prompt, lower the strength")
    pg.select_option("#f-edit select[name=engine]", "qwen"); pg.click(".exprs .chip:has-text('윙크')"); assert "윙크" in pg.input_value("#f-edit textarea[name=prompt]"); ok("expression chips write a sentence for Qwen")
    # CN 칸
    pg.select_option("#f-edit select[name=engine]", "sdxl"); assert pg.locator("#f-edit details:has-text('ControlNet')").is_visible(); ok("edit tab has a ControlNet section for SDXL")
    print("page errors:", errs); assert not errs
print("UI5 TESTS PASSED")
