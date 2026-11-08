"""2026.10.18.10: 접이식 섹션, GPU 상태 바."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, stat
os.environ["TEST_HUB_PORT"] = "17872"
sys.path.insert(0, BASE + "/test")
fake = Path = None
from pathlib import Path
FD = Path(os.environ["TMPDIR"]) / "fakebin"; FD.mkdir(exist_ok=True)
(FD / "nvidia-smi").write_text('#!/bin/sh\necho "RTX 4070, 12282" | grep -q name && true\nif echo "$@" | grep -q "memory.used"; then echo "10400, 12282, 63, 71, 140.5, 200.0"; else echo "NVIDIA GeForce RTX 4070, 12282"; fi\n')
(FD / "nvidia-smi").chmod(0o755)
os.environ["PATH"] = str(FD) + os.pathsep + os.environ["PATH"]
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(500); None; pg.wait_for_timeout(500)
    # GPU 바
    pg.wait_for_selector("#gbars:not([hidden]) .gb", timeout=8000)
    t = pg.inner_text("#gbars"); assert "VRAM" in t and "10.2 / 12.0 GB" in t and "63%" in t and "71°C" in t and "140 / 200 W" in t, t
    w = pg.locator("#gbars .gb").nth(0).locator(".gl i").evaluate("e=>e.className")
    assert w == "warm", w   # 10400/12282 = 84.7% -> 주황
    yv = pg.locator("#ver").bounding_box()["y"]; yg = pg.locator("#gbars").bounding_box()["y"]; ys = pg.locator("#stat").bounding_box()["y"]
    assert yv < yg < ys, (yv, yg, ys); ok("GPU bars (VRAM/usage/temp/power) sit under the version text, colored by load")
    pg.screenshot(path=os.environ["TMPDIR"]+"/gpu.png",clip={"x":0,"y":0,"width":260,"height":600})
    # 접기
    pg.click("nav button[data-v=setup]"); pg.wait_for_timeout(500)
    st = lambda i: pg.locator("#"+i).is_visible()
    assert st("fold-rec") and not st("fold-disk") and not st("fold-manage")
    assert pg.locator("#disk-scan").is_hidden() and pg.locator("#manage").is_hidden()
    pg.click("#setup-nav button[data-pane=disk]"); assert pg.locator("#disk-scan").is_visible()
    pg.click("#setup-nav button[data-pane=rec]"); assert pg.locator("#cat-img").is_visible()
    pg.click("#setup-nav button[data-pane=disk]")
    pg.reload(); pg.wait_for_timeout(500); pg.click("nav button[data-v=setup]"); pg.wait_for_timeout(300)
    assert st("fold-disk") and not st("fold-rec"); ok("setup tab: recommended / disk / installed sections fold, and the choice is remembered after reload")
    pg.click("#setup-nav button[data-pane=rec]"); pg.wait_for_timeout(200); assert pg.locator("#cat-img .card, #cat-img *").count() > 0
    pg.click("#setup-nav button[data-pane=manage]"); assert pg.locator("#manage").is_visible(); ok("sections still load content while folded")
    b.close()
assert not errs, errs; print("ALL OK")
