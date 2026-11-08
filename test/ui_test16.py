"""LoRA 정보: 칸 아래 트리거 단어 + 모델 정보 목록."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, struct
os.environ["TEST_HUB_PORT"] = "17883"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
def st(path, keys, md=None):
    meta = {k: {"dtype": "F16", "shape": [4, 8], "data_offsets": [0, 2]} for k in keys}
    if md: meta["__metadata__"] = md
    b = json.dumps(meta).encode(); Path(path).write_bytes(struct.pack("<Q", len(b)) + b + b"\0\0")
L = M / "loras"
st(L / "kohya_style.safetensors", ["lora_unet_x.lora_down.weight", "lora_te2_y.lora_down.weight"], {"ss_output_name": "My Style", "ss_network_dim": "32", "ss_tag_frequency": json.dumps({"d": {"1girl": 100, "mystyle": 120}})})
st(L / "spec.safetensors", ["lora_unet_single_blocks_0_linear1.lora_down.weight"], {"modelspec.trigger_phrase": "tok, ohwx style"})
Image.new("RGB", (400, 400), (0, 200, 0)).save(L / "spec.preview.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.click("nav button[data-v=gen]"); pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)"); pg.wait_for_timeout(300)
    pg.fill("#f-gen textarea[name=prompt]", "1girl")
    pg.select_option("#f-gen select[name=lora1]", "kohya_style.safetensors"); pg.wait_for_selector("#f-gen .lora-row .ltr .lt-chip", timeout=5000)
    t = pg.inner_text("#f-gen .lora-row .ltr"); assert "자주 쓰인 태그" in t and "mystyle" in t, t
    pg.click("#f-gen .lora-row .lt-chip >> text=mystyle"); assert pg.input_value("#f-gen textarea[name=prompt]") == "1girl, mystyle"; ok("LoRA row shows its frequent tags; clicking one adds it to the prompt")
    pg.select_option("#f-gen select[name=lora1]", "spec.safetensors"); pg.wait_for_selector("#f-gen .lora-row .ltr:has-text('트리거 단어')", timeout=5000)
    assert pg.locator("#f-gen .lora-row .ltr .lt-chip").count() == 2 and pg.locator("#f-gen .lora-row .ltr").count() == 1; ok("trigger-phrase LoRA shows 'trigger words'; switching LoRA replaces the chips (no duplicates)")
    pg.select_option("#f-gen select[name=lora1]", ""); assert pg.locator("#f-gen .lora-row .ltr").count() == 0
    pg.click("nav button[data-v=setup]"); pg.wait_for_timeout(400); pg.click("#setup-nav button[data-pane=minfo]"); pg.wait_for_selector("#mi-list .mcard2")
    t = pg.inner_text("#mi-list"); assert "My Style" in t and "차원 32" in t and "ohwx style" in t and "FLUX" in t; assert pg.locator("#mi-list img.mimg").count() == 1; ok("model info list: title/dim/tags/trigger words/family badge, preview image only where a sidecar exists")
    pg.fill("#mi-q", "ohwx"); assert pg.locator("#mi-list .mcard2").count() == 1; pg.fill("#mi-q", "")
    pg.select_option("#mi-kind", "checkpoints"); pg.wait_for_timeout(600); assert "noobai_xl_v11" in pg.inner_text("#mi-list"); ok("search by trigger word; checkpoint list")
    pg.screenshot(path=os.environ["TMPDIR"] + "/mi.png")
    b.close()
assert not errs, errs; print("ALL OK")
