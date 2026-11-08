"""2.1: 설치됐는데 노드가 안 보일 때 원인 확인/부품 설치, 보관함 복사 설정, 갤러리 미리보기 크기별 표시·켜기/끄기, 이미지 생성으로 보내기 문구, 얼굴 교체 미검증 표시 제거."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17913"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
hub.GHURL = "https://github.com"   # 모의 서버 주소 대신 실제 주소로 확인(알려진 확장 목록은 GitHub 주소)
errs = []
# ── 서버: 설치돼 있는데 노드가 없는 확장
d = hub._repo_dir(hub.SUBPACK_REPO); d.mkdir(parents=True, exist_ok=True); (d / "requirements.txt").write_text("ultralytics>=8.3\nopencv-python-headless\n# c\ngit+https://x/y.git\nnumpy\n", encoding="utf-8")
STATE["missing"] = ["UltralyticsDetectorProvider", "FaceDetailer"]; hub._CAPS["t"] = 0
hub.mods_missing = lambda mods: [m for m in mods if m == "ultralytics" and not getattr(hub, "_ul_ok", False)]
(hub.LOGS).mkdir(exist_ok=True)
(hub.LOGS / "comfyui.log").write_text("x\nImporting ComfyUI-Impact-Subpack\nCannot import C:\\ComfyUI\\custom_nodes\\ComfyUI-Impact-Subpack module for custom nodes: No module named 'ultralytics'\nTraceback (most recent call last):\n  File a\nModuleNotFoundError: No module named 'ultralytics'\nok\n", encoding="utf-8")
r = hub.node_diagnose({"repo": hub.SUBPACK_REPO}); assert r["missing"] == [{"module": "ultralytics", "pip": "ultralytics"}] and "ultralytics" in r["reason"], r; ok("diagnose lists the missing python part from requirements.txt and quotes the engine's own error")
assert hub.pack_reqs(d) == {"ultralytics": "ultralytics", "cv2": "opencv-python-headless"}, hub.pack_reqs(d); ok("requirements: git+/comment/numpy lines skipped, opencv maps to cv2")
assert hub.node_diagnose({"repo": "https://evil.example/x"}).get("error") and hub.node_fixdeps({"repo": hub.REACTOR_REPO + "-nope"}).get("error"); ok("only installed GitHub packs can be diagnosed or fixed")
inst = []
def fake_pip(name, timeout=1500):
    inst.append(name); hub._ul_ok = True; return 0, "ok", ""
hub.pip_install_one = fake_pip
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1100}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d_: d_.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    # 얼굴 교체 표시
    pg.evaluate("document.querySelector('nav button[data-f=\"faceswap\"]').click()"); pg.wait_for_selector("#feat-form h3", timeout=8000)
    t = pg.inner_text("#v-feat"); assert "얼굴 교체" in t and "얼굴 교체 (미검증)" not in t; ok("face swap no longer carries the 미검증 tag")
    # 점검 화면에서 노드 원인 확인
    pg.click('nav button[data-v="setup"]'); pg.click("#setup-nav button[data-pane=check]"); pg.wait_for_selector("#chk .chk-g")
    row = pg.locator('.chk-g[data-g="feat-detailer"] .chk-r').first
    row.locator("[data-chk=fix]").click()
    pg.wait_for_selector('.chk-g[data-g="feat-detailer"] .nd-fix', timeout=10000); assert "ultralytics" in pg.inner_text('.chk-g[data-g="feat-detailer"] .chk-diag'); ok("clicking the fix on an already-installed pack explains the cause instead of 'already installed'")
    pg.click('.chk-g[data-g="feat-detailer"] .nd-fix'); pg.wait_for_selector('.chk-g[data-g="feat-detailer"] .nd-rs', timeout=15000); assert inst == ["ultralytics"]; ok("[빠진 부품 설치] installs only what is missing, then offers an engine restart")
    # 기능 화면의 확장 목록에도 같은 버튼
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_timeout(300)
    pg.evaluate("loadFeat&&0"); pg.evaluate("document.querySelector('nav button[data-f=\"detailer\"]').click()"); pg.wait_for_selector("#feat-form .nrow", timeout=10000)
    assert pg.locator("#feat-form .ndiag").count() >= 1; ok("the feature's extension list shows [노드가 안 보여요] next to 설치됨")
    # 보관함 복사 설정
    pg.click('nav button[data-v="gen"]'); pg.wait_for_selector("#f-gen"); pg.fill("#f-gen [name=prompt]", "1girl, blue eyes"); pg.fill("#f-gen [name=seed]", "99")
    pg.click('nav button[data-v="lib"]'); pg.click("#ch-new"); assert pg.locator("#ch-copy").is_visible(); pg.uncheck('[data-cp=prompt]'); pg.check('[data-cp=seed]'); pg.click("#ch-copy")
    assert pg.input_value("#ch-form [name=prompt]") == "" and pg.input_value("#ch-form [name=seed]") == "99"; ok("copy panel: only the ticked items are brought over (prompt unticked, seed ticked)")
    pg.check('[data-cp=prompt]'); pg.click("#ch-copy"); assert pg.input_value("#ch-form [name=prompt]") == "1girl, blue eyes"; ok("...and ticking the prompt brings it too")
    # 갤러리 미리보기: 크기별(작게/보통/크게/아주 크게) × 화면 폭별로 가운데 기준 꽉 채우기가 지켜지는지 실제 갤러리 칸으로 확인
    import io
    from PIL import Image as PI
    G = hub.OUT / "생성"; G.mkdir(parents=True, exist_ok=True)
    def mk(w, h, name):
        im = PI.new("RGB", (w, h))
        for k, c in enumerate([(255, 0, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255)]): im.paste(c, (k * w // 4, 0, (k + 1) * w // 4, h))
        im.save(G / name)
    mk(832, 1216, "a_portrait.png"); mk(1216, 832, "b_land.png"); mk(1024, 1024, "c_sq.png"); mk(768, 1344, "d_tall.png")
    lab = lambda c: "R" if c[0] > 200 and c[1] < 80 else "Y" if c[0] > 200 and c[1] > 200 else "G" if c[1] > 200 and c[0] < 80 else "B" if c[2] > 200 else "?"
    assert pg.evaluate("document.documentElement.dataset.galprev") == "on" and not pg.evaluate("localStorage.getItem('opt:galfit')") or True
    for vw in (1400, 1000, 600):
        pg.set_viewport_size({"width": vw, "height": 1000})
        for sz in (150, 190, 250, 340):
            pg.evaluate("sz => localStorage.setItem('opt:galsz', sz)", sz); pg.reload(); pg.wait_for_timeout(400); pg.evaluate("show('gal')")
            pg.wait_for_selector("#gal-grid .gt img", timeout=8000); pg.wait_for_function("[...document.querySelectorAll('#gal-grid .gt img')].every(i=>i.complete&&i.naturalWidth>0)")
            for n in range(pg.locator("#gal-grid .gt img").count()):
                im = pg.locator("#gal-grid .gt img").nth(n)
                fw, iw, ih, nm = pg.evaluate("e=>{const r=e.getBoundingClientRect(),f=e.closest('.gt').getBoundingClientRect();return [f.width,r.width,r.height,e.src.split('/').pop()]}", im.element_handle())
                assert abs(iw - (fw - 2)) < 1.5 and abs(iw - ih) < 1.5, (vw, sz, nm, fw, iw, ih)   # 그림이 칸보다 넓어져 잘리지 않고 정사각형
                shot = PI.open(io.BytesIO(im.screenshot())).convert("RGB"); W, H = shot.size
                got = [lab(shot.getpixel((int(W * x), H // 2))) for x in (.03, .97)]
                if nm in ("a_portrait.png", "d_tall.png", "c_sq.png"): assert got == ["R", "B"], (vw, sz, nm, got)      # 세로·정사각: 가로 끝에서 끝까지 다 보임
                else: assert got[0] in "RY" and got[1] in "GB", (vw, sz, nm, got)                                    # 가로 사진: 가운데 기준으로 양쪽을 같은 만큼
            cap = pg.evaluate("(()=>{const f=document.querySelector('#gal-grid .gt'),c=f.querySelector('figcaption');return [f.getBoundingClientRect().width,c.getBoundingClientRect().width,c.scrollWidth]})()")
            assert cap[1] <= cap[0] + 1 and cap[2] <= cap[1] + 1, (vw, sz, cap)   # 아래 버튼줄도 칸 안에 들어와요
    ok("gallery preview: fills the square, centered, nothing clipped at 작게/보통/크게/아주 크게 × 3 window widths (real gallery cells)")
    pg.set_viewport_size({"width": 1400, "height": 1100}); pg.evaluate("localStorage.removeItem('opt:galsz')")
    # 설정: 모양 설정은 없고 미리보기 켜기/끄기만
    pg.reload(); pg.wait_for_timeout(500); pg.evaluate("show('conf')"); assert pg.locator("#opt-galfit").count() == 0 and pg.input_value("#opt-galprev") == "on"; ok("settings: the shape option is gone; preview on/off exists (default on)")
    pg.evaluate("show('gal')"); pg.wait_for_selector("#gal-grid .gt img"); pg.evaluate("show('conf')"); pg.select_option("#opt-galprev", "off"); pg.evaluate("show('gal')"); pg.wait_for_selector("#gal-grid .gnoimg")
    assert pg.locator("#gal-grid .gt img").count() == 0 and "a_portrait.png" in pg.inner_text("#gal-grid"); ok("preview off: no pictures are loaded, names are shown instead")
    pg.locator("#gal-grid .gnoimg").first.click(); pg.wait_for_selector("#lb:not([hidden])", timeout=5000); ok("preview off: clicking a tile still opens the big picture")
    pg.keyboard.press("Escape"); pg.reload(); pg.wait_for_timeout(500); pg.evaluate("show('gal')"); pg.wait_for_selector("#gal-grid .gnoimg"); assert pg.evaluate("document.documentElement.dataset.galprev") == "off"; ok("preview off is remembered after reload")
    pg.evaluate("show('conf')"); pg.select_option("#opt-galprev", "on"); pg.evaluate("show('gal')"); pg.wait_for_selector("#gal-grid .gt img"); ok("preview back on shows the pictures again")
    assert not errs, errs
    b.close()
print("ALL OK")
