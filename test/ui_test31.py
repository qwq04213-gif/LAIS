"""Krea 2 컨트롤 LoRA 화면: ControlNet 칸이 컨트롤 LoRA 목록으로 바뀌고, 확장이 없으면 설치 버튼이 나온다."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17897"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
for d, n in (("diffusion_models", "krea2_turbo_fp8_scaled.safetensors"), ("text_encoders", "qwen3vl_4b_fp8_scaled.safetensors"), ("vae", "qwen_image_vae.safetensors"), ("loras", "krea2-depth-control-lora.safetensors")):
    (M / d).mkdir(parents=True, exist_ok=True); (M / d / n).write_bytes(b"x")
STATE["missing"].add("Krea2ControlLoRALoader"); hub.caps(True)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1100}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="gen"]')
    pg.select_option("#f-gen select[name=gengine]", "chroma"); assert not pg.locator("#f-gen details:has(summary:has-text('ControlNet'))").is_visible(); ok("Chroma: no ControlNet fold")
    pg.select_option("#f-gen select[name=gengine]", "krea2"); pg.wait_for_timeout(500)
    fold = pg.locator("#f-gen details:has(summary:has-text('ControlNet'))"); assert fold.is_visible(); pg.evaluate("document.querySelector('#f-gen select[name=cn_model]').closest('details').open=true")
    opts = pg.eval_on_selector_all("#f-gen select[name=cn_model] option", "e=>e.map(x=>x.value)"); assert opts == ["", "krea2-depth-control-lora.safetensors"], opts
    assert pg.input_value("#f-gen input[name=cn_strength]") == "1"; ok("Krea 2: fold shows control LoRAs only, strength defaults to 1")
    pg.wait_for_selector("#f-gen .cn-node [data-a=inst]", state="attached", timeout=8000); assert pg.is_visible("#f-gen .cn-node [data-a=inst]"); assert "Krea2" in pg.inner_text("#f-gen .cn-node"); ok("missing extension → install button with the reviewed pack")
    assert pg.is_hidden("#f-gen input[name=cn_start]"); ok("start/end percent boxes hidden (not used by control LoRAs)")
    pg.screenshot(path="/tmp/tt/k2cn.png")
    pg.select_option("#f-gen select[name=gengine]", "flux"); pg.wait_for_timeout(300)
    assert pg.input_value("#f-gen input[name=cn_strength]") == "0.7" and "krea2-depth-control-lora.safetensors" not in pg.eval_on_selector_all("#f-gen select[name=cn_model] option", "e=>e.map(x=>x.value)"); ok("back to FLUX: ControlNet models and 0.7 strength restored")
    print("page errors:", errs); assert not errs
print("ALL OK")
