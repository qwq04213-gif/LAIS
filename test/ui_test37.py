"""설치한 확장·부품 관리 화면: 목록 → 지우기(확인창) → 사라짐."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17899"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
cn = hub.COMFY / "custom_nodes"; cn.mkdir(parents=True, exist_ok=True)
(cn / "demo-pack").mkdir(exist_ok=True); (cn / "demo-pack" / "a.py").write_bytes(b"x" * 2048)
(hub.MODELS / "insightface").mkdir(parents=True, exist_ok=True); (hub.MODELS / "insightface" / "m.onnx").write_bytes(b"i" * 4096)
hub._pip_present = lambda: ["timm"]
class FP:
    args = ["python", "main.py"]
    def terminate(s): pass
    def wait(s, timeout=0): pass
hub.procs.append(FP())          # 스튜디오가 켠 ComfyUI 인 것처럼
hub.alive = lambda url: False
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    msgs = []; pg.on("dialog", lambda d: (msgs.append(d.message), d.accept()))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="setup"]'); pg.wait_for_timeout(500)
    pg.click("#setup-nav button[data-pane=parts]"); pg.click("#parts-scan"); pg.wait_for_selector("#parts .pdel", timeout=8000)
    t = pg.inner_text("#parts"); assert "demo-pack" in t and "insightface" in t and "timm" in t and ("KB" in t or "B" in t); ok("extension, model folder and python part are listed with sizes")
    pg.screenshot(path="/tmp/tt/parts.png")
    hub.part_delete.__globals__["start_engines"] = lambda: None
    pg.click('#parts .pdel[data-name="demo-pack"]'); pg.wait_for_timeout(900)
    assert msgs and "demo-pack" in msgs[-1] and "되돌릴 수 없어요" in msgs[-1]; assert not (cn / "demo-pack").exists(); ok("confirm dialog shown first, then the extension folder is gone")
    assert pg.locator('#parts .pdel[data-name="demo-pack"]').count() == 0; ok("list refreshes without the deleted extension")
    pg.click('#parts .pdel[data-name="insightface"]'); pg.wait_for_timeout(700); assert not (hub.MODELS / "insightface").exists(); ok("model folder deleted via the same flow")
    assert not errs, errs
    b.close()
print("ALL OK")
