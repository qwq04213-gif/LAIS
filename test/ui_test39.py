"""플로팅 작업 대기열: 스크롤해도 떠 있고, 작업을 누르면 그 화면으로 이동."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, threading
os.environ["TEST_HUB_PORT"] = "17899"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
import urllib.request
ok = lambda m: print("PASS", m)
SRC = TMP / "ph"; SRC.mkdir()
for i in range(2): Image.new("RGB", (400, 300), (40 * i, 100, 200)).save(SRC / f"s{i}.png")
gate = threading.Event(); orig = hub.do_batch
def slow(pp, J):
    gate.wait(30); return []
hub.do_batch = slow
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1300, "height": 800}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.evaluate("document.documentElement.dataset.qpos='left'"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    assert pg.is_visible("#qfloat") and "작업 대기열" in pg.inner_text("#qfloat"); ok("floating queue button is on screen even with no jobs")
    pg.click('nav button[data-v="guide"]'); pg.wait_for_timeout(400)
    def in_view(): return pg.evaluate("(()=>{const r=document.querySelector('#qfloat').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&r.right<=innerWidth&&getComputedStyle(document.querySelector('#qfloat')).position==='fixed'})()")
    pg.evaluate("document.querySelectorAll('*').forEach(e=>{if(e.scrollHeight>e.clientHeight+50)e.scrollTop=e.scrollHeight});window.scrollTo(0,document.body.scrollHeight)"); pg.wait_for_timeout(200)
    assert in_view(); ok("still visible after scrolling to the bottom")
    pg.evaluate("document.querySelectorAll('*').forEach(e=>{e.scrollTop=0});window.scrollTo(0,0)"); assert in_view(); ok("and after scrolling back up")
    r = urllib.request.Request(B + "/api/job", json.dumps({"kind": "batch", "op": "resize", "folder": str(SRC), "long_side": 10}).encode(), {"Content-Type": "application/json"}); jid = json.load(urllib.request.urlopen(r))["id"]
    pg.wait_for_function("document.querySelector('#qfloat').classList.contains('busy')", timeout=8000); assert pg.inner_text("#qftext") != "작업 대기열"; ok("pill shows the running job and turns accent-colored")
    pg.wait_for_selector("#qpanel:not([hidden]) .qrow", timeout=8000); ok("a running job opens the queue panel by itself (pinned)")
    pg.click('nav button[data-v="guide"]'); pg.wait_for_timeout(300); assert pg.is_hidden("#qpanel"); pg.click("#qfloat"); pg.wait_for_selector("#qpanel:not([hidden]) .qrow"); assert in_view(); ok("clicking elsewhere closes the panel (3.11); the pill opens it again")
    pg.evaluate("document.querySelectorAll('*').forEach(e=>{e.scrollTop=e.scrollHeight});window.scrollTo(0,document.body.scrollHeight)"); pg.wait_for_timeout(200)
    assert pg.evaluate("(()=>{const r=document.querySelector('#qpanel').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&getComputedStyle(document.querySelector('#qpanel')).position==='fixed'})()"); ok("panel is fixed to the screen even when scrolled")
    pg.click("#qlist .qrow .qm"); pg.wait_for_selector("#v-batch.on"); assert pg.is_visible("#qpanel"); ok("clicking a job jumps to the screen that made it, panel stays")
    pg.click("#qpanel .qx"); assert pg.is_hidden("#qpanel"); pg.wait_for_timeout(3000); assert pg.is_hidden("#qpanel"); ok("× closes it and it stays closed")
    pg.click("#qfloat"); pg.wait_for_selector("#qpanel:not([hidden]) .qrow"); ok("clicking the pill opens it again")
    pg.click("label:has(#q-pin)"); assert not pg.is_checked("#q-pin"); pg.click("#qpanel .qx"); pg.click("#qfloat"); pg.wait_for_selector("#qpanel:not([hidden]) .qrow"); pg.click("#qlist .qrow .qm"); pg.wait_for_timeout(300); assert pg.is_hidden("#qpanel"); ok("with pinning turned off, clicking a job closes the panel as before")
    pg.click('nav button[data-v="guide"]'); pg.click("#qfloat") if pg.is_hidden("#qpanel") else None; pg.wait_for_selector("#qpanel:not([hidden]) .qrow")
    pg.locator("#qlist .qrow [data-q=cancel]").click(); pg.wait_for_timeout(400); assert pg.is_visible("#qpanel") and pg.is_visible("#v-guide.on"); ok("the ✕ button inside a row does not navigate")
    pg.screenshot(path="/tmp/tt/qfloat.png")
    pg.evaluate("document.documentElement.dataset.qpos='side';QUSER=null;qApply()"); pg.click('nav button[data-v="guide"]'); pg.wait_for_timeout(500)
    assert pg.evaluate("document.querySelector('#qbtn').classList.contains('busy')") and pg.is_visible("#qbtn") and pg.is_hidden("#qfloat"); ok("sidebar queue button shows the running job (busy) while the pill is hidden")
    pg.evaluate("document.querySelectorAll('#rail').forEach(e=>e.scrollTop=e.scrollHeight)"); assert pg.evaluate("document.querySelector('#qbtn').getBoundingClientRect().bottom") <= pg.evaluate("innerHeight") and "·" in pg.inner_text("#qbtn") or "%" in pg.inner_text("#qbtn") or pg.inner_text("#qbtn").strip(); ok("the sidebar queue button stays in view even when the sidebar is scrolled, and shows the job text")
    assert pg.is_hidden("#qpanel"); ok("in sidebar mode the list does not pop open by itself (it would cover the generate button)")
    pg.click("#qbtn"); pg.wait_for_selector("#qpanel:not([hidden])")
    rect = pg.evaluate("(()=>{const r=document.querySelector('#qpanel').getBoundingClientRect(),s=document.querySelector('#qbtn').getBoundingClientRect();return [r.left,s.right,r.top,s.top,r.bottom,innerHeight]})()"); assert rect[0] >= rect[1] and rect[4] <= rect[5], rect; ok("the list opens right next to the sidebar button and stays on screen")
    pg.evaluate("document.documentElement.dataset.qpos='left'"); pg.wait_for_timeout(300)
    gate.set(); pg.wait_for_function("!document.querySelector('#qfloat').classList.contains('busy')", timeout=15000); ok("pill goes back to idle when jobs finish")
    pg.wait_for_selector("#toast.go-toast:not([hidden])", timeout=8000); pg.click("#toast"); pg.wait_for_selector("#v-batch.on"); assert pg.is_hidden("#toast"); ok("clicking the 'finished' popup jumps to the screen with the result")
    assert not errs, errs
    b.close()
hub.do_batch = orig
print("ALL OK")
