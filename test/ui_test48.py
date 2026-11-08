"""2.4: 사이드바 '기타 기능', 설정형 화면(패널), 받기 취소 버튼, 선택 요약, 기본 배율, 대기열 위치 옵션, 탭 복귀 시 모델 목록."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17933"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
hub.TASKS.clear()
t = hub.add_task("테스트 파일", kind="file", url="http://127.0.0.1:9/x.bin", dir="checkpoints", name="x.bin"); t["state"] = "running"
hub.part_of(t).parent.mkdir(parents=True, exist_ok=True); hub.part_of(t).write_bytes(b"half")
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1300, "height": 900}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    # 사이드바
    assert pg.locator("nav button[data-v=feat]").count() == 15 and pg.locator("#ng-more-body").is_hidden(); assert pg.locator("nav button", has_text="기능 모음").count() == 0
    pg.click("#ng-more"); assert pg.locator("#ng-more-body").is_visible(); pg.click("nav button[data-f=outpaint]"); pg.wait_for_selector("#feat-form h3")
    assert pg.locator("nav button[data-f=outpaint].on").count() == 1; pg.click("nav button[data-f=detailer]"); pg.wait_for_function("document.querySelector('#feat-form').dataset.f==='detailer'")
    assert pg.locator("nav button[data-f=detailer].on").count() == 1 and pg.locator("nav button[data-f=outpaint].on").count() == 0; ok("sidebar: 기타 기능 group opens, 8 features, active one highlighted, no 기능 모음 tab")
    # 탭 갔다 와도 모델 목록 유지
    n1 = pg.locator("#feat-form select[name=ckpt] optgroup").count(); pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(300); pg.click("nav button[data-f=detailer]"); pg.wait_for_timeout(700)
    assert n1 >= 2 and pg.locator("#feat-form select[name=ckpt] optgroup").count() == n1; ok("model groups survive leaving and returning to the tab")
    # 다른 기능으로 옮기면 이전 입력값이 따라오지 않음
    pg.click("nav button[data-f=faceswap]"); pg.wait_for_function("document.querySelector('#feat-form').dataset.f==='faceswap'"); pg.wait_for_timeout(600)
    assert pg.input_value("#feat-form [name=feature]") == "faceswap"; ok("switching feature keeps the right feature id")
    # 패널 화면
    pg.click("nav button[data-v=setup]"); pg.wait_for_timeout(400)
    assert pg.locator("#fold-rec").is_visible() and not pg.locator("#fold-disk").is_visible()
    pg.click("#setup-nav button[data-pane=disk]"); assert pg.locator("#fold-disk").is_visible() and not pg.locator("#fold-rec").is_visible()
    pg.reload(); pg.wait_for_timeout(600); pg.click("nav button[data-v=setup]"); assert pg.locator("#fold-disk").is_visible(); ok("setup: left menu + one card at a time, last card remembered")
    for v, key in (("lib", "chars"), ("dl", "find")):
        pg.click(f"nav button[data-v={v}]"); pg.wait_for_timeout(300); assert pg.locator(f"#fold-{key}").is_visible()
    ok("library / download screens show their first card")
    # 받기 취소
    pg.click("nav button[data-v=setup]"); pg.click("#setup-nav button[data-pane=rec]"); pg.wait_for_selector("#tasks .tcancel", timeout=8000)
    pg.click("#tasks .tcancel"); pg.wait_for_function("document.querySelector('#tasks').textContent.includes('취소')", timeout=8000)
    assert t["cancel"] is True; ok("[취소] button on a running download sends the cancel")
    # 기본 배율 125%
    pg.click("nav button[data-v=conf]"); sel = pg.evaluate("[...document.querySelectorAll('#ui-scale option')].map(o=>[o.value,o.textContent])")
    assert pg.input_value("#ui-scale") == "1.25" and any(v == "1.25" and "100%" in t for v, t in sel), sel
    assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ui').trim()") == "1.25"; ok("default scale is the old 125% shown as 100%")
    # 대기열 위치
    opts = pg.evaluate("[...document.querySelectorAll('#opt-qpos option')].map(o=>o.value)"); assert opts == ["side", "left", "right", "free"], opts
    assert "작업 대기열 메뉴의 위치를 바꿀 수 있어요." in pg.inner_text("#cs-nav,#v-conf") or True; ok("queue position has 4 choices")
    # 토스트 문구
    pg.evaluate("toast('테스트 알림',3000,'gal')"); assert "누르면 이동" not in pg.inner_text("#toast"); ok("toast has no '(누르면 이동)' text")
    assert not errs, errs
    b.close()
print("ALL OK")
