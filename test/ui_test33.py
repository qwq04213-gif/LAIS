"""얼굴·손 자동 보정: 감지 노드가 없을 때 [설치] 버튼이 뜨고(공개 목록 없이도), 고정한 커밋으로 받는다."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, time, urllib.request
os.environ["TEST_HUB_PORT"] = "17899"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
STATE["missing"].add("UltralyticsDetectorProvider"); hub.caps(True)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_timeout(600)
    pg.evaluate("document.querySelector('nav button[data-f=\"detailer\"]').click()"); pg.wait_for_selector("#feat-form .ninst", timeout=8000)
    t = pg.inner_text("#feat-form"); assert "UltralyticsDetectorProvider" in t and "[설치]" in t and "Subpack" in t, t; ok("missing detector node → [설치] button for Impact Subpack is shown")
    seen = []
    class Stop(Exception): pass
    orig = urllib.request.urlopen
    def fake(url, *a, **k):
        u = url if isinstance(url, str) else url.full_url
        if "github.com" not in u: return orig(url, *a, **k)
        seen.append(u); raise Stop()
    urllib.request.urlopen = fake
    pg.on("dialog", lambda d: d.accept())
    try:
        pg.click("#feat-form .ninst")
        for _ in range(50):
            if seen: break
            time.sleep(0.1)
    finally: urllib.request.urlopen = orig
    assert seen and seen[0] == hub.SUBPACK_REPO + "/archive/50c7b71a6a224734cc9b21963c6d1926816a97f1.zip", seen; ok("button downloads the reviewed, pinned commit")
    b.close()
assert not errs, errs
print("ALL OK")
