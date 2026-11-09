"""대화 목록(저장·새 대화·검색·이름·삭제·내보내기), 테마·단축키, 진단 파일 버튼."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time
os.environ["TEST_HUB_PORT"] = "17896"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 1000}, accept_downloads=True); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept(d.default_value if d.type == "prompt" else None))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    pg.evaluate("localStorage.setItem('chat', JSON.stringify([{role:'user',content:'예전 대화 질문'},{role:'assistant',content:'예전 대화 답'}]))")
    pg.reload(); pg.wait_for_timeout(500); None
    pg.wait_for_function("document.querySelectorAll('#cl-list .ci').length==1"); assert "예전 대화" in pg.inner_text("#log") and pg.evaluate("localStorage.getItem('chat')") == "[]"; ok("old single browser-saved chat moves into the list and opens")
    pg.wait_for_function("document.querySelectorAll('#llm option').length>0")
    pg.click("#cl-new"); assert pg.locator("#log .m").count() == 0 and pg.locator("#cl-list .ci").count() == 1; ok("[새 대화] starts empty and keeps the previous conversation in the list")
    pg.fill("#msg", "안녕! 자기소개 해줘"); pg.press("#msg", "Enter"); pg.wait_for_function("document.querySelectorAll('#cl-list .ci').length==2", timeout=10000)
    assert "안녕하세요" in pg.inner_text("#log"); first = pg.locator("#cl-list .ci").first; assert "안녕! 자기소개" in first.inner_text() and "on" in first.get_attribute("class"); ok("a conversation is saved automatically after the reply, titled from the first question")
    pg.fill("#msg", "한 마디 더"); pg.keyboard.press("Control+Enter"); pg.wait_for_function("document.querySelectorAll('#log .m.user').length==2", timeout=10000); ok("Ctrl+Enter sends from the chat box")
    pg.locator("#cl-list .ci", has_text="예전 대화").click(); pg.wait_for_function("document.querySelector('#log').innerText.includes('예전 대화 답')"); assert "안녕하세요" not in pg.inner_text("#log"); ok("clicking an old conversation opens it")
    pg.fill("#cl-q", "자기소개"); pg.wait_for_function("document.querySelectorAll('#cl-list .ci').length==1"); assert "안녕! 자기소개" in pg.inner_text("#cl-list"); pg.fill("#cl-q", ""); pg.wait_for_function("document.querySelectorAll('#cl-list .ci').length==2"); ok("search narrows the list")
    pg.locator("#cl-list .ci", has_text="예전 대화").hover(); pg.locator("#cl-list .ci", has_text="예전 대화").locator("[data-ren]").click(force=True)
    pg.wait_for_timeout(300)
    with pg.expect_download() as dl: pg.click("#cl-export")
    d = dl.value; txt = open(d.path(), encoding="utf-8").read(); assert d.suggested_filename.endswith(".md") and "예전 대화 답" in txt and "**AI**" in txt; ok("export saves the open conversation as markdown")
    pg.locator("#cl-list .ci", has_text="안녕! 자기소개").hover(); pg.locator("#cl-list .ci", has_text="안녕! 자기소개").locator("[data-del]").click(force=True)
    pg.wait_for_function("document.querySelectorAll('#cl-list .ci').length==1"); ok("delete (after confirm) removes one conversation only")
    pg.click("#cl-toggle"); assert pg.locator("#clist").is_hidden(); pg.reload(); pg.wait_for_timeout(500); assert pg.locator("#clist").is_hidden(); pg.click("#cl-toggle"); assert pg.locator("#clist").is_visible(); ok("the list can be hidden; the choice is remembered")
    # ── 결과 카드: 더 보기 메뉴 + 비슷하게 여러 장
    pg.click("nav button[data-v=gen]"); pg.wait_for_function("LISTS.checkpoints.length>0"); pg.fill("#f-gen textarea[name=prompt]", "1girl, red jacket"); pg.fill("#f-gen input[name=n]", "1") if pg.locator("#f-gen input[name=n]").count() else None
    pg.click("#f-gen .go"); pg.wait_for_selector("#v-gen .res figure", timeout=30000)
    cap = pg.locator("#v-gen .res figcaption").first; vis = [x.strip() for x in cap.locator(":scope > a, :scope > button, :scope > details > summary").all_inner_texts()]; assert vis == ["저장", "편집으로", "업스케일", "같은 설정으로", "영상으로", "더 보기"], vis
    assert pg.locator("#v-gen .res .more .menu").first.is_hidden(); ok("result card shows 저장 / 편집으로 / 업스케일 / 같은 설정으로 / 영상으로 + [더 보기]")
    pg.locator("#v-gen .res .more summary").first.click(); pg.wait_for_function("getComputedStyle(document.querySelector('#v-gen .res .more .menu')).visibility==='visible'", timeout=3000); menu = [x.strip() for x in pg.locator("#v-gen .res .more .menu button").first.locator("xpath=..").locator("button").all_inner_texts()]; assert menu == ["여러 장 변형", "캐릭터·스타일로 저장", "사진 편집기로", "배경 지우기", "정보", "폴더 열기"], menu
    mb = pg.evaluate("(()=>{const r=document.querySelector('#v-gen .res .more[open] .menu').getBoundingClientRect();return [r.top,r.bottom,innerHeight]})()"); assert mb[0] >= 0 and mb[1] <= mb[2], mb; ok("menu stays fully on screen")
    pg.mouse.click(5, 5); assert pg.locator("#v-gen .res .more[open]").count() == 0; ok("[더 보기] holds the rest and closes when you click elsewhere")
    n0 = len(SUBMITTED); pg.locator("#v-gen .res .more summary").first.click(); pg.locator("#v-gen .res button[data-to=var]").first.click(); pg.wait_for_selector("#v-gen .varbar")
    pg.select_option("#v-gen .varbar .v-lv", "0.65"); pg.select_option("#v-gen .varbar .v-n", "2"); pg.click("#v-gen .varbar .v-go"); pg.wait_for_function("document.querySelectorAll('#v-gen .res .batch').length==2", timeout=40000)
    g = SUBMITTED[-1]; ks = [n["inputs"] for n in g.values() if n["class_type"] == "KSampler"][0]; assert abs(ks["denoise"] - 0.65) < 1e-6 and any(n["class_type"] == "VAEEncode" for n in g.values()) and len(SUBMITTED) - n0 == 2, (ks, len(SUBMITTED) - n0)
    assert pg.locator("#v-gen .varbar").count() == 0; ok("variation: starts from the picked image at the chosen strength, makes the chosen number of images, panel tidies up")
    # ── 테마
    pg.click("nav button[data-v=conf]"); pg.wait_for_timeout(400)
    pg.check("#theme-pick input[value=dark]"); dark = pg.evaluate("getComputedStyle(document.body).backgroundColor"); pg.check("#theme-pick input[value=light]"); light = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    assert dark != light and pg.evaluate("document.documentElement.dataset.theme") == "light"; pg.reload(); pg.wait_for_timeout(300); assert pg.evaluate("document.documentElement.dataset.theme") == "light" and pg.evaluate("getComputedStyle(document.body).backgroundColor") == light; ok("light theme applies and is remembered across reloads (no flash: set before first paint)")
    pg.screenshot(path=os.environ.get("SHOTDIR", "/tmp") + "/light_setup.png")
    pg.click("nav button[data-v=conf]"); pg.wait_for_timeout(500); pg.evaluate("document.querySelector('#cs-nav button[data-pane=ui]').click()"); pg.check("#theme-pick input[value=dark]"); assert pg.evaluate("document.documentElement.dataset.theme") == "dark"
    # ── 단축키 /
    pg.click("nav button[data-v=gal]"); pg.keyboard.press("/"); assert pg.evaluate("document.activeElement.id") == "gal-q"; ok("'/' jumps to the search box")
    # ── 진단
    pg.click("nav button[data-v=conf]"); pg.wait_for_timeout(500); pg.evaluate("document.querySelector('#cs-nav button[data-pane=diag]').click()")
    with pg.expect_download() as dl: pg.click("#diag-go")
    assert dl.value.suggested_filename.endswith(".zip"); ok("diagnostic zip downloads from the screen")
    b.close()
real = [e for e in errs if "ResizeObserver" not in e]; assert not real, real
print("ALL OK")
