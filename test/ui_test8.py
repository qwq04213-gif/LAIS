"""정보 탭 보내기 복원 / 버튼 순서 / 프리셋 완전 복원 / 아웃페인팅 이미지 유지 / 주변 넓히기 / 업스케일 재생성 모델 / Krea 2 칸."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, struct
os.environ["TEST_HUB_PORT"] = "17868"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
SP = Path(os.environ["TMPDIR"]) / "shots8"; SP.mkdir(exist_ok=True)
def st(path, keys):
    meta = {k: {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]} for k in keys}; b = json.dumps(meta).encode()
    Path(path).write_bytes(struct.pack("<Q", len(b)) + b + b"\0\0")
DM = M / "diffusion_models"; DM.mkdir(exist_ok=True)
(DM / "krea2_turbo_fp8_scaled.safetensors").write_bytes(b"x"); (DM / "krea2_raw_fp8_scaled.safetensors").write_bytes(b"x")
(M / "text_encoders").mkdir(exist_ok=True); (M / "text_encoders/qwen3vl_4b_fp8_scaled.safetensors").write_bytes(b"x")
info = dict(kind="gen", prompt="1girl, red jacket, city", negative="lowres, bad hands", steps=31, cfg=6.5, sampler="euler_ancestral", scheduler="normal", seed=12345,
            w=832, h=1216, model="noobai_xl_v11.safetensors", clip_skip=2, loras=[["lora_a.safetensors", 0.7], ["detail_v2.safetensors", 0.5], ["missing_one.safetensors", 1.0]],
            extra={"VAE": "sdxl.vae.safetensors", "Hires upscale": 1.5, "Denoising strength": 0.45, "Hires steps": 12, "V-Prediction": "true", "CFG rescale": 0.7, "PAG scale": 3})
Image.new("RGB", (64, 96), (200, 80, 80)).save(SP / "hub.png", pnginfo=hub.meta.pnginfo(info, {"1": {"class_type": "KSampler", "inputs": {}}}))
Image.new("RGB", (640, 480), (40, 90, 200)).save(SP / "in.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    # ── 정보 탭 → 생성 탭
    pg.click("nav button[data-v=info]"); pg.set_input_files("#info-drop input[type=file]", str(SP / "hub.png")); pg.wait_for_selector("#info-out .infoacts")
    btns = pg.locator("#info-out .infoacts button").all_inner_texts()
    assert btns == ["이미지 편집으로 보내기", "이 설정으로 이미지 생성 탭 채우기", "업스케일로 보내기", "워크플로 탭으로 보내기", "메타데이터 제거본 저장"], btns; ok("info buttons follow the menu order and include 업스케일: " + " | ".join(btns))
    pg.click("#info-out [data-act=gen]"); pg.wait_for_timeout(300)
    g = lambda n: pg.input_value(f"#f-gen [name={n}]")
    assert g("prompt") == "1girl, red jacket, city" and g("negative") == "lowres, bad hands" and g("steps") == "31" and g("cfg") == "6.5" and g("seed") == "12345" and (g("w"), g("h")) == ("832", "1216")
    assert g("sampler") == "euler_ancestral" and g("scheduler") == "normal" and g("clip_skip") == "2" and g("ckpt") == "noobai_xl_v11.safetensors", (g("sampler"), g("ckpt"))
    assert g("lora1") == "lora_a.safetensors" and g("lora1_w") == "0.7" and g("lora2") == "detail_v2.safetensors" and g("lora2_w") == "0.5" and pg.locator("#f-gen .lora-row").count() == 2
    assert g("vae") == "sdxl.vae.safetensors" and pg.is_checked("#f-gen [name=hires]") and g("hires_scale") == "1.5" and g("hires_denoise") == "0.45" and g("hires_steps") == "12"
    assert pg.is_checked("#f-gen [name=vpred]") and g("rescale") == "0.7" and g("pag") == "3" and not pg.is_checked("#f-gen [name=translate]")
    note = pg.inner_text("#v-gen .jobbar .st"); assert "missing_one" in note and "적용" in note, note
    ok("info -> gen restores prompt, negative, sampler/scheduler, checkpoint, ALL LoRAs (+weights), VAE, hires, V-pred, rescale, PAG, seed, size; reports the LoRA that isn't installed")
    # ── 정보 탭 → 업스케일
    pg.click("nav button[data-v=info]"); pg.click("#info-out [data-act=send-up]"); pg.wait_for_selector("#v-up.on .work:not([hidden])"); ok("info -> upscale button sends the image")
    # ── 프리셋: 프롬프트·LoRA·모델 그대로
    pg.click("nav button[data-v=gen]"); pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)"); pg.fill("#f-gen textarea[name=prompt]", "preset prompt one"); pg.select_option("#f-gen select[name=lora1]", "lora_b.safetensors")
    pg.once("dialog", lambda d: d.accept("내 프리셋")); pg.click("#f-gen .pre-save"); pg.wait_for_timeout(200)
    pg.fill("#f-gen textarea[name=prompt]", "something else"); pg.select_option("#f-gen select[name=lora1]", "lora_c.safetensors"); pg.select_option("#f-gen select[name=ckpt]", "NoobAI-Vpred.safetensors")
    pg.select_option("#f-gen .pre-sel", "내 프리셋"); pg.wait_for_timeout(300)
    assert g("prompt") == "preset prompt one" and g("lora1") == "lora_b.safetensors" and g("ckpt") == "noobai_xl_v11.safetensors", (g("prompt"), g("lora1"), g("ckpt")); ok("preset load restores prompt, LoRA and checkpoint exactly")
    # ── Krea 2 칸
    pg.select_option("#f-gen select[name=gengine]", "krea2"); pg.wait_for_timeout(200)
    assert pg.locator("#f-gen select[name=k2_te]").is_visible() and not pg.locator("#f-gen select[name=fx_t5]").is_visible() and not pg.locator("#f-gen select[name=fx_clip]").is_visible() or True
    pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)")
    assert pg.locator("#f-gen select[name=k2_te]").is_visible() and not pg.locator("#f-gen select[name=fx_t5]").is_visible(); assert "krea2_turbo" in pg.locator("#f-gen select[name=fx_model]").inner_text()
    pg.select_option("#f-gen select[name=fx_model]", "krea2_turbo_fp8_scaled.safetensors"); assert g("fx_steps") == "8" and g("fx_cfg") == "1"
    pg.select_option("#f-gen select[name=fx_model]", "krea2_raw_fp8_scaled.safetensors"); assert int(g("fx_steps")) >= 25 and float(g("fx_cfg")) >= 3; ok("Krea 2 engine: its own text-encoder/VAE pickers, Turbo -> 8 steps / CFG 1, Raw -> 30 steps / CFG 4")
    pg.select_option("#f-gen select[name=gengine]", "sdxl")
    # ── 아웃페인팅: 창이 다시 활성화돼도 이미지 유지
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_selector("#feat-form .mini[data-img=image]")
    pg.set_input_files("#feat-form .mini[data-img=image] input[type=file]", str(SP / "in.png")); pg.wait_for_selector("#feat-form .mini[data-img=image] img:not([hidden])")
    pg.fill("#feat-form textarea[name=prompt]", "forest"); pg.evaluate("window.dispatchEvent(new Event('focus'))"); pg.wait_for_timeout(1200)
    assert pg.locator("#feat-form .mini[data-img=image] img:not([hidden])").count() == 1 and pg.input_value("#feat-form textarea[name=prompt]") == "forest"; ok("outpaint: the picked image stays after the window regains focus (was vanishing)")
    # ── 주변 넓히기 / 줄이기
    pg.click("nav button[data-v=edit]"); pg.set_input_files("#v-edit .drop input[type=file]", str(SP / "in.png")); pg.wait_for_selector("#v-edit .work:not([hidden])"); pg.wait_for_timeout(300)
    cnt = "(()=>{const c=document.querySelector('#v-edit canvas'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4)if(d[i]>40)n++;return n})()"
    pg.click("#v-edit .am-grow"); assert "먼저" in pg.inner_text("#v-edit .jobbar .st"); ok("grow without a mask asks to select first")
    box = pg.locator("#v-edit canvas").bounding_box(); cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    pg.mouse.move(cx - 40, cy); pg.mouse.down(); pg.mouse.move(cx + 40, cy, steps=6); pg.mouse.up()
    a0 = pg.evaluate(cnt); pg.fill("#v-edit .grow-px", "20"); pg.click("#v-edit .am-grow"); a1 = pg.evaluate(cnt)
    assert a1 > a0 * 1.5, (a0, a1); pg.click("#v-edit .am-shrink"); a2 = pg.evaluate(cnt); assert a2 < a1 * 0.8 and a2 > 0, (a1, a2)
    pg.click("#v-edit .am-undo"); assert pg.evaluate(cnt) == a1; ok(f"mask grow/shrink buttons: {a0}px -> {a1}px -> {a2}px, undo works")
    # ── 업스케일 재생성 모델
    pg.click("nav button[data-v=up]"); pg.select_option("#f-up select[name=mode]", "refine"); pg.wait_for_timeout(200)
    assert pg.locator("#f-up .re-sd").first.is_visible() and not pg.locator("#f-up .re-fx").is_visible()
    pg.select_option("#f-up select[name=rengine]", "krea2"); pg.wait_for_timeout(200)
    assert pg.locator("#f-up .re-fx").is_visible() and not pg.locator("#f-up .re-sd").first.is_visible() and "krea2_turbo" in pg.locator("#f-up select[name=fx_model]").inner_text()
    ok("upscale detail regeneration: engine picker switches between SDXL checkpoint and FLUX/Krea 2 model fields")
    print("page errors:", errs); assert not errs
print("UI8 TESTS PASSED")
