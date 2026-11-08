"""FLUX 선택 시 ControlNet 칸: 보이기, 모델 목록 걸러내기, 없을 때 안내."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17900"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
(M / "controlnet").mkdir(exist_ok=True)
(M / "controlnet" / "xinsir_sdxl.safetensors").write_bytes(b"x")
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 1000}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="gen"]'); cn = pg.locator("#f-gen details", has_text="ControlNet (구도·포즈 고정)").first
    assert cn.is_visible(); cn.locator("summary").click(); opts = lambda: pg.evaluate("[...document.querySelectorAll('#f-gen select[name=cn_model] option')].filter(o=>!o.disabled).map(o=>o.value)")
    assert opts() == ["", "union_promax.safetensors", "xinsir_sdxl.safetensors"], opts(); ok("SDXL mode: ControlNet visible, only non-FLUX models")
    pg.select_option("#f-gen select[name=gengine]", "flux"); assert cn.is_visible(), "cn"; cn.evaluate("d=>d.open=true"); assert opts() == [""], opts(); assert pg.locator("#f-gen .cn-fam").is_visible(); assert "FLUX ControlNet Union" in pg.inner_text("#f-gen .cn-fam"), pg.inner_text("#f-gen .cn-fam"); ok("FLUX mode: SDXL model hidden, install hint shown")
    (M / "controlnet" / "FLUX.1-dev-ControlNet-Union-Pro-2.0.safetensors").write_bytes(b"x")
    pg.reload(); pg.wait_for_timeout(600); pg.click('nav button[data-v="gen"]'); cn.evaluate("d=>d.open=true"); assert pg.evaluate("document.querySelector('#f-gen select[name=gengine]').value") == "flux"
    assert opts() == ["", "FLUX.1-dev-ControlNet-Union-Pro-2.0.safetensors"] and pg.locator("#f-gen .cn-fam").is_hidden(); ok("with the FLUX model installed: only it is listed, hint hidden")
    pg.select_option("#f-gen select[name=gengine]", "chroma"); cn.wait_for(state="hidden"); ok("Chroma: ControlNet box hidden")
    pg.select_option("#f-gen select[name=gengine]", "sdxl"); assert opts() == ["", "union_promax.safetensors", "xinsir_sdxl.safetensors"]; ok("back to SDXL: lists restored")
    b.close()
assert not errs, errs
print("ALL OK")
