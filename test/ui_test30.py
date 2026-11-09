"""이미지 생성 화면: 모델 종류 목록, SD3.5 모델 목록·기본값(HiDream·Lumina 는 3.17 에서 삭제)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17896"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
def mk(d, n): (M / d).mkdir(parents=True, exist_ok=True); (M / d / n).write_bytes(b"x")
for d, n in (("diffusion_models", "hidream_i1_full_fp8.safetensors"), ("diffusion_models", "hidream_i1_fast_fp8.safetensors"), ("text_encoders", "clip_l_hidream.safetensors"),
             ("text_encoders", "clip_g_hidream.safetensors"), ("text_encoders", "llama_3.1_8b_instruct_fp8_scaled.safetensors"),
             ("diffusion_models", "lumina_2_model_bf16.safetensors"), ("checkpoints", "sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors")): mk(d, n)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="gen"]')
    opts = pg.eval_on_selector_all("#f-gen select[name=gengine] option", "e=>e.map(x=>x.value)"); assert opts == ["sdxl", "flux", "chroma", "krea2", "sd35", "qwenimg", "moss", "zimage", "flux3k"], opts; ok("model kinds (HiDream·Lumina removed in 3.17)")
    pg.select_option("#f-gen select[name=gengine]", "sd35"); pg.wait_for_timeout(300)
    assert pg.input_value("#f-gen input[name=fx_steps]") == "28" and pg.locator("#f-gen select[name=fx_model] option").count() == 1; ok("SD3.5 lists its checkpoint and defaults 28 steps")
    pg.select_option("#f-gen select[name=gengine]", "sdxl"); pg.wait_for_timeout(300); assert pg.is_visible("#f-gen [data-blk=sd-main]"); ok("switching back to SDXL restores its form")
    print("page errors:", errs); assert not errs
print("ALL OK")
