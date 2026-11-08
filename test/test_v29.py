"""2.9.x: 말하는 영상 길게(5초씩 이어 붙이기), 영상 → GIF(진짜 ffmpeg), 결과·큰 화면에서 배경 지우기 바로가기, 시작하기 탭 숨기기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, subprocess, urllib.request
os.environ["TEST_HUB_PORT"] = "17954"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def job(o):
    jid = post("/api/job", o)["id"]
    for _ in range(600):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def cls(c): return [v["inputs"] for v in SUBMITTED[-1].values() if v["class_type"] == c]
def png():
    b = io.BytesIO(); Image.new("RGB", (300, 200), (10, 120, 200)).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
for f in ("diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors", "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "vae/wan_2.1_vae.safetensors", "audio_encoders/wav2vec2_large_english_fp16.safetensors"):
    (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
AUD = "data:audio/wav;base64," + base64.b64encode(b"RIFF" + bytes(4000)).decode()
j = job({"kind": "vid", "wan_ver": "s2v", "prompt": "talking", "image": png(), "audio": AUD, "sec": "15"}); assert j["state"] == "done", j
ext, cat = cls("WanSoundImageToVideoExtend"), cls("LatentConcat"); assert len(ext) == 3 and len(cat) == 3 and all(c["dim"] == "t" for c in cat) and cls("WanSoundImageToVideo")[0]["length"] == 77
dec = [v for v in SUBMITTED[-1].values() if v["class_type"] == "VAEDecode"][0]["inputs"]; assert SUBMITTED[-1][dec["samples"][0]]["class_type"] == "LatentConcat"
j = job({"kind": "vid", "wan_ver": "s2v", "prompt": "talking", "image": png(), "audio": AUD, "sec": "3"}); assert not cls("WanSoundImageToVideoExtend") and cls("WanSoundImageToVideo")[0]["length"] == 49
ok("talking video: 15s → 4 chunks of 77 frames joined on the time axis; 3s → single chunk")
j = job({"kind": "vid", "wan_ver": "s2v", "prompt": "talking", "image": png(), "audio": AUD, "sec": "15", "fast": "on"}); assert "가속 LoRA" in (j.get("error") or ""), j
(M / "loras").mkdir(exist_ok=True); (M / "loras" / "wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors").write_bytes(b"x"); (M / "loras" / "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors").write_bytes(b"x")
assert hub.vid_more_state()["s2v_fast"]
j = job({"kind": "vid", "wan_ver": "s2v", "prompt": "talking", "image": png(), "audio": AUD, "sec": "15", "fast": "on"}); assert j["state"] == "done", j
lo = cls("LoraLoaderModelOnly"); ks = cls("KSampler"); assert len(lo) == 1 and "high_noise" in lo[0]["lora_name"] and len(ks) == 4 and all(k["steps"] == 4 and k["cfg"] == 1.0 and k["model"] == ks[0]["model"] for k in ks)
assert SUBMITTED[-1][ks[0]["model"][0]]["class_type"] == "LoraLoaderModelOnly"; ok("S2V fast mode: lightx2v high-noise LoRA, 4 steps, CFG 1 on every chunk; clear message when the LoRA is missing")
vid = hub.OUT / "영상" / "t.mp4"; vid.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=1", str(vid)], check=True)
n0 = len(SUBMITTED); j = job({"kind": "vpost", "op": "gif", "video": "/out/영상/t.mp4"}); assert j["state"] == "done" and j["images"][0].endswith(".gif"), j
g = Image.open(io.BytesIO(urllib.request.urlopen(B + j["images"][0]).read())); assert g.format == "GIF" and g.n_frames >= 10 and g.width == 320 and len(SUBMITTED) == n0, (g.n_frames, g.size)
ok("video → GIF with the real ffmpeg, no ComfyUI job")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click("nav button[data-v=gen]"); pg.fill("#f-gen textarea[name=prompt]", "a cat"); pg.click("#f-gen .go"); pg.wait_for_selector("#v-gen .res figure img", timeout=20000)
    pg.locator("#v-gen .res figure .more summary").first.click(); pg.locator("#v-gen .res figure button[data-to=rmbg]").first.click()
    pg.wait_for_function("document.querySelector('#feat-form') && document.querySelector('#feat-form').dataset.f==='rmbg' && document.querySelector('#feat-form .mini[data-img=image]').value")
    ok("result card → 배경 지우기 opens the tool with the image filled in")
    pg.click("nav button[data-v=vid]"); pg.select_option("#f-vid select[name=wan_ver]", "s2v"); assert pg.eval_on_selector("#f-vid option[value='30']", "o=>!o.disabled")
    pg.select_option("#f-vid select[name=sec]", "30"); pg.select_option("#f-vid select[name=wan_ver]", "5b"); assert pg.input_value("#f-vid select[name=sec]") == "5" and pg.eval_on_selector("#f-vid option[value='30']", "o=>o.disabled"); ok("15/30s lengths only for talking video")
    pg.select_option("#f-vid select[name=wan_ver]", "s2v"); pg.select_option("#f-vid select[name=sec]", "30"); pg.wait_for_timeout(200)
    assert pg.is_visible("#vid-long-warn") and "7번" in pg.inner_text("#vid-long-warn") and pg.is_visible("#vid-fast-row"); pg.select_option("#f-vid select[name=wan_ver]", "5b"); assert pg.is_hidden("#vid-long-warn"); ok("long talking video warns and offers fast mode")
    pg.click("nav button[data-v=conf]"); pg.wait_for_timeout(300); pg.locator("#opt-start").evaluate("e=>e.closest('.cpane')&&e.closest('.cpane').id")
    pg.evaluate("document.querySelector('#opt-start').click()"); assert pg.is_hidden("nav button[data-v=start]")
    pg.reload(); pg.wait_for_timeout(600); assert pg.is_hidden("nav button[data-v=start]"); pg.evaluate("document.querySelector('#opt-start').click()"); assert pg.is_visible("nav button[data-v=start]"); ok("시작하기 tab can be hidden in settings (remembered)")
    assert not errs, errs
print("ALL OK")
