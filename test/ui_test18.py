"""일괄 처리 화면 · 작업 대기열 창 · 완료 알림 · 설정 백업 · 사이드바."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, shutil, threading, time
os.environ["TEST_HUB_PORT"] = "17889"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
TMPD = os.environ["TMPDIR"]
SRC = TMP / "ph"; SRC.mkdir()
for i in range(3): Image.new("RGB", (800, 600), (40 * i, 100, 200)).save(SRC / f"s{i}.png")
Image.new("RGB", (640, 480), (70, 120, 60)).save(TMPD + "/subj.png")
RMDIR = hub.MODELS / "rmbg"; RMDIR.mkdir(exist_ok=True)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 1000}, accept_downloads=True); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(600); None
    # 사이드바
    assert pg.locator("#rail nav button svg.ico").count() == 42 and pg.locator("#rail nav .ngt").count() == 9; groups = pg.eval_on_selector_all("#rail nav .ngt", "e=>e.map(x=>x.textContent)"); assert groups == ["처음", "대화", "내 작업", "이미지", "이미지 기능", "영상", "소리", "자동화", "관리"], groups; ok("sidebar: icons on all items, 9 labelled groups in the planned order")
    # 일괄 처리: 폴더 크기 변경
    pg.click("nav button[data-v=batch]"); pg.wait_for_selector("#v-batch.on"); pg.wait_for_selector("#f-batch")
    pg.fill("#f-batch input[name=folder]", str(SRC)); pg.click("#bt-scan"); pg.wait_for_function("document.querySelector('#bt-info').textContent.includes('3장')"); ok("folder scan shows the photo count")
    pg.fill("#f-batch input[name=long_side]", "300"); pg.click("#f-batch .go"); pg.wait_for_selector("#bt-res .bt-done", timeout=30000)
    assert "3장 완료" in pg.inner_text("#bt-res") and pg.locator("#bt-res .bt-grid img").count() == 3 and len(list((hub.OUT / "일괄").rglob("s*_크기변경.png"))) == 3; ok("resize batch from the screen: summary + thumbnails, files saved")
    pg.wait_for_function("window.QBEEP>=1", timeout=8000); assert "끝났어요" in pg.inner_text("#toast"); ok("finishing a job beeps and shows a toast (sound on by default)")
    # 아무것도 안 고르면 안내
    for k, v in (("long_side", "0"),): pg.fill(f"#f-batch input[name={k}]", v)
    pg.click("#f-batch .go"); pg.wait_for_function("document.querySelector('#v-batch .jobbar .st').textContent.includes('하나 이상')"); ok("nothing chosen → friendly message")
    # 배경 지우기: 설치 전/후
    pg.check("#f-batch input[name=op][value=rmbg]"); pg.wait_for_function("!document.querySelector('#bt-rm-install').hidden"); assert "설치되지 않았" in pg.inner_text("#bt-rm-note")
    pg.click("#f-batch .go"); pg.wait_for_function("document.querySelector('#v-batch .jobbar .st').textContent.includes('설치')"); ok("rmbg not installed → install button + message, run is blocked")
    shutil.copy(BASE + "/rmbg-test/u2netp.onnx", RMDIR / "u2netp.onnx"); pg.select_option("#f-batch select[name=rmodel]", "fast"); pg.wait_for_function("document.querySelector('#bt-rm-install').hidden && document.querySelector('#bt-rm-note').textContent.includes('설치됨')"); ok("once the model file exists the note turns to ✔ installed")
    pg.check("#f-batch input[name=srcm][value=files]"); pg.set_input_files("#bt-files", [TMPD + "/subj.png", TMPD + "/subj.png"], ); pg.wait_for_function("document.querySelector('#bt-drop').textContent.includes('2장 선택됨')")
    pg.select_option("#f-batch select[name=bg]", "white"); pg.select_option("#f-batch select[name=fmt]", "jpg"); pg.click("#f-batch .go"); pg.wait_for_function("document.querySelectorAll('#bt-res .bt-done').length==2", timeout=60000)
    assert "2장 완료" in pg.locator("#bt-res .bt-done").first.inner_text(); assert len(list((hub.OUT / "일괄").rglob("subj*_배경없음*.jpg"))) == 2 and not list(hub.BATCH_IN.glob("*")); ok("pick files → uploaded → background removal (real model) → JPEG with white bg; temp uploads removed")
    pg.check("#f-batch input[name=srcm][value=out]"); pg.select_option("#f-batch select[name=outsub]", "일괄"); pg.click("#bt-scan"); pg.wait_for_function("/사진 \\d+장/.test(document.querySelector('#bt-info').textContent)"); ok("'program result folder' source")
    # 대기열 창
    gate = threading.Event(); orig = hub.do_batch
    def slow(pp, J):
        if pp.get("tag") == "first": gate.wait(30)
        return []
    hub.do_batch = slow
    try:
        import urllib.request
        def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
        ids = [post("/api/job", {"kind": "batch", "op": "resize", "folder": str(SRC), "long_side": 10, "tag": t})["id"] for t in ("first", "b", "c")]
        pg.wait_for_function("!document.querySelector('#qcount').hidden && document.querySelector('#qcount').textContent=='3'", timeout=8000); ok("sidebar badge shows how many jobs are active")
        pg.click("#qbtn"); pg.wait_for_selector("#qpanel:not([hidden]) .qrow", timeout=8000); rows = pg.locator("#qlist .qrow"); assert rows.nth(0).get_attribute("class").find("s-running") > 0 and "s-queued" in rows.nth(1).get_attribute("class") and "s-queued" in rows.nth(2).get_attribute("class"); ok("panel lists the running job and the waiting ones")
        order = lambda: pg.eval_on_selector_all("#qlist .qrow.s-queued", "e=>e.map(x=>x.dataset.id)")
        assert order() == [ids[1], ids[2]]
        pg.locator(f"#qlist .qrow[data-id='{ids[2]}'] [data-q=top]").click(); pg.wait_for_function(f"document.querySelector('#qlist .qrow.s-queued').dataset.id=='{ids[2]}'"); assert order() == [ids[2], ids[1]]; ok("⤒ moves a waiting job to the front")
        pg.locator(f"#qlist .qrow[data-id='{ids[2]}'] [data-q=cancel]").click(); pg.wait_for_function(f"!document.querySelector(\"#qlist .qrow.s-queued[data-id='{ids[2]}']\")"); assert order() == [ids[1]]; ok("✕ removes a waiting job from the queue")
        pg.screenshot(path=TMPD + "/queue.png")
        gate.set(); pg.wait_for_function("document.querySelector('#qcount').hidden", timeout=15000); ok("badge disappears when everything is done")
        pg.click("#qbtn") if pg.is_hidden("#qpanel") else None; pg.uncheck("#q-sound"); n0 = pg.evaluate("window.QBEEP"); pg.click("#q-test"); assert pg.evaluate("window.QBEEP") == n0 + 1; assert pg.evaluate("JSON.parse(localStorage.getItem('q:sound'))") is False; ok("sound toggle is remembered; the test button still triggers the notification path")
    finally:
        hub.do_batch = orig
    pg.click("#qpanel .qx"); assert pg.locator("#qpanel").is_hidden()
    # 백업/복원
    pg.click("nav button[data-v=conf]"); pg.wait_for_timeout(500); pg.click("#cs-nav button[data-pane=backup]")
    pg.evaluate("localStorage.setItem('preset:f-gen', JSON.stringify({'내 프리셋': {prompt: 'saved prompt', w: '640'}}))")
    with pg.expect_download() as dl: pg.click("#bk-export")
    path = dl.value.path(); data = json.load(open(path, encoding="utf-8")); assert data["app"] == "LocalAI-Studio" and data["presets"]["preset:f-gen"]["내 프리셋"]["prompt"] == "saved prompt" and "prompts" in data and dl.value.suggested_filename.startswith("LocalAI-백업-"); ok("backup file downloads with presets from the browser + server data")
    pg.evaluate("localStorage.removeItem('preset:f-gen')"); hub_prompts = hub.ROOT / "prompts.json"
    json.dump({**data, "prompts": data["prompts"] + [{"id": "zz9", "name": "복원됨", "text": "restored prompt"}]}, open(TMPD + "/bk.json", "w", encoding="utf-8"), ensure_ascii=False)
    pg.set_input_files("#bk-file", TMPD + "/bk.json"); pg.wait_for_selector("#bk-box:not([hidden])"); assert "프롬프트" in pg.inner_text("#bk-sum")
    pg.click("#bk-go"); pg.wait_for_function("document.querySelector('#toast').textContent.includes('되살렸어요')"); assert pg.evaluate("JSON.parse(localStorage.getItem('preset:f-gen'))['내 프리셋'].prompt") == "saved prompt" and "restored prompt" in hub_prompts.read_text(encoding="utf-8"); ok("restore brings back browser presets and server data from the file")
    open(TMPD + "/notbk.json", "w").write('{"a":1}'); pg.set_input_files("#bk-file", TMPD + "/notbk.json"); pg.wait_for_function("document.querySelector('#toast').textContent.includes('백업 파일이 아니에요')"); assert pg.locator("#bk-box").is_hidden(); ok("a non-backup file is refused")
    # 모바일
    m = b.new_context(viewport={"width": 420, "height": 800}).new_page(); m.goto(B + "/"); m.wait_for_timeout(500); (None) if m.locator("#ackb").is_visible() else None; m.click("nav button[data-v=batch]"); m.wait_for_selector("#v-batch.on"); assert m.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1"); m.click("#qbtn"); m.wait_for_selector("#qpanel:not([hidden])"); m.screenshot(path=TMPD + "/m_q.png"); ok("mobile: no sideways scroll, queue panel opens")
    pg.click("nav button[data-v=batch]"); pg.screenshot(path=TMPD + "/batch.png", full_page=False)
    b.close()
assert not errs, errs; print("ALL OK")
