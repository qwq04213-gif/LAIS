"""2.3 화면: 업스케일 배율 입력·빠른 선택 버튼, 기능 모음의 모델 목록(얼굴·손 보정은 모든 종류, 참고 이미지는 Chroma 제외)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17931"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
(M / "diffusion_models" / "krea2_turbo_fp8_scaled.safetensors").write_bytes(b"x"); (M / "text_encoders" / "qwen3vl_4b_fp8_scaled.safetensors").write_bytes(b"x")
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="up"]'); pg.wait_for_selector("#f-up input[name=scale]")
    sc = pg.locator("#f-up input[name=scale]"); assert sc.get_attribute("type") == "number" and sc.input_value() == "4" and sc.get_attribute("min") == "0.1" and sc.get_attribute("max") == "8"; ok("upscale: the factor is a number box (default 4, 0.1–8)")
    labels = pg.locator("#f-up .scalechips button").all_inner_texts(); assert labels == ["0.5배", "1.5배", "2배", "3배", "4배"], labels
    pg.click('#f-up .scalechips button[data-sc="1.5"]'); assert sc.input_value() == "1.5"; pg.click('#f-up .scalechips button[data-sc="0.5"]'); assert sc.input_value() == "0.5"; ok("quick buttons fill the box (0.5배 … 4배)")
    sc.fill("2.75"); assert sc.input_value() == "2.75"; assert "줄여요" in pg.inner_text("#f-up"); ok("any value can be typed; the form explains that below 1 shrinks")
    # 일괄 처리 화면
    pg.click('nav button[data-v="batch"]'); pg.wait_for_selector("#v-batch")
    pg.check('#v-batch input[name=op][value=upscale]'); bs = pg.locator('#v-batch .bt-opts[data-op=upscale] input[name=scale]'); assert bs.is_visible() and bs.input_value() == "4"
    pg.click('#v-batch .bt-opts[data-op=upscale] .scalechips button[data-sc="2"]'); assert bs.input_value() == "2"; assert "업스케일 · 줄이기" in pg.inner_text("#v-batch"); ok("batch screen: same factor box and buttons")
    # 기능 모음
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_selector("#feat-form h3")
    def groups(fid):
        pg.evaluate(f"document.querySelector('nav button[data-f=\"{fid}\"]').click()"); pg.wait_for_function(f"document.querySelector('#feat-form').dataset.f==='{fid}' && document.querySelector('#feat-form h3')"); pg.wait_for_selector("#feat-form select[name=ckpt]")
        return pg.eval_on_selector_all("#feat-form select[name=ckpt] optgroup", "e=>e.map(x=>x.label)")
    g = groups("detailer"); assert g == ["SD·SDXL 체크포인트", "FLUX·Krea(FLUX.1)", "Krea 2", "Chroma"], g; ok("face/hand fix: model list offers SDXL, FLUX.1, Krea 2 and Chroma")
    assert "FLUX.1" in pg.text_content("#feat-form")
    g = groups("ipadapter"); assert g == ["SD·SDXL 체크포인트", "FLUX·Krea(FLUX.1)", "Krea 2"], g; ok("reference image: model list offers SDXL, FLUX.1 and Krea 2 (no Chroma)")
    t = pg.inner_text("#feat-form"); assert "Redux" in t and "Kontext" in t and "스타일 참조" in t; ok("reference image form explains which method each family uses")
    assert pg.locator("#feat-form input[name=kweight]").count() == 1; ok("Krea 2 style strength box exists (advanced)")
    assert not errs, errs
    b.close()
print("ALL OK")
