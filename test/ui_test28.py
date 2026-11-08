"""메모리 부족 안내가 화면에 나오고, 버튼이 동작하며, 다음 실행 때 사라진다."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17893"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
freed = []; hub.free_comfy = lambda: freed.append(1); hub.free_ollama = lambda: None
orig = hub.do_gen
def bad(p, J): raise RuntimeError("CUDA out of memory. Tried to allocate 2 GiB")
hub.do_gen = bad
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1300, "height": 900}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="gen"]'); pg.fill("#f-gen textarea[name=prompt]", "1girl"); pg.click("#f-gen .go")
    pg.wait_for_selector("#v-gen .oom", timeout=15000)
    t = pg.inner_text("#v-gen .oom"); assert "메모리가 모자라" in t and "해상도" in t and pg.locator("#v-gen .oom li").count() == 3, t; ok("guide with 3 tips shows under the status bar")
    pg.click("#v-gen [data-memfree]"); pg.wait_for_function("document.querySelector('#v-gen .mf-st').textContent.includes('비웠어요')"); assert freed; ok("memory-free button works")
    pg.locator("#v-gen .jobbar").screenshot(path="/tmp/tt/oom.png")
    hub.do_gen = orig; pg.click("#f-gen .go"); pg.wait_for_function("document.querySelectorAll('#v-gen .oom').length==0", timeout=15000); ok("guide disappears on the next run")
    print("page errors:", errs); assert not errs
print("ALL OK")
