"""사진 편집기 3: 이미지를 새 레이어로 넣기(파일·크기 맞춤)·크기·좌우 반전, 기록 갤러리 소리·3D 칸."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17958"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
T = os.environ["TMPDIR"]
Image.new("RGB", (400, 300), (40, 120, 220)).save(T + "/bg4.png"); Image.new("RGB", (800, 200), (250, 20, 20)).save(T + "/red4.png")
for sub, n, data in (("음악", "a-music-0.wav", b"RIFF0000WAVE"), ("기능", "b-vid-0.glb", b"glTF"), ("사진 편집", "c.png", None)):
    d = hub.OUT / sub; d.mkdir(parents=True, exist_ok=True)
    (Image.new("RGB", (8, 8)).save(d / n) if data is None else (d / n).write_bytes(data))
(hub.OUT / "음악" / "a-music-0.wav.json").write_text('{"prompt": "calm piano"}', encoding="utf-8")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1600, "height": 1000}); ctx.add_init_script("localStorage.setItem('ui:scale','1')"); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=photo]"); pg.set_input_files("#pe-file", T + "/bg4.png"); pg.wait_for_selector("#pe-wrap:not([hidden])")
    px = lambda x, y: pg.evaluate(f"[...document.querySelector('#pe-cv').getContext('2d').getImageData({x},{y},1,1).data]")
    pg.set_input_files("#pe-addimg", T + "/red4.png"); pg.wait_for_function("document.querySelectorAll('#pe-layers .pe-layer').length===2")
    assert px(200, 150)[0] > 200 and px(200, 20)[2] > 200, (px(200, 150), px(200, 20)); ok("image added as a new layer, shrunk to fit (400x100 band)")
    assert pg.locator(".pe-tools [data-tool=move]").get_attribute("aria-pressed") == "true"
    pg.evaluate("(()=>{const r=document.querySelector('#pe-lsc');r.value=50;r.dispatchEvent(new Event('input'));r.dispatchEvent(new Event('change'))})()")
    assert px(20, 150)[2] > 200 and px(200, 150)[0] > 200, (px(20, 150), px(200, 150)); ok("layer size 50% shrinks around the center")
    pg.click("#pe-undo"); assert px(20, 150)[0] > 200; ok("undo restores the size")
    pg.click("#pe-lflip"); assert px(200, 150)[0] > 200; ok("flip keeps the layer in place")
    pg.click("nav button[data-v=gal]"); pg.wait_for_selector("#gal-grid .gt")
    assert pg.locator("#gal-grid .gt[data-type=audio] audio").count() == 1 and pg.locator("#gal-grid .gt[data-type='3d'] a[download]").count() == 1
    assert pg.locator("#gal-grid .gt[data-u*='%EC%82%AC%EC%A7%84']").count() == 1; ok("gallery shows audio, 3D and photo-editor files")
    pg.select_option("#gal-type", "audio"); pg.wait_for_timeout(500); assert pg.locator("#gal-grid .gt").count() == 1
    pg.select_option("#gal-type", ""); pg.select_option("#gal-kind", "사진 편집"); pg.wait_for_timeout(500); assert pg.locator("#gal-grid .gt").count() == 1; ok("type and folder filters")
    pg.fill("#gal-q", "piano"); pg.select_option("#gal-kind", ""); pg.wait_for_timeout(700); assert pg.locator("#gal-grid .gt").count() == 1; ok("audio prompt search from sidecar")
    st = urllib.request.urlopen(B + "/out/" + urllib.parse.quote("사진 편집") + "/c.png").status; assert st == 200; ok("photo-editor files are served")
    # 기능 모음(색 보정) 결과에도 전후 비교 슬라이더
    pg.evaluate("document.querySelector('nav button[data-f=\"color\"]').click()"); pg.wait_for_selector("#feat-form h3")
    pg.evaluate(f"document.querySelector('#feat-form .mini[data-img=image]').set('data:image/png;base64,' + {repr(__import__('base64').b64encode(open(T + '/bg4.png','rb').read()).decode())})")
    pg.fill("#f-feat [name=bright]", "140"); pg.click("#feat-form .go"); pg.wait_for_selector("#v-feat .res [data-to=cmpi]", timeout=20000)
    pg.click("#v-feat .res [data-to=cmpi]"); assert pg.is_visible("#v-feat .res .cbr") and pg.is_visible("#v-feat .res .cbf")
    pg.evaluate("(()=>{const r=document.querySelector('#v-feat .res .cbr');r.value=30;r.dispatchEvent(new Event('input',{bubbles:true}))})()")
    assert "70%" in pg.evaluate("document.querySelector('#v-feat .res .cbf').style.clipPath"); ok("feature results get an inline before/after slider")
    # 사이드바 묶음 접기 · 기억
    pg.click("#rail nav .ng[data-g=vid] .ngt"); assert pg.locator("nav button[data-v=vedit]").is_hidden()
    pg.reload(); pg.wait_for_timeout(600); assert pg.locator("nav button[data-v=vedit]").is_hidden(); pg.evaluate("show('vedit')"); assert pg.locator("nav button[data-v=vedit]").is_visible(); ok("every sidebar group collapses, remembers, and opens for the current view")
    # 갤러리: 체크박스 다중 선택 · 보내기 메뉴 · 큰 화면(영상·3D)
    (hub.OUT / "영상").mkdir(parents=True, exist_ok=True); shutil.copy(T + "/../v.mp4" if False else __file__, hub.OUT / "영상" / "x.mp4") if False else None
    pg.evaluate("show('gal')"); pg.fill("#gal-q", ""); pg.wait_for_timeout(700)
    n = pg.locator("#gal-grid .gt").count(); pg.locator("#gal-grid .gt").first.hover(); pg.locator("#gal-grid .gt [data-pick]").nth(0).check(); pg.locator("#gal-grid .gt").nth(1).hover(); pg.locator("#gal-grid .gt [data-pick]").nth(1).check()
    assert pg.locator("#gal-grid .gt.picked").count() == 2 and pg.is_visible("#gal-delsel") and "2" in pg.inner_text("#gal-delsel")
    pg.locator("#gal-grid .gt").nth(2).click(position={"x": 60, "y": 60}); assert pg.locator("#gal-grid .gt.picked").count() == 3; ok("checkbox multi-select; card click adds while selecting")
    pg.click("#gal-sel"); assert pg.locator("#gal-grid .gt.picked").count() == 0
    img = pg.locator("#gal-grid .gt[data-type=image]").first; img.locator(".gmore summary").click(); assert img.locator(".gmore .menu [data-to='feat:color']").count() == 1 and img.locator(".gmore .menu [data-to=photol]").count() == 1; ok("card send menu lists every destination")
    pg.locator("#gal-grid .gt[data-type='3d'] [data-gview]").click(); pg.wait_for_selector("#lb:not([hidden]) #lb-media model-viewer"); pg.click("#lb-cont summary"); assert pg.locator("#lb-cont .menu [data-to=fs]").count() == 1; pg.keyboard.press("Escape")
    pg.locator("#gal-grid .gt[data-type='3d'] [data-g3d]").click(); assert pg.locator("#gal-grid model-viewer.gmv").count() == 1; ok("3D preview in card and big view")
    pg.locator("#gal-grid .gt[data-type=image] img").first.click(); pg.wait_for_selector("#lb:not([hidden])"); pg.click("#lb-cont summary"); assert pg.locator("#lb-cont .menu [data-to='feat:rmbg']").count() == 1; pg.keyboard.press("Escape"); ok("big view menu matches")
    # 자유 변형
    pg.evaluate("show('photo')"); pg.set_input_files("#pe-file", T + "/bg4.png"); pg.wait_for_selector("#pe-wrap:not([hidden])"); pg.set_input_files("#pe-addimg", T + "/red4.png"); pg.wait_for_timeout(300); pg.keyboard.press("Control+t"); assert pg.locator(".pe-tools [data-tool=xf]").get_attribute("aria-pressed") == "true"
    bb = pg.locator("#pe-cv").bounding_box(); X = lambda x: bb["x"] + x * bb["width"] / 400; Y = lambda y: bb["y"] + y * bb["height"] / 300
    pg.mouse.move(X(200), Y(150)); pg.mouse.down(); pg.mouse.move(X(250), Y(150), steps=4); pg.mouse.up()
    px = lambda x, y: pg.evaluate(f"[...document.querySelector('#pe-cv').getContext('2d').getImageData({x},{y},1,1).data]")
    assert px(20, 150)[2] > 200 and px(399, 150)[0] > 200, (px(20, 150), px(399, 150))
    hb = pg.evaluate("1"); pg.mouse.move(X(50), Y(200)); pg.mouse.down(); pg.mouse.move(X(150), Y(175), steps=5); pg.mouse.up()   # 왼쪽 아래 모서리를 안쪽으로 → 비율 유지 축소
    info = pg.inner_text("#pe-xfinfo"); pg.keyboard.press("Enter"); assert info.startswith("300×75"), info
    ok("free transform: move and corner scale keep the ratio; Enter applies (" + info + ")")
    pg.keyboard.press("Control+z"); pg.keyboard.press("Control+z")
    # LoRA 이름 붙이기
    pg.evaluate("show('setup')"); pg.wait_for_timeout(400); pg.click("#setup-nav button[data-pane=minfo]"); pg.wait_for_selector("#mi-list .mcard2")
    card = pg.locator("#mi-list .mcard2", has=pg.locator("[data-alias='style.safetensors']")); card.locator("[data-act=alias]").click()
    pg.keyboard.type("은발 마법사"); pg.keyboard.press("Enter"); pg.wait_for_function("[...document.querySelectorAll('#mi-list .mcard2 .mbody>b')].some(b=>b.textContent==='은발 마법사')")
    pg.evaluate("show('gen')"); pg.wait_for_timeout(300)
    assert pg.evaluate("[...document.querySelectorAll('#f-gen .lora-row select option')].some(o=>o.value==='style.safetensors'&&o.textContent.includes('은발 마법사'))"); ok("naming a LoRA shows the name on its card and in the LoRA picker")
    b.close()
assert not errs, errs
print("ALL OK")
