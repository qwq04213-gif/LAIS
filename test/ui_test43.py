"""캐릭터·스타일 보관함: 만들기(참고 이미지 포함) → 생성/편집/참고 이미지로 넣기 → 수정 → 삭제, 생성 화면·큰 화면에서 저장."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17905"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
Image.new("RGB", (900, 600), (200, 80, 90)).save(str(TMP / "ref.png")); Image.new("RGB", (300, 300), (20, 80, 190)).save(str(TMP / "ref2.png"))
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1100}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="lib"]'); pg.wait_for_selector("#ch-list"); pg.wait_for_function("document.querySelector('#ch-list').textContent.includes('아직 저장한')")
    pg.click("#ch-new"); pg.fill("#ch-form [name=name]", "은발 마법사 리아"); pg.select_option("#ch-form [name=kind]", "캐릭터")
    pg.fill("#ch-form [name=prompt]", "1girl, silver hair, wizard robe"); pg.fill("#ch-form [name=negative]", "bad hands"); pg.fill("#ch-form [name=seed]", "777")
    pg.select_option("#ch-loras .ch-lora", "style.safetensors"); pg.fill("#ch-loras .ch-w", "0.65")
    pg.locator('#ch-form .mini[data-img=chref1] input').set_input_files(str(TMP / "ref.png")); pg.locator('#ch-form .mini[data-img=chref2] input').set_input_files(str(TMP / "ref2.png"))
    pg.wait_for_function("document.querySelector('#ch-form .mini[data-img=chref2]').value")
    pg.click("#ch-form button[type=submit]"); pg.wait_for_selector("#ch-list .chcard"); t = pg.inner_text("#ch-list"); assert "은발 마법사 리아" in t and "style" in t and "시드 777" in t and "참고 이미지 2장" in t; ok("saved entry shows its LoRA, seed and reference count")
    d = json.loads((hub.ROOT / "library" / "chars.json").read_text(encoding="utf-8")); assert len(d) == 1 and d[0]["loras"] == [["style.safetensors", 0.65]] and len(d[0]["refs"]) == 2; assert all((hub.ROOT / "library" / "img" / n).is_file() for n in d[0]["refs"]); ok("stored on the server (json + PNG files in library/)")
    pg.wait_for_function("document.querySelector('#ch-list img').naturalWidth>0", timeout=10000); ok("thumbnail is served")
    pg.screenshot(path="/tmp/tt/chars.png")
    pg.click("nav button[data-v=gen]"); pg.wait_for_selector("#f-gen"); pg.fill("#f-gen [name=prompt]", "snowy street")
    pg.click("nav button[data-v=lib]"); pg.click('#ch-list [data-ch=gen]'); pg.wait_for_selector("#v-gen.on")
    v = pg.evaluate("(()=>{const f=document.querySelector('#f-gen');return [f.elements.prompt.value,f.elements.seed.value,[...f.querySelectorAll('.lora-row')].map(r=>[r.querySelector('select').value,r.querySelector('input').value]),f.elements.negative.value]})()")
    assert v[0] == "snowy street, 1girl, silver hair, wizard robe" and v[1] == "777" and ["style.safetensors", "0.65"] in v[2] and "bad hands" in v[3], v; ok("[이미지 생성에 넣기] appends the prompt, sets LoRA with its strength, seed and negative")
    pg.click("nav button[data-v=lib]"); pg.click('#ch-list [data-ch=gen]'); pg.wait_for_selector("#v-gen.on")
    v2 = pg.evaluate("(()=>{const f=document.querySelector('#f-gen');return [f.elements.prompt.value,[...f.querySelectorAll('.lora-row select')].filter(s=>s.value=='style.safetensors').length]})()")
    assert v2[1] == 1, v2; ok("applying twice does not duplicate the LoRA row")
    pg.click("nav button[data-v=lib]"); pg.click('#ch-list [data-ch=edit]'); pg.wait_for_selector("#v-edit.on")
    assert pg.evaluate("document.querySelector('#f-edit .mini[data-img=ref1]').value") and pg.evaluate("document.querySelector('#f-edit .mini[data-img=ref2]').value"); ok("[편집에 참고로] fills reference image slots")
    pg.click("nav button[data-v=lib]"); pg.click('#ch-list [data-ch=ipa]'); pg.wait_for_selector("#v-feat.on"); pg.wait_for_function("document.querySelector('#feat-form .mini[data-img=image]')&&document.querySelector('#feat-form .mini[data-img=image]').value", timeout=8000); ok("[참고 이미지로 그리기] puts the picture into the feature form")
    pg.click("nav button[data-v=lib]"); pg.click('#ch-list [data-ch=edit-item]'); assert pg.input_value("#ch-form [name=name]") == "은발 마법사 리아" and pg.evaluate("!!document.querySelector('#ch-form .mini[data-img=chref1]').value"); pg.fill("#ch-form [name=name]", "리아 (수정)"); pg.click("#ch-form .mini[data-img=chref2] .x"); pg.click("#ch-form button[type=submit]")
    pg.wait_for_function("document.querySelector('#ch-list').textContent.includes('리아 (수정)')"); d = json.loads((hub.ROOT / "library" / "chars.json").read_text(encoding="utf-8")); assert len(d) == 1 and len(d[0]["refs"]) == 1; assert len(list((hub.ROOT / "library" / "img").glob("*.png"))) == 1; ok("edit keeps the first picture, removing one deletes its file")
    pg.click("nav button[data-v=gen]"); pg.wait_for_selector(".ch-save-gen"); pg.click(".ch-save-gen"); pg.wait_for_selector("#ch-form:not([hidden])")
    assert "snowy street" in pg.input_value("#ch-form [name=prompt]") and pg.input_value("#ch-form [name=seed]") == "777"; ok("[캐릭터·스타일로 저장] on the gen form carries over the current settings")
    pg.fill("#ch-form [name=name]", "눈 오는 거리"); pg.select_option("#ch-form [name=kind]", "배경"); pg.click("#ch-form button[type=submit]"); pg.wait_for_function("document.querySelectorAll('#ch-list .chcard').length==2")
    pg.select_option("#ch-kind", "배경"); assert pg.locator("#ch-list .chcard").count() == 1; pg.select_option("#ch-kind", ""); pg.fill("#ch-q", "리아"); assert pg.locator("#ch-list .chcard").count() == 1; pg.fill("#ch-q", ""); ok("kind filter and search work")
    pg.click("nav button[data-v=gen]"); pg.click("#f-gen .go"); pg.wait_for_selector("#v-gen .res figure img", timeout=30000)
    pg.locator("#v-gen .res figure details.more summary").first.click(); pg.click('#v-gen .res [data-to=chsave]'); pg.wait_for_selector("#ch-form:not([hidden])", timeout=8000)
    assert pg.evaluate("!!document.querySelector('#ch-form .mini[data-img=chref1]').value") and "snowy street" in pg.input_value("#ch-form [name=prompt]"); ok("[캐릭터·스타일로 저장] from a result reads the picture's own settings and uses it as the cover")
    pg.click("#ch-cancel")
    pg.click('#ch-list .chcard >> nth=0 >> [data-ch=del]'); pg.wait_for_function("document.querySelectorAll('#ch-list .chcard').length==1"); ok("delete asks first, then removes the entry")
    left = len(list((hub.ROOT / "library" / "img").glob("*.png"))); assert left <= 1, left; ok("its picture files are removed with it")
    assert not errs, errs
    b.close()
print("ALL OK")
