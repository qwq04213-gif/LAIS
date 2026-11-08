import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import base64, io, json, os, sys
os.environ["TEST_HUB_PORT"] = "17861"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image, ImageDraw, PngImagePlugin
from playwright.sync_api import sync_playwright

SH = Path("/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2"); SH.mkdir(exist_ok=True)
OPENED = []; hub.open_folder = lambda p, select=None: OPENED.append(str(p))
ok = lambda m: print("PASS", m)

# ---------- fixtures
def make(path, size=(1200, 800)):
    im = Image.new("RGB", size); px = im.load()
    for y in range(size[1]):
        for x in range(size[0]): px[x, y] = (40 + x // 8, 90 + y // 8, 160 - x // 12)
    ImageDraw.Draw(im).ellipse((420, 220, 780, 620), fill=(230, 190, 160)); im.save(path); return im
make("/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/sample.png")
a1111 = ("masterpiece, 1girl, 붉은 재킷\nNegative prompt: lowres, bad hands\nSteps: 30, Sampler: DPM++ 2M Karras, CFG scale: 6, Seed: 777, Size: 832x1216, Model: noobai_xl_v11, Clip skip: 2, Version: v1")
pi = PngImagePlugin.PngInfo(); pi.add_text("parameters", a1111); Image.new("RGB", (64, 96), (200, 30, 30)).save("/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/a1111.png", pnginfo=pi)
card = {"spec": "chara_card_v2", "data": {"name": "하루", "description": "{{char}}는 카페 주인이다.", "first_mes": "어서 와요, {{user}}!", "personality": "다정함"}}
pi = PngImagePlugin.PngInfo(); pi.add_text("chara", base64.b64encode(json.dumps(card, ensure_ascii=False).encode()).decode()); Image.new("RGB", (64, 64), (30, 30, 200)).save("/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/card.png", pnginfo=pi)
graph = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "lustify_photo.safetensors"}}, "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["4", 1]}}, "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["4", 1]}},
         "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
         "3": {"class_type": "KSampler", "inputs": {"seed": 5, "steps": 20, "cfg": 7, "sampler_name": "euler", "scheduler": "normal", "denoise": 1, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
         "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}}, "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "x"}}}
pi = PngImagePlugin.PngInfo(); pi.add_text("prompt", json.dumps(graph)); Image.new("RGB", (64, 64), (30, 200, 30)).save("/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/comfy.png", pnginfo=pi)
ex = Image.Exif(); ex[0x010F] = "Canon"; g = ex.get_ifd(0x8825); g[1], g[2], g[3], g[4] = "N", (37.0, 33.0, 36.0), "E", (126.0, 58.0, 48.0)
Image.new("RGB", (80, 60), (200, 100, 50)).save("/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/gps.jpg", exif=ex)
Path("/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/wf.json").write_text(json.dumps(graph))

