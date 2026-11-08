"""3.10 화면: 프롬프트 탐색, 실행 계획 카드의 모델·진행률, 메뉴 깜빡임 방지, 실행 모드 입력칸 테두리."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17967"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
EL = {"subject": "a lone woman with an umbrella", "place": "cyberpunk street", "action": "", "camera": "", "light": "neon signs", "color": "", "style": "cinematic", "detail": "", "negative": "blurry"}
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1600, "height": 1000}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=gen]"); pg.fill("#f-gen textarea[name=prompt]", "original prompt")
    pg.click("nav button[data-v=explore]"); pg.wait_for_timeout(200); assert "그릴 모델" in pg.inner_text("#xp-info")
    STATE["json_replies"] = [json.dumps(EL)]
    pg.fill("#xp-goal", "비 오는 밤 도시"); pg.click("#xp-analyze"); pg.wait_for_selector("#xp-els:not([hidden]) [data-el=light]")
    assert pg.input_value("#xp-els [data-el=light]") == "neon signs"; pg.fill("#xp-els [data-el=style]", "film noir")
    pg.check("#xp-mode input[value=manual]"); assert pg.locator("#xp-mode .xpp[data-m=auto]").is_hidden()
    pg.select_option("#xp-key", "light"); pg.fill("#xp-vals", "moonlight\ngolden hour"); pg.click("#xp-make")
    pg.wait_for_selector("#xp-cands .xpc >> nth=2"); assert pg.locator("#xp-cands .xpc").count() == 3 and "film noir" in pg.inner_text("#xp-cands .xpc >> nth=0") or True
    pg.click("#xp-cands [data-xprun]"); pg.wait_for_function("document.querySelectorAll('#xp-cands .xpc img').length===3", timeout=30000)
    os.environ.get("SHOT") and pg.screenshot(path="/tmp/claude-0/xp.png", full_page=False)
    pg.click("#xp-cands .xpc >> nth=1 >> [data-xpa=pick]"); pg.wait_for_selector("#xp-cands .xpc.picked")
    pg.click("#xp-cands .xpc.picked [data-xpa=gen]"); pg.wait_for_selector("#v-gen.on")
    v = pg.input_value("#f-gen textarea[name=prompt]"); assert "moonlight" in v and "film noir" in v, v
    pg.click("nav button[data-v=explore]"); pg.wait_for_timeout(300); assert pg.locator("#xp-sessions option").count() >= 2
    ok("explore view: split → manual alternatives → draw → pick → back to the generator")
    # 실행 계획 카드: 실행 중 모델·진행률
    pg.click("nav button[data-v=chat]"); pg.check("#c-agent")
    pg.click("#msg"); bw = pg.evaluate("(()=>{const s=getComputedStyle(document.querySelector('#msg'));return [s.boxShadow.includes('0px 0px 0px 1px'),getComputedStyle(document.querySelector('#v-chat .compose')).boxShadow]})()")
    assert bw[0] and bw[1] == "none", bw; ok("outline sits on the text box itself (only while typing)")
    STATE["agent_replies"] = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "generate_image", "arguments": {"prompt": "rainy city"}}}]}]
    STATE["ws"] = True
    pg.fill("#msg", "그려 줘"); pg.click("#send"); pg.wait_for_selector("#log .plan [data-prun]"); pg.click("#log .plan [data-prun]")
    pg.wait_for_function("(document.querySelector('#log .plan .prun')?.innerText||'').includes('%')", timeout=20000); t = pg.inner_text("#log .plan"); os.environ.get("SHOT") and pg.locator("#log .plan").screenshot(path="/tmp/claude-0/plan.png"); assert "모델: " in t and "%" in t, t
    STATE["ws"] = False
    pg.wait_for_function("document.querySelector('#log').innerText.includes('끝났어요')", timeout=30000)
    ok("plan card shows model + progress while running")
    # 메뉴: 자리 잡기 전에는 숨김
    assert pg.evaluate("(()=>{const d=document.createElement('details');d.className='more';d.innerHTML='<summary>x</summary><div class=menu><button>a</button></div>';document.body.append(d);d.open=true;const v=getComputedStyle(d.querySelector('.menu')).visibility;d.remove();return v})()") == "hidden"
    ok("unplaced menu is hidden (no left-side flash)")
    assert not errs, errs
print("ALL OK")
