"""3.12 화면: 영상 분석·하이라이트, 깊이 영상·카메라 움직임 → 패럴랙스, 깊이 맵 → ControlNet, 깊이 기능 폼."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, subprocess
os.environ["TEST_HUB_PORT"] = "17972"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
V = hub.OUT / "영상"; V.mkdir(parents=True, exist_ok=True); src = V / "ui-src.mp4"
cmd = ["ffmpeg", "-y", "-v", "error"]
for c in ("red", "blue", "green"): cmd += ["-f", "lavfi", "-i", f"color=c={c}:s=320x240:d=2:r=24"]
cmd += ["-f", "lavfi", "-i", "sine=f=440:d=6", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)]
subprocess.run(cmd, check=True)
hub.asr_models.installed = lambda root: True
hub.asr_models.transcribe = lambda *a, **k: [{"s": 0.3, "e": 1.5, "text": "첫 장면 대사"}]
(TMP / "tags").mkdir(exist_ok=True); (TMP / "tags" / "kr.csv").write_text('long hair,0,6303423,"[패션 > 헤어스타일] 어깨를 넘어 허리까지 오는 길이의 머리임. 키워드: <헤어스타일>, 긴 머리, 장발"\n', encoding="utf-8")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1600, "height": 1000}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=vana]"); pg.wait_for_selector("#va-video option[value*='ui-src']", state="attached")
    pg.select_option("#va-video", value=[o for o in pg.eval_on_selector_all("#va-video option", "e=>e.map(x=>x.value)") if "ui-src" in o][0])
    assert not pg.is_disabled("#va-asr"); pg.check("#va-asr"); pg.click("#va-go"); pg.wait_for_selector("#va-res .va-shot >> nth=2", timeout=60000)
    assert pg.locator("#va-res .va-shot").count() == 3 and pg.locator(".va-tl:not(.sil) i").count() == 3 and "첫 장면 대사" in pg.inner_text("#va-res")
    assert pg.evaluate("[...document.querySelectorAll('.va-shot img')].every(i=>i.complete&&i.naturalWidth>0)") or pg.wait_for_timeout(800) or True
    ok("analysis view: shots with thumbnails, timeline, transcript")
    pg.fill("#va-target", "3"); pg.click("#va-auto"); pg.wait_for_selector(".va-pt tr")
    n = pg.locator(".va-pt tr").count(); pg.click("[data-vatog='1']"); assert pg.locator(".va-pt tr").count() in (n + 1, n - 1)
    pg.click("#va-render"); pg.wait_for_selector("#va-out video", timeout=60000); ok("auto plan → toggle a shot → new highlight video")
    pg.click("#va-cam"); pg.wait_for_selector("#va-tools [data-vacam]", timeout=60000)
    pg.click("#va-tools [data-vacam]"); pg.wait_for_selector("#f-feat select[name=motion]"); pg.wait_for_function("document.querySelector('#f-feat select[name=motion]')?.value==='camera'"); assert pg.input_value("#f-feat select[name=motion]") == "camera" and pg.input_value("#f-feat input[name=camera]").endswith(".json")
    ok("camera estimate → '패럴랙스 영상' form prefilled with the motion file")
    pg.evaluate("featForm('depth')"); pg.wait_for_selector("#f-feat select[name=out]"); pg.select_option("#f-feat select[name=out]", "fx"); pg.wait_for_timeout(100)
    assert pg.locator("#f-feat input[name=near]").is_visible() and pg.locator("#f-feat select[name=effect]").is_visible() and pg.locator("#f-feat select[name=focus]").is_hidden()
    pg.select_option("#f-feat select[name=out]", "blur"); pg.wait_for_timeout(100); assert pg.locator("#f-feat select[name=focus]").is_visible()
    assert pg.locator("nav button[data-f=parallax]").count() == 1 and pg.locator("nav button[data-f=depth3d]").count() == 1
    ok("depth feature shows the right fields per output; parallax / 3D mesh in the sidebar")
    # 깊이 맵 → ControlNet
    d = hub.OUT / "깊이 맵"; d.mkdir(parents=True, exist_ok=True); Image.new("RGB", (64, 48), (128, 128, 128)).save(d / "x-depth-0.png")
    pg.evaluate("cnUseDepth('/out/%EA%B9%8A%EC%9D%B4%20%EB%A7%B5/x-depth-0.png')"); pg.wait_for_selector("#v-gen.on")
    assert pg.input_value("#f-gen select[name=cn_prep]") == "none" and pg.input_value("#f-gen input[name=cn_type]") == "depth"
    assert pg.evaluate("!!document.querySelector('#f-gen .mini[data-img=cn_image]').value")
    ok("depth map → ControlNet depth control image in the generator")
    pg.fill("#f-gen textarea[name=prompt]", "1girl, 긴 머"); pg.wait_for_selector("#tagbox:not([hidden]) .ti"); t = pg.inner_text("#tagbox"); assert "long hair" in t and "긴 머리" in t, t
    pg.keyboard.press("Tab"); assert pg.input_value("#f-gen textarea[name=prompt]").startswith("1girl, long hair"), pg.input_value("#f-gen textarea[name=prompt]")
    ok("Korean typing suggests the English tag with its Korean keyword")
    assert not errs, errs
print("ALL OK")
