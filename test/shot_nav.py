import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17886"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
T = os.environ["TMPDIR"]
with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h, n in ((1400, 900, "nav_d"), (420, 800, "nav_m")):
        pg = b.new_context(viewport={"width": w, "height": h}).new_page(); pg.goto(B + "/"); pg.wait_for_timeout(500)
        None; pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(300); pg.screenshot(path=f"{T}/{n}.png")
    b.close()
