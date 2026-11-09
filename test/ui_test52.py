"""사진 편집기(열기·브러시·지우개·글자 레이어·도형·자르기·조정·되돌리기·저장), 영상 편집 화면, 추천 모델 상단 고정 막대."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, subprocess
os.environ["TEST_HUB_PORT"] = "17956"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
T = os.environ["TMPDIR"]; Image.new("RGB", (400, 300), (40, 120, 220)).save(T + "/pe.png")
V = hub.OUT / "영상"; V.mkdir(parents=True, exist_ok=True)
for n in ("a", "b"): subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=1", str(V / f"{n}.mp4")], check=True)
errs = []
px = lambda pg, x, y: pg.evaluate(f"(()=>{{const c=document.querySelector('#pe-cv');return [...c.getContext('2d').getImageData({x},{y},1,1).data]}})()")
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 950}); ctx.add_init_script("localStorage.setItem('ui:scale','1')"); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept("200"))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=photo]"); pg.set_input_files("#pe-file", T + "/pe.png"); pg.wait_for_selector("#pe-wrap:not([hidden])")
    assert pg.evaluate("[document.querySelector('#pe-cv').width,document.querySelector('#pe-cv').height]") == [400, 300] and pg.locator("#pe-layers .pe-layer").count() == 1; ok("open a photo → canvas + one layer")
    bb = pg.locator("#pe-cv").bounding_box(); X = lambda x: bb["x"] + x * bb["width"] / 400; Y = lambda y: bb["y"] + y * bb["height"] / 300
    pg.click(".pe-tools [data-tool=brush]"); pg.fill("#pe-color", "#ff0000")
    pg.mouse.move(X(50), Y(50)); pg.mouse.down(); pg.mouse.move(X(150), Y(50), steps=8); pg.mouse.up()
    r = px(pg, 100, 50); assert r[0] > 200 and r[2] < 80, r; ok("brush paints on the layer")
    pg.click("#pe-undo"); r = px(pg, 100, 50); assert r[2] > 150, r; pg.click("#pe-redo"); assert px(pg, 100, 50)[0] > 200; ok("undo / redo")
    pg.click(".pe-tools [data-tool=eraser]"); pg.mouse.move(X(300), Y(200)); pg.mouse.down(); pg.mouse.move(X(320), Y(200), steps=4); pg.mouse.up(); assert px(pg, 310, 200)[3] < 30; ok("eraser makes pixels transparent")
    pg.click(".pe-tools [data-tool=text]"); pg.fill("#pe-text", "HELLO"); pg.mouse.click(X(20), Y(120)); assert pg.locator("#pe-layers .pe-layer").count() == 2 and "글자" in pg.inner_text("#pe-layers"); ok("text goes on its own layer")
    pg.click(".pe-tools [data-tool=rect]"); pg.check("#pe-fill"); pg.mouse.move(X(200), Y(20)); pg.mouse.down(); pg.mouse.move(X(260), Y(80), steps=4); pg.mouse.up(); assert px(pg, 230, 50)[0] > 200; ok("filled rectangle")
    pg.locator("[data-adj=b]").fill("40"); pg.locator("[data-adj=b]").dispatch_event("input"); assert not pg.is_disabled("#pe-adjok"); pg.click("#pe-adjok"); ok("brightness adjustment applied to the active layer")
    pg.click("#pe-ladd"); assert pg.locator("#pe-layers .pe-layer").count() == 3; pg.click("#pe-lmerge"); assert pg.locator("#pe-layers .pe-layer").count() == 2; ok("add / merge layers")
    pg.click(".pe-tools [data-tool=crop]"); pg.mouse.move(X(10), Y(10)); pg.mouse.down(); pg.mouse.move(X(210), Y(160), steps=4); pg.mouse.up(); pg.click("#pe-cropok")
    w, h = pg.evaluate("[document.querySelector('#pe-cv').width,document.querySelector('#pe-cv').height]"); assert abs(w - 200) <= 2 and abs(h - 150) <= 2, (w, h); ok(f"crop → {w}×{h}")
    pg.click("#pe-rotr"); assert pg.evaluate("document.querySelector('#pe-cv').width") == h; ok("rotate 90°")
    pg.click("#pe-save"); pg.wait_for_timeout(800); saved = list(hub.out_files(hub.OUT / "사진 편집", {".png"})); assert saved and Image.open(saved[0]).size == (h, w), saved; ok("saved into outputs/사진 편집")
    pg.locator("#v-photo details.more summary").click(); pg.click("[data-pto=up]"); pg.wait_for_selector("#v-up.on"); ok("send the edit to another screen")
    # 영상 편집
    pg.click("nav button[data-v=vedit]"); pg.wait_for_selector("#ve-list .verow"); assert pg.locator("#ve-list .verow").count() == 2
    opts = pg.eval_on_selector_all("#ve-list .verow select >> nth=0", "e=>[...e[0].options].map(o=>o.value)"); assert any("a.mp4" in o for o in opts), opts
    pg.select_option("#ve-list .verow select >> nth=0", [o for o in opts if "a.mp4" in o][0]); pg.select_option("#ve-list .verow select >> nth=1", [o for o in opts if "b.mp4" in o][0])
    pg.click("#ve-add"); assert pg.locator("#ve-list .verow").count() == 3; pg.locator("#ve-list [data-rm]").nth(2).click(); assert pg.locator("#ve-list .verow").count() == 2
    pg.click("#f-vedit .go"); pg.wait_for_selector("#v-vedit .res video", timeout=30000); ok("영상 편집: join two videos from the screen")
    pg.click("#f-vedit .vemodes label:has-text('자르기')"); assert pg.inner_text("#f-vedit .go") == "자르기" and pg.is_visible("#ve-setS"); pg.click("#f-vedit .vemodes label:has-text('AI 이어 그리기')"); assert pg.is_visible("#ve-novace"); ok("modes switch the form")
    # 추천 모델 막대
    pg.click("nav button[data-v=setup]"); pg.wait_for_selector("#cat-img .item"); pg.mouse.wheel(0, 3000); pg.wait_for_timeout(300)
    top = pg.locator(".recbar").bounding_box()["y"]; assert pg.locator("#inst").is_visible() and top < 300, top; ok("install button and progress stay on screen while scrolling the list")
    assert not errs, errs
print("ALL OK")
