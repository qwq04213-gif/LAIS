"""설정 화면 분리 + UI 배율: 저장, 새로고침 유지, 가로 넘침 없음."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17898"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1280, "height": 800}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="setup"]'); assert pg.is_visible("#v-setup") and not pg.is_visible("#v-conf") and pg.locator("#v-setup #fold-app").count()==0; ok("설치와 모델 no longer holds settings folds")
    pg.click('nav button[data-v="conf"]'); assert pg.is_visible("#v-conf") and pg.is_visible("#ui-scale"); ok("설정 view has the scale control")
    for v in ["1", "1.25", "1.5"]:
        pg.click('nav button[data-v="conf"]'); pg.select_option("#ui-scale", v); pg.wait_for_timeout(150)
        assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ui').trim()") == v
        for view in ["conf", "setup", "gen", "chat", "gal"]:
            pg.click(f'nav button[data-v="{view}"]'); pg.wait_for_timeout(150)
            assert pg.evaluate("document.documentElement.scrollWidth<=innerWidth+1"), (v, view)
            assert pg.evaluate("(()=>{const n=document.querySelector('#rail nav');return n.scrollWidth<=n.clientWidth+1})()"), (v, view, "rail")
        ok(f"scale {v}: set, no sideways overflow in main views and rail")
    pg.click('nav button[data-v="conf"]'); pg.select_option("#ui-scale", "1.25"); pg.reload(); pg.wait_for_timeout(600)
    assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ui').trim()") == "1.25"
    pg.click('nav button[data-v="conf"]'); assert pg.input_value("#ui-scale") == "1.25"; ok("scale survives reload")
    print("page errors:", errs); assert not errs
print("ALL OK")
