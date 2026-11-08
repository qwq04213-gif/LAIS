"""3.15·3.16 화면: 영상 복원(진단 → 추천 설정 → 복원 → 비교 막대) · 소리 분리·복원(엔진 안내 → 고치기 → 원본 ↔ 결과 → 영상에 넣기), 사이드바 버튼."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, subprocess, urllib.parse
from pathlib import Path
os.environ["TEST_HUB_PORT"] = "17985"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
vd = hub.OUT / "영상"; vd.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=4", "-f", "lavfi", "-i", "sine=f=440:d=4",
                "-vf", "noise=alls=40:allf=t", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(vd / "old.mp4")], check=True)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 950}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=vrestore]"); pg.wait_for_selector("#vr-video option[value*='old.mp4']", state="attached")
    pg.click("#vr-diag"); pg.wait_for_selector("#vr-report table", timeout=60000)
    assert pg.locator("#vr-report tr").count() >= 8 and pg.input_value("#vr-denoise") != "off" and pg.is_checked("#vr-interp")
    ups = req("/api/lists").get("upscalers") or []
    assert pg.input_value("#vr-scale") == ("2" if ups else "0"), (ups, pg.input_value("#vr-scale"))
    ok("diagnosis table + recommended settings applied (upscale only with a model)")
    pg.uncheck("#vr-interp"); pg.select_option("#vr-scale", "0"); pg.click("#vr-go"); pg.wait_for_selector("#vr-cmp video.vr-b", timeout=120000)
    assert "소리 그대로" in pg.inner_text("#vr-out") and pg.locator("#vr-out img.vr-png").count() == 1
    pg.fill("#vr-wipe", "20"); pg.dispatch_event("#vr-wipe", "input")
    assert "80%" in pg.get_attribute("#vr-cmp .vr-a", "style")
    pg.screenshot(path=os.environ.get("TMPDIR", "/tmp") + "/vrestore.png")
    ok("restore → audio check message, before/after wipe slider, comparison image")
    pg.click("nav button[data-v=audio]"); pg.wait_for_selector("#au-inst")
    assert pg.is_disabled("#au-sep")
    pg.select_option("#au-src", label="old.mp4"); pg.click("#au-fix"); pg.wait_for_selector("#au-out [data-ab]", timeout=60000)
    assert "LUFS" in pg.inner_text("#au-out") and pg.locator("#au-out audio").count() == 2
    assert pg.locator("#au-out [data-aumux]").count() == 1
    pg.click("#au-out [data-ab]"); pg.wait_for_timeout(300)
    pg.click("#au-out [data-aumux]"); pg.wait_for_selector("#au-res2 video", timeout=60000)
    pg.screenshot(path=os.environ.get("TMPDIR", "/tmp") + "/audio.png")
    ok("audio: engine install prompt, fix video's sound → original ↔ result rows, put back into the video")
    assert not errs, errs
print("ALL OK")
