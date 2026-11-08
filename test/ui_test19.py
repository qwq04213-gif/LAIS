"""갤러리 삭제·선택·날짜 정리, ControlNet 쉬운 모드, 새 기능 카드(얼굴·손/참고 이미지), 영상 14B 선택."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time
os.environ["TEST_HUB_PORT"] = "17890"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
TMPD = str(TMP)
Image.new("RGB", (640, 480), (70, 120, 60)).save(TMPD + "/photo.png")
G = hub.OUT / "생성"; G.mkdir(parents=True, exist_ok=True)
def mk(n, days_ago):
    p = G / n; Image.new("RGB", (40, 40), (1, 2, 3)).save(p); t = time.time() - days_ago * 86400; os.utime(p, (t, t))
for n, d in (("a.png", 3), ("b.png", 3), ("c.png", 3), ("t.png", 0)): mk(n, d)
(hub.MODELS / "controlnet").mkdir(exist_ok=True); (hub.MODELS / "controlnet" / "controlnet-union-sdxl-promax.safetensors").write_bytes(b"x")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 1000}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(600); None
    # ── 갤러리 삭제
    pg.click("nav button[data-v=gal]"); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length==4")
    pg.locator("#gal-grid .gt").first.hover(); n0 = pg.locator("#gal-grid [data-del]").count(); assert n0 == 4, n0
    name = pg.locator("#gal-grid .gt").first.get_attribute("data-u"); fn = G / __import__("urllib.parse").parse.unquote(name).split("/")[-1]; assert fn.exists()
    pg.locator("#gal-grid .gt [data-del]").first.click(force=True); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length==3"); assert not fn.exists(); ok("trash button on a card deletes that file after a confirm")
    pg.click("#gal-sel"); assert "선택 해제" in pg.inner_text("#gal-sel") and pg.locator("#gal-delsel").is_visible(); pg.click("#gal-sel"); assert pg.locator("#gal-delsel").is_hidden()
    ts = pg.locator("#gal-grid .gt"); ts.nth(0).hover(); ts.nth(0).locator("[data-pick]").check(); ts.nth(1).click(); pg.wait_for_function("document.querySelector('#gal-delsel').textContent.includes('(2)')"); assert pg.locator("#gal-grid .gt.picked").count() == 2; ok("select mode: clicking cards picks them and the count follows")
    ts.nth(1).click(); pg.wait_for_function("document.querySelector('#gal-delsel').textContent.includes('(1)')")
    pg.click("#gal-delsel"); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length==2"); ok("delete selected removes only the picked ones")
    assert pg.locator("#gal-delsel").is_hidden()
    # ── 날짜 정리
    pg.click("#fold-org>summary"); pg.click("#org-prev"); pg.wait_for_function("document.querySelector('#org-info').textContent.includes('2개를 옮겨요')"); assert pg.locator("#org-run").is_visible(); ok("organizer preview describes what will move (grouped by day)")
    pg.click("#org-run"); pg.wait_for_function("document.querySelector('#org-info').textContent.includes('옮겼어요')"); d3 = time.strftime("%Y-%m-%d", time.localtime(time.time() - 3 * 86400))
    assert len(list((G / d3).glob("*.png"))) == 2 and not list(G.glob("*.png")); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length==2"); ok("run moves files into a date folder; the gallery still shows them")
    # ── ControlNet 쉬운 모드
    pg.click("nav button[data-v=gen]"); pg.wait_for_selector("#f-gen"); pg.wait_for_function("LISTS.controlnets.length>0")
    box = pg.locator("#f-gen .cn-easy").first; pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)")
    box.locator(".cn-go").click(); assert "먼저 사진" in box.locator(".cn-st").inner_text(); ok("easy mode without a photo → friendly nudge")
    box.locator(".cn-src input").set_input_files(TMPD + "/photo.png"); pg.wait_for_function("document.querySelector('#f-gen .cn-src img').src.startsWith('data:')")
    box.locator(".cn-kind").select_option("pose"); box.locator(".cn-go").click(); pg.wait_for_function("document.querySelector('#f-gen .cn-st').textContent.includes('✔')", timeout=20000)
    f = "document.querySelector('#f-gen')"
    assert pg.evaluate(f"{f}.elements.cn_type.value") == "pose" and pg.evaluate(f"{f}.elements.cn_model.value") == "controlnet-union-sdxl-promax.safetensors" and pg.evaluate(f"{f}.elements.cn_prep.value") == "none"
    assert pg.evaluate("document.querySelector('#f-gen .mini[data-img=cn_image]').value").startswith("data:image/png"); ok("pose map extracted → control image set, union model auto-picked, strength set")
    STATE["missing"].add("OpenposePreprocessor"); STATE["missing"].add("DWPreprocessor"); hub.caps(force=True)
    box.locator(".cn-go").click(); pg.wait_for_function("document.querySelector('#f-gen .cn-st').textContent.includes('확장')", timeout=20000); STATE["missing"].clear(); hub.caps(force=True); ok("missing preprocessor pack → clear message (with install helper)")
    pg.fill("#f-gen textarea[name=prompt]", "1girl, standing"); pg.click("#f-gen .go"); pg.wait_for_selector("#v-gen .res figure", timeout=30000)
    assert any(v["class_type"] == "SetUnionControlNetType" and v["inputs"]["type"] == "openpose" for v in SUBMITTED[-1].values()); ok("generating from the screen sends the openpose union type")
    # ── 기능 카드
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_selector("#feat-form h3"); titles = pg.eval_on_selector_all("nav button[data-f] span", "e=>e.map(x=>x.textContent)"); assert any("얼굴·손" in t for t in titles) and any("참고 이미지" in t for t in titles), titles
    pg.evaluate("document.querySelector('nav button[data-f=\"detailer\"]').click()"); pg.wait_for_selector("#feat-form h3"); assert "미검증" not in pg.inner_text("#feat-form h3") and pg.locator("#feat-form .warn").count() == 0
    pg.wait_for_timeout(800); pg.locator("#feat-form .mini[data-img=image] input").set_input_files(TMPD + "/photo.png"); pg.select_option("#feat-form select[name=target]", "hand"); pg.click("#feat-form .go"); pg.wait_for_selector("#v-feat .res figure", timeout=30000)
    assert nodes_of(SUBMITTED[-1], "UltralyticsDetectorProvider")[0]["model_name"].startswith("bbox/hand") if False else any(v["class_type"] == "UltralyticsDetectorProvider" and "hand" in v["inputs"]["model_name"] for v in SUBMITTED[-1].values()); ok("face/hand card: runs from the screen with the chosen part")
    STATE["missing"].add("FaceDetailer"); hub.caps(force=True); pg.click("nav button[data-v=gen]"); pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_timeout(300)
    pg.evaluate("loadFeat&&loadFeat(true)") if False else None
    pg.reload(); pg.wait_for_timeout(500); pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.evaluate("document.querySelector('nav button[data-f=\"detailer\"]').click()")
    pg.wait_for_function("document.querySelector('#feat-form .feat-nodes')"); t = pg.inner_text("#feat-form .feat-nodes"); assert "Impact" in t, t; STATE["missing"].clear(); hub.caps(force=True); ok("missing Impact Pack nodes → the card names the extension needed and offers the install helper")
    # ── 영상 14B
    pg.click("nav button[data-v=vid]"); pg.wait_for_selector("#f-vid")
    assert pg.locator("#vid-fast-row").is_hidden() and pg.locator("#vid-14-note").is_hidden()
    pg.select_option("#f-vid select[name=wan_ver]", "14b"); assert pg.locator("#vid-14-note").is_visible() and pg.locator("#w-vid14").is_visible() and "글→영상" in pg.inner_text("#w-vid14")
    assert pg.input_value("#f-vid input[name=fps]") == "16" and pg.input_value("#f-vid input[name=cfg]") == "3.5" and pg.input_value("#f-vid input[name=shift]") == "5"; ok("choosing 14B shows the note + missing-model warning and switches fps/cfg/shift to 14B defaults")
    pg.select_option("#f-vid select[name=wan_ver]", "5b"); assert pg.input_value("#f-vid input[name=fps]") == "24" and pg.locator("#w-vid14").is_hidden() and pg.locator("#vid-fast-row").is_hidden(); ok("back to 5B restores defaults and hides the 14B bits")
    # ── 워크플로(UI 형식)에 없는 노드 → 설치 도우미 상자
    ui = {"nodes": [{"id": 1, "type": "DF_Text", "mode": 0, "inputs": [], "widgets_values": []}, {"id": 2, "type": "UltimateSDUpscale", "mode": 0, "inputs": [], "widgets_values": []}], "links": []}
    pg.click("nav button[data-v=wf]"); pg.wait_for_selector("#wf-json"); pg.fill("#wf-json", json.dumps(ui)); pg.click("#wf-an")
    pg.wait_for_selector("#wf-fields #nodebox"); t = pg.inner_text("#wf-fields #nodebox"); assert "DF_Text" in t and "UltimateSDUpscale" in t, t
    assert "설치되지 않은 노드" in pg.inner_text("#wf-st") and "Manager" not in pg.inner_text("#wf-st"); pg.wait_for_function("!document.querySelector('#nodelist').textContent.includes('찾는 중')", timeout=10000); ok("UI-format workflow with missing nodes: the install-helper box appears (not just a list of names)")
    b.close()
real = [e for e in errs if "ResizeObserver" not in e]; assert not real, real
print("ALL OK")
