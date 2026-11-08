"""갤러리 날짜별 보기·폴더 열기, 버전별 변경 사항 화면, 빠진 파이썬 부품 설치 버튼."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, types
os.environ["TEST_HUB_PORT"] = "17893"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
TMPD = str(TMP)
Image.new("RGB", (320, 240), (70, 120, 60)).save(TMPD + "/photo.png")
(hub.ROOT / "README.txt").write_text(open(BASE + "/LocalAI-Studio/README.txt", encoding="utf-8-sig").read(), encoding="utf-8")
G = hub.OUT / "생성"; G.mkdir(parents=True, exist_ok=True)
def mk(n, d):
    p = G / n; Image.new("RGB", (30, 30), (5, 5, 5)).save(p); t = time.time() - d * 86400; os.utime(p, (t, t))
for n, d in (("a.png", 0), ("b.png", 0), ("c.png", 2), ("d.png", 5)): mk(n, d)
(hub.MODELS / "controlnet").mkdir(exist_ok=True); (hub.MODELS / "controlnet" / "controlnet-union-sdxl-promax.safetensors").write_bytes(b"x")
hub.VERSION = "4.0.1"; errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 1000}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    opened = []; pg.route("**/api/open", lambda r: (opened.append(r.request.post_data), r.fulfill(json={"ok": True})))
    pg.goto(B + "/"); pg.wait_for_timeout(600); None
    # ── 갤러리
    pg.click("nav button[data-v=gal]"); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length==4")
    assert pg.locator("#gal-grid .gday").count() == 0; ok("default view: flat grid, no day headings")
    pg.click("#v-gal [data-open=outputs]"); pg.wait_for_timeout(300); assert opened and "outputs" in opened[-1]; ok("'outputs 폴더 열기' button asks the studio to open the outputs folder")
    opts = pg.eval_on_selector_all("#gal-date option", "e=>e.map(x=>x.textContent)"); assert len(opts) == 4 and opts[0] == "모든 날짜" and "오늘" in opts[1] and opts[1].endswith("2개"), opts; ok("date picker lists each day with its count (today marked)")
    pg.check("#gal-group"); pg.wait_for_function("document.querySelectorAll('#gal-grid .gday').length==3")
    heads = pg.eval_on_selector_all("#gal-grid .gday", "e=>e.map(x=>x.textContent)"); assert "오늘" in heads[0] and heads[0].rstrip().endswith("2개"), heads
    order = pg.eval_on_selector_all("#gal-grid > *", "e=>e.map(x=>x.className)"); assert order[0] == "gday" and order[1:3] == ["gt", "gt"] and order[3] == "gday", order; ok("'날짜별로 묶어 보기' groups cards under day headings (newest day first)")
    pg.reload(); pg.wait_for_timeout(500); pg.click("nav button[data-v=gal]"); pg.wait_for_function("document.querySelectorAll('#gal-grid .gday').length==3"); assert pg.is_checked("#gal-group"); ok("the grouping choice is remembered")
    d2 = time.strftime("%Y-%m-%d", time.localtime(time.time() - 2 * 86400)); pg.select_option("#gal-date", d2); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length==1"); assert "1개" in pg.inner_text("#gal-n"); ok("picking a day shows only that day")
    pg.select_option("#gal-date", ""); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length==4")
    pg.locator("#gal-grid .gt").nth(3).hover(); pg.locator("#gal-grid .gt [data-del]").nth(3).click(force=True); pg.wait_for_function("document.querySelectorAll('#gal-grid .gt').length==3")
    assert pg.locator("#gal-grid .gday").count() == 2; ok("deleting the last card of a day also removes its heading")
    # ── 변경 사항
    pg.click("#ver"); pg.wait_for_selector("#v-log.on .logv"); n = pg.locator("#log-list .logv").count(); assert n >= 13, n
    first = pg.locator("#log-list .logv").first; assert "4.0.1" in first.inner_text() and "지금 쓰는 버전" in first.inner_text() and first.evaluate("e=>e.open") and not pg.locator("#log-list .logv").nth(1).evaluate("e=>e.open"); ok("clicking the version label opens the change log: newest first, current version badged and expanded")
    pg.click("#log-open"); assert pg.locator("#log-list .logv[open]").count() == n; pg.click("#log-close"); assert pg.locator("#log-list .logv[open]").count() == 0
    pg.fill("#log-q", "RealVisXL"); pg.wait_for_function("document.querySelectorAll('#log-list .logv').length>=1 && document.querySelectorAll('#log-list .logv').length<document.querySelectorAll('#log-list .logv[open]').length+1"); assert pg.locator("#log-list .logv").count() < n and "RealVisXL" in pg.inner_text("#log-list"); ok("expand/collapse all and search filter the versions")
    pg.fill("#log-q", ""); pg.click("nav button[data-v=conf]"); pg.wait_for_timeout(400); pg.click("#cs-nav button[data-pane=app]"); pg.click("#fold-app [data-go=log]"); pg.wait_for_selector("#v-log.on"); ok("also reachable from 설치와 모델 → 프로그램 관리")
    # ── 빠진 파이썬 부품
    orig = hub.run_wf
    def boom(*a, **k): raise RuntimeError("DWPreprocessor: No module named 'matplotlib'")
    hub.run_wf = boom; calls = []
    hub.subprocess.run = lambda cmd, **kw: (calls.append(cmd), types.SimpleNamespace(returncode=0, stdout="", stderr=""))[1]; hub.PY = Path(sys.executable)
    pg.click("nav button[data-v=gen]"); pg.wait_for_function("LISTS.controlnets.length>0"); pg.evaluate("document.querySelectorAll('#f-gen details').forEach(d=>d.open=true)")
    box = pg.locator("#f-gen .cn-easy").first; box.locator(".cn-src input").set_input_files(TMPD + "/photo.png"); pg.wait_for_function("document.querySelector('#f-gen .cn-src img').src.startsWith('data:')")
    box.locator(".cn-go").click(); pg.wait_for_selector("#f-gen .cn-st [data-pymod=matplotlib]", timeout=20000); assert "matplotlib" in pg.inner_text("#f-gen .cn-st"); ok("easy mode 'No module named matplotlib' → message + install button")
    pg.click("#f-gen .cn-st [data-pymod]"); pg.wait_for_function("document.querySelector('#f-gen .cn-st .pm-st').textContent.includes('설치했어요')", timeout=15000); assert any("pip" in c and "matplotlib" in c for c in calls); ok("button installs the part and says to retry")
    hub.run_wf = orig
    b.close()
real = [e for e in errs if "ResizeObserver" not in e]; assert not real, real
print("ALL OK")
