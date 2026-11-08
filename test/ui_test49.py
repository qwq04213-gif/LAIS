"""2.5: 탭을 갔다 와도 고른 모델 유지, 마우스 뒤로가기·단축키."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17935"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1300, "height": 900}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    # 이미지 생성: 두 번째 체크포인트를 고르고 탭을 오가도 유지
    pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(500)
    opts = pg.evaluate("[...document.querySelectorAll('#f-gen select[name=ckpt] option')].map(o=>o.value)"); assert len(opts) >= 2, opts
    pg.select_option("#f-gen select[name=ckpt]", opts[1])
    for v in ("chat", "gal", "setup", "gen"):
        pg.click(f"nav button[data-v={v}]"); pg.wait_for_timeout(250)
    pg.evaluate("window.dispatchEvent(new Event('focus'))"); pg.wait_for_timeout(500)
    assert pg.input_value("#f-gen select[name=ckpt]") == opts[1]; ok("gen: chosen checkpoint stays after visiting other tabs and refocusing")
    # 기타 기능: 모델 고르고 다른 기능·탭을 다녀와도 유지
    for fid in ("ipadapter", "detailer"):
        pg.evaluate(f"document.querySelector('nav button[data-f=\"{fid}\"]').click()"); pg.wait_for_function(f"document.querySelector('#feat-form').dataset.f==='{fid}'"); pg.wait_for_selector("#feat-form select[name=ckpt]"); pg.wait_for_timeout(500)
        fo = pg.evaluate("[...document.querySelectorAll('#feat-form select[name=ckpt] option')].map(o=>o.value)"); assert len(fo) >= 2, fo
        pg.select_option("#feat-form select[name=ckpt]", fo[1]); pg.fill("#feat-form input[name=steps], #feat-form input[name=denoise]", "0.33") if False else None
        picked = pg.input_value("#feat-form select[name=ckpt]"); globals()["pk_" + fid] = picked
    for fid in ("ipadapter", "detailer", "ipadapter"):
        pg.click("nav button[data-v=gal]"); pg.wait_for_timeout(200)
        pg.evaluate(f"document.querySelector('nav button[data-f=\"{fid}\"]').click()"); pg.wait_for_function(f"document.querySelector('#feat-form').dataset.f==='{fid}'"); pg.wait_for_timeout(600)
        assert pg.input_value("#feat-form select[name=ckpt]") == globals()["pk_" + fid], (fid, pg.input_value("#feat-form select[name=ckpt]"), globals()["pk_" + fid])
    ok("기타 기능: each feature remembers its own chosen model across features and tabs")
    # 마우스 뒤로가기·단축키
    for v in ("chat", "gen", "gal"):
        pg.click(f"nav button[data-v={v}]"); pg.wait_for_timeout(150)
    def cur(): return pg.evaluate("document.querySelector('.view.on').id")
    mb = lambda n: pg.evaluate("n=>{for(const t of ['mousedown','mouseup']){const ev=new MouseEvent(t,{button:n,bubbles:true,cancelable:true});document.dispatchEvent(ev)}}", n)
    assert cur() == "v-gal"; mb(3); pg.wait_for_timeout(150); assert cur() == "v-gen"; mb(3); pg.wait_for_timeout(150); assert cur() == "v-chat"; mb(4); pg.wait_for_timeout(150); assert cur() == "v-gen"; ok("mouse button 4 goes back, 5 goes forward through visited screens")
    pg.keyboard.press("Alt+ArrowLeft"); pg.wait_for_timeout(150); assert cur() == "v-chat"; pg.keyboard.press("Alt+ArrowRight"); pg.wait_for_timeout(150); assert cur() == "v-gen"; ok("Alt+Left / Alt+Right work the same")
    pg.keyboard.press("Alt+5"); pg.wait_for_timeout(150); assert cur() == "v-gal"; pg.keyboard.press("Alt+2"); pg.wait_for_timeout(150); assert cur() == "v-gen"; ok("Alt+number jumps to the main screens")
    pg.click("nav button[data-v=guide]"); pg.keyboard.press("?"); pg.wait_for_timeout(300); assert cur() == "v-conf" and pg.locator("#fold-input").is_visible(); ok("? opens the shortcut list")
    pg.click("nav button[data-v=gal]"); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('lb').hidden=false"); mb(3); pg.wait_for_timeout(150); assert pg.evaluate("document.getElementById('lb').hidden") and cur() == "v-gal"; ok("back button closes an open image viewer first")
    pg.click("nav button[data-v=conf]"); pg.click("#cs-nav button[data-pane=input]"); pg.uncheck("#opt-mouseback"); pg.click("nav button[data-v=chat]"); mb(3); pg.wait_for_timeout(150); assert cur() == "v-chat"; ok("mouse-back can be turned off in settings")
    assert not errs, errs
    b.close()
print("ALL OK")
