import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17890"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: print("PAGEERR", e)); pg.on("console", lambda m: print("CONSOLE", m.type, m.text[:200]) if m.type == "error" else None)
    pg.goto(B + "/"); pg.wait_for_timeout(600); None
    print("typeof", pg.evaluate("[typeof startInit, typeof show, typeof qPoll, typeof btInit, typeof miLoad, typeof coachMount]")); pg.click("nav button[data-v=start]"); pg.wait_for_timeout(1500)
    print(pg.inner_html("#st-goals")[:300]); print(pg.evaluate("document.querySelector('#v-start').className"))
