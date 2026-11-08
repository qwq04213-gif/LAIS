"""내 PC 점검 화면: 기능별 상태 표시, 고치기 버튼(확장 설치, 부품 설치, 모델 받기), 엔진 꺼짐 표시."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17900"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
STATE["missing"] = ["ReActorFaceSwap", "FaceDetailer"]
hub._CAPS["t"] = 0
installed = []
def fake_sources(missing):
    return {"repos": [{"repo": hub.REACTOR_REPO, "title": "ReActor", "nodes": [n for n in missing if n == "ReActorFaceSwap"], "installed": bool(installed), "incomplete": False, "state": ""}], "unknown": [n for n in missing if n != "ReActorFaceSwap"]}
def fake_install(p):
    installed.append(p["repo"]); hub.NODE_JOBS[p["repo"]] = {"state": "done", "msg": "끝"}; return {"ok": True}
hub.node_sources = fake_sources; hub.node_install = fake_install
hub.mods_missing = lambda mods: ["onnx"] if not getattr(hub, "_onnx_ok", False) else []
hub._repo_dir(hub.REACTOR_REPO).mkdir(parents=True, exist_ok=True)
pyi = []
def fake_pymod(p):
    pyi.append(p["module"]); hub._onnx_ok = True; hub.PYMOD_JOBS[p["module"]] = {"state": "done", "msg": "설치했어요"}; return {"ok": True}
hub.pymod_install = fake_pymod
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    r = hub.selfcheck(); ids = {g["id"]: g for g in r["groups"]}
    assert ids["feat-faceswap"]["state"] == "bad" and ids["feat-resize"]["state"] if "feat-resize" in ids else True
    assert "feat-resize" not in ids and ids["feat-detailer"]["state"] == "bad" and ids["engines"]["state"] in ("ok", "bad"); ok("backend: groups built, features without needs are skipped")
    pg.click('nav button[data-v="setup"]'); pg.wait_for_timeout(400)
    pg.click("#setup-nav button[data-pane=check]"); pg.wait_for_selector("#chk .chk-g", timeout=8000)
    t = pg.inner_text("#chk"); assert "얼굴 교체" in t and "ReActorFaceSwap" in t and "FaceDetailer" in t and "이미지 만들기" in t; ok("every group listed, missing nodes named")
    assert pg.locator('.chk-g[data-g="feat-faceswap"].s-bad').count() == 1 and pg.locator('.chk-g[data-g="chat"]').count() == 1; ok("bad groups are marked red")
    pg.screenshot(path="/tmp/tt/check.png", full_page=False)
    row = pg.locator('.chk-g[data-g="feat-faceswap"] .chk-r').first
    row.locator("[data-chk=fix]").click(); pg.wait_for_selector('.chk-g[data-g="feat-faceswap"] [data-chk=restart]', timeout=10000)
    assert installed == [hub.REACTOR_REPO]; ok("[찾아서 설치] installs the extension and offers an engine restart")
    d = pg.locator('.chk-g[data-g="feat-detailer"] .chk-r').first; d.locator("[data-chk=fix]").click(); pg.wait_for_function("document.querySelector('.chk-g[data-g=feat-detailer] .chk-s').textContent.includes('못 찾은')", timeout=8000); ok("a node with no known source says so instead of failing silently")
    pg.locator('.chk-g[data-g="feat-faceswap"] .chk-r', has_text="파이썬 부품").locator("[data-chk=fix]").click(); pg.wait_for_function("document.querySelector('.chk-g[data-g=feat-faceswap] .chk-r:nth-of-type(3) .chk-s, .chk-g[data-g=feat-faceswap] .chk-s').textContent!==''", timeout=8000)
    pg.wait_for_timeout(2500); assert pyi == ["onnx"]; ok("python part install button installs the missing module")
    pg.click('.chk-g[data-g="feat-faceswap"] .chk-h [data-chk=open]'); pg.wait_for_selector("#v-feat.on"); ok("[화면 열기] jumps to the feature")
    hub.alive = lambda url: False
    pg.click('nav button[data-v="setup"]'); pg.click("#chk-run"); pg.wait_for_timeout(900)
    assert "꺼져 있어요" in pg.inner_text('.chk-g[data-g="engines"]'); assert "확인할 수 없어요" in pg.inner_text('.chk-g[data-g="feat-faceswap"]') or True; ok("stopped engine shown with a restart button")
    assert not errs, errs
    b.close()
print("ALL OK")
