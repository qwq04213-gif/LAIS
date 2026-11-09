"""4.0 화면: 3D 만들기(사진 고르기 → 점검·방향 칸 → 내 사진 넣기 → 만들기 → 뷰어·LOD 표·묶음 저장), Blender 설치 칸, 엔진별 자동 번역 기억."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, io, base64
os.environ["TEST_HUB_PORT"] = "17993"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
class FakeCut:
    def cut(self, img, _):
        a = Image.new("L", img.size, 0); w, h = img.size; a.paste(255, (w // 4, h // 6, w * 3 // 4, h * 5 // 6)); o = img.convert("RGBA"); o.putalpha(a); return o
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True; hub.rmbg_engine = lambda k: FakeCut()
for f in ("diffusion_models/trellis_2_int8_convrot.safetensors", "clip_vision/dino_v3_vit_l.safetensors", "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors"):
    (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
D = TMP / "pics"; D.mkdir()
im = Image.new("RGBA", (400, 400), (0, 0, 0, 0)); im.paste((200, 60, 60, 255), (100, 60, 300, 360)); im.save(D / "knight.png")
Image.new("RGB", (300, 300), (20, 200, 20)).save(D / "side.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 950})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/unpkg.com/**", lambda r: r.fulfill(status=200, content_type="text/javascript", body="customElements.define('model-viewer',class extends HTMLElement{})"))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    pg.click("nav button[data-v=m3d]"); pg.wait_for_timeout(500)
    assert pg.is_disabled("#m3-go") and not pg.is_visible("#m3-viewset") and "Blender 설치" in pg.inner_text("#m3-bl") and not pg.is_visible("#m3-del")
    ok("3D view: empty state, build disabled, Blender install offered")
    pg.select_option("#m3-kind", "character"); assert pg.input_value("#m3-height") == "1.7" and pg.input_value("#m3-faces") == "200000" and pg.is_checked("#m3-photo") and pg.locator("#m3-faces option[value='700000']").count() == 1
    pg.fill("#m3-name", "knight")
    pg.set_input_files("#m3-file", str(D / "knight.png")); pg.wait_for_function("!document.querySelector('#m3-go').disabled", timeout=15000)
    assert pg.locator("#m3-check li").count() >= 1 and pg.locator("#m3-slots .m3-slot").count() == 4 and pg.locator("#m3-slots .m3-slot img").count() == 1
    assert pg.locator("#m3-slots input[data-use]:disabled").count() == 3 and "Pixal3D" in pg.inner_text("#m3-mvnote")
    assert pg.input_value("#m3-sess") != "" and "knight" in pg.inner_text("#m3-sess") and pg.is_visible("#m3-del")
    ok("photo picked → checks, 4 slots (front filled, others empty), multi-view note, session listed")
    with pg.expect_file_chooser() as fc:
        pg.click("#m3-slots [data-slotup=left]")
    fc.value.set_files(str(D / "side.png")); pg.wait_for_function("document.querySelectorAll('#m3-slots .m3-slot img').length==2", timeout=10000)
    assert pg.is_checked("#m3-slots input[data-use=left]") and pg.locator("#m3-slots [data-slotclr=left]").count() == 1
    pg.click("#m3-slots [data-slotclr=left]"); pg.wait_for_function("document.querySelectorAll('#m3-slots .m3-slot img').length==1", timeout=10000)
    ok("slot: put my own photo in, then clear it")
    os.environ["BLENDER_EXE"] = BASE + "/test/fake_blender.py"; os.chmod(os.environ["BLENDER_EXE"], 0o755)
    pg.click("nav button[data-v=gen]"); pg.click("nav button[data-v=m3d]"); pg.wait_for_function("document.querySelector('#m3-bl').innerText.includes('준비됨')", timeout=5000)
    pg.check("#m3-fmt-obj"); pg.select_option("#m3-tex", "1024")
    pg.click("#m3-go"); pg.wait_for_selector("#m3-mv", timeout=30000)
    s = SUBMITTED[-1]; assert any(v["class_type"] == "UnwrapMesh" and v["inputs"]["resolution"] == 1024 for v in s.values())
    assert pg.locator(".m3-stat tbody tr").count() == 3 and pg.locator("#m3-out a[href$='.zip']").count() == 1 and pg.locator("#m3-out a[href$='.glb']").count() == 1
    assert "1.70" in pg.inner_text("#m3-out") and "obj" in pg.inner_text(".m3-stat") and pg.get_attribute("#m3-mv", "src").endswith(".glb")
    pg.click("#m3-spin"); assert pg.inner_text("#m3-spin") == "회전하기"
    ok("build → viewer, LOD table (3 rows, OBJ included), GLB + zip downloads, height 1.7m")
    pg.once("dialog", lambda d: d.accept()); pg.click("#m3-del"); pg.wait_for_timeout(600)
    assert pg.is_disabled("#m3-go") and pg.input_value("#m3-sess") == "" and not list(hub.M3D_DIR.iterdir())
    ok("delete the work session")
    # 엔진별 자동 번역 기억 (Qwen 은 기본 꺼짐)
    pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(300); tr = "#f-gen input[name=translate]"; pg.evaluate("document.querySelector('#f-gen input[name=translate]').closest('details').open=true")
    pg.select_option("#f-gen select[name=gengine]", "qwenimg"); assert not pg.is_checked(tr)
    pg.select_option("#f-gen select[name=gengine]", "sdxl"); assert pg.is_checked(tr)
    pg.select_option("#f-gen select[name=gengine]", "moss"); assert not pg.is_checked(tr); pg.check(tr)
    pg.select_option("#f-gen select[name=gengine]", "sdxl"); pg.uncheck(tr)
    pg.select_option("#f-gen select[name=gengine]", "moss"); assert pg.is_checked(tr)
    pg.select_option("#f-gen select[name=gengine]", "sdxl"); assert not pg.is_checked(tr)
    ok("auto-translate: off by default for Qwen/MOSS, on/off remembered per engine")
    pg.set_viewport_size({"width": 1100, "height": 800}); pg.click("nav button[data-v=m3d]"); pg.wait_for_timeout(300)
    assert pg.evaluate("document.querySelector('#v-m3d form').scrollWidth<=document.querySelector('#v-m3d form').clientWidth+1")
    b.close()
assert not errs, errs
print("ALL OK")
