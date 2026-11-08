"""음악 만들기 화면: 사이드바 항목, 모델 없을 때 안내, 입력→생성→오디오 재생기, 가사 칸 숨김, 입력 기억."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17899"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    assert pg.locator('nav button[data-v="music"]').is_visible(); pg.click('nav button[data-v="music"]'); pg.wait_for_timeout(500)
    assert pg.is_visible("#v-music") and pg.is_visible("#w-music") and "ACE-Step" in pg.inner_text("#w-music"); ok("sidebar item opens the view; no model → install hint")
    pg.click("#f-music .go"); assert "스타일" in pg.inner_text("#v-music .jobbar .st"); ok("empty style → asks for it, nothing is sent")
    (M / "checkpoints").mkdir(exist_ok=True); (M / "checkpoints" / "ace_step_1.5_turbo_aio.safetensors").write_bytes(b"x")
    pg.click('nav button[data-v="gen"]'); pg.click('nav button[data-v="music"]'); pg.evaluate("loadLists(true)"); pg.wait_for_timeout(800)
    assert pg.is_hidden("#w-music"); ok("warning disappears once the model is installed")
    pg.fill("#f-music textarea[name=tags]", "lo-fi, chill, piano"); pg.check("#f-music input[name=instrumental]"); assert pg.is_hidden("#mu-lyr"); pg.uncheck("#f-music input[name=instrumental]"); assert pg.is_visible("#mu-lyr"); ok("lyrics box hides for instrumental")
    pg.fill("#f-music textarea[name=lyrics]", "[verse]\n안녕"); pg.select_option("#f-music select[name=seconds]", "30")
    assert pg.eval_on_selector_all("#mu-key option", "e=>e.length") == 34 and pg.input_value("#mu-key") == "C major"; ok("key list has 34 entries, major first")
    pg.click("#f-music .go"); pg.wait_for_selector("#v-music audio", timeout=20000)
    assert pg.is_visible("#v-music .jobbar[data-m=ok]") and pg.get_attribute("#v-music audio", "src").endswith(".mp3") and pg.is_visible("#v-music .mfig a[download]"); ok("result shows a player and a save link")
    pg.screenshot(path="/tmp/tt/music.png")
    pg.reload(); pg.wait_for_timeout(700); pg.click('nav button[data-v="music"]'); assert pg.input_value("#f-music textarea[name=tags]") == "lo-fi, chill, piano" and pg.input_value("#f-music select[name=seconds]") == "30"; ok("inputs are remembered after reload")
    print("page errors:", errs); assert not errs
print("ALL OK")
