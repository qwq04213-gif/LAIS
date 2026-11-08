"""사진 편집기 2: 선택(사각·올가미·자동)·반전·지우기·새 레이어로 복사, 선택 안에서만 칠하기, 혼합 모드, 밝게·흐리게·복제 도장."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17957"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import ImageDraw
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
T = os.environ["TMPDIR"]; im = Image.new("RGB", (400, 300), (40, 120, 220)); ImageDraw.Draw(im).rectangle((250, 150, 350, 250), fill=(240, 240, 30)); im.save(T + "/pe3.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1600, "height": 1000}); ctx.add_init_script("localStorage.setItem('ui:scale','1')"); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=photo]"); pg.set_input_files("#pe-file", T + "/pe3.png"); pg.wait_for_selector("#pe-wrap:not([hidden])")
    bb = pg.locator("#pe-cv").bounding_box(); X = lambda x: bb["x"] + x * bb["width"] / 400; Y = lambda y: bb["y"] + y * bb["height"] / 300
    px = lambda x, y: pg.evaluate(f"[...document.querySelector('#pe-cv').getContext('2d').getImageData({x},{y},1,1).data]")
    drag = lambda a, c, steps=6: (pg.mouse.move(X(a[0]), Y(a[1])), pg.mouse.down(), pg.mouse.move(X(c[0]), Y(c[1]), steps=steps), pg.mouse.up())
    tool = lambda t: pg.click(f".pe-tools [data-tool={t}]")
    # 사각 선택 → 브러시는 선택 안에서만
    tool("msel"); drag((20, 20), (120, 120)); assert not pg.is_disabled("#pe-snone")
    edge = pg.evaluate("(()=>{const d=document.querySelector('#pe-ov').getContext('2d').getImageData(0,70,400,1).data;let n=0;for(let i=0;i<d.length;i+=4)if(d[i+2]>200&&d[i]<80)n++;return n})()"); assert edge >= 2, edge
    tool("brush"); pg.fill("#pe-color", "#ff0000"); pg.fill("#pe-size", "40"); drag((60, 70), (200, 70), 12)
    assert px(80, 70)[0] > 200 and px(180, 70)[2] > 150, (px(80, 70), px(180, 70)); ok("rectangle selection limits the brush")
    pg.keyboard.press("Control+d"); assert pg.is_disabled("#pe-snone"); ok("Ctrl+D clears the selection")
    # 자동 선택(노란 사각형) → 새 레이어로 복사 → 혼합 모드
    tool("wand"); pg.mouse.click(X(300), Y(200)); assert not pg.is_disabled("#pe-scopy"); pg.click("#pe-scopy"); assert pg.locator("#pe-layers .pe-layer").count() == 2
    pg.select_option("#pe-lblend", "multiply"); m = px(300, 200); assert m[2] < 20 and m[0] > 200, m; ok("magic wand picks the yellow square; copy to new layer; multiply blend darkens")
    pg.select_option("#pe-lblend", "source-over")
    # 반전 → 지우기: 사각형 바깥이 투명
    pg.click("#pe-sinv"); pg.click("#pe-sdel"); assert px(30, 250)[3] == 255 and pg.evaluate("[...document.querySelector('#pe-cv').getContext('2d').getImageData(300,200,1,1).data][3]") == 255
    pg.click("#pe-snone"); ok("invert + delete on the copied layer leaves only the square there")
    # 올가미 → 조정은 선택 안에서만
    pg.click("#pe-layers .pe-layer >> nth=1"); tool("lasso")
    pg.mouse.move(X(20), Y(200)); pg.mouse.down()
    for x, y in ((120, 200), (120, 280), (20, 280), (20, 201)): pg.mouse.move(X(x), Y(y), steps=4)
    pg.mouse.up(); before_in, before_out = px(70, 240), px(200, 120)
    pg.locator("[data-adj=b]").fill("30"); pg.locator("[data-adj=b]").dispatch_event("input"); pg.click("#pe-adjok")
    assert px(70, 240)[2] < before_in[2] * 0.5 and abs(px(200, 120)[2] - before_out[2]) < 4, (px(70, 240), px(200, 120)); pg.click("#pe-snone"); ok("lasso selection limits the brightness adjustment")
    # 밝게 문지르기
    tool("dodge"); pg.fill("#pe-size", "30"); b0 = px(200, 40); drag((170, 40), (230, 40), 8); b1 = px(200, 40); assert sum(b1[:3]) > sum(b0[:3]) + 30, (b0, b1); ok("dodge brush brightens where rubbed")
    # 복제 도장: 노란 사각형을 왼쪽 위로 옮겨 그리기
    tool("clone"); pg.keyboard.down("Alt"); pg.mouse.click(X(300), Y(200)); pg.keyboard.up("Alt"); assert px(300, 50)[2] > 150
    pg.fill("#pe-size", "20"); drag((300, 50), (305, 52), 3); c = px(300, 50); assert c[0] > 180 and c[1] > 180 and c[2] < 120, c; ok("clone stamp copies from the Alt-clicked source")
    pg.keyboard.press("Control+z"); assert px(300, 50)[2] > 150; ok("undo after retouch")
    assert not errs, errs
print("ALL OK")
