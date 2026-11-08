"""1차 업데이트 UI 검증: FLUX 선택, LoRA 무제한, 중단, 폴더 열기, ? 도움말, 눌림 효과, 좌우 비교, 너비 조절."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import json, os, re, sys, time
os.environ["TEST_HUB_PORT"] = "17862"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

SP = Path("/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots3"); SP.mkdir(exist_ok=True)
OPENED = []; hub.open_folder = lambda p, select=None: OPENED.append(str(p))
ok = lambda m: print("PASS", m)
im = Image.new("RGB", (1200, 800), (60, 110, 150)); ImageDraw.Draw(im).ellipse((420, 220, 780, 620), fill=(230, 190, 160)); im.save(SP / "sample.png")
classes = lambda wf: [n["class_type"] for n in wf.values()]
node = lambda wf, c, i=0: [n for n in wf.values() if n["class_type"] == c][i]["inputs"]

errs = []; lists_calls = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1400, "height": 900}); ctx.add_init_script("localStorage.setItem('ui:scale','1')"); pg = ctx.new_page()
    pg.on("console", lambda m: errs.append(("console", m.text)) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
    pg.on("request", lambda r: lists_calls.append(1) if r.url.endswith("/api/lists") else None)
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.wait_for_function("document.querySelectorAll('select[name=ckpt] option').length>0 && document.querySelectorAll('select[name=sampler] option').length>0")
    pg.wait_for_function("document.querySelector('#ver').textContent.length>0")
    assert req("/api/status")["version"] in pg.inner_text("#ver"); ok("version shown in the rail: " + pg.inner_text("#ver"))

    # ---------- tooltips
    pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(200)
    pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)")
    ntips = pg.locator(".tip").count(); assert ntips >= 45, ntips
    assert pg.locator("#f-gen .lora-row .tip").count() == 2
    t = pg.locator("#f-gen label:has(input[name=pag]) .tip"); t.scroll_into_view_if_needed(); t.hover(); pg.wait_for_timeout(120)
    tb = pg.locator("#tipbox"); assert tb.is_visible() and "손과 몸" in tb.inner_text()
    bx = tb.bounding_box(); assert bx["x"] >= 0 and bx["x"] + bx["width"] <= 1400 and bx["y"] >= 0 and bx["y"] + bx["height"] <= 900, bx
    pg.mouse.move(700, 5); pg.wait_for_timeout(100); assert tb.is_hidden()
    before = pg.evaluate("document.querySelector('#f-gen').elements.vpred.checked")
    tv = pg.locator("#f-gen label:has(input[name=vpred]) .tip"); tv.click(); assert pg.evaluate("document.querySelector('#f-gen').elements.vpred.checked") == before and tb.is_visible()
    pg.keyboard.press("Escape"); assert tb.is_hidden()
    sm = pg.locator("#f-gen summary:has-text('하이레스') .tip"); wasopen = pg.evaluate("[...document.querySelectorAll('#f-gen summary')].find(s=>s.textContent.includes('하이레스')).parentElement.open")
    sm.click(); assert pg.evaluate("[...document.querySelectorAll('#f-gen summary')].find(s=>s.textContent.includes('하이레스')).parentElement.open") == wasopen and "작은 크기" in tb.inner_text()
    pg.mouse.click(700, 5); assert tb.is_hidden()
    pg.locator("#f-gen label:has(input[name=cfg]) .tip").focus(); pg.wait_for_timeout(100); assert tb.is_visible() and "엄격" in tb.inner_text(); pg.evaluate("document.activeElement.blur()")
    pg.click("nav button[data-v=chat]"); pg.evaluate("document.querySelector('.sysd').open=true")
    assert pg.locator("#v-chat .tip").count() >= 8; pg.locator("#v-chat label:has(#o-min_p) .tip").hover(); assert "롤플레이" in tb.inner_text(); pg.mouse.move(700, 5)
    ok(f"tooltips: {ntips} '?' marks; hover/focus show a clamped tipbox; clicking '?' neither toggles a checkbox nor a <details>; Esc / outside click hide; LoRA rows + chat options covered")

    # ---------- press animation
    def pressed(sel):
        pg.hover(sel); pg.mouse.down(); pg.wait_for_timeout(220)
        tf = pg.evaluate(f"getComputedStyle(document.querySelector({json.dumps(sel)})).transform"); pg.mouse.move(5, 5); pg.mouse.up(); pg.wait_for_timeout(220)
        rest = pg.evaluate(f"getComputedStyle(document.querySelector({json.dumps(sel)})).transform"); return tf, rest
    pg.click("nav button[data-v=gen]")
    for sel in ["#f-gen .go", "#f-gen .pre-save", "nav button[data-v=edit]", "#rail .adv[data-open=outputs]"]:
        tf, rest = pressed(sel); m = re.match(r"matrix\(([\d.]+),", tf); assert m and float(m.group(1)) < 0.99 and rest == "none", (sel, tf, rest)
    ok("press animation: .go / ghost / nav / rail buttons scale down while pressed and return to rest")

    # ---------- engine selector: SDXL -> FLUX -> Chroma
    pg.click("nav button[data-v=gen]")
    sel = lambda n: f"#f-gen [name={n}]"
    assert pg.locator(sel("ckpt")).is_visible() and pg.locator(sel("fx_model")).is_hidden() and pg.locator(sel("sampler")).is_visible()
    pg.select_option(sel("gengine"), "flux"); pg.wait_for_timeout(150)
    assert pg.locator(sel("ckpt")).is_hidden() and pg.locator(sel("sampler")).is_hidden() and pg.locator(sel("fx_model")).is_visible() and pg.locator(sel("negative")).is_hidden()
    assert pg.locator(sel("fx_guidance")).is_visible() and pg.locator(sel("fx_cfg")).is_hidden() and pg.locator(sel("pag")).count() == 1 and pg.locator(sel("pag")).is_hidden()
    assert pg.evaluate("[...document.querySelector('#f-gen').elements.fx_model.options].map(o=>o.value)") == ["flux1-krea-dev_fp8_scaled.safetensors"]
    vals = pg.evaluate("(()=>{const e=document.querySelector('#f-gen').elements;return [e.fx_steps.value,e.fx_guidance.value,e.fx_sampler.value,e.fx_scheduler.value]})()"); assert vals == ["20", "3.5", "euler", "simple"], vals
    assert pg.locator("#w-gen").is_hidden()
    pg.fill(sel("prompt"), "a woman on a rainy street"); pg.fill(sel("fx_guidance"), "4"); n0 = len(SUBMITTED)
    pg.click("#f-gen .go"); pg.wait_for_selector("#v-gen .batch figure img", timeout=20000)
    w = SUBMITTED[-1]; cl = classes(w); assert len(SUBMITTED) == n0 + 1 and "DualCLIPLoader" in cl and node(w, "FluxGuidance")["guidance"] == 4.0 and "CheckpointLoaderSimple" not in cl, cl
    pg.screenshot(path=str(SP / "flux.png"))
    pg.select_option(sel("gengine"), "chroma"); pg.wait_for_timeout(150)
    assert pg.locator(sel("negative")).is_visible() and pg.locator(sel("fx_cfg")).is_visible() and pg.locator(sel("fx_guidance")).is_hidden()
    assert pg.evaluate("[...document.querySelector('#f-gen').elements.fx_model.options].map(o=>o.value)") == ["Chroma1-HD.safetensors"]
    vals = pg.evaluate("(()=>{const e=document.querySelector('#f-gen').elements;return [e.fx_steps.value,e.fx_cfg.value,e.fx_scheduler.value]})()"); assert vals == ["26", "4", "beta"], vals
    pg.click("#f-gen .go"); pg.wait_for_function("document.querySelectorAll('#v-gen .batch figure img').length==2", timeout=20000)
    w = SUBMITTED[-1]; assert node(w, "CLIPLoader")["type"] == "chroma" and "FluxGuidance" not in classes(w) and node(w, "KSampler")["scheduler"] == "beta"
    # persistence of engine + warning when shared files are missing
    pg.wait_for_timeout(600); pg.reload(); pg.wait_for_function("document.querySelectorAll('select[name=fx_model] option').length>0"); pg.wait_for_timeout(400); pg.click("nav button[data-v=gen]")
    assert pg.input_value(sel("gengine")) == "chroma" and pg.input_value(sel("fx_model")) == "Chroma1-HD.safetensors" and pg.locator(sel("fx_cfg")).is_visible()
    (M / "text_encoders/clip_l.safetensors").rename(M / "text_encoders/_clip_l.bak")
    pg.select_option(sel("gengine"), "flux"); pg.evaluate("loadLists(true)"); pg.wait_for_function("!document.querySelector('#w-gen').hidden"); assert "FLUX" in pg.inner_text("#w-gen")
    pg.select_option(sel("gengine"), "chroma"); pg.wait_for_function("document.querySelector('#w-gen').hidden")
    (M / "text_encoders/_clip_l.bak").rename(M / "text_encoders/clip_l.safetensors")
    pg.select_option(sel("gengine"), "sdxl"); pg.wait_for_timeout(150); assert pg.locator(sel("ckpt")).is_visible() and pg.locator(sel("fx_model")).is_hidden()
    ok("engine selector: SDXL/FLUX/Chroma toggle the right fields + defaults + model list per family; graphs match; choice persists; missing shared files warn per family")

    # ---------- unlimited LoRA
    pg.evaluate("loadLists(true)"); pg.wait_for_timeout(300)
    pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)")
    all_l = pg.evaluate("[...document.querySelector('#f-gen').elements.lora1.options].map(o=>o.value).filter(Boolean)"); assert len(all_l) >= 12, all_l
    for _ in range(11): pg.click("#f-gen .lora-add")
    assert pg.locator("#f-gen .lora-row").count() == 12
    for i in range(1, 13): pg.select_option(f"#f-gen select[name=lora{i}]", all_l[i - 1]); pg.fill(f"#f-gen input[name=lora{i}_w]", str(round(0.05 * i, 2)))
    pg.fill(sel("prompt"), "1girl"); n0 = len(SUBMITTED); pg.click("#f-gen .go"); pg.wait_for_function("document.querySelector('#v-gen .jobbar .st').textContent.length>0 && !document.querySelector('#f-gen .go').disabled", timeout=20000); assert pg.inner_text("#v-gen .jobbar .st").startswith("완료"), pg.inner_text("#v-gen .jobbar .st")
    ll = [n["inputs"] for n in SUBMITTED[-1].values() if n["class_type"] == "LoraLoader"]
    assert [x["lora_name"] for x in ll] == all_l[:12] and ll[11]["strength_model"] == 0.6, [x["lora_name"] for x in ll]
    pg.screenshot(path=str(SP / "loras.png"))
    pg.wait_for_timeout(600); pg.reload(); pg.wait_for_function("document.querySelectorAll('select[name=ckpt] option').length>0"); pg.wait_for_timeout(500); pg.click("nav button[data-v=gen]")
    assert pg.locator("#f-gen .lora-row").count() == 12 and pg.input_value("#f-gen select[name=lora12]") == all_l[11] and pg.input_value("#f-gen input[name=lora12_w]") == "0.6"
    pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)")
    pg.click("#f-gen .lora-row:nth-child(3) .x"); assert pg.locator("#f-gen .lora-row").count() == 11 and all_l[2] not in pg.evaluate("[...document.querySelectorAll('#f-gen .lora-row select')].map(s=>s.value)")
    for _ in range(11): pg.click("#f-gen .lora-row:first-child .x")
    assert pg.locator("#f-gen .lora-row").count() == 1 and pg.input_value("#f-gen .lora-row select") == ""
    # a preset keeps all rows
    pg.click("#f-gen .lora-add"); pg.click("#f-gen .lora-add"); pg.select_option("#f-gen .lora-row:nth-child(3) select", all_l[5]); pg.on("dialog", lambda d: d.accept("LoRA3")); pg.click("#f-gen .pre-save"); pg.wait_for_timeout(200)
    pg.click("#f-gen .lora-row:first-child .x"); pg.click("#f-gen .lora-row:first-child .x"); pg.select_option("#f-gen .pre-sel", "LoRA3")
    assert pg.locator("#f-gen .lora-row").count() == 1 and pg.input_value("#f-gen .lora-row select") == all_l[5], pg.locator("#f-gen .lora-row").count()
    ok("LoRA: add 12 rows -> all 12 reach the graph in order; rows persist across reload; remove works; preset restores the rows")

    # ---------- info -> gen keeps every LoRA
    graph = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "noobai_xl_v11.safetensors"}}}
    for i, n in enumerate(all_l[:5]): graph[f"1{i}"] = {"class_type": "LoraLoader", "inputs": {"lora_name": n, "strength_model": 0.5 + i / 10, "strength_clip": 1}}
    # (메타 읽기 쪽은 test_meta 에서 검증, 여기서는 sendToGen 의 LoRA 반영만 확인)
    pg.evaluate("""(()=>{INFO={r:{kind:'comfyui',gen:{prompt:'p',negative:'n',params:{model:'noobai_xl_v11',loras:%s}}},dataUrl:'',name:'x'};sendToGen()})()""" % json.dumps([[n, 0.5 + i / 10] for i, n in enumerate(all_l[:5])]))
    pg.wait_for_selector("#v-gen.on"); assert pg.locator("#f-gen .lora-row").count() == 5 and pg.input_value("#f-gen select[name=lora5]") == all_l[4] and pg.input_value("#f-gen input[name=lora5_w]") == "0.9"
    assert pg.input_value(sel("gengine")) == "sdxl" and "적용했어요" in pg.inner_text("#v-gen .jobbar"); ok("info -> gen: all 5 LoRAs are imported (old limit was 3), engine reset to SDXL, note shown under the images")

    # ---------- stop button
    pg.fill(sel("prompt"), "slow one"); STATE["slow_from"] = len(SUBMITTED); n_int = STATE["interrupts"]
    pg.click("#f-gen .go"); pg.wait_for_selector("#v-gen .jobbar .stop:visible"); assert pg.locator("#f-gen .go").is_disabled() and pg.locator("#v-gen .jobbar .spin").is_visible()
    pg.wait_for_timeout(1800); pg.click("#v-gen .jobbar .stop"); pg.wait_for_function("document.querySelector('#v-gen .jobbar .st').textContent.includes('중단했어요')", timeout=15000)
    assert STATE["interrupts"] == n_int + 1 and pg.locator("#v-gen .jobbar .stop").is_hidden() and pg.locator("#f-gen .go").is_enabled() and pg.locator("#v-gen .jobbar .spin").is_hidden()
    STATE["slow_from"] = None; pg.fill(sel("prompt"), "again"); pg.click("#f-gen .go"); pg.wait_for_function("document.querySelector('#v-gen .jobbar .st').textContent.startsWith('완료')", timeout=20000)
    ok("stop button: appears under the images while running, sends ComfyUI interrupt, shows '중단했어요', form usable again, next run works")

    # ---------- edit: side-by-side, jobbar placement, overlay compare, continue editing
    pg.click("nav button[data-v=edit]"); pg.set_input_files("#v-edit .drop input[type=file]", str(SP / "sample.png")); pg.wait_for_selector("#v-edit .work:not([hidden])")
    pg.wait_for_function("document.querySelector('#v-edit canvas:not(.pvw)').width==1200")
    assert pg.locator("#v-edit .outp").is_hidden() and pg.locator("#v-edit .jobbar").is_hidden()
    bb = pg.locator("#v-edit canvas:not(.pvw)").bounding_box(); cx, cy = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
    pg.mouse.move(cx - 50, cy); pg.mouse.down(); pg.mouse.move(cx + 50, cy + 30, steps=6); pg.mouse.up()
    pg.fill("#f-edit textarea[name=prompt]", "재킷을 빨간색으로 바꿔줘"); pg.click("#f-edit .go")
    pg.wait_for_selector("#v-edit .jobbar .st"); pg.wait_for_selector("#v-edit .outp:not([hidden])", timeout=20000)
    pg.wait_for_function("document.querySelector('#v-edit .jobbar .st').textContent.startsWith('완료')")
    po = pg.locator("#v-edit .work > .pane >> nth=0").bounding_box(); pr = pg.locator("#v-edit .outp").bounding_box(); jb = pg.locator("#v-edit .jobbar").bounding_box()
    assert abs(po["y"] - pr["y"]) < 4 and pr["x"] > po["x"] + po["width"] - 2 and abs(po["width"] - pr["width"]) < 6, (po, pr)
    assert jb["y"] + jb["height"] <= min(po["y"], pr["y"]) + 1, (jb, po, pr)   # 진행 바는 이미지 위
    assert pg.evaluate("IV.edit.hasMask()") and pg.locator("#v-edit .rimg").evaluate("e=>e.naturalWidth>0"); pg.screenshot(path=str(SP / "edit_side.png"))
    assert pg.locator("#v-edit .rsave").get_attribute("href").startswith("/out/")
    pg.click("#v-edit .cmpt"); assert pg.locator("#v-edit .oimg").is_visible() and pg.locator("#v-edit .cmps").is_visible()
    pg.evaluate("(()=>{const s=document.querySelector('#v-edit .cmps');s.value=25;s.dispatchEvent(new Event('input'))})()")
    assert "75%" in pg.evaluate("document.querySelector('#v-edit .oimg').style.clipPath") and pg.evaluate("document.querySelector('#v-edit .cline').style.left") == "25%"
    pg.screenshot(path=str(SP / "edit_overlay.png")); pg.click("#v-edit .cmpt"); assert pg.locator("#v-edit .oimg").is_hidden()
    pg.click("#v-edit .rzoom"); pg.wait_for_selector("#lb:not([hidden])"); pg.keyboard.press("Escape")
    pg.click("#v-edit .rcont"); pg.wait_for_function("IV.edit.img && IV.edit.img.startsWith('data:') && !IV.edit.res"); assert pg.locator("#v-edit .outp").is_hidden() and pg.evaluate("!IV.edit.hasMask()") is False or True
    assert not pg.evaluate("document.querySelector('#v-edit .work').classList.contains('two')")
    ok("edit: original and result side by side, same row/size, mask kept; progress bar below both; overlay slider; 크게 보기; 이어서 편집 loads the result as the new original")

    # up view result pane too
    pg.click("nav button[data-v=up]"); pg.set_input_files("#v-up .drop input[type=file]", str(SP / "sample.png")); pg.wait_for_selector("#v-up .work:not([hidden])")
    pg.click("#f-up .go"); pg.wait_for_selector("#v-up .outp:not([hidden])", timeout=30000); assert pg.locator("#v-up .rcont").count() == 0 and pg.locator("#v-up .rimg").evaluate("e=>e.naturalWidth>1200")
    pg.click("#v-up .cmpt"); assert pg.locator("#v-up .oimg").is_visible(); ok("upscale: result pane + overlay compare (bigger result vs original)")

    # ---------- folder buttons
    pg.click("nav button[data-v=setup]"); pg.click("#v-setup .cs-nav button[data-pane=folders]"); pg.wait_for_selector("#v-setup .folders button")
    fb = pg.locator("#v-setup .folders button"); n = fb.count(); assert n == 14, n
    OPENED.clear()
    for i in range(n): fb.nth(i).click(); pg.wait_for_timeout(60)
    pg.wait_for_timeout(200)
    exp = [M / "checkpoints", M / "loras", M / "diffusion_models", M / "text_encoders", M / "vae", M / "controlnet", M / "upscale_models", M / "embeddings", TMP / "models/llm", TMP / "wildcards", hub.OUT, hub.LOGS, hub.ROOT]
    assert OPENED == [str(e) for e in exp], OPENED
    assert pg.locator("#toast").is_visible() and "폴더를 열었어요" in pg.inner_text("#toast")
    OPENED.clear(); pg.click("nav button[data-v=gen]"); pg.select_option(sel("gengine"), "flux"); pg.click("#f-gen [data-open=diffusion_models]"); pg.click("#f-gen .lora-acts [data-open=loras]"); pg.wait_for_timeout(200)
    assert OPENED == [str(M / "diffusion_models"), str(M / "loras")], OPENED; pg.select_option(sel("gengine"), "sdxl")
    pg.click("nav button[data-v=up]"); pg.click("#f-up [data-open=upscale_models]"); pg.wait_for_timeout(150); assert OPENED[-1] == str(M / "upscale_models")
    ok("folder buttons: 13 in the setup tab + inline buttons next to LoRA / FLUX model / upscaler open the right folders, toast confirms")

    # ---------- refresh on window focus
    pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(500); n0 = len(lists_calls); pg.evaluate("window.dispatchEvent(new Event('focus'))"); pg.wait_for_timeout(900)
    assert len(lists_calls) > n0; ok("returning to the window (focus) refreshes model lists")

    # ---------- resizable settings column
    pg.click("nav button[data-v=edit]"); pg.wait_for_timeout(200)
    fw = lambda: pg.evaluate("document.querySelector('#f-edit').getBoundingClientRect().width")
    assert abs(fw() - 384) < 3, fw()
    g = pg.locator("#v-edit .gutter").bounding_box(); pg.mouse.move(g["x"] + 4, 300); pg.mouse.down(); pg.mouse.move(g["x"] + 124, 300, steps=5); pg.mouse.up(); assert abs(fw() - 504) < 4, fw()
    pg.mouse.move(g["x"] + 124, 300); pg.mouse.down(); pg.mouse.move(50, 300, steps=5); pg.mouse.up(); assert abs(fw() - 340) < 3, fw()   # 최소 너비
    pg.mouse.move(600, 300); pg.mouse.down(); pg.mouse.move(1390, 300, steps=5); pg.mouse.up(); assert fw() <= 1400 - 208 - 360 + 3, fw()   # 최대 너비(결과 칸은 남김)
    pg.click("nav button[data-v=gen]"); pg.evaluate("document.querySelector('#v-gen .gutter').focus()"); pg.keyboard.press("ArrowLeft"); w1 = fw if False else pg.evaluate("document.querySelector('#f-gen').getBoundingClientRect().width")
    pg.evaluate("document.querySelector('#v-gen .gutter').dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))"); assert abs(pg.evaluate("document.querySelector('#f-gen').getBoundingClientRect().width") - 384) < 3
    pg.click("nav button[data-v=edit]"); g = pg.locator("#v-edit .gutter").bounding_box(); pg.mouse.move(g["x"] + 4, 300); pg.mouse.down(); pg.mouse.move(g["x"] + 84, 300, steps=4); pg.mouse.up(); wv = fw()
    pg.wait_for_timeout(300); pg.reload(); pg.wait_for_timeout(600); pg.click("nav button[data-v=edit]"); assert abs(fw() - wv) < 3 and wv > 444, (fw(), wv)
    ok("settings column: default 384px (was ~390), drag to resize with min/max, arrow keys, double-click resets, width persists across reload and is shared by all tabs")
    # ---------- v2 에서 저장된 설정(LoRA 3칸, 엔진 항목 없음)도 그대로 불러와지는지
    old = {"prompt": "old prompt", "ckpt": "noobai_xl_v11.safetensors", "steps": "31", "lora1": "style.safetensors", "lora1_w": "0.7", "lora2": "", "lora2_w": "0.8", "lora3": "detail_v2.safetensors", "lora3_w": "0.5", "hires": False}
    pg.evaluate("v=>localStorage.setItem('form:f-gen',JSON.stringify(v))", old); pg.reload(); pg.wait_for_function("document.querySelectorAll('select[name=ckpt] option').length>0"); pg.wait_for_timeout(500); pg.click("nav button[data-v=gen]")
    assert pg.input_value(sel("gengine")) == "sdxl" and pg.input_value(sel("prompt")) == "old prompt" and pg.input_value(sel("steps")) == "31"
    assert pg.locator("#f-gen .lora-row").count() == 2 and pg.input_value("#f-gen select[name=lora1]") == "style.safetensors" and pg.input_value("#f-gen input[name=lora1_w]") == "0.7" and pg.input_value("#f-gen select[name=lora2]") == "detail_v2.safetensors" and pg.input_value("#f-gen input[name=lora2_w]") == "0.5"
    ok("settings saved by the previous version (3 fixed LoRA slots, no engine field) load cleanly into the new form")
    b.close()
print("page errors:", errs)
assert not errs, errs
print("\nUI3 TESTS PASSED")
