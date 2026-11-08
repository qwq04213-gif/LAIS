"""4.1 화면: 3D 만들기 — 방향 약속 안내, 맞지 않는 방향 그림 표시(체크 풀림), T자 자세로 바꾸기·원래 자세로, 뼈대 넣기 → 뼈대 정보·움직임 미리보기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17964"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
PERSON = [(170, 40, 230, 100), (150, 100, 250, 260), (250, 110, 330, 130), (160, 260, 195, 380), (205, 260, 240, 380)]   # 좌우 비대칭
class Cut:
    def cut(self, img, _):
        a = Image.new("L", img.size, 0); w, h = img.size
        for x0, y0, x1, y1 in PERSON: a.paste(255, (x0 * w // 400, y0 * h // 400, x1 * w // 400, y1 * h // 400))
        o = img.convert("RGBA"); o.putalpha(a); return o
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True; hub.rmbg_engine = lambda k: Cut()
for f in ("diffusion_models/trellis_2_int8_convrot.safetensors", "clip_vision/dino_v3_vit_l.safetensors", "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors"):
    (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
os.environ["BLENDER_EXE"] = BASE + "/test/fake_blender.py"; os.chmod(os.environ["BLENDER_EXE"], 0o755)
D = TMP / "pics"; D.mkdir()
Image.new("RGB", (400, 400), (40, 90, 200)).save(D / "hero.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 950})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/unpkg.com/**", lambda r: r.fulfill(status=200, content_type="text/javascript",
             body="customElements.define('model-viewer',class extends HTMLElement{play(){window.__played=(window.__played||0)+1}})"))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    pg.click("nav button[data-v=m3d]"); pg.wait_for_timeout(400)
    pg.select_option("#m3-kind", "object"); assert not pg.is_checked("#m3-rig")
    pg.select_option("#m3-kind", "character"); assert pg.is_checked("#m3-rig")
    pg.set_input_files("#m3-file", str(D / "hero.png")); pg.wait_for_function("!document.querySelector('#m3-go').disabled", timeout=15000)
    assert pg.is_visible("#m3-tpose") and not pg.is_visible("#m3-tundo") and "왼쪽" in pg.inner_text(".m3-dir") and "얼굴" in pg.inner_text(".m3-dir")
    ok("character: rig on by default (off for objects), T-pose button, direction rule shown")
    pg.click("#m3-views"); pg.wait_for_function("document.querySelectorAll('#m3-slots .m3-slot img').length==4", timeout=30000)
    # 가짜 편집은 그림을 뒤집지 않아요 → 뒤(앞을 뒤집은 모양이어야 함)·왼쪽/오른쪽(서로 거울) 모두 '맞지 않아요'
    assert pg.locator("#m3-slots .m3-slot.sus").count() == 3 and pg.locator(".m3-sus").count() == 3
    assert pg.locator("#m3-slots input[data-use]:checked").count() == 0 and "체크를 풀어" in pg.inner_text("#m3-st")
    assert "달라" in (pg.get_attribute("#m3-slots [data-side=back] .m3-sus", "title") or "")
    ok("generated views that don't match the front are flagged and left unchecked")
    pg.click("#m3-tpose"); pg.wait_for_selector("#m3-tundo:not([hidden])", timeout=30000)
    assert any("T-pose" in str(v["inputs"].get("prompt", "")) + str(v["inputs"].get("text", "")) for v in SUBMITTED[-1].values())
    pg.click("#m3-tundo"); pg.wait_for_selector("#m3-tundo[hidden]", state="attached", timeout=5000)
    ok("T-pose → 'back to original pose' appears, restores and hides")
    pg.click("#m3-go"); pg.wait_for_selector("#m3-mv", timeout=30000)
    t = pg.inner_text(".m3-rig"); assert "뼈대 22개" in t and "T자" in t and "Mixamo" in t and "Unity" in t, t
    zip_ = pg.get_attribute("#m3-out a[href$='.zip']", "href"); glb = pg.get_attribute("#m3-mv", "src")
    pg.click("#m3-move"); pg.wait_for_timeout(200)
    assert "rig_preview.glb" in pg.get_attribute("#m3-mv", "src") and pg.get_attribute("#m3-mv", "autoplay") is not None and pg.inner_text("#m3-move") == "움직임 끄기"
    pg.evaluate("document.querySelector('#m3-mv').dispatchEvent(new Event('load'))"); assert pg.evaluate("window.__played") == 1
    pg.click("#m3-move"); assert pg.get_attribute("#m3-mv", "src") == glb and pg.get_attribute("#m3-mv", "autoplay") is None
    ok("build with rig → bone info, motion preview toggles the viewer and plays")
    pg.select_option("#m3-kind", "object"); pg.click("#m3-go"); pg.wait_for_function("document.querySelector('#m3-mv') && !document.querySelector('.m3-rig')", timeout=30000)
    assert pg.locator("#m3-move").count() == 0
    ok("rig off → no bone info, no motion preview")
    pg.set_viewport_size({"width": 1100, "height": 800}); pg.wait_for_timeout(200)
    assert pg.evaluate("document.querySelector('#v-m3d form').scrollWidth<=document.querySelector('#v-m3d form').clientWidth+1")
    b.close()
assert not errs, errs
print("ALL OK")
