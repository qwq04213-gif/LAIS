import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17910"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
os.makedirs("/tmp/tt/audit", exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    for theme in ("dark", "light"):
        for w in (1500, 900):
            ctx = b.new_context(viewport={"width": w, "height": 1000}); pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(B + "/"); pg.evaluate(f"localStorage.setItem('theme','{theme}')"); pg.reload(); pg.wait_for_timeout(700)
            if pg.locator("#ackb").is_visible(): None
            views = pg.evaluate("[...document.querySelectorAll('nav button[data-v]')].map(b=>b.dataset.v)")
            for v in views:
                pg.click(f'nav button[data-v="{v}"]'); pg.wait_for_timeout(250)
                over = pg.evaluate("document.documentElement.scrollWidth>innerWidth+2")
                pg.screenshot(path=f"/tmp/tt/audit/{theme}-{w}-{v}.png")
                print(theme, w, v, "H-OVERFLOW" if over else "")
            print("errs", errs); ctx.close()
    b.close()
