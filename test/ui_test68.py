"""4.2 화면: 3D 만들기 > 장면 전체 — 선택 도구 설치 안내 → 원본 사진에서 물체 누르기(가짜 MobileSAM) → 이 물체 넣기·빼기 →
가려진 부분 채우기 → 장면 만들기 → 물체 표(키·거리·면)·묶음 저장."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17948"
sys.path.insert(0, BASE + "/test")
from mocks import *
import fake_sam
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
class Cut:
    def cut(self, img, _):
        a = Image.new("L", img.size, 0); w, h = img.size; a.paste(255, (w // 4, h // 6, w * 3 // 4, h * 5 // 6)); o = img.convert("RGBA"); o.putalpha(a); return o
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True; hub.rmbg_engine = lambda k: Cut()
for f in ("diffusion_models/trellis_2_int8_convrot.safetensors", "clip_vision/dino_v3_vit_l.safetensors", "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors"):
    (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
D = TMP / "pics"; D.mkdir()
photo = Image.new("RGB", (600, 400), (90, 120, 150)); photo.paste((220, 40, 40), (60, 120, 220, 360)); photo.paste((40, 210, 40), (380, 200, 500, 330)); photo.save(D / "room.png")
def fake_install(t):
    for n in (hub.sam.ENCODER, hub.sam.DECODER): (hub.MODELS / "sam" / n).write_bytes(b"0" * 2_000_000)
    t["msg"] = "완료"
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1000})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/unpkg.com/**", lambda r: r.fulfill(status=200, content_type="text/javascript", body="customElements.define('model-viewer',class extends HTMLElement{})"))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    pg.click("nav button[data-v=m3d]"); pg.wait_for_timeout(300); assert not pg.is_visible("#m3-sceneset")
    pg.set_input_files("#m3-file", str(D / "room.png")); pg.wait_for_function("!document.querySelector('#m3-go').disabled", timeout=15000)
    pg.locator("#m3-sceneset").scroll_into_view_if_needed(); assert not pg.is_visible("#m3-sorig")      # 4.7: 접혀서 맨 아래
    assert pg.evaluate("[...document.querySelectorAll('#v-m3d form > *')].pop().id") == "m3-sceneset"
    pg.click("#m3-sceneset > summary"); assert pg.is_visible("#m3-sorig") and pg.is_disabled("#m3-sgo") and "아직" in pg.inner_text("#m3-sobjs")
    pg.wait_for_function("document.querySelector('#m3-sorig').naturalWidth===600", timeout=5000)
    ok("scene panel appears with the original photo once a photo is picked")
    def click_at(fx, fy, shift=False):
        pg.locator("#m3-sorig").scroll_into_view_if_needed(); bb = pg.locator("#m3-sorig").bounding_box(); pg.mouse.click(bb["x"] + bb["width"] * fx, bb["y"] + bb["height"] * fy) if not shift else (pg.keyboard.down("Shift"), pg.mouse.click(bb["x"] + bb["width"] * fx, bb["y"] + bb["height"] * fy), pg.keyboard.up("Shift"))
    click_at(0.23, 0.6); pg.wait_for_selector("#m3-ssam:not([hidden])", timeout=5000); assert "선택 도구" in pg.inner_text("#m3-st")
    (hub.MODELS / "sam").mkdir(exist_ok=True); hub.sam_run_install = fake_install; hub.SAM["factory"] = fake_sam.factory; hub.SAM["engine"] = None; hub.sam.have_ort = lambda: True
    pg.click("#m3-ssam"); pg.wait_for_selector("#m3-ssam", state="hidden", timeout=20000)
    ok("no selection tool → install button; installing hides it")
    click_at(0.23, 0.6); pg.wait_for_function("!document.querySelector('#m3-sadd').disabled", timeout=10000)
    assert pg.evaluate("M3S.pts.length") == 1 and pg.evaluate("M3S.mask.startsWith('data:image/png')")
    px = pg.evaluate("(()=>{const c=document.querySelector('#m3-smask'),x=c.getContext('2d');return [x.getImageData(140,240,1,1).data[3],x.getImageData(20,20,1,1).data[3],c.width]})()")
    assert px[0] > 0 and px[1] == 0 and px[2] == 600, px
    pg.click("#m3-sadd"); pg.wait_for_function("document.querySelectorAll('#m3-sobjs .m3-sobj').length===1", timeout=10000)
    assert pg.evaluate("M3S.pts.length") == 0 and pg.is_disabled("#m3-sadd") and not pg.is_disabled("#m3-sgo") and "1개" in pg.inner_text("#m3-sgo")
    click_at(0.73, 0.66); pg.wait_for_function("!document.querySelector('#m3-sadd').disabled", timeout=10000)
    click_at(0.1, 0.1, shift=True); pg.wait_for_timeout(500); assert pg.evaluate("M3S.pts.map(p=>p[2])") == [1, 0]
    pg.click("#m3-sadd"); pg.wait_for_function("document.querySelectorAll('#m3-sobjs .m3-sobj').length===2", timeout=10000)
    click_at(0.5, 0.05); pg.wait_for_function("!document.querySelector('#m3-sadd').disabled", timeout=10000); pg.click("#m3-sreset"); assert pg.evaluate("M3S.pts.length") == 0
    ok("click an object → highlighted; add it; Shift+click excludes; reset clears the current pick")
    pg.click("#m3-sobjs [data-srm]:first-of-type >> nth=0"); pg.wait_for_function("document.querySelectorAll('#m3-sobjs .m3-sobj').length===1", timeout=5000)
    click_at(0.23, 0.6); pg.wait_for_function("!document.querySelector('#m3-sadd').disabled", timeout=10000); pg.click("#m3-sadd")
    pg.wait_for_function("document.querySelectorAll('#m3-sobjs .m3-sobj').length===2", timeout=10000)
    ok("remove an object (×) and add it back")
    pg.check("#m3-sfill"); n0 = len(SUBMITTED)
    pg.click("#m3-sgo"); pg.wait_for_selector("#m3-mv", timeout=60000)
    txt = " ".join(str(v["inputs"].get("prompt", "")) + str(v["inputs"].get("text", "")) for g in SUBMITTED[n0:] for v in g.values()); assert txt.count("hidden or missing part") == 2
    assert pg.locator(".m3-stat tbody tr").count() == 2 and "거리" in pg.inner_text(".m3-stat") and "AI" in pg.inner_text("#m3-out") and "layout.json" in pg.inner_text("#m3-out") and "물체 1" in pg.inner_text(".m3-stat") and ".blend" not in pg.inner_text("#m3-out")
    assert pg.locator("#m3-out a[href$='.zip']").count() == 1 and pg.get_attribute("#m3-mv", "src").endswith(".glb") and "장면을 만들었어요" in pg.inner_text("#m3-st")
    ok("build scene (with fill) → viewer, object table (height · distance · faces), zip download")
    pg.set_viewport_size({"width": 1100, "height": 800}); pg.wait_for_timeout(200)
    assert pg.evaluate("document.querySelector('#v-m3d form').scrollWidth<=document.querySelector('#v-m3d form').clientWidth+1")
    b.close()
assert not errs, errs
print("ALL OK")
