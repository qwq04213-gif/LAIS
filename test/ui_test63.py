"""3.17 화면: 한 줄 너비 유지, 글꼴, 대화 입력창(테두리·자동 높이), 실행 계획 이미지 보존, Ctrl+K 검색, 웹 검색 설정, 영상 미리보기, 프롬프트 탐색 틀, LoRA 사진 불리기, 되묻기 칩."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, io, subprocess, urllib.parse
os.environ["TEST_HUB_PORT"] = "17979"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
vd = hub.OUT / "영상"; vd.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x120:r=12:d=2", "-pix_fmt", "yuv420p", str(vd / "v.mp4")], check=True)
gd = hub.OUT / "생성"; gd.mkdir(parents=True, exist_ok=True); Image.new("RGB", (300, 300), (200, 30, 30)).save(gd / "red_cat.png")
(gd / "red_cat.png.json").write_text(json.dumps({"prompt": "a red cat on a sofa"}), encoding="utf-8")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1600, "height": 950}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    assert pg.locator("#ack").count() == 0
    # 설정: 한 줄 너비 · 글꼴
    pg.click("nav button[data-v=conf]"); pg.wait_for_timeout(300)
    pg.select_option("#opt-pagew", "1240"); pg.select_option("#opt-font", "Malgun Gothic")
    pg.reload(); pg.wait_for_timeout(700)
    css = pg.evaluate("[getComputedStyle(document.documentElement).getPropertyValue('--pagew').trim(),getComputedStyle(document.body).fontFamily]")
    assert css[0] == "1240px" and "Malgun Gothic" in css[1], css
    ok("page width + font survive restart (applied at start)")
    # 모델 종류별 칸: Qwen-Image 2.1 · MOSS 는 SDXL 체크포인트 칸을 숨겨요
    pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(300)
    for g in ("qwenimg", "moss"):
        pg.select_option("#f-gen select[name=gengine]", g); pg.wait_for_timeout(200)
        assert not pg.is_visible("#f-gen select[name=ckpt]") and pg.is_visible("#f-gen select[name=fx_model]"), g
    pg.select_option("#f-gen select[name=gengine]", "sdxl"); pg.wait_for_timeout(200); assert pg.is_visible("#f-gen select[name=ckpt]")
    ok("Qwen-Image 2.1 / MOSS hide the SDXL checkpoint field")
    # 대화 입력창
    pg.click("nav button[data-v=chat]"); pg.wait_for_timeout(300)
    bc = lambda: pg.evaluate("getComputedStyle(document.querySelector('#msg')).borderTopColor")
    pg.click("#c-agent"); pg.click("nav button[data-v=gal]"); pg.click("nav button[data-v=chat]"); pg.wait_for_timeout(200)
    idle = bc(); pg.click("#msg"); focus = bc(); assert idle != focus, (idle, focus)
    h1 = pg.evaluate("document.querySelector('#msg').offsetHeight"); pg.fill("#msg", "\n".join(["줄"] * 6)); pg.dispatch_event("#msg", "input")
    h2 = pg.evaluate("document.querySelector('#msg').offsetHeight"); pg.fill("#msg", ""); pg.dispatch_event("#msg", "input")
    h3 = pg.evaluate("document.querySelector('#msg').offsetHeight"); assert h2 > h1 and h3 == h1, (h1, h2, h3)
    ok("chat box: border only when focused (also in run mode), grows with text and shrinks back")
    # 되묻기 칩 · 계획 이미지 보존
    STATE.setdefault("agent_replies", []).append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "ask_user", "arguments": {"question": "어떤 스타일로 할까요?", "options": ["실사", "애니"]}}}]})
    pg.fill("#msg", "예쁜 여성"); pg.click("#send"); pg.wait_for_selector("#log .copts [data-opt]")
    assert pg.locator("#log .copts .chip").count() == 3
    STATE["agent_replies"].append({"role": "assistant", "content": "그릴게요", "tool_calls": [{"function": {"name": "generate_image", "arguments": {"prompt": "a woman, anime style"}}}]})
    pg.click("#log .copts [data-opt='애니']"); pg.wait_for_selector("#log [data-prun]"); pg.click("#log [data-prun]")
    pg.wait_for_selector("#log .pimgs img", timeout=30000); pg.wait_for_timeout(800)
    pg.click("#cl-new"); pg.wait_for_timeout(300); pg.click("#cl-list .ci >> nth=0"); pg.wait_for_selector("#log .pimgs img", timeout=5000)
    ok("ask_user chips answer in one click; plan result images stay after switching chats")
    # Ctrl+K 검색
    pg.keyboard.press("Control+k"); pg.wait_for_selector("#sp[open]"); pg.fill("#sp-q", "업스케일"); pg.wait_for_selector("#sp-list .sp-i")
    pg.keyboard.press("Enter"); pg.wait_for_selector("#v-up.on")
    pg.keyboard.press("Control+k"); pg.fill("#sp-q", "red_cat"); pg.wait_for_selector("#sp-list .sp-g:has-text('기록 갤러리')")
    pg.keyboard.press("Escape"); pg.keyboard.press("Control+k"); pg.fill("#sp-q", "글꼴"); pg.wait_for_selector("#sp-list .sp-g:has-text('설정')"); pg.keyboard.press("Enter")
    pg.wait_for_selector("#v-conf.on"); pg.wait_for_timeout(300); assert pg.locator("#fold-ui.on").count() == 1
    ok("Ctrl+K search: menu → opens screen, gallery prompt match, settings row jump")
    pg.click("#cs-nav button[data-pane=web]"); pg.wait_for_selector("#ws-st:has-text('꺼져')")
    ok("web search settings pane shows SearXNG state")
    # 영상 미리보기 · 프롬프트 탐색 틀
    for v, sel, prev in (("vana", "#va-video", "#va-prev"), ("vrestore", "#vr-video", "#vr-prev"), ("audio", "#au-src", "#au-prev")):
        pg.click(f"nav button[data-v={v}]"); pg.wait_for_selector(f"{sel} option[value*='v.mp4']", state="attached")
        pg.select_option(sel, label="v.mp4") if v != "vana" else None; pg.wait_for_timeout(300)
        assert pg.is_visible(prev) and "v.mp4" in (pg.get_attribute(prev, "src") or ""), v
    pg.click("nav button[data-v=explore]"); pg.wait_for_timeout(400)
    assert pg.evaluate("getComputedStyle(document.querySelector('#v-explore')).display") == "grid" and pg.is_visible("#xp-empty") and pg.locator("#xp-genbox #f-gen").count() == 1
    ok("video/sound previews under the picker; explore uses the two-column layout with the gen form on the left")
    # LoRA 사진 불리기
    pg.click("nav button[data-v=lora]"); pg.wait_for_timeout(300)
    pg.fill("#lo-name", "t"); pg.click("#lo-create"); pg.wait_for_selector("#lo-data:not([hidden])")
    T = os.environ.get("TMPDIR", "/tmp"); Image.new("RGB", (600, 600), (40, 90, 160)).save(T + "/la.png"); pg.set_input_files("#lo-in", [T + "/la.png"])
    pg.wait_for_selector("#lo-grid .lo-c"); pg.click("#lo-aug > summary"); pg.fill("#lo-acount", "4"); pg.click("#lo-aug-go"); pg.wait_for_selector("#lo-cands .lo-cand", timeout=20000)
    pg.locator("#lo-cands .lo-cand input").nth(0).uncheck(); pg.click("#lo-ckeep"); pg.wait_for_timeout(800)
    assert pg.locator("#lo-grid .lo-c").count() == 4 and pg.locator("#lo-cands .lo-cand").count() == 0
    ok("LoRA augment: candidates → keep checked (3) → set has 4 photos")
    assert not errs, errs
print("ALL OK")
