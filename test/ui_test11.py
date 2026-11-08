"""영상 만들기 화면."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17874"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
SP = Path(os.environ["TMPDIR"]) / "shots11"; SP.mkdir(exist_ok=True)
Image.new("RGB", (640, 480), (40, 90, 200)).save(SP / "in.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.click("nav button[data-v=vid]"); pg.wait_for_timeout(400)
    assert pg.locator("#w-vid").is_visible(); ok("no Wan files -> warning with link to setup")
    pg.click("#w-vid a"); assert pg.locator("#v-setup.on").count() == 1
    for d, f in (("diffusion_models", "wan2.2_ti2v_5B_fp16.safetensors"), ("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"), ("vae", "wan2.2_vae.safetensors")): (M / d / f).write_bytes(b"x")
    pg.click("#refresh-models"); pg.wait_for_timeout(800); pg.click("nav button[data-v=vid]"); pg.wait_for_timeout(600)
    assert pg.locator("#w-vid").is_hidden(); ok("after files exist (refresh) the warning disappears")
    pg.click("#f-vid button.go"); pg.wait_for_timeout(200); assert "장면 설명" in pg.inner_text("#v-vid .jobbar"); ok("empty prompt -> asks for a description")
    pg.fill("#f-vid textarea[name=prompt]", "a cat walking"); pg.select_option("#f-vid select[name=sec]", "2")
    pg.set_input_files("#vid-file", str(SP / "in.png")); pg.wait_for_selector("#vid-thumb:not([hidden])"); assert pg.locator("#vid-ratio-row").is_visible()
    n0 = len(SUBMITTED); pg.click("#f-vid button.go"); pg.wait_for_selector("#v-vid .res video", timeout=30000)
    g = SUBMITTED[n0]; L = [n["inputs"] for n in g.values() if n["class_type"] == "Wan22ImageToVideoLatent"][0]
    assert "start_image" in L and L["length"] == 49 and L["width"] > L["height"], L
    src = pg.get_attribute("#v-vid .res video", "src"); assert src.endswith(".mp4"); ok("form -> job: start image + 2s sent, result shows a <video> player with save button")
    assert pg.locator("#v-vid .res figcaption a[download]").count() == 1
    pg.screenshot(path=os.environ["TMPDIR"] + "/vid.png")
    # 설정 기억
    pg.reload(); pg.wait_for_timeout(500); pg.click("nav button[data-v=vid]"); assert pg.input_value("#f-vid select[name=sec]") == "2" and "cat" in pg.input_value("#f-vid textarea[name=prompt]"); ok("video form remembers its settings after reload")
    # 이미지→영상 버튼
    pg.click("nav button[data-v=gen]"); pg.fill("#f-gen textarea[name=prompt]", "1girl"); pg.click("#f-gen button.go"); pg.wait_for_selector("#v-gen .res figure img", timeout=30000)
    pg.evaluate("document.querySelectorAll('.res .more').forEach(d=>d.open=true)"); pg.click("#v-gen .res figcaption button[data-to=vid]"); pg.wait_for_timeout(600)
    assert pg.locator("#v-vid.on").count() == 1 and pg.locator("#vid-thumb").is_visible(); ok("'영상으로' on an image result sends it to the video tab as the start image")
    b.close()
assert not errs, errs; print("ALL OK")
