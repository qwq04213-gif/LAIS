"""라운드 C UI: LoRA 호환 표시, 시드 위치, 같은 설정으로 생성, FLUX 편집 칸, Qwen 재생성 칸, 크게 보며 선택, 진행 단계 표시, 저장 공간 점검."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, struct
os.environ["TEST_HUB_PORT"] = "17871"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
SP = Path(os.environ["TMPDIR"]) / "shots9"; SP.mkdir(exist_ok=True)
def st(path, keys):
    meta = {k: {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]} for k in keys}; b = json.dumps(meta).encode()
    Path(path).write_bytes(struct.pack("<Q", len(b)) + b + b"\0\0")
st(M / "loras/flux_style.safetensors", ["lora_unet_single_blocks_0_linear1.lora_down.weight"])
st(M / "loras/xl_detail.safetensors", ["lora_te1_x.lora_down.weight", "lora_te2_x.lora_down.weight"])
DM = M / "diffusion_models"; (DM / "flux1-kontext-dev_fp8.safetensors").write_bytes(b"x")
(M / "text_encoders/qwen3vl_4b_fp8_scaled.safetensors").write_bytes(b"x"); (DM / "krea2_turbo_fp8_scaled.safetensors").write_bytes(b"x")
(M / "checkpoints/dupB.safetensors").write_bytes(b"D" * (60 << 20)); (M / "loras/dupA.safetensors").write_bytes(b"D" * (60 << 20))
(INPUT.parent / "temp").mkdir(exist_ok=True); (INPUT.parent / "temp/old.png").write_bytes(b"T" * 5000)
Image.new("RGB", (640, 480), (40, 90, 200)).save(SP / "in.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    # ── 시드 위치: 접힌 칸 밖에 보여야 해요
    pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(200)
    assert pg.locator("#f-gen input[name=seed]").is_visible() and pg.locator("#f-gen .seed-pick").is_visible()
    y_seed = pg.locator("#f-gen input[name=seed]").bounding_box()["y"]; y_prompt = pg.locator("#f-gen textarea[name=prompt]").bounding_box()["y"]; y_go = pg.locator("#f-gen button.go").bounding_box()["y"]
    assert y_go < y_prompt < y_seed < 900, (y_go, y_prompt, y_seed); ok("gen: seed is visible without opening any fold, below the prompt and not at the very top")
    pg.click("nav button[data-v=edit]"); pg.wait_for_timeout(200); assert pg.locator("#f-edit input[name=seed]").is_visible(); ok("edit: seed visible without opening a fold")
    # ── LoRA 호환 표시
    pg.click("nav button[data-v=gen]"); pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)")
    pg.select_option("#f-gen select[name=gengine]", "sdxl"); pg.wait_for_timeout(200)
    labs = pg.locator("#f-gen select[name=lora1] optgroup").evaluate_all("e=>e.map(x=>x.label)")
    assert any("SDXL" in l and "맞는" in l for l in labs) and any("다른 모델용" in l and "FLUX" in l for l in labs), labs
    pg.select_option("#f-gen select[name=lora1]", "flux_style.safetensors"); pg.wait_for_timeout(100)
    n = pg.inner_text("#f-gen .lora-row .lnote"); assert "FLUX" in n and "⚠" in n, n
    pg.select_option("#f-gen select[name=lora1]", "xl_detail.safetensors"); n = pg.inner_text("#f-gen .lora-row .lnote"); assert "✓" in n, n
    pg.select_option("#f-gen select[name=gengine]", "flux"); pg.wait_for_timeout(200)
    labs = pg.locator("#f-gen select[name=lora1] optgroup").evaluate_all("e=>e.map(x=>x.label)"); assert any("FLUX" in l and "맞는" in l for l in labs), labs
    pg.select_option("#f-gen select[name=lora1]", "flux_style.safetensors"); assert "✓" in pg.inner_text("#f-gen .lora-row .lnote")
    pg.select_option("#f-gen select[name=lora1]", "xl_detail.safetensors"); assert "⚠" in pg.inner_text("#f-gen .lora-row .lnote")
    ok("LoRA list is grouped by compatible model; the note under a LoRA says which model it is for and warns on a mismatch (follows the engine)")
    pg.select_option("#f-gen select[name=lora1]", ""); pg.select_option("#f-gen select[name=gengine]", "sdxl")
    # ── 같은 설정으로 생성
    pg.fill("#f-gen textarea[name=prompt]", "1girl, red jacket"); pg.fill("#f-gen input[name=seed]", "4242"); pg.fill("#f-gen input[name=steps]", "17")
    pg.click("#f-gen button.go"); pg.wait_for_selector("#v-gen .res figure img", timeout=30000)
    assert pg.locator("#v-gen .res figcaption button[data-to=regen]").count() >= 1
    pg.fill("#f-gen textarea[name=prompt]", "totally different"); pg.fill("#f-gen input[name=seed]", "1"); pg.fill("#f-gen input[name=steps]", "9")
    pg.evaluate("document.querySelectorAll('.res .more').forEach(d=>d.open=true)"); pg.click("#v-gen .res figcaption button[data-to=regen]"); pg.wait_for_timeout(600)
    g = lambda n: pg.input_value(f"#f-gen [name={n}]")
    assert "red jacket" in g("prompt") and g("seed") == "4242" and g("steps") == "17", (g("prompt"), g("seed"), g("steps")); ok("result button '같은 설정으로 생성' puts that image's prompt, seed and settings straight back into the generate form")
    # ── FLUX 계열 편집 칸
    pg.click("nav button[data-v=edit]"); pg.set_input_files("#v-edit .drop input[type=file]", str(SP / "in.png")); pg.wait_for_selector("#v-edit .work:not([hidden])"); pg.wait_for_timeout(300)
    pg.select_option("#f-edit select[name=engine]", "flux"); pg.wait_for_timeout(200)
    assert pg.locator("#f-edit select[name=fengine]").is_visible() and pg.locator("#f-edit select[name=fx_model]").is_visible() and not pg.locator("#f-edit select[name=ckpt]").is_visible() and not pg.locator("#f-edit input[name=q_steps]").is_visible()
    assert "flux1-krea-dev" in pg.locator("#f-edit select[name=fx_model]").inner_text() and pg.is_checked("#f-edit input[name=translate]")
    assert pg.locator("#f-edit .fe-c").is_hidden() and pg.locator("#f-edit .fe-g").is_visible(); pg.select_option("#f-edit select[name=fengine]", "krea2"); pg.wait_for_timeout(200)
    assert "krea2_turbo" in pg.locator("#f-edit select[name=fx_model]").inner_text() and pg.input_value("#f-edit input[name=fx_steps]") == "8" and pg.locator("#f-edit .fe-g").is_hidden(); pg.select_option("#f-edit select[name=fengine]", "flux")
    pg.fill("#f-edit textarea[name=prompt]", "red robe"); pg.click("#f-edit button.go"); pg.wait_for_timeout(300)
    assert "칠" in pg.inner_text("#v-edit .jobbar .st") or "칠" in pg.inner_text("#v-edit"); ok("edit: 'FLUX·Krea·Krea 2·Chroma' engine shows its own model fields (Krea 2 -> 8 steps), asks for a mask first")
    pg.select_option("#f-edit select[name=fx_model]", "flux1-kontext-dev_fp8.safetensors"); pg.click("#f-edit button.go"); pg.wait_for_selector("#v-edit .res figure img", timeout=30000)
    assert any("ReferenceLatent" == n["class_type"] for n in SUBMITTED[-1].values()); ok("edit: a Kontext model runs without a mask")
    # ── 크게 보며 선택
    small = pg.locator("#v-edit .stage").bounding_box()["width"]
    pg.click("#v-edit .bigsel"); pg.wait_for_timeout(300)
    bigw = pg.locator("#v-edit .stage").bounding_box()["width"]; assert not pg.locator("#f-edit").is_visible() and bigw > small * 1.2, (small, bigw)
    box = pg.locator("#v-edit canvas").bounding_box(); cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    pg.mouse.move(cx - 60, cy); pg.mouse.down(); pg.mouse.move(cx + 60, cy, steps=6); pg.mouse.up()
    with pg.expect_download() as dl: pg.click("#v-edit .am-cut")
    assert dl.value.suggested_filename == "cutout.png"; cut = Image.open(dl.value.path()); assert cut.mode == "RGBA" and cut.getpixel((5, 5))[3] == 0 and cut.getpixel((cut.width // 2, cut.height // 2))[3] > 200, (cut.mode, cut.getpixel((5, 5)))
    cnt = "(()=>{const c=document.querySelector('#v-edit canvas'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4)if(d[i]>40)n++;return n})()"
    assert pg.evaluate(cnt) > 500; pg.click("#v-edit .am-grow"); assert pg.evaluate(cnt) > 500
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200); assert pg.locator("#f-edit").is_visible() and pg.evaluate(cnt) > 500
    pg.click("#v-edit .bigsel"); pg.wait_for_timeout(200)
    w1 = pg.locator("#v-edit .stage").bounding_box()["width"]; pg.evaluate("(()=>{const z=document.querySelector('#v-edit .bigzoom');z.value=200;z.dispatchEvent(new Event('input',{bubbles:true}))})()"); pg.wait_for_timeout(150)
    w2 = pg.locator("#v-edit .stage").bounding_box()["width"]; assert 1.8 < w2 / w1 < 2.2, (w1, w2)
    area = pg.locator("#v-edit .work").bounding_box(); assert area["width"] > 1100 and area["height"] >= 900, area   # 화면 전체(설정 칸·메뉴 없이)를 써요
    pg.evaluate("(()=>{const z=document.querySelector('#v-edit .bigzoom');z.value=100;z.dispatchEvent(new Event('input',{bubbles:true}))})()")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
    ok(f"'크게 보며 선택': the image grows {small:.0f}px -> {bigw:.0f}px, painting + grow tool work there, Esc returns with the mask kept")
    n0 = pg.locator("#v-edit .res figure").count(); pg.click("#v-edit .bigsel"); pg.wait_for_timeout(200)
    pg.click("#v-edit .bigrun"); pg.wait_for_function(f"document.querySelectorAll('#v-edit .res figure').length>{n0}", timeout=30000); assert pg.locator("#f-edit").is_visible(); ok("'닫고 편집 실행' leaves the big view and runs the edit")
    # ── 겹쳐서 비교 (크게 보기 뒤에도)
    pg.click("#v-edit .rzoom") if pg.locator("#v-edit .rzoom").is_visible() else None
    pg.wait_for_timeout(300)
    if pg.locator("#lb").is_visible():
        assert pg.inner_text("#lb-cmp").strip() == "겹쳐서 비교" and pg.locator("#lb-cmp").is_visible(); pg.keyboard.press("c"); pg.wait_for_timeout(200)
        assert pg.locator("#lb-split").is_visible() and pg.locator("#lb-before").is_visible(); pg.keyboard.press("Escape"); ok("lightbox opened with [크게 보기] has [겹쳐서 비교] (and the C key) without toggling compare first")
    # ── 업스케일: Qwen 재생성
    pg.click("nav button[data-v=up]"); pg.select_option("#f-up select[name=mode]", "refine"); pg.select_option("#f-up select[name=rengine]", "qwen"); pg.wait_for_timeout(200)
    assert pg.locator("#f-up .re-q").is_visible() and not pg.locator("#f-up .re-fx").is_visible() and not pg.locator("#f-up .re-sd").first.is_visible() and pg.input_value("#f-up input[name=rdenoise]") == "0.45"
    pg.select_option("#f-up select[name=rengine]", "sdxl"); assert pg.input_value("#f-up input[name=rdenoise]") == "0.3" and not pg.locator("#f-up .re-q").is_visible(); ok("upscale detail regeneration: Qwen-Image-Edit option (its own hint/fast mode, denoise default 0.45; back to 0.3 for others)")
    # ── 아웃페인팅 모델 목록
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_selector("#feat-form select[name=ckpt]")
    labs = pg.locator("#feat-form select[name=ckpt] optgroup").evaluate_all("e=>e.map(x=>x.label)"); assert "SD·SDXL 체크포인트" in labs and any("FLUX" in l for l in labs) and "Krea 2" in labs and "Chroma" in labs, labs
    ok("outpaint model list groups SDXL checkpoints with FLUX / Krea / Krea 2 / Chroma models: " + " | ".join(labs))
    # ── 진행 단계 표시
    STATE["ws"] = True; STATE["load_delay"] = 2.2
    pg.click("nav button[data-v=gen]"); pg.fill("#f-gen textarea[name=prompt]", "x"); n0 = pg.locator("#v-gen .res figure").count(); pg.click("#f-gen button.go"); seen = set(); det = False
    for _ in range(60):
        t = pg.inner_text("#v-gen .jobbar .st"); has_val = pg.evaluate("(()=>{const e=document.querySelector('#v-gen .jobbar .pg');return !e.hidden&&e.getAttribute('value')===null})()")
        if "불러오는" in t and has_val: det = True
        seen.add("load" if "불러오는" in t else "other"); pg.wait_for_timeout(120)
        if pg.locator("#v-gen .res figure").count() > n0: break
    STATE["ws"] = False
    assert det, "no indeterminate bar while loading"; ok("progress: '모델 불러오는 중…' with a moving (indeterminate) bar while the model loads, then the normal generating bar")
    # ── 모델 목록 새로고침
    pg.click("nav button[data-v=gen]"); (M / "loras/brand_new.safetensors").write_bytes(b"x")
    assert "brand_new" not in pg.locator("#f-gen select[name=lora1]").inner_text(); pg.click("#refresh-models"); pg.wait_for_timeout(800)
    assert "brand_new" in pg.locator("#f-gen select[name=lora1]").inner_text() and "목록을 새로 읽었어요" in pg.inner_text("#toast"); ok("refresh button re-reads model lists immediately (new LoRA appears)")
    pg.click("#f-gen .refresh-models"); pg.wait_for_timeout(500)
    # ── 워크플로: UI 형식 JSON
    pg.click("nav button[data-v=wf]"); ui = {"nodes": [{"id": 1, "type": "KSampler", "mode": 0, "inputs": [], "widgets_values": [5, "fixed", 20, 7, "euler", "normal", 1]}], "links": []}
    pg.fill("#wf-json", json.dumps(ui)); pg.click("#wf-an"); pg.wait_for_selector("#wf-st", state="visible"); pg.wait_for_timeout(400); assert "읽었어요" in pg.inner_text("#wf-st"), pg.inner_text("#wf-st"); ok("workflow tab accepts a UI-format (Save) workflow")
    # ── 저장 공간 점검
    pg.click("nav button[data-v=setup]"); pg.click("#setup-nav button[data-pane=disk]"); pg.click("#disk-scan"); pg.wait_for_selector("#disk .disktb", timeout=20000)
    txt = pg.inner_text("#disk"); assert "디스크 여유" in txt and "dupA.safetensors" in txt and "dupB.safetensors" in txt and "임시 미리보기" in txt, txt[:600]
    pg.locator("#disk .cl[data-w=temp]").click(); pg.wait_for_timeout(800); assert not (INPUT.parent / "temp/old.png").exists(); ok("setup tab: disk check lists folders, duplicate files, biggest files; the 'temp previews' button frees the space")
    pg.locator("#disk .del[data-name='dupB.safetensors']").first.click(); [pg.wait_for_timeout(300) for _ in range(20) if (M / "checkpoints/dupB.safetensors").exists()]; assert not (M / "checkpoints/dupB.safetensors").exists(); ok("delete a duplicate from the disk panel")
    print("page errors:", errs); assert not errs
print("UI9 TESTS PASSED")
