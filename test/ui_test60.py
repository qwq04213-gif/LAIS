"""3.13 화면: 구도 바꾸기·새 장면 폼(방법별 칸, 구조 모드는 생성 설정 함께 보냄), 영상 분석의 3D 카메라 버튼."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17976"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs, sent = [], []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 950}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("request", lambda r: sent.append(r.post_data) if r.url.endswith("/api/job") and r.method == "POST" else None)
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.evaluate("document.querySelector('nav button[data-f=\"recompose\"]').click()"); pg.wait_for_selector("#f-feat select[name=mode]")
    vis = lambda sel: pg.locator(sel).is_visible()
    assert vis("#f-feat select[name=az]") and not vis("#f-feat .mini[data-img=pose_ref]") and not vis("#f-feat textarea[name=scene]")
    pg.select_option("#f-feat select[name=mode]", "pose"); pg.wait_for_timeout(100); assert vis("#f-feat .mini[data-img=pose_ref]") and not vis("#f-feat select[name=az]")
    pg.select_option("#f-feat select[name=mode]", "scene"); pg.wait_for_timeout(100); assert vis("#f-feat textarea[name=scene]") and pg.is_checked("#f-feat input[name=keep_outfit]")
    pg.select_option("#f-feat select[name=mode]", "structure"); pg.wait_for_timeout(100); assert vis("#f-feat select[name=skind]") and not vis("#f-feat input[name=extra]")
    pg.evaluate("$('#f-feat .mini[data-img=image]').set('data:image/png;base64,'+btoa('x'))"); pg.fill("#f-feat textarea[name=prompt]", "a robot")
    pg.click("#f-feat .go"); pg.wait_for_timeout(800)
    body = json.loads([x for x in sent if x and '"feature":"recompose"' in x.replace(" ", "")][-1]); assert body["mode"] == "structure" and body["gen"]["gengine"], body.keys()
    ok("recompose form shows the right fields per method; structure mode sends the generator settings")
    pg.click("nav button[data-v=vana]"); assert pg.locator("#va-cam3d").is_visible(); ok("3D camera button in video analysis")
    assert not errs, errs
print("ALL OK")
