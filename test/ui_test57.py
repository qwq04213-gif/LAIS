"""3.11 화면: 탐색 화면의 생성 설정 빌려 오기·더 탐색 창·카드 정렬, 떠 있는 창 바깥 클릭 닫기, 바로 받기, 조명·깊이 기능 폼."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17969"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
hub.gpu_live = lambda: {"used_mb": 6000, "total_mb": 12288, "util": 55, "temp": 61, "power": 150, "power_max": 300}
EL = {"subject": "a cat", "place": "rooftop", "light": "neon signs", "style": "cinematic"}
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1700, "height": 1000}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    # 1) 생성 설정 빌려 오기
    pg.click("nav button[data-v=explore]"); pg.wait_for_selector("#xp-genbox #f-gen")
    assert pg.locator("#xp-genbox select[name=gengine]").is_visible() and pg.locator("#xp-genbox textarea[name=prompt]").is_hidden() and pg.locator("#xp-genbox .go").is_hidden()
    assert pg.locator("#xp-genbox [name^=lora]").count() >= 1, "LoRA picker present"
    pg.select_option("#xp-genbox input[name=w] >> xpath=..", None) if False else None
    pg.fill("#xp-genbox input[name=w]", "768")
    os.environ.get("SHOT") and pg.screenshot(path="/tmp/claude-0/xpgen.png")
    pg.click("nav button[data-v=gen]"); pg.wait_for_selector("#v-gen #f-gen"); assert pg.locator("#f-gen textarea[name=prompt]").is_visible() and pg.input_value("#f-gen input[name=w]") == "768"
    ok("explore borrows the full generator settings (model · LoRA · size) and gives them back")
    # 2) 후보 → 그리기 → 카드 정렬 → 더 탐색 창
    pg.click("nav button[data-v=explore]"); STATE["json_replies"] = [json.dumps(EL)]
    pg.fill("#xp-goal", "고양이"); pg.click("#xp-analyze"); pg.wait_for_selector("#xp-els [data-el=light]")
    pg.check("#xp-mode input[value=manual]"); pg.select_option("#xp-key", "light"); pg.fill("#xp-vals", "moonlight\ngolden hour"); pg.click("#xp-make")
    pg.wait_for_selector("#xp-cands .xpc >> nth=2"); pg.click("#xp-cands [data-xprun]"); pg.wait_for_function("document.querySelectorAll('#xp-cands .xpc img').length===3", timeout=30000)
    pg.wait_for_function("[...document.querySelectorAll('#xp-cands .xpc img')].every(i=>i.complete&&i.naturalWidth)"); pg.wait_for_timeout(300)
    os.environ.get("SHOT") and pg.screenshot(path="/tmp/claude-0/xp2.png", full_page=True)
    h0 = pg.evaluate("document.querySelectorAll('#xp-cands .xpc')[0].getBoundingClientRect().height"); iw = pg.evaluate("document.querySelector('#xp-cands .xpc img').getBoundingClientRect().width")
    pg.click("#xp-cands .xpc >> nth=1 >> details summary"); pg.wait_for_timeout(150)
    h1 = pg.evaluate("document.querySelectorAll('#xp-cands .xpc')[0].getBoundingClientRect().height"); assert abs(h0 - h1) < 1, (h0, h1)
    assert iw >= 370, iw
    g = pg.evaluate("(()=>{const r=document.querySelector('#xp-cands .xpgrid').getBoundingClientRect(),c=[...document.querySelectorAll('#xp-cands .xpgrid .xpc')].map(x=>x.getBoundingClientRect());return [r.left,r.right,Math.min(...c.map(x=>x.left)),Math.max(...c.map(x=>x.right))]})()")
    assert abs((g[2] - g[0]) - (g[1] - g[3])) < 4, g
    ok("cards don't stretch when a neighbour opens its prompt; bigger, centered")
    pg.click("#xp-cands .xpc >> nth=1 >> [data-xpa=more]"); pg.wait_for_selector("#xp-more:not([hidden])")
    assert pg.locator("#xp-more-img").is_visible() and "moonlight" in pg.inner_text("#xp-more-label")
    os.environ.get("SHOT") and pg.screenshot(path="/tmp/claude-0/modal.png")
    pg.click("#xp-more [data-xmn]"); assert pg.input_value("#xp-more-note") == "더 따뜻한 색감"
    STATE["json_replies"] = [json.dumps({"variants": [{"label": "따뜻", "changes": {"color": "warm"}}]})]
    pg.click("#xp-more-go"); pg.wait_for_selector("#xp-more", state="hidden"); pg.wait_for_selector("#xp-cands .xpr >> text=2차")
    assert "더 따뜻한 색감" in STATE["jsonreq"][-1]["messages"][-1]["content"]
    pg.click("#xp-cands .xpc >> nth=0 >> [data-xpa=more]"); pg.mouse.click(10, 10); pg.wait_for_selector("#xp-more", state="hidden")
    ok("'더 탐색' opens a styled in-app dialog (chips, count), closes on outside click")
    # 3) 알림/대기열 → 탐색 화면
    pg.click("nav button[data-v=gen]"); pg.evaluate("qGo({view:'explore',xp:XP.id})"); assert pg.locator("#v-explore").evaluate("e=>e.classList.contains('on')")
    ok("explore job notification opens the explore screen")
    # 4) 떠 있는 창 바깥 클릭
    pg.click("#qbtn"); pg.wait_for_selector("#qpanel:not([hidden])"); pg.mouse.click(900, 500); assert pg.locator("#qpanel").is_hidden()
    pg.click("#gbars"); pg.wait_for_selector("#hwpanel:not([hidden])"); assert "스튜디오가 쓰는" in pg.inner_text("#hwpanel"); pg.mouse.click(900, 500); assert pg.locator("#hwpanel").is_hidden()
    ok("queue / task manager close when clicking elsewhere")
    # 5) 바로 받기 (영상 모델 없음)
    pg.click("nav button[data-v=vid]"); pg.wait_for_selector("#w-vid:not([hidden]) .needdl [data-needgo]", timeout=10000)
    t = pg.inner_text("#w-vid .needdl"); assert "Wan 2.2" in t and "GB" in t, t
    pg.click("#w-vid [data-needgo]"); pg.wait_for_function("!document.querySelector('#w-vid .needdl .ndl').textContent.includes('Wan 2.2 영상 5B (')", timeout=10000)
    tk = req("/api/install"); assert any(x.get("mid") == "wan22-ti2v-5b" for x in tk), tk
    for x in tk:
        if x["state"] in ("queued", "running"): req("/api/install/cancel", {"id": x["id"]})
    ok("missing model → one-click download with inline status")
    # 6) 조명·깊이 기능 폼
    pg.evaluate("document.querySelector('nav button[data-f=\"relight\"]').click()"); pg.wait_for_selector("#feat-form h3"); assert "조명 바꾸기" in pg.inner_text("#feat-form h3")
    assert pg.locator("nav button[data-f=depth]").count() == 1; pg.wait_for_selector("#f-feat select[name=light]")
    assert pg.is_checked("#f-feat input[name=keep]") and pg.locator("#f-feat textarea[name=custom]").is_hidden()
    pg.select_option("#f-feat select[name=light]", "custom"); pg.wait_for_timeout(100); assert pg.locator("#f-feat textarea[name=custom]").is_visible()
    pg.evaluate("featForm('depth')"); pg.wait_for_selector("#f-feat select[name=out]"); assert pg.locator("#f-feat input[name=near]").is_hidden()
    pg.select_option("#f-feat select[name=out]", "cut"); pg.wait_for_timeout(100); assert pg.locator("#f-feat input[name=near]").is_visible()
    ok("relight / depth feature forms with conditional fields")
    assert not errs, errs
print("ALL OK")
