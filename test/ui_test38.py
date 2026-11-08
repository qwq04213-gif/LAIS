"""바깥 캐시 옮기기 화면."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, tempfile, pathlib
os.environ["TEST_HUB_PORT"] = "17899"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
home = pathlib.Path(tempfile.mkdtemp(prefix="fakehome-")); pathlib.Path.home = classmethod(lambda c: home)
for k in ("HF_HUB_CACHE", "TORCH_HOME", "PIP_CACHE_DIR", "HF_HOME", "LOCALAPPDATA"): os.environ.pop(k, None)
(home / ".cache" / "torch").mkdir(parents=True); (home / ".cache" / "torch" / "m.pth").write_bytes(b"T" * 3000)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    msgs = []; pg.on("dialog", lambda d: (msgs.append(d.message), d.accept()))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="setup"]'); pg.wait_for_timeout(500)
    pg.click("#setup-nav button[data-pane=disk]"); pg.wait_for_selector("#cache-move", timeout=8000)
    assert "PyTorch" in pg.inner_text("#cachein"); ok("panel lists the cache with its real path")
    pg.screenshot(path="/tmp/tt/cachein.png")
    pg.click("#cache-move"); pg.wait_for_selector("#cachein p.hint:has-text('옮겼어요')", timeout=15000)
    assert msgs and "원래 폴더를 지워요" in msgs[-1] and not (home / ".cache" / "torch").exists() and (hub.CACHE_IN / "torch" / "m.pth").exists(); ok("confirm → moved, result text shown")
    assert not errs, errs
    b.close()
print("ALL OK")
