"""2.8 화면: 추천 모델 분류·삭제 버튼, 효과음 모드, 영상 모델(S2V 소리 칸), 사진→3D 메뉴, 메모리·GPU 설정."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17952"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
for f in ("diffusion_models/wan2.2_ti2v_5B_fp16.safetensors", "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "vae/wan2.2_vae.safetensors"):
    (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=setup]"); pg.wait_for_selector("#cat-vid .item")
    for i, t in (("#cat-vid", "Wan 2.2 영상 5B"), ("#cat-aud", "Stable Audio"), ("#cat-3d", "TRELLIS.2"), ("#cat-img", "Qwen-Image")): assert t in pg.inner_text(i), (i, pg.inner_text(i)[:200])
    assert "Wan 2.2 영상 5B" not in pg.inner_text("#cat-img"); pg.wait_for_selector("#cat-voice .item"); assert "XTTS" in pg.inner_text("#cat-voice"); vw = pg.eval_on_selector("#cat-voice .item span", "e=>e.getBoundingClientRect().width"); assert vw > 300, vw
    row = pg.locator("#cat-vid .item", has_text="Wan 2.2 영상 5B"); assert row.locator(".cat-del").count() == 1; ok("recommended models split into image/video/audio/voice/3D; installed row has a delete button")
    row.locator(".cat-del").click(); pg.wait_for_function("![...document.querySelectorAll('#cat-vid .item')].find(e=>e.innerText.includes('Wan 2.2 영상 5B')).innerText.includes('설치됨')")
    assert not (M / "diffusion_models/wan2.2_ti2v_5B_fp16.safetensors").exists(); ok("delete removes the installed model files")
    pg.click("nav button[data-v=music]"); pg.select_option("#f-music select[name=mengine]", "sfx"); pg.wait_for_timeout(200)
    assert pg.is_visible("#f-music input[name=sfx_seconds]") and pg.is_hidden("#mu-lyr") and pg.inner_text("#f-music .go") == "효과음 만들기"
    pg.select_option("#f-music select[name=mengine]", "music"); assert pg.is_visible("#mu-lyr"); ok("music screen switches to sound-effect mode")
    pg.click("nav button[data-v=vid]"); pg.select_option("#f-vid select[name=wan_ver]", "s2v"); pg.wait_for_timeout(200)
    assert pg.is_visible("#vid-audio-row") and pg.is_visible("#vid-more-note"); pg.fill("#f-vid textarea[name=prompt]", "talking"); pg.click("#f-vid .go"); pg.wait_for_timeout(300)
    assert "사진" in pg.inner_text("#v-vid"); pg.select_option("#f-vid select[name=wan_ver]", "ltx"); assert pg.is_hidden("#vid-audio-row"); ok("video models: S2V shows voice upload and requires a photo; LTX hides it")
    pg.evaluate("document.querySelector('nav button[data-f=img3d]').click()"); pg.wait_for_timeout(500); assert "3D" in pg.inner_text("#v-feat"); ok("photo → 3D feature in the sidebar")
    pg.click("nav button[data-v=conf]"); pg.wait_for_timeout(300); pg.click("#cs-nav button[data-pane=gen]"); pg.wait_for_selector("#pf-vram")
    pg.select_option("#pf-vram", "low"); pg.wait_for_timeout(400); assert hub.prefs()["vram_mode"] == "low" and "다시 시작" in pg.inner_text("#pf-msg")
    pg.select_option("#pf-chatgpu", "cpu"); pg.wait_for_timeout(400); assert hub.prefs()["chat_gpu"] == "cpu"; ok("memory/GPU settings saved")
    assert not errs, errs
print("ALL OK")
