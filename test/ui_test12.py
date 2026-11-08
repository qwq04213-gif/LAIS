"""기록 갤러리 · 프롬프트 보관함 · 와일드카드 · 이미지→프롬프트 화면."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time
os.environ["TEST_HUB_PORT"] = "17876"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
SP = Path(os.environ["TMPDIR"]) / "shots12"; SP.mkdir(exist_ok=True)
Image.new("RGB", (640, 480), (40, 90, 200)).save(SP / "in.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept(d.default_value))
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    # ── 갤러리: 먼저 하나 만들기
    pg.click("nav button[data-v=gen]"); pg.fill("#f-gen textarea[name=prompt]", "1girl, red jacket, rain"); pg.click("#f-gen button.go"); pg.wait_for_selector("#v-gen .res figure img", timeout=30000)
    pg.click("nav button[data-v=gal]"); pg.wait_for_selector("#gal-grid .gt img", timeout=5000)
    assert pg.locator("#gal-grid .gt").count() == 1 and "1개" in pg.inner_text("#gal-n")
    assert pg.locator("#gal-grid .gt img").evaluate("e=>e.getAttribute('src')").startswith("/thumb/"); ok("gallery lists the generated image with a thumbnail")
    pg.fill("#gal-q", "red jacket"); pg.wait_for_timeout(800); assert pg.locator("#gal-grid .gt").count() == 1
    pg.fill("#gal-q", "zzzz"); pg.wait_for_timeout(800); assert pg.locator("#gal-grid .gt").count() == 0; pg.fill("#gal-q", ""); pg.wait_for_timeout(800); ok("search by prompt")
    pg.click("#gal-grid .star"); pg.wait_for_timeout(300); assert "★" in pg.inner_text("#gal-grid .star"); pg.check("#gal-fav"); pg.wait_for_timeout(600); assert pg.locator("#gal-grid .gt").count() == 1
    pg.click("#gal-grid .star"); pg.wait_for_timeout(300); assert pg.locator("#gal-grid .gt").count() == 0; pg.uncheck("#gal-fav"); pg.wait_for_timeout(600); ok("favorite toggle + favorites-only filter")
    pg.click("#gal-grid .gt img"); pg.wait_for_selector("#lb:not([hidden])"); pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    pg.click("#gal-grid button[data-to=regen]"); pg.wait_for_timeout(800); assert pg.locator("#v-gen.on").count() == 1 and "red jacket" in pg.input_value("#f-gen textarea[name=prompt]"); ok("click opens lightbox; ↻ sends the settings back to the generate tab")
    # ── 보관함
    pg.click("nav button[data-v=lib]"); pg.wait_for_timeout(500)
    pg.click("#lib-nav button[data-pane=plib]")
    pg.click("#pl-new"); pg.fill("#pl-form [name=name]", "비 오는 거리"); pg.fill("#pl-form [name=text]", "rainy street, neon lights"); pg.fill("#pl-form [name=tags]", "배경, 밤"); pg.click("#pl-form button.go"); pg.wait_for_timeout(500)
    assert pg.locator("#pl-list .plitem").count() == 1 and "배경" in pg.inner_text("#pl-list"); ok("library: create item with tags")
    pg.click("#pl-list [data-pl=vid]"); pg.wait_for_timeout(500); assert pg.locator("#v-vid.on").count() == 1 and pg.input_value("#f-vid textarea[name=prompt]") == "rainy street, neon lights"; ok("'영상에 넣기' fills the video prompt and switches tab")
    pg.click("nav button[data-v=gen]"); pg.fill("#f-gen textarea[name=prompt]", "1girl"); pg.select_option("#f-gen .plib-sel", label="비 오는 거리"); pg.wait_for_timeout(200)
    assert pg.input_value("#f-gen textarea[name=prompt]") == "1girl, rainy street, neon lights"; ok("picker in the generate form appends the saved prompt")
    pg.fill("#f-gen textarea[name=prompt]", "my new prompt here"); pg.click("#f-gen .plib-save"); pg.wait_for_timeout(500)
    pg.click("nav button[data-v=lib]"); pg.wait_for_timeout(500); assert pg.locator("#pl-list .plitem").count() == 2; ok("'보관함에 저장' from a form adds an item")
    pg.fill("#pl-q", "neon"); assert pg.locator("#pl-list .plitem").count() == 1; pg.fill("#pl-q", "")
    pg.click("#pl-list .plitem:first-child [data-pl=del]"); pg.wait_for_timeout(500); assert pg.locator("#pl-list .plitem").count() == 1; ok("search + delete")
    # ── 와일드카드
    pg.click("#lib-nav button[data-pane=wc]"); pg.wait_for_selector("#wc-list .chip"); assert "__hair_color__" in pg.inner_text("#wc-list")
    pg.click("#wc-list .chip"); pg.wait_for_timeout(400); assert "blonde hair" in pg.input_value("#wc-form [name=text]")
    pg.fill("#wc-form [name=name]", "mood"); pg.fill("#wc-form [name=text]", "happy\nsad"); pg.click("#wc-form button.go"); pg.wait_for_timeout(600); assert "__mood__" in pg.inner_text("#wc-list")
    assert (hub.ROOT / "wildcards/mood.txt").read_text() == "happy\nsad"; ok("wildcard editor: open, create, appears in list and on disk")
    pg.click("#wc-del"); pg.wait_for_timeout(500); assert "__mood__" not in pg.inner_text("#wc-list")
    # ── 이미지→프롬프트
    pg.click("#lib-nav button[data-pane=i2p]"); pg.wait_for_timeout(300); assert pg.locator("#w-i2p").is_visible(); ok("no vision model -> install hint")
    STATE["vision"] = {"testmodel:latest"}; hub._VIS.clear(); pg.click("nav button[data-v=gen]"); pg.click("nav button[data-v=lib]"); pg.wait_for_timeout(600)
    assert pg.locator("#w-i2p").is_hidden(); pg.set_input_files("#i2p-file", str(SP / "in.png")); pg.select_option("#i2p-style", "tags"); pg.click("#i2p-go"); pg.wait_for_selector("#i2p-out:not([hidden])", timeout=15000)
    assert pg.input_value("#i2p-out") == "1girl, red jacket, rain"
    pg.click("[data-i2p=gen]"); pg.wait_for_timeout(300); assert pg.locator("#v-gen.on").count() == 1 and pg.input_value("#f-gen textarea[name=prompt]") == "1girl, red jacket, rain"; ok("image->prompt: result goes into the generate form")
    pg.screenshot(path=os.environ["TMPDIR"] + "/lib.png")
    b.close()
assert not errs, errs; print("ALL OK")
