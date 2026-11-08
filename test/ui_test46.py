"""2.2: 전부 고치기, 확장 진단(설치 단계 다시), 보관함 정렬·복제, 갤러리 정렬·같은 프롬프트 모아 보기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time
os.environ["TEST_HUB_PORT"] = "17923"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
from PIL import Image
ok = lambda m: print("PASS", m)
errs = []
# ── 갤러리 데이터: 같은 프롬프트 3장 + 다른 프롬프트 1장 + 정보 없는 1장
G = hub.OUT / "생성"; G.mkdir(parents=True, exist_ok=True)
def png(name, prompt, t):
    im = Image.new("RGB", (64, 64), (20, 20, 20))
    from PIL.PngImagePlugin import PngInfo
    pi = PngInfo()
    if prompt is not None: pi.add_text("hub", json.dumps({"prompt": prompt}))
    im.save(G / name, "PNG", pnginfo=pi); os.utime(G / name, (t, t))
now = time.time()
png("a1.png", "1girl, red hair", now - 500); png("b1.png", "a cat on a sofa", now - 400); png("a2.png", "1girl,  RED hair", now - 300); png("n1.png", None, now - 200); png("a3.png", "1girl, red hair", now - 100)
# ── 점검 화면 데이터
STATE["missing"] = ["ReActorFaceSwap", "FaceDetailer"]; hub._CAPS["t"] = 0
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
# ── 서버: 설치 단계가 있는 확장(ReActor)은 진단 뒤 그 단계를 다시 돌려요
hub.GHURL = "https://github.com"
d = hub._repo_dir(hub.REACTOR_REPO); (d / "install.py").write_text("print('x')"); (d / ".hub-setup-done").write_text("ok")
(hub.LOGS).mkdir(exist_ok=True); (hub.LOGS / "comfyui.log").write_text("Cannot import C:\\x\\custom_nodes\\ComfyUI-ReActor module for custom nodes: No module named 'insightface'\nModuleNotFoundError: No module named 'insightface'\n", encoding="utf-8")
dg = hub.node_diagnose({"repo": hub.REACTOR_REPO}); assert dg["setup"] is True and "insightface" in dg["reason"], dg
ran = []
hub._node_install = lambda repo: ran.append(repo) or hub.NODE_JOBS[repo].update(state="done", msg="설치했어요")
r = hub.node_fixdeps({"repo": hub.REACTOR_REPO}); time.sleep(0.5); assert r == {"ok": True} and ran == [hub.REACTOR_REPO] and not (d / ".hub-setup-done").exists(); ok("pack with its own setup step (ReActor): diagnosis offers re-running that step, marker cleared, install job started")
(d / ".hub-setup-done").write_text("ok")
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1100}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda x: x.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    # ── 전부 고치기
    pg.click('nav button[data-v="setup"]'); pg.click("#setup-nav button[data-pane=check]"); pg.wait_for_selector("#chk .chk-g", timeout=8000); pg.wait_for_selector("#chk-fixall:not([hidden])")
    n = pg.inner_text("#chk-fixall"); assert "전부 고치기" in n and "(" in n; ok("[전부 고치기] appears with the number of auto-fixable items: " + n)
    installed.clear(); pyi.clear(); ran.clear()
    pg.click("#chk-fixall"); pg.wait_for_function("document.querySelector('#chk-all').textContent.includes('끝났어요')", timeout=60000)
    t = pg.inner_text("#chk-all"); assert installed == [hub.REACTOR_REPO] and pyi == ["onnx"] and "설치" in t and "고치지 못한 것" in t, (installed, pyi, t); ok("fix-all installs the extension and python part in order and summarizes: " + t.splitlines()[0])
    assert pg.locator("#chk-all-rs").count() == 1 and pg.locator("#chk-all-again").count() == 1; ok("one engine restart is offered at the end (not after each item)")
    pg.click("#chk-all-again"); pg.wait_for_selector("#chk .chk-g"); assert pg.locator("#chk-all").is_hidden(); ok("[다시 점검] rescans")
    assert pg.locator("#chk-diag").count() == 1; ok("diagnostic file button sits next to the check")
    # ── 보관함 정렬·복제
    for nm, t0 in (("가나다 마법사", 100), ("나 병사", 300), ("다 기사", 200)):
        pg.evaluate("""async ([nm]) => { await api('/api/chars', {action:'save', name:nm, kind:'캐릭터', prompt:'p-'+nm, loras:[], refs:[]}) }""", [nm])
    hub_items = hub.chars_load(); assert len(hub_items) == 3
    pg.click('nav button[data-v="lib"]'); pg.click("#lib-nav button[data-pane=chars]"); pg.wait_for_selector("#ch-list .chcard"); names = pg.locator("#ch-list .chcard .plh b").all_inner_texts(); assert names == ["가나다 마법사", "나 병사", "다 기사"], names
    pg.select_option("#ch-sort", "name"); names = pg.locator("#ch-list .chcard .plh b").all_inner_texts(); assert names == sorted(names, key=lambda s: s), names
    # '이미지 생성에 넣기'를 누르면 최근 사용으로 기록돼서 최근 사용순 맨 앞으로
    pg.locator("#ch-list .chcard", has_text="다 기사").locator("[data-ch=gen]").click(); pg.wait_for_timeout(600); pg.click('nav button[data-v="lib"]'); pg.wait_for_selector("#ch-list .chcard")
    pg.select_option("#ch-sort", "used"); assert pg.locator("#ch-list .chcard .plh b").first.inner_text() == "다 기사"; ok("library sorts by name and by recent use (using an entry moves it to the front)")
    pg.reload(); pg.wait_for_timeout(500); pg.click('nav button[data-v="lib"]'); pg.wait_for_selector("#ch-list .chcard"); assert pg.input_value("#ch-sort") == "used"; ok("the chosen library sort is remembered")
    # 복제
    ref = Image.new("RGB", (8, 8), (255, 0, 0)); import io; bb = io.BytesIO(); ref.save(bb, "PNG"); import base64
    pg.evaluate("""async (u) => { await api('/api/chars', {action:'save', name:'참고 있는 항목', kind:'스타일', prompt:'x', loras:[], refs:[{data:u}]}) }""", "data:image/png;base64," + base64.b64encode(bb.getvalue()).decode())
    pg.reload(); pg.wait_for_timeout(500); pg.click('nav button[data-v="lib"]'); pg.wait_for_selector("#ch-list .chcard")
    pg.locator("#ch-list .chcard", has_text="참고 있는 항목").locator("[data-ch=dup]").click(); pg.wait_for_function("document.querySelectorAll('#ch-list .chcard').length===5")
    its = hub.chars_load(); a = [x for x in its if x["name"] == "참고 있는 항목"][0]; c = [x for x in its if x["name"] == "참고 있는 항목 (복사)"][0]
    assert c["id"] != a["id"] and len(c["refs"]) == 1 and c["refs"][0] != a["refs"][0] and (hub.CHARS_DIR / "img" / c["refs"][0]).is_file() and (hub.CHARS_DIR / "img" / a["refs"][0]).is_file() and c["kind"] == "스타일" and c["used"] is None; ok("duplicate copies settings and its own copy of the reference image (original untouched)")
    # ── 갤러리 정렬·같은 프롬프트 모아 보기
    pg.click('nav button[data-v="gal"]'); pg.wait_for_selector("#gal-grid .gt"); names = [x.split("/")[-1] for x in pg.eval_on_selector_all("#gal-grid .gt", "e=>e.map(x=>x.dataset.u)")]; assert names[0] == "a3.png" and names[-1] == "a1.png", names
    pg.select_option("#gal-sort", "old"); pg.wait_for_function("((document.querySelector('#gal-grid .gt')||{dataset:{u:''}}).dataset.u||'').endsWith('a1.png')"); ok("gallery: oldest-first sorting")
    pg.select_option("#gal-sort", "name"); pg.wait_for_function("((document.querySelector('#gal-grid .gt')||{dataset:{u:''}}).dataset.u||'').endsWith('a1.png')"); names = [x.split("/")[-1] for x in pg.eval_on_selector_all("#gal-grid .gt", "e=>e.map(x=>x.dataset.u)")]; assert names == sorted(names), names; ok("gallery: file-name sorting")
    pg.select_option("#gal-sort", "new"); pg.check("#gal-same"); pg.wait_for_selector("#gal-grid h3.gday[data-g]")
    heads = pg.locator("#gal-grid h3.gday[data-g]").all_inner_texts(); order = [x.split("/")[-1] for x in pg.eval_on_selector_all("#gal-grid .gt", "e=>e.map(x=>x.dataset.u)")]
    assert len(heads) == 3 and "3장" in heads[0] and "프롬프트 정보 없음" in heads[-1] and order[:3] == ["a3.png", "a2.png", "a1.png"] and order[3] == "b1.png" and order[-1] == "n1.png", (heads, order); ok("gallery: same-prompt grouping (case/space-insensitive), biggest-first by newest, items without info last")
    assert pg.is_disabled("#gal-group"); pg.reload(); pg.wait_for_timeout(500); pg.click('nav button[data-v="gal"]'); pg.wait_for_selector("#gal-grid .gt"); assert pg.is_checked("#gal-same"); ok("grouping choice is remembered (and replaces the by-date grouping)")
    # 미리보기 끄기에서도 정렬·검색 가능
    pg.evaluate("localStorage.setItem('opt:galprev', JSON.stringify('off'))"); pg.reload(); pg.wait_for_timeout(500); pg.click('nav button[data-v="gal"]'); pg.wait_for_selector("#gal-grid .gnoimg")
    pg.fill("#gal-q", "cat"); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length===1"); assert "b1.png" in pg.inner_text("#gal-grid"); ok("search and grouping work with the preview turned off")
    assert not errs, errs
    b.close()
print("ALL OK")
