"""3.14 화면: LoRA 만들기 — 세트 만들기·사진 넣기·캡션·학습·생성 화면에서 써 보기, 갤러리에서 보내기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, io
from pathlib import Path
os.environ["TEST_HUB_PORT"] = "17978"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
T = os.environ.get("TMPDIR", "/tmp")
eng = TMP / "engine/lora"; (eng / "sd-scripts").mkdir(parents=True, exist_ok=True); (eng / ".ready").write_text("ok")
(eng / "sd-scripts/sdxl_train_network.py").write_text('''
import sys, time, pathlib
a = sys.argv[1:]; g = lambda k: a[a.index(k) + 1]
out = pathlib.Path(g("--output_dir")); out.mkdir(parents=True, exist_ok=True); n = int(g("--max_train_steps"))
for i in range(1, n + 1):
    print(f"steps: {i*100//n}%|#| {i}/{n} [00:01<00:01, avr_loss=0.1]", flush=True); time.sleep(0.02)
open(out / (g("--output_name") + ".safetensors"), "wb").write(b"lora")
''', encoding="utf-8")
hub.lora_train.py_of = lambda root: Path(sys.executable)
hub.model_family = lambda folder, name: ("sdxl", True, "test")
hub.bgremove.have_ort = lambda: True; hub.wd14.ready = lambda m: True; hub.wd14.tags = lambda m, img, **k: ["1girl", "smile"]
files_ = []
for i in range(5):
    p = f"{T}/lo{i}.png"; Image.new("RGB", (600, 600), (i * 40, 90, 160)).save(p); files_.append(p)
gd = hub.OUT / "생성"; gd.mkdir(parents=True, exist_ok=True); Image.new("RGB", (512, 512), (9, 9, 9)).save(gd / "g1.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 950}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=lora]"); pg.wait_for_selector("#lo-eng:has-text('준비됨')")
    pg.fill("#lo-name", "테스트 캐릭터"); pg.fill("#lo-file", "test_char"); pg.fill("#lo-trig", "tchar"); pg.click("#lo-create"); pg.wait_for_selector("#lo-data:not([hidden])")
    pg.set_input_files("#lo-in", files_); pg.wait_for_function("document.querySelectorAll('#lo-grid .lo-c').length===5")
    pg.click("#lo-cap"); pg.wait_for_function("[...document.querySelectorAll('#lo-grid textarea')].every(t=>t.value==='1girl, smile')", timeout=20000)
    pg.fill("#lo-grid .lo-c >> nth=0 >> textarea", "1girl, waving"); pg.click("#lo-capsave"); pg.wait_for_timeout(500)
    assert "1girl, waving" in json.dumps(req("/api/lora/set/" + pg.evaluate("LO.S.id")))
    ok("set → upload 5 photos → auto captions → edit & save a caption")
    assert "5장" in pg.inner_text("#lo-est")
    pg.click("#lo-train details > summary"); pg.fill("#lo-steps", "30"); pg.click("#lo-go"); pg.wait_for_selector("#lo-done:has-text('test_char.safetensors')", timeout=60000)
    pg.click("#lo-use"); pg.wait_for_selector("#v-gen.on"); pg.wait_for_timeout(500)
    assert pg.input_value("#f-gen textarea[name=prompt]").startswith("tchar"), pg.input_value("#f-gen textarea[name=prompt]")
    assert any(v == "test_char.safetensors" for v in pg.eval_on_selector_all("#f-gen select[name^=lora]", "e=>e.map(x=>x.value)"))
    ok("train (fake engine) → LoRA registered → '생성 화면에서 써 보기' adds LoRA + trigger")
    pg.click("nav button[data-v=gal]"); pg.wait_for_selector("#gal-grid .gt"); pg.click("#gal-grid .gt >> nth=0 >> [data-pick]")
    assert pg.locator("#gal-lora").is_visible(); pg.click("#gal-lora"); pg.wait_for_timeout(800)
    assert len(req("/api/lora/set/" + pg.evaluate("LO.S.id"))["images"]) == 6
    ok("gallery selection → 'LoRA 학습 사진으로'")
    assert not errs, errs
print("ALL OK")
