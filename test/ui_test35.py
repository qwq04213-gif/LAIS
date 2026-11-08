"""음성 만들기 화면: 탭 열기, 목소리 목록, 방법 바꾸기, 만들기→재생기, 입력 기억."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17899"
sys.path.insert(0, BASE + "/test")
from mocks import *
import tts
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
tts.FORCE_SAPI = True; tts.edge_ready = lambda: False
tts.sapi_voices = lambda *a, **k: [("Microsoft Heami Desktop", "ko-KR"), ("Microsoft Zira Desktop", "en-US")]
tts.speak_sapi = lambda text, voice, rate, vol, cd, run=None: b"RIFF" + b"\0" * 300
tts.speak_edge = lambda text, voice, rate, vol, pitch, cd, run=None, py=None: b"ID3" + b"\0" * 300
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="tts"]'); pg.wait_for_timeout(600)
    assert pg.is_visible("#v-tts") and pg.eval_on_selector_all("#tt-voice option", "e=>e.length") == 2 and pg.is_hidden("#tt-edge-warn") and pg.is_hidden("#tt-pitch-row"); ok("tab opens; Windows voices listed; Edge-only controls hidden")
    pg.click("#f-tts .go"); assert "글" in pg.inner_text("#v-tts .jobbar .st"); ok("empty text → asks for it")
    pg.fill("#f-tts textarea[name=text]", "안녕하세요. 테스트예요."); assert pg.inner_text("#tt-count") == "13"; ok("character counter")
    pg.select_option("#tt-voice", "Microsoft Zira Desktop"); pg.click("#f-tts .go"); pg.wait_for_selector("#v-tts audio", timeout=20000)
    assert pg.get_attribute("#v-tts audio", "src").endswith(".wav") and pg.is_visible("#v-tts .mfig a[download]"); ok("result shows an audio player with save link")
    pg.select_option("#tt-engine", "edge"); pg.wait_for_timeout(300)
    assert pg.is_visible("#tt-edge-warn") and pg.is_visible("#tt-pitch-row") and pg.eval_on_selector("#tt-voice", "e=>e.options[0].value") == "ko-KR-SunHiNeural"; ok("Edge: install button shown while the part is missing, Korean voice first")
    tts.edge_ready = lambda: True; pg.click('nav button[data-v="gen"]'); pg.click('nav button[data-v="tts"]'); pg.wait_for_timeout(500)
    assert pg.is_hidden("#tt-edge-warn"); pg.click("#f-tts .go"); pg.wait_for_function("document.querySelectorAll('#v-tts audio').length==2", timeout=20000)
    assert pg.eval_on_selector_all("#v-tts audio", "e=>e[0].src.endsWith('.mp3')"); ok("Edge result is an mp3 player; warning disappears once the part exists")
    pg.screenshot(path="/tmp/tt/tts.png")
    pg.reload(); pg.wait_for_timeout(700); pg.click('nav button[data-v="tts"]'); pg.wait_for_timeout(500)
    assert pg.input_value("#f-tts textarea[name=text]").startswith("안녕하세요") and pg.input_value("#tt-engine") == "edge"; ok("input and choices are remembered")
    b.close()
assert not errs, errs
print("ALL OK")
