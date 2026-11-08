"""3.16: 소리 분리·복원 — 고치기(ffmpeg 잡음·음량 2단계), 원본 비교 재생, 나누기(가짜 Demucs 일꾼)·갈래 이름, 다시 섞기, 영상에 넣기, 엔진 상태, 올린 파일 미리듣기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, subprocess, urllib.request, urllib.parse, functools
from pathlib import Path
os.environ["TEST_HUB_PORT"] = "17983"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def job2(o, t=300):
    jid = post("/api/job", o)["id"]
    for _ in range(t * 10):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
    raise AssertionError("timeout")
FF = "ffmpeg"
md = hub.OUT / "음악"; md.mkdir(parents=True, exist_ok=True)
song = md / "song.wav"
subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=60:d=6", "-f", "lavfi", "-i", "sine=f=880:d=6", "-f", "lavfi", "-i", "anoisesrc=d=6:a=0.05",
                "-filter_complex", "[0][1][2]amix=inputs=3:normalize=0,volume=0.2", "-ac", "2", "-ar", "44100", str(song)], check=True)
url = "/out/" + urllib.parse.quote("음악") + "/song.wav"
# 1) 엔진 상태
E = get("/api/audio/engine"); assert E["installed"] is False and "htdemucs" in E["models"] and "MIT" in E["license"]
j = job2({"kind": "audio", "op": "sep", "src": url}); assert j["state"] == "error" and "분리 엔진 설치" in j["error"], j
ok("engine status / separation without engine → install guidance")
# 2) 고치기
j = job2({"kind": "audio", "op": "fix", "src": url}); assert j["state"] == "error" and "고칠 항목" in j["error"]
j = job2({"kind": "audio", "op": "fix", "src": url, "rumble": True, "hum": "60", "declick": True, "denoise": "medium", "loud": "speech"})
assert j["state"] == "done", j
L = j["loud"]; assert L["before"] < -20 and abs(L["after"] + 16) < 1.5, L
assert "/소리 분리·복원/" in urllib.parse.unquote(j["images"][0]) and j["images"][0].endswith(".wav") and j["tracks"][0]["label"] == "고친 소리"
assert "윙 소리(60Hz)" in j["msg"] and "음량" in j["msg"]
r = urllib.request.urlopen(B + j["orig"]); assert r.headers["Content-Type"] == "audio/wav" and r.read(4) == b"RIFF"
try: urllib.request.urlopen(B + "/aorig/../x.wav"); raise AssertionError("must 404")
except urllib.error.HTTPError: pass
fixed = j["images"][0]
assert any(a["url"] == fixed for a in get("/api/vmix/list")["audios"])
ok(f"fix: rumble/hum/declick/denoise + 2-pass loudness {L['before']} → {L['after']} LUFS, original served for A/B, listed for reuse")
# 3) 나누기(가짜 일꾼: 진짜 worker.py 대신 같은 약속(PROGRESS/DONE)으로 wav 를 써요)
fake = TMP / "fake_worker.py"
fake.write_text(r'''
import sys, json, wave, shutil, pathlib
job = json.load(open(sys.argv[1], encoding="utf-8")); out = pathlib.Path(job["out"])
print("PROGRESS:0.02 분리 모델 불러오는 중", flush=True)
names = ["vocals", "no_vocals"] if job["two"] else ["drums", "bass", "other", "vocals"]
for i, n in enumerate(names):
    shutil.copy(job["wav"], out / f"{n}.wav"); print(f"PROGRESS:{(i+1)/len(names):.2f} 나누는 중 {i+1}/{len(names)}", flush=True)
print("DONE:" + json.dumps([{"stem": n, "file": n + ".wav"} for n in names]), flush=True)
''', encoding="utf-8")
hub.audio_sep.installed = lambda root: True
hub.audio_sep.py_of = lambda root: Path(sys.executable)
real_popen = subprocess.Popen
def fpop(cmd, **k): cmd = list(cmd); cmd[1] = str(fake); return real_popen(cmd, **k)
hub.audio_sep.separate = functools.partial(hub.audio_sep.separate, popen=fpop)
(hub.ROOT / "engine/demucs").mkdir(parents=True, exist_ok=True)
j = job2({"kind": "audio", "op": "sep", "src": url, "model": "htdemucs"}); assert j["state"] == "done", j
assert [t["stem"] for t in j["tracks"]] == ["vocals", "drums", "bass", "other"] and j["tracks"][0]["label"] == "목소리" and len(j["images"]) == 4, j
assert all("/소리 분리·복원/" in urllib.parse.unquote(u) for u in j["images"]) and j["orig"].startswith("/aorig/")
meta = json.loads((hub.OUT / "소리 분리·복원" / (urllib.parse.unquote(j["images"][0]).split("/")[-1] + ".json")).read_text(encoding="utf-8"))
assert meta["stem"] == "vocals" and meta["model"] == "htdemucs" and meta["source"] == "song.wav"
j2 = job2({"kind": "audio", "op": "sep", "src": url, "two": True}); assert [t["label"] for t in j2["tracks"]] == ["목소리", "반주(목소리 뺀 것)"]
assert not list((hub.ROOT / "cache/audio").glob("*/in.wav")), "work folders cleaned"
ok("separate: worker protocol, stems in fixed order with Korean names, two-stem mode, own folder + settings json")
# 4) 다시 섞기 · 영상에 넣기
j3 = job2({"kind": "audio", "op": "mix", "tracks": [{"url": j["images"][0], "vol": 0}, {"url": j["images"][1], "vol": 1.0}, {"url": j["images"][2], "vol": 0.5}]})
assert j3["state"] == "done" and j3["images"][0].endswith(".wav"), j3
assert job2({"kind": "audio", "op": "mix", "tracks": [{"url": j["images"][0], "vol": 0}]})["error"].startswith("소리를 켠")
assert job2({"kind": "audio", "op": "mix", "tracks": [{"url": "/out/../../etc/passwd", "vol": 1}]})["state"] == "error"
vd = hub.OUT / "영상"; vd.mkdir(parents=True, exist_ok=True)
subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x120:r=12:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(vd / "clip.mp4")], check=True)
j4 = job2({"kind": "audio", "op": "mux", "video": "/out/" + urllib.parse.quote("영상") + "/clip.mp4", "audio": fixed}); assert j4["state"] == "done", j4
o = hub.vmix.probe(FF, hub.OUT / "소리 분리·복원" / urllib.parse.unquote(j4["images"][0]).split("/")[-1]); assert o["audio"] and o["video"], o
ok("remix by volume (vocals off), bad paths rejected, new audio muxed into a video (video not re-encoded)")
# 5) 영상 소리로 고치기 · 올린 파일 미리듣기
r = urllib.request.Request(B + "/api/vmix/upload?kind=video&name=" + urllib.parse.quote("내 영상.mp4"), data=(vd / "clip.mp4").read_bytes(), method="POST")
U = json.load(urllib.request.urlopen(r)); rr = urllib.request.urlopen(B + "/upfile/" + U["id"][3:]); assert rr.headers["Content-Type"] == "video/mp4"
j5 = job2({"kind": "audio", "op": "fix", "src": U["id"], "loud": "music"}); assert j5["state"] == "error" and "소리가 없어요" in j5["error"], j5   # 소리 없는 영상
try: urllib.request.urlopen(B + "/upfile/zzz"); raise AssertionError("must 404")
except urllib.error.HTTPError: pass
ok("uploaded file preview route, silent video → clear error")
print("ALL OK")
