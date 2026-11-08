"""워크플로 탭의 커스텀 노드 도우미."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time
os.environ["TEST_HUB_PORT"] = "17878"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
hub.PY = Path(sys.executable)
errs = []
G = {"1": {"class_type": "CoolSampler", "inputs": {"seed": 1}}, "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}}}
STATE["missing"].add("CoolSampler"); hub._CAPS["t"] = 0
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 950}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.click("nav button[data-v=wf]"); pg.fill("#wf-json", json.dumps(G)); pg.click("#wf-an"); pg.wait_for_selector("#nodelist .nrow", timeout=8000)
    t = pg.inner_text("#nodebox"); assert "CoolSampler" in t and "Cool Nodes" in t and "설치" in t; ok("analyze shows the missing node with where to get it")
    pg.click("#nodelist .ninst"); pg.wait_for_selector("#nodelist .badge", timeout=20000)
    assert (hub.COMFY / "custom_nodes/CoolNodes/__init__.py").is_file() and "다시 시작" in pg.inner_text("#nodelist .nst"); ok("click install -> confirm -> installed badge + restart hint")
    pg.click("#node-restart"); pg.wait_for_timeout(500); assert "스튜디오가 켠" in pg.inner_text("#toast") or "다시 시작" in pg.inner_text("#toast"); ok("restart button gives feedback")
    b.close()
assert not errs, errs; print("ALL OK")
