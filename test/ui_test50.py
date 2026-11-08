"""PC 소리 녹음 → 자르기 → 목소리 샘플 (화면 공유는 440Hz 소리를 내는 가짜 스트림으로 대신)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17950"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
FAKE = """navigator.mediaDevices.getDisplayMedia = async () => { const ac = new AudioContext(), o = ac.createOscillator(), g = ac.createGain(); g.gain.value = 0.3;
  const dst = ac.createMediaStreamDestination(); o.connect(g); g.connect(dst); o.start();
  const cv = document.createElement('canvas'); const vt = cv.captureStream(1).getVideoTracks()[0];
  return new MediaStream([...dst.stream.getAudioTracks(), vt]); };"""
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"]); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="tts"]'); pg.wait_for_timeout(400); pg.evaluate(FAKE)
    pg.evaluate("$('#tt-rec').click()"); assert pg.is_visible("#rec-dlg"); ok("recorder dialog opens")
    pg.click("#rec-start"); pg.wait_for_function("document.querySelector('#rec-st').textContent.includes('녹음 중')"); pg.wait_for_timeout(4500)
    pg.click("#rec-stop"); pg.wait_for_selector("#rec-wave:not([hidden])", timeout=10000)
    dur = pg.evaluate("parseFloat(document.querySelector('#rec-len').textContent.split('전체 ')[1])"); assert 3.5 < dur < 6.5, dur; ok(f"recorded {dur:.1f}s, waveform shown")
    box = pg.locator("#rec-wave").bounding_box(); pg.mouse.move(box["x"] + box["width"] * 0.05, box["y"] + 50); pg.mouse.down(); pg.mouse.move(box["x"] + box["width"] * 0.9, box["y"] + 50, steps=5); pg.mouse.up()
    s, e = float(pg.input_value("#rec-s")), float(pg.input_value("#rec-e")); assert s < 0.6 and e > dur * 0.8, (s, e); ok("drag on the waveform selects a range")
    with pg.expect_download() as dl: pg.click("#rec-save")
    raw = Path(dl.value.path()).read_bytes(); assert raw[:4] == b"RIFF" and raw[8:12] == b"WAVE" and abs((len(raw) - 44) / 2 / 24000 - (e - s)) < 0.15; ok("wav export: 24kHz mono 16-bit, selected length")
    pg.fill("#rec-s", "0"); pg.fill("#rec-e", "1"); pg.click("#rec-use"); assert "3초" in pg.inner_text("#rec-st"); ok("too-short selection refused")
    pg.fill("#rec-e", str(round(dur - 0.2, 1))); pg.click("#rec-use"); pg.wait_for_function("document.querySelector('#tt-ref').value.length===12")
    assert not pg.is_visible("#rec-dlg") and list((hub.TTS_DIR / "ref").glob("*.wav")); ok("selection uploaded as the voice sample")
    assert not errs, errs
print("ALL OK")
