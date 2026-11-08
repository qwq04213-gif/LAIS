"""기능 모음 / 길잡이 / 시드 버튼 / 진행 바 위치 / VAE·텍스트 인코더 선택."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17866"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
SP = Path(os.environ["TMPDIR"]) / "shots6"; SP.mkdir(exist_ok=True)
Image.new("RGB", (640, 480), (40, 90, 200)).save(SP / "in.png")
(M / "vae").mkdir(exist_ok=True); (M / "text_encoders").mkdir(exist_ok=True); (M / "vae/zz_custom_vae.safetensors").write_bytes(b"x"); (M / "text_encoders/zz_enc.safetensors").write_bytes(b"x")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.wait_for_function("document.querySelectorAll('select[name=vae] option').length>1")
    assert "zz_custom_vae.safetensors" in pg.locator("#f-gen select[name=vae]").inner_text() and "zz_custom_vae" in pg.locator("#f-gen select[name=fx_vae]").inner_text() and "zz_enc" in pg.locator("#f-gen select[name=fx_t5]").inner_text()
    ok("VAE / text-encoder pickers list the files that are in the folders")
    # 시드 버튼
    pg.click("nav button[data-v=gen]"); pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)")
    pg.click("#f-gen .seed-pick"); v = int(pg.input_value("#f-gen input[name=seed]")); assert v >= 0, v
    pg.click("#f-gen .seed-rand"); assert pg.input_value("#f-gen input[name=seed]") == "-1"; ok("seed buttons: 🎲 picks a number, -1 resets to random")
    # 진행 바는 이미지 위
    for view in ("edit", "gen", "up"):
        pg.click(f"nav button[data-v={view}]"); pg.wait_for_timeout(150)
        jy = pg.locator(f"#v-{view} .jobbar").evaluate("e=>e.getBoundingClientRect().top"); dy = pg.locator(f"#v-{view} .col > :not(.jobbar)").first.evaluate("e=>e.getBoundingClientRect().top")
        assert jy <= dy, (view, jy, dy)
    ok("progress bar sits above the image area in edit / gen / upscale")
    # 길잡이
    pg.click("nav button[data-v=guide]"); assert pg.locator("#v-guide .gloss dt").count() >= 10 and pg.locator("#v-guide .cov tbody tr").count() >= 10; ok("guide: glossary + coverage table")
    # 기능 모음
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_selector("#feat-form h3"); assert pg.locator("nav button[data-f]").count() == 15
    pg.click("#feat-form .go"); pg.wait_for_function("document.querySelector('#v-feat .jobbar .st').textContent.includes('이미지를 올려')"); ok("outpaint without an image: friendly message")
    pg.set_input_files("#feat-form .mini[data-img=image] input[type=file]", str(SP / "in.png")); pg.fill("#feat-form textarea[name=prompt]", "forest, trees")
    pg.click("#feat-form .go"); pg.wait_for_selector("#v-feat .res figure img", timeout=30000)
    assert pg.evaluate("document.querySelector('#v-feat .res figure img').src").count("%EA%B8%B0%EB%8A%A5") == 1; ok("outpaint from the UI: result appears and is stored in the 기능 folder")
    pg.evaluate("document.querySelector('nav button[data-f=\"regional\"]').click()"); pg.click("#feat-form .go"); pg.wait_for_function("document.querySelector('#v-feat .jobbar .st').textContent.includes('칸')"); ok("regional: empty region text -> message")
    pg.select_option("#feat-form select[name=layout]", "lr"); pg.fill("#feat-form textarea[name=r1]", "a girl"); pg.fill("#feat-form textarea[name=r2]", "a cat"); pg.click("#feat-form .go")
    pg.wait_for_function("document.querySelectorAll('#v-feat .res figure').length>=2", timeout=30000); ok("regional prompts run from the UI")
    pg.evaluate("document.querySelector('nav button[data-f=\"compare\"]').click()"); pg.fill("#feat-form textarea[name=prompt]", "1girl"); pg.fill("#feat-form input[name=values]", "3,6"); pg.click("#feat-form .go")
    pg.wait_for_function("document.querySelectorAll('#v-feat .res figure').length>=3", timeout=40000); pg.screenshot(path=str(SP / "feat.png")); ok("compare grid runs from the UI")
    print("page errors:", errs); assert not errs
print("UI6 TESTS PASSED")
