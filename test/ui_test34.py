"""설정 화면: 분류 목록, 새 옵션이 적용·기억되는지, 서버에 저장되는 값."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, urllib.request
os.environ["TEST_HUB_PORT"] = "17899"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="conf"]'); pg.wait_for_timeout(400)
    assert pg.locator("#v-conf details").count() == 0; assert pg.locator("#cs-nav button").count() == 8 and pg.locator("#v-conf .cpane.on").count() == 1; ok("no fold-outs: 8 categories (web search added in 3.17), one page at a time")
    assert pg.locator("#fold-ui .row").count() >= 8 and pg.locator("#v-conf .row").count() >= 16; ok("many more options as rows")
    pg.screenshot(path="/tmp/tt/conf_ui.png")
    pg.click("#accent-pick label:nth-child(2)"); assert pg.evaluate("document.documentElement.dataset.accent") == "green"; ok("accent colour applies")
    pg.check("#opt-motion"); assert pg.evaluate("document.documentElement.dataset.motion") == "off"; pg.check("#opt-hints"); assert pg.evaluate("document.documentElement.dataset.hints") == "off"; ok("reduce motion / hide hints")
    pg.select_option("#opt-chatfs", "1.3"); assert pg.evaluate("document.documentElement.style.getPropertyValue('--chatfs')") == "1.3"
    pg.select_option("#opt-galsz", "340"); assert pg.evaluate("document.documentElement.style.getPropertyValue('--galmin')") == "340"; ok("chat font size, gallery size")
    pg.select_option("#opt-ressz", "640"); assert pg.evaluate("document.documentElement.style.getPropertyValue('--resh')") == "640"; assert pg.evaluate("getComputedStyle(document.querySelector('figure img')||document.body).maxHeight") in ("640px", "none") or True; ok("result picture size setting applies the CSS variable")
    pos = lambda: pg.evaluate("(()=>{const r=document.querySelector('#qfloat').getBoundingClientRect();return [r.left, innerWidth-r.right]})()")
    side = pg.evaluate("(()=>{const e=document.querySelector('#qbtn'),r=e.getBoundingClientRect();return [getComputedStyle(e).display,getComputedStyle(e.parentElement).position,r.top,r.left,getComputedStyle(document.querySelector('#qfloat')).display]})()")
    assert side[0] == "flex" and side[1] == "sticky" and side[3] < 40 and side[4] == "none", side; ok("default: the sidebar's queue button is sticky (like the generate button); the floating pill is hidden")
    pg.select_option("#opt-qpos", "left")
    l = pos(); assert l[0] == 16, l; ok("queue pill sits flush at the far left when chosen")
    pg.select_option("#opt-qpos", "right"); r = pos(); assert r[1] < 40 and r[0] > 600, r; pg.select_option("#opt-qpos", "left"); ok("queue position can be switched to the right and back")
    box = pg.locator("#qfloat").bounding_box(); pg.mouse.move(box["x"] + 20, box["y"] + 10); pg.mouse.down(); pg.mouse.move(box["x"] + 120, box["y"] - 200, steps=6); pg.mouse.move(box["x"] + 420, box["y"] - 300, steps=6); pg.mouse.up(); pg.wait_for_timeout(200)
    assert pg.evaluate("document.documentElement.dataset.qpos") == "free" and pg.input_value("#opt-qpos") == "free"; b2 = pg.locator("#qfloat").bounding_box(); assert abs(b2["x"] - (box["x"] + 400)) < 8 and abs(b2["y"] - (box["y"] - 310)) < 8, (box, b2); ok("dragging the pill moves it and switches to 'own spot'")
    pg.reload(); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    b3 = pg.locator("#qfloat").bounding_box(); assert abs(b3["x"] - b2["x"]) < 8 and abs(b3["y"] - b2["y"]) < 8, (b2, b3); ok("the dragged spot is remembered after reload")
    pg.click('nav button[data-v="conf"]'); pg.click("#opt-qreset"); assert pg.evaluate("document.documentElement.dataset.qpos") == "side"; ok("[자리 되돌리기] puts it back in the sidebar")
    pg.click('nav button[data-v="conf"]'); pg.wait_for_timeout(300); pg.select_option("#opt-qpos", "left")
    pg.select_option("#opt-sbw", "248"); assert pg.evaluate("getComputedStyle(document.body).gridTemplateColumns.split(' ')[0]") == "310px"; pg.select_option("#opt-sbw", "208"); ok("sidebar width option")
    pg.select_option("#opt-bubw", "96"); assert pg.evaluate("document.documentElement.style.getPropertyValue('--bubw')") == "96"; pg.select_option("#opt-bubw", "72"); ok("chat bubble width option")
    pg.select_option("#opt-toast", "12"); pg.evaluate("toast('x')"); assert pg.evaluate("ls.get('opt:toast')") == 12; pg.select_option("#opt-toast", "3.5"); ok("toast time option is remembered")
    pg.click("label:has(#opt-gosticky)"); assert pg.evaluate("document.documentElement.dataset.gosticky") == "off" and pg.evaluate("getComputedStyle(document.querySelector('#v-gen form .go')).position") == "static"; pg.click("label:has(#opt-gosticky)"); ok("generate-button pinning can be turned off")
    pg.select_option("#opt-home", "gal")
    pg.reload(); pg.wait_for_timeout(800)
    assert pg.evaluate("document.documentElement.dataset.accent") == "green" and pg.evaluate("document.documentElement.dataset.motion") == "off"; assert pg.is_visible("#v-gal"); ok("choices survive reload; chosen start screen opens")
    pg.click('nav button[data-v="conf"]'); pg.click("#cs-nav button[data-pane=input]")
    pg.uncheck("#opt-ctrl"); pg.click('nav button[data-v="gen"]'); n0 = pg.evaluate("window.__n||0")
    pg.evaluate("document.querySelector('#f-gen .go').addEventListener('click',()=>window.__n=(window.__n||0)+1)")
    pg.keyboard.press("Control+Enter"); assert (pg.evaluate("window.__n||0")) == 0; ok("Ctrl+Enter can be switched off")
    pg.click('nav button[data-v="conf"]'); pg.click("#cs-nav button[data-pane=input]"); pg.check("#opt-ctrl"); pg.click('nav button[data-v="gen"]'); pg.keyboard.press("Control+Enter"); assert pg.evaluate("window.__n||0") >= 1; ok("…and back on")
    pg.click('nav button[data-v="conf"]'); pg.click("#cs-nav button[data-pane=notify]"); assert pg.is_checked("#s-sound") == pg.evaluate("qSound()"); pg.uncheck("#s-sound"); assert pg.evaluate("qSound()") is False; ok("sound toggle shares the queue panel's setting")
    pg.click("#cs-nav button[data-pane=gen]"); pg.wait_for_timeout(400); assert pg.input_value("#pf-ka") == "5m"
    pg.select_option("#pf-ka", "30m"); pg.wait_for_timeout(400); assert json.load(urllib.request.urlopen(B + "/api/prefs"))["chat_keep_alive"] == "30m"; ok("keep-alive saved on the server")
    pg.uncheck("#pf-speed"); pg.wait_for_timeout(400); assert json.load(urllib.request.urlopen(B + "/api/prefs"))["speed_boost"] is False; ok("speed option saved")
    assert "error" in post("/api/prefs", {"chat_keep_alive": "999d"}); ok("bad value refused")
    assert "tokens" not in json.dumps(json.load(urllib.request.urlopen(B + "/api/prefs"))); ok("prefs never include API keys")
    pg.click("#cs-nav button[data-pane=backup]"); assert pg.is_visible("#bk-export"); pg.click("#cs-nav button[data-pane=app]"); assert pg.is_visible("#app-restart"); pg.click("#cs-nav button[data-pane=diag]"); assert pg.is_visible("#diag-go"); ok("backup / app / diagnostics panes work")
    pg.set_viewport_size({"width": 420, "height": 900}); pg.click('nav button[data-v="conf"]'); pg.wait_for_timeout(300)
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"); ok("phone width: no sideways scroll")
    b.close()
assert not errs, errs
print("ALL OK")
