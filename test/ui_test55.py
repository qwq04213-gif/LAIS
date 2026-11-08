"""3.9 화면: 대화 실행 모드, 작업 관리자, 펼침 메뉴 위치(FHD), 갤러리 순서."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17965"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
T = os.environ.get("TMPDIR", "/tmp")
hub.gpu_live = lambda: {"used_mb": 6000, "total_mb": 12288, "util": 55, "temp": 61, "power": 150, "power_max": 300}
d = hub.OUT / "생성"; d.mkdir(parents=True, exist_ok=True)
for i in range(30): Image.new("RGB", (512, 512), (i * 8, 100, 200)).save(d / f"2026-{i:03d}-gen-0.png")
Image.new("RGB", (800, 600), (40, 120, 220)).save(T + "/p55.png")
def inview(pg, sel_js):
    return pg.evaluate(f"(()=>{{const m={sel_js};const r=m.getBoundingClientRect();const W=document.documentElement.clientWidth,H=innerHeight;return r.width>0&&r.left>=0&&r.top>=0&&r.right<=W+0.5&&r.bottom<=H+0.5}})()")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1920, "height": 1080}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    # 1) 사이드바: 기록 갤러리가 대화 바로 아래
    assert pg.eval_on_selector_all("#rail nav .ngt", "e=>e.map(x=>x.textContent)")[:3] == ["처음", "대화", "내 작업"]; ok("gallery group moved up")
    # 2) 사진 편집기 '다른 화면으로' 메뉴가 FHD 오른쪽 끝에서 잘리지 않아요
    pg.click("nav button[data-v=photo]"); pg.set_input_files("#pe-file", T + "/p55.png"); pg.wait_for_timeout(300)
    pg.click("#v-photo details.more > summary"); pg.wait_for_timeout(150)
    assert inview(pg, "document.querySelector('#v-photo details.more[open] .menu')"); ok("photo editor menu stays inside 1920px")
    pg.mouse.click(900, 600)
    # 3) 갤러리 ⋯ 메뉴: 오른쪽 끝·맨 위·맨 아래 칸에서도 화면 안
    pg.click("nav button[data-v=gal]"); pg.wait_for_selector("#gal-grid .gt"); pg.wait_for_timeout(300)
    idx = pg.evaluate("(()=>{const c=[...document.querySelectorAll('#gal-grid .gt')];const top=c[0].getBoundingClientRect().top;let k=0;c.forEach((x,i)=>{if(Math.abs(x.getBoundingClientRect().top-top)<5)k=i});return k})()")
    for where in ("top", "bottom"):
        pg.evaluate(f"(()=>{{const c=document.querySelectorAll('#gal-grid .gt')[{idx}+({idx}+1)*({1 if where=='bottom' else 0})];c.scrollIntoView({{block:'{'start' if where=='top' else 'end'}'}})}})()"); pg.wait_for_timeout(200)
        k = idx + (idx + 1) * (1 if where == "bottom" else 0)
        card = pg.locator("#gal-grid .gt").nth(k); card.hover(); card.locator(".gmore > summary").click(); pg.wait_for_timeout(150)
        js = f"document.querySelectorAll('#gal-grid .gt')[{k}].querySelector('.gmore .menu')"
        assert inview(pg, js), (where, pg.evaluate(f"JSON.stringify({js}.getBoundingClientRect())"))
        hit = pg.evaluate(f"(()=>{{const m={js};const r=m.getBoundingClientRect();const e=document.elementFromPoint(r.left+r.width/2,r.top+12);return m.contains(e)}})()"); assert hit, where
        card.locator(".gmore > summary").click()
    ok("gallery ⋯ menu fully visible at right/top/bottom edges")
    # 4) 작업 관리자
    pg.click("nav button[data-v=chat]"); pg.wait_for_selector("#gbars:not([hidden])", timeout=15000); pg.click("#gbars"); pg.wait_for_selector("#hwpanel:not([hidden]) .hwr")
    pg.wait_for_timeout(300); os.environ.get("SHOT") and pg.screenshot(path="/tmp/claude-0/hw.png")
    t = pg.inner_text("#hwpanel"); assert "testmodel:latest" in t and "ComfyUI" in t and "12.0 GB" in t, t
    r1, r2 = pg.evaluate("[JSON.stringify(document.querySelector('#gbars').getBoundingClientRect()),JSON.stringify(document.querySelector('#hwpanel').getBoundingClientRect())]")
    assert json.loads(r2)["left"] >= json.loads(r1)["right"], (r1, r2)
    f0 = STATE["freed"]; pg.click("#hwpanel [data-hw=comfy]"); pg.wait_for_timeout(500); assert STATE["freed"] > f0
    od = len(GEN); pg.click("#hwpanel [data-hw='ollama:testmodel:latest']"); pg.wait_for_timeout(500); assert any(g.get("keep_alive") == 0 and g.get("model") == "testmodel:latest" for g in GEN[od:]), GEN[od:]
    pg.keyboard.press("Escape"); assert pg.locator("#hwpanel").is_hidden(); ok("task manager opens beside the monitor, frees models")
    # 5) 실행 모드
    STATE["agent_replies"] = [{"role": "assistant", "content": "두 장 그릴게요.", "tool_calls": [{"function": {"name": "generate_image", "arguments": {"prompt": "rainy neon city", "count": 2}}}]}]
    pg.check("#c-agent")
    pg.fill("#msg", "비 오는 네온 도시 두 장"); pg.click("#send"); pg.wait_for_selector("#log .plan [data-prun]")
    assert "이미지 만들기 · 2장" in pg.inner_text("#log .plan")
    base = STATE["agentreq"][-1]; assert base["messages"][-1]["content"].startswith("비 오는")
    pg.click("#log .plan [data-prun]"); pg.wait_for_selector("#log .plan .pimgs img", timeout=30000); pg.wait_for_function("document.querySelector('#log').innerText.includes('끝났어요')", timeout=15000)
    assert pg.locator("#log .plan .pimgs img").count() == 2
    os.environ.get("SHOT") and pg.screenshot(path="/tmp/claude-0/agent.png")
    pg.click("#log .plan .pimgs img >> nth=0"); pg.wait_for_selector("#lb:not([hidden])"); pg.keyboard.press("Escape")
    pg.reload(); pg.wait_for_timeout(500); assert pg.is_checked("#c-agent"); ok("agent mode: plan card → run → results in chat, mode remembered")
    assert not errs, errs
print("ALL OK")