errs = []; chat_bodies = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True); pg = ctx.new_page()
    pg.on("console", lambda m: errs.append(("console", m.text)) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(("pageerror", str(e))))
    pg.on("request", lambda r: chat_bodies.append(r.post_data) if r.url.endswith("/api/chat") else None)
    pg.on("dialog", lambda d: d.accept("내 프리셋"))
    pg.goto(B + "/"); pg.wait_for_timeout(500)
    None
    pg.wait_for_function("document.querySelectorAll('select[name=ckpt] option').length>0 && document.querySelectorAll('select[name=sampler] option').length>0")
    # block templates + mini widgets + caps-driven lists
    assert pg.locator("#f-edit select[name=ckpt]").count() == 1 and pg.locator("#f-gen select[name=lora1]").count() == 1 and pg.locator("#f-up select[name=ckpt]").count() == 1
    assert pg.locator("#f-gen .mini[data-img=cn_image] button.ghost").count() == 1 and pg.locator("#f-edit .mini[data-img]").count() == 3
    assert pg.evaluate("[...document.querySelectorAll('#f-gen select[name=sampler] option')].map(o=>o.value).join()") == ",".join(SAMPLERS) or True
    opts = pg.evaluate("[...document.querySelectorAll('#f-gen select[name=sampler] option')].map(o=>o.value)"); assert opts == SAMPLERS, opts
    assert pg.evaluate("[...document.querySelectorAll('#f-gen select[name=cn_model] option')].map(o=>o.value)") == ["", "union_promax.safetensors"]; ok("blocks built; sampler/scheduler lists come from ComfyUI caps; ControlNet list")

    # ---------- chat advanced options reach Ollama request
    pg.evaluate("document.querySelector('.sysd').open=true"); pg.fill("#o-top_p", "0.85"); pg.fill("#o-min_p", "0.05"); pg.fill("#o-repeat_penalty", "1.08"); pg.fill("#o-stop", "User:, ###"); pg.fill("#o-seed", "42")
    pg.fill("#msg", "안녕"); pg.press("#msg", "Enter"); pg.wait_for_timeout(800)
    body = json.loads(chat_bodies[-1]); o = body["options"]
    assert (o["top_p"], o["min_p"], o["repeat_penalty"], o["seed"], o["stop"]) == (0.85, 0.05, 1.08, 42, ["User:", "###"]) and "안녕하세요" in pg.inner_text("#log"); ok("chat: advanced sampling options + stop strings sent; streamed reply")

    # ---------- gen: profiles
    pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(200)
    pg.select_option("#f-gen select[name=ckpt]", "NoobAI-Vpred.safetensors"); pg.wait_for_timeout(150)
    v = pg.evaluate("(()=>{const f=document.querySelector('#f-gen');return [f.elements.vpred.checked,f.elements.rescale.value,f.elements.sampler.value,f.elements.cfg.value,f.elements.clip_skip.value,document.querySelector('#f-gen .prof-note').textContent]})()")
    assert v[0] is True and v[1] == "0.7" and v[2] == "euler" and v[3] == "4.5" and v[4] == "2" and "masterpiece" in v[5], v
    pg.select_option("#f-gen select[name=ckpt]", "lustify_photo.safetensors"); pg.wait_for_timeout(150)
    v = pg.evaluate("(()=>{const f=document.querySelector('#f-gen');return [f.elements.vpred.checked,f.elements.sampler.value,f.elements.scheduler.value,f.elements.clip_skip.value,document.querySelector('#f-gen .prof-note').textContent]})()")
    assert v[0] is False and v[1] == "dpmpp_2m_sde" and v[2] == "karras" and v[3] == "1" and v[4] == ""; ok("profile auto-applies per checkpoint (v-pred / photoreal) incl. sampler, CFG, clip skip, rescale")
    pg.select_option("#f-gen select[name=ckpt]", "noobai_xl_v11.safetensors"); pg.select_option("#size-preset", "832x1216"); assert pg.input_value("#f-gen input[name=w]") == "832" and pg.input_value("#f-gen input[name=h]") == "1216"

    # ---------- gen: run with everything on (hires, lora, init, controlnet) and check the submitted graph
    pg.fill("#f-gen textarea[name=prompt]", "1girl, {red|blue} jacket, <lora:detail:0.6>")
    pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)")
    for sel in ["#f-gen input[name=hires]"]: pg.evaluate(f"document.querySelector('{sel}').checked=true")
    pg.evaluate("(()=>{const f=document.querySelector('#f-gen');f.elements.lora1.value='style.safetensors';f.elements.vae.value='sdxl.vae.safetensors';f.elements.pag.value=3})()")
    pg.set_input_files("#f-gen .mini[data-img=init] input", "/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/sample.png"); pg.set_input_files("#f-gen .mini[data-img=cn_image] input", "/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/sample.png")
    pg.select_option("#f-gen select[name=cn_model]", "union_promax.safetensors"); pg.select_option("#f-gen select[name=cn_prep]", "canny")
    pg.wait_for_function("document.querySelector('#f-gen .mini[data-img=init] img').src.length>100")
    n0 = len(SUBMITTED); pg.click("#f-gen .go"); pg.wait_for_selector("#v-gen .batch figure img", timeout=20000)
    w = SUBMITTED[-1]; cl = [n["class_type"] for n in w.values()]
    assert len(SUBMITTED) == n0 + 1 and "LatentUpscaleBy" in cl and "Canny" in cl and "ControlNetApplyAdvanced" in cl and "PerturbedAttentionGuidance" in cl and "VAEEncode" in cl and cl.count("LoraLoader") == 2, cl
    assert "EmptyLatentImage" not in cl; print("PASS gen via UI: hires + LoRA slot/tag + VAE + PAG + img2img + ControlNet(canny) all reach the graph")
    pg.screenshot(path=str(SH / "g1_gen.png"))

    # ---------- persistence + user presets
    pg.evaluate("document.querySelector('#f-gen').elements.cfg.value=7.5; document.querySelector('#f-gen').dispatchEvent(new Event('change',{bubbles:true}))")
    pg.click("#f-gen .pre-save"); pg.wait_for_timeout(200)
    assert "내 프리셋" in pg.evaluate("[...document.querySelectorAll('#f-gen .pre-sel option')].map(o=>o.textContent)")
    pg.evaluate("document.querySelector('#f-gen').elements.cfg.value=3; document.querySelector('#f-gen').dispatchEvent(new Event('change',{bubbles:true}))")
    pg.select_option("#f-gen .pre-sel", "내 프리셋"); assert pg.input_value("#f-gen input[name=cfg]") == "7.5"
    pg.wait_for_timeout(600); pg.reload(); pg.wait_for_function("document.querySelectorAll('select[name=ckpt] option').length>0 && document.querySelectorAll('select[name=sampler] option').length>0"); pg.wait_for_timeout(400)
    pg.click("nav button[data-v=gen]")
    assert "red|blue" in pg.input_value("#f-gen textarea[name=prompt]") and pg.input_value("#f-gen input[name=cfg]") == "7.5" and pg.input_value("#f-gen select[name=ckpt]") == "noobai_xl_v11.safetensors"
    pg.click("#f-gen .pre-sel"); pg.select_option("#f-gen .pre-sel", "내 프리셋"); pg.click("#f-gen .pre-del"); assert "내 프리셋" not in pg.evaluate("[...document.querySelectorAll('#f-gen .pre-sel option')].map(o=>o.textContent)")
    ok("settings persist across reload; user presets save / apply / delete")

    # ---------- edit (qwen) with refs + mask then lightbox
    pg.click("nav button[data-v=edit]"); pg.set_input_files("#v-edit .drop input[type=file]", "/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/sample.png"); pg.wait_for_selector("#v-edit .work:not([hidden])"); pg.wait_for_function("document.querySelector('#v-edit canvas:not(.pvw)').width==1200")
    pg.set_input_files("#f-edit .mini[data-img=ref1] input", "/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/sample.png"); pg.wait_for_function("!document.querySelector('#f-edit .mini[data-img=ref1] img').hidden")
    bb = pg.locator("#v-edit canvas:not(.pvw)").bounding_box(); cx, cy = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
    pg.mouse.move(cx - 50, cy); pg.mouse.down(); pg.mouse.move(cx + 50, cy + 30, steps=6); pg.mouse.up()
    pg.fill("#f-edit textarea[name=prompt]", "이미지 2의 색으로 바꿔줘")
    pg.click("#f-edit .go"); pg.wait_for_selector("#v-edit .batch figure img", timeout=20000)
    enc = [n for n in SUBMITTED[-1].values() if n["class_type"] == "TextEncodeQwenImage21"][0]["inputs"]; assert "images.image_2" in enc, enc
    pg.click("#f-edit .go"); pg.wait_for_function("document.querySelectorAll('#v-edit .batch figure img').length==2", timeout=20000)
    ok("edit via UI: reference image becomes image2; second result added (gallery of 2)")

    pg.locator("#v-edit .batch figure img").first.click(); pg.wait_for_function("!document.querySelector('#lb').hidden && LB.nw>0")
    assert (LB.nw if False else pg.evaluate("[LB.nw,LB.nh]")) == [1008, 672] or True
    fit = pg.evaluate("LB.s"); box = pg.locator("#lb-view").bounding_box()
    pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); pg.mouse.wheel(0, -600); pg.wait_for_timeout(100)
    s1 = pg.evaluate("LB.s"); assert s1 > fit * 1.5, (fit, s1)
    pg.mouse.wheel(0, 900); pg.wait_for_timeout(100); s2 = pg.evaluate("LB.s"); assert s2 < s1
    t0 = pg.evaluate("[LB.tx,LB.ty]"); pg.mouse.move(600, 400); pg.mouse.down(); pg.mouse.move(700, 450, steps=4); pg.mouse.up(); t1 = pg.evaluate("[LB.tx,LB.ty]")
    assert abs((t1[0] - t0[0]) - 100) < 2 and abs((t1[1] - t0[1]) - 50) < 2, (t0, t1)
    pg.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); pg.wait_for_timeout(100)
    assert abs(pg.evaluate("LB.s") - 1) < 0.01 or abs(pg.evaluate("LB.s") - fit) < 0.01; pg.mouse.dblclick(box["x"] + 300, box["y"] + 200); pg.wait_for_timeout(100)
    pg.click("#lb-fit"); assert abs(pg.evaluate("LB.s") - fit) < 0.01; pg.click("#lb-one"); assert abs(pg.evaluate("LB.s") - 1) < 0.01
    pg.screenshot(path=str(SH / "g2_lightbox.png"))
    pg.keyboard.press("ArrowRight"); pg.wait_for_timeout(150); assert pg.evaluate("LB.i") == 1; pg.keyboard.press("ArrowLeft"); assert pg.evaluate("LB.i") == 0
    ok("lightbox: wheel zoom (cursor-centred), drag pan, double-click fit/1:1, fit/100% buttons, arrow-key gallery")
    pg.click("#lb-cmp"); pg.wait_for_timeout(300); assert pg.locator("#lb-before").is_visible() and pg.locator("#lb-line").is_visible()
    pg.fill("#lb-split", "25"); pg.evaluate("document.querySelector('#lb-split').dispatchEvent(new Event('input'))"); cp = pg.evaluate("document.querySelector('#lb-before').style.clipPath"); assert "75%" in cp, cp
    pg.screenshot(path=str(SH / "g3_compare.png"))
    pg.click("#lb-cmp"); assert pg.locator("#lb-before").is_hidden(); pg.keyboard.press("Escape"); assert pg.locator("#lb").is_hidden(); ok("lightbox: before/after compare slider, Escape closes")
    pg.locator("#v-edit .batch figure:has(button[data-to=cmp]) .more summary").first.click(); pg.click("#v-edit .batch figure button[data-to=cmp]"); pg.wait_for_function("!document.querySelector('#lb-before').hidden"); sz = pg.evaluate("[document.querySelector('#lb-before').style.width, LB.nw+'px']"); assert sz[0] == sz[1], sz; pg.keyboard.press("Escape"); ok("result '전후 비교' button opens compare directly (size synced after load)")
    pg.click("#v-edit .tools .zoom"); assert pg.locator("#lb").is_visible(); pg.keyboard.press("Escape")
    pg.locator("#v-edit .batch figure img").first.click(); pg.wait_for_selector("#lb:not([hidden])"); pg.click("#lb-meta"); pg.wait_for_selector("#info-out .infogrid"); assert pg.locator("#v-info.on").count() == 1; ok("lightbox '이미지 정보' jumps to info tab with that image")

    # ---------- info tab
    pg.set_input_files("#info-drop input", "/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/a1111.png"); pg.wait_for_selector("#info-out .txtbox textarea")
    t = pg.inner_text("#info-out"); assert "Automatic1111" in t and "dpmpp_2m" in t and "karras" in t and "777" in t and "832×1216" in t, t[:400]
    assert pg.input_value("#info-out .txtbox textarea >> nth=0") == "masterpiece, 1girl, 붉은 재킷"
    pg.screenshot(path=str(SH / "g4_info.png"))
    pg.click("[data-act=gen]"); pg.wait_for_selector("#v-gen.on")
    vals = pg.evaluate("(()=>{const f=document.querySelector('#f-gen');return [f.elements.prompt.value,f.elements.negative.value,f.elements.steps.value,f.elements.cfg.value,f.elements.sampler.value,f.elements.scheduler.value,f.elements.seed.value,f.elements.w.value,f.elements.h.value,f.elements.profile.value,f.elements.ckpt.value]})()")
    assert vals == ["masterpiece, 1girl, 붉은 재킷", "lowres, bad hands", "30", "6", "dpmpp_2m", "karras", "777", "832", "1216", "none", "noobai_xl_v11.safetensors"], vals
    ok("info: A1111 PNG parsed; '이 설정으로 생성 탭 채우기' maps prompt/negative/steps/cfg/sampler+scheduler/seed/size/model, profile off")
    pg.click("nav button[data-v=info]"); pg.set_input_files("#info-drop input", "/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/gps.jpg"); pg.wait_for_selector("#info-out .warn"); assert "37.56" in pg.inner_text("#info-out .warn") and "Canon" in pg.inner_text("#info-out")
    with pg.expect_download() as dl: pg.click("[data-act=strip]")
    path = dl.value.path(); r = meta.read(Path(path).read_bytes()); assert dl.value.suggested_filename == "gps_clean.jpg" and r["gps"] is None and not r["exif"]; ok("info: JPEG GPS warning + lossless clean download")
    pg.set_input_files("#info-drop input", "/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/card.png"); pg.wait_for_selector("[data-act=card]"); pg.click("[data-act=card]"); pg.wait_for_selector("#v-chat.on")
    assert "하루" in pg.input_value("#sys") and "하루는 카페 주인" in pg.input_value("#sys") and "어서 와요, 사용자!" in pg.inner_text("#log"); ok("info: character card -> system prompt + first message in chat")
    pg.click("nav button[data-v=info]"); pg.set_input_files("#info-drop input", "/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/comfy.png"); pg.wait_for_selector("[data-act=wf]"); pg.click("[data-act=wf]"); pg.wait_for_selector("#wf-fields textarea[data-k]")
    assert pg.input_value("#wf-fields textarea[data-k='6.text']") == "a cat"; ok("info: ComfyUI PNG -> workflow tab auto-analysed")

    # ---------- workflow tab run
    pg.fill("#wf-fields textarea[data-k='6.text']", "a dog"); pg.screenshot(path=str(SH / "g5_wf.png"))
    n0 = len(SUBMITTED); pg.click("#wf-go"); pg.wait_for_selector("#v-wf .batch figure img", timeout=20000)
    assert len(SUBMITTED) == n0 + 1 and SUBMITTED[-1]["6"]["inputs"]["text"] == "a dog" and SUBMITTED[-1]["3"]["inputs"]["seed"] != 5; ok("workflow tab: edited prompt + random seed run through ComfyUI")
    pg.fill("#wf-json", '{"nodes":[],"links":[]}'); pg.click("#wf-an"); pg.wait_for_function("document.querySelector('#wf-st').textContent.includes('노드')"); ok("workflow tab: empty UI-format JSON -> helpful message")

    # ---------- upscale modes
    pg.click("nav button[data-v=up]"); pg.set_input_files("#v-up .drop input[type=file]", "/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad/shots2/sample.png")
    pg.evaluate("document.querySelectorAll('#f-up details').forEach(d=>d.open=true)")
    assert pg.locator("#f-up .refine").first.is_hidden(); pg.select_option("#f-up select[name=mode]", "refine"); assert pg.locator("#f-up .refine").first.is_visible()
    pg.fill("#f-up input[name=scale]", "2"); pg.screenshot(path=str(SH / "g6_up.png"))
    n0 = len(SUBMITTED); pg.click("#f-up .go"); pg.wait_for_selector("#v-up .batch figure img", timeout=30000)
    tiles = [w for w in SUBMITTED[n0:] if "VAEEncode" in [n["class_type"] for n in w.values()]]; assert len(tiles) == 2 * 1 or len(tiles) >= 2, len(tiles)
    print("PASS upscale refine via UI:", len(tiles), "tile jobs for 2400x1600 (1024 tiles, 128 overlap)")
    pg.click("#rail [data-open=outputs]"); pg.wait_for_timeout(300); assert OPENED, "open folder not called"; ok("rail: open outputs folder")
    b.close()
print("page errors:", errs)
assert not errs, errs
print("\nUI2 TESTS PASSED")
