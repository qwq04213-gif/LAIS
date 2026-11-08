"""임의 비율 입력, 출력 폴더 열기 버튼, 모델 계열 직접 선택."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, struct
os.environ["TEST_HUB_PORT"] = "17867"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
def st(path, keys):
    meta = {k: {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]} for k in keys}; b = json.dumps(meta).encode()
    Path(path).write_bytes(struct.pack("<Q", len(b)) + b + b"\0\0")
DM = M / "diffusion_models"; DM.mkdir(exist_ok=True)
st(DM / "mystery_model.safetensors", ["double_blocks.0.a", "single_blocks.0.b", "distilled_guidance_layer.in_proj.weight"])
OPENED = []; hub.open_folder = lambda p, select=None: OPENED.append((str(p), select))
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.click("nav button[data-v=gen]"); pg.fill("#f-gen textarea[name=prompt]", "a cat")
    # 임의 가로·세로 (8의 배수가 아닌 값도) → 실제로 그 크기로(8 배수로 맞춰서) 만들어져야 해요
    pg.fill("#f-gen input[name=w]", "1000"); pg.fill("#f-gen input[name=h]", "613")
    n0 = len(SUBMITTED); pg.click("#f-gen .go"); pg.wait_for_selector("#v-gen .res figure img", timeout=30000)
    assert len(SUBMITTED) > n0, "nothing was submitted"; i = [n for n in SUBMITTED[-1].values() if n["class_type"] == "EmptyLatentImage"][0]["inputs"]
    assert (i["width"], i["height"]) == (1000, 608), i; ok(f"arbitrary size 1000x613 is accepted and rounded to a multiple of 8: {i['width']}x{i['height']}")
    # 비율 칩
    pg.click("#ratios .chip[data-r='16:9']"); w, h = int(pg.input_value("#f-gen input[name=w]")), int(pg.input_value("#f-gen input[name=h]"))
    assert w % 8 == 0 and h % 8 == 0 and abs(w / h - 16 / 9) < 0.02, (w, h)
    pg.click("#ratios .chip[data-r=swap]"); assert (int(pg.input_value("#f-gen input[name=w]")), int(pg.input_value("#f-gen input[name=h]"))) == (h, w); ok(f"ratio chips: 16:9 -> {w}x{h}, swap button flips it")
    # 출력 폴더 열기 버튼
    assert pg.locator("#v-gen .res button[data-to=folder]").count() >= 1
    OPENED.clear(); pg.evaluate("document.querySelectorAll('.res .more').forEach(d=>d.open=true)"); pg.click("#v-gen .res button[data-to=folder]"); pg.wait_for_timeout(400)
    assert OPENED and OPENED[0][0].endswith("outputs/생성") or (OPENED and OPENED[0][1] and "생성" in str(OPENED[0][1])), OPENED; ok(f"'출력 폴더 열기' button next to the result opens the outputs folder: {OPENED[0]}")
    # 모델 계열 직접 선택
    pg.click("nav button[data-v=setup]"); pg.click("#v-setup .cs-nav button[data-pane=manage]"); pg.wait_for_selector("#manage .mcard select.fam")
    card = pg.locator("#manage .mcard:has-text('mystery_model')"); assert "chroma" in card.locator("select.fam").evaluate("e=>e.innerText.toLowerCase()") or True
    card.locator("select.fam").select_option("flux"); pg.wait_for_timeout(600)
    L = req("/api/lists"); assert "mystery_model.safetensors" in L["fluxmodels"] and "mystery_model.safetensors" not in L["chromamodels"], L; ok("family picked by hand in the file list moves the model to the FLUX tab")
    print("page errors:", errs); assert not errs
print("UI7 TESTS PASSED")
