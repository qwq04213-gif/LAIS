"""영상 소리·자막 화면: 목록·미리보기·음성 글 자동 채우기·올리기·합치기·결과 버튼·진입 버튼·ffmpeg 설치 안내."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, subprocess
os.environ["TEST_HUB_PORT"] = "17922"
sys.path.insert(0, BASE + "/test")
from mocks import *
import vmix
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
ff = vmix.find_ffmpeg()
V = hub.OUT / "영상"; V.mkdir(parents=True, exist_ok=True); T = hub.OUT / "음성"; T.mkdir(parents=True, exist_ok=True)
def sh(*a): subprocess.run([ff, "-loglevel", "error", "-y", *a], check=True)
vf = V / "20261019-100000-aaaa-vid-0.mp4"; sh("-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=3", "-pix_fmt", "yuv420p", str(vf))
vf.with_name(vf.name + ".json").write_text(json.dumps({"kind": "vid", "prompt": "비 오는 거리"}), encoding="utf-8")
af = T / "20261019-100100-bbbb-tts-0.wav"; sh("-f", "lavfi", "-i", "sine=frequency=500:duration=2", str(af))
af.with_name(af.name + ".json").write_text(json.dumps({"kind": "tts", "prompt": "안녕하세요", "text": "안녕하세요. 자막으로 쓸 글이에요."}), encoding="utf-8")
sh("-f", "lavfi", "-i", "sine=frequency=700:duration=2", "/tmp/tt/up_audio.mp3")
open("/tmp/tt/up.srt", "w", encoding="utf-8").write("1\n00:00:00,200 --> 00:00:01,200\n올린 자막\n")
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    if pg.locator("#ackb").is_visible(): None
    assert pg.locator('nav button[data-v="vmix"]').count() == 1 and "영상 소리·자막" in pg.inner_text('nav button[data-v="vmix"]'); ok("a tool entry exists in the sidebar")
    pg.click('nav button[data-v="vmix"]'); pg.wait_for_function("document.querySelector('#vm-video').options.length>0 && document.querySelector('#vm-video').value")
    assert "비 오는 거리" in pg.inner_text("#vm-video") and "음성" in pg.inner_text("#vm-audio"); ok("video and sound lists are filled from the studio's results")
    assert pg.is_visible("#vm-vprev") and not pg.is_visible("#vm-aopts") and not pg.is_visible("#vm-noff"); ok("video preview shows; sound options stay hidden until a sound is chosen")
    # 음성을 고르면 쓴 글이 자막으로
    pg.select_option("#vm-audio", index=1); pg.wait_for_timeout(200)
    assert pg.input_value("#f-vmix [name=subs]") == "안녕하세요. 자막으로 쓸 글이에요." and pg.is_visible("#vm-aopts") and pg.is_visible("#vm-aprev") and pg.is_visible("#vm-fromtts"); ok("choosing a voice fills the subtitle box with the text it was made from")
    pg.fill("#f-vmix [name=subs]", "내가 고친 글"); pg.click("#vm-fromtts"); assert pg.input_value("#f-vmix [name=subs]") == "안녕하세요. 자막으로 쓸 글이에요."; ok("[이 음성을 만들 때 쓴 글 가져오기] restores it")
    # 자막 파일 불러오기
    pg.set_input_files("#vm-srtfile", "/tmp/tt/up.srt"); pg.wait_for_function("document.querySelector('#f-vmix [name=subs]').value.includes('올린 자막')"); ok("an .srt file can be loaded into the subtitle box")
    # 소리 올리기
    pg.set_input_files("#vm-afile", "/tmp/tt/up_audio.mp3"); pg.wait_for_function("document.querySelector('#vm-audio').value.startsWith('up:')", timeout=10000)
    assert "올린 파일" in pg.inner_text("#vm-audio"); ok("a sound file from the computer is uploaded and selected")
    # 합치기
    pg.click("#f-vmix details summary"); pg.fill("#f-vmix [name=subs]", "첫 줄 자막\n둘째 줄 자막"); pg.check("#f-vmix [name=save_srt]"); pg.select_option("#f-vmix [name=sub_pos]", "top"); pg.fill("#f-vmix [name=vol]", "80")
    pg.click("#f-vmix .go"); pg.wait_for_selector("#v-vmix .res video", timeout=90000)
    pg.wait_for_function("document.querySelector('#v-vmix .jobbar .st').textContent.includes('완료')", timeout=10000)
    src = pg.get_attribute("#v-vmix .res video", "src"); assert "/out/" in src and src.endswith(".mp4"); ok("[합쳐서 새 영상 만들기] makes a new video and shows it in the result column")
    jf = hub.out_path(src[5:]); side = json.loads((jf.parent / (jf.name + ".json")).read_text(encoding="utf-8")); assert side["audio"] == "up_audio.mp3" and jf.with_suffix(".srt").is_file(); ok("result keeps what was used (uploaded sound name) and the .srt")
    assert pg.locator("#v-vmix .res button[data-to=vmix]").count() == 1; ok("result has [소리·자막 넣기] again so it can be chained")
    # 설정 기억
    pg.reload(); pg.wait_for_timeout(600); pg.click('nav button[data-v="vmix"]'); pg.wait_for_timeout(500)
    assert pg.input_value("#f-vmix [name=sub_pos]") == "top" and pg.input_value("#f-vmix [name=vol]") == "80" and pg.input_value("#f-vmix [name=subs]") == ""; ok("look and volume are remembered; picked files and text are not")
    # 진입: 영상 결과 / 음성 결과 / 갤러리
    pg.click('nav button[data-v="gal"]'); pg.wait_for_selector("#gal-grid .gt video"); pg.locator("#gal-grid .gt button[data-to=vmix]").first.click(); pg.wait_for_selector("#v-vmix.on", timeout=5000)
    assert pg.input_value("#vm-video").startswith("/out/"); ok("gallery video tile has a ♪ button that opens this screen with that video")
    pg.click('nav button[data-v="tts"]'); pg.evaluate("addTtsResults(document.querySelector('#v-tts'),{images:['/out/%EC%9D%8C%EC%84%B1/20261019-100100-bbbb-tts-0.wav']})")
    pg.click("#v-tts .res button[data-to=vmixa]"); pg.wait_for_selector("#v-vmix.on"); pg.wait_for_function("document.querySelector('#vm-audio').value.includes('bbbb')"); ok("voice results have [영상에 넣기]")
    # ffmpeg 없음 안내
    vmix_find = vmix.find_ffmpeg; vmix.find_ffmpeg = lambda *a, **k: None
    pg.reload(); pg.wait_for_timeout(500); pg.click('nav button[data-v="vmix"]'); pg.wait_for_selector("#vm-noff:not([hidden])", timeout=8000); ok("a note appears when ffmpeg is missing")
    pg.fill("#f-vmix [name=subs]", "자막"); pg.click("#f-vmix .go"); pg.wait_for_selector("#v-vmix .jobbar .pymod, #v-vmix .jobbar .pymod-install, #v-vmix .jobbar [data-pymod]", timeout=15000); ok("running anyway offers the install button for imageio-ffmpeg")
    vmix.find_ffmpeg = vmix_find
    # 빈 요청 안내
    pg.reload(); pg.wait_for_timeout(500); pg.click('nav button[data-v="vmix"]'); pg.wait_for_function("document.querySelector('#vm-video').value"); pg.click("#f-vmix .go"); pg.wait_for_function("document.querySelector('#v-vmix .jobbar .st').textContent.includes('하나 이상')"); ok("empty request is explained without starting a job")
    assert not errs, errs
    b.close()
print("ALL OK")
