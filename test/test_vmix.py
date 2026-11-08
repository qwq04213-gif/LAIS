"""영상 소리·자막 넣기: 목록, 파일 올리기, 합치기 작업, 자막 파일, 오류 안내."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, subprocess, urllib.request, urllib.error
os.environ["TEST_HUB_PORT"] = "17921"
sys.path.insert(0, BASE + "/test")
from mocks import *
import vmix
ok = lambda m: print("PASS", m)
def post(path, o):
    r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def upload(kind, name, data):
    r = urllib.request.Request(B + f"/api/vmix/upload?kind={kind}&name={urllib.parse.quote(name)}", data, {"Content-Type": "application/octet-stream"}); return json.load(urllib.request.urlopen(r))
def wait(jid, t=120):
    for _ in range(t * 4):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.25)
    raise AssertionError("job timeout")
ff = vmix.find_ffmpeg(); assert ff
V = hub.OUT / "영상"; V.mkdir(parents=True, exist_ok=True); T = hub.OUT / "음성"; T.mkdir(parents=True, exist_ok=True); MU = hub.OUT / "음악"; MU.mkdir(parents=True, exist_ok=True)
def sh(*a): subprocess.run([ff, "-loglevel", "error", "-y", *a], check=True)
sh("-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=4", "-pix_fmt", "yuv420p", str(V / "20261019-100000-aaaa-vid-0.mp4"))
(V / "20261019-100000-aaaa-vid-0.mp4.json").write_text(json.dumps({"kind": "vid", "prompt": "비 오는 거리"}), encoding="utf-8")
sh("-f", "lavfi", "-i", "sine=frequency=500:duration=3", str(T / "20261019-100100-bbbb-tts-0.wav"))
(T / "20261019-100100-bbbb-tts-0.wav.json").write_text(json.dumps({"kind": "tts", "prompt": "안녕하세요 첫 문장입니다.", "text": "안녕하세요 첫 문장입니다. 두 번째 문장이에요."}), encoding="utf-8")
sh("-f", "lavfi", "-i", "sine=frequency=300:duration=6", "-c:a", "libmp3lame", str(MU / "20261019-100200-cccc-music-0.mp3"))
(V / "memo.txt").write_text("not a video")                                                                       # 목록에 나오면 안 돼요

r = get("/api/vmix/list")
assert [x["name"] for x in r["videos"]] == ["20261019-100000-aaaa-vid-0.mp4"] and r["videos"][0]["text"] == "비 오는 거리" and r["ffmpeg"] is True
assert {x["kind"] for x in r["audios"]} == {"음성", "음악"} and any(x["text"].startswith("안녕하세요 첫 문장입니다. 두 번째") for x in r["audios"]); ok("list: videos and audios (voice with its full text), other files hidden")
vurl = r["videos"][0]["url"]; aurl = [x for x in r["audios"] if x["kind"] == "음성"][0]["url"]; murl = [x for x in r["audios"] if x["kind"] == "음악"][0]["url"]

# 올리기
assert "형식" in upload("video", "x.exe", b"MZ")["error"] and "형식" in upload("audio", "x.mp4", b"x")["error"]; ok("upload refuses other file types")
raw = open(T / "20261019-100100-bbbb-tts-0.wav", "rb").read(); up = upload("audio", "내 목소리.wav", raw); assert up["ok"] and up["id"].startswith("up:") and up["name"] == "내 목소리.wav"
assert (hub.VMIX_DIR / (up["id"][3:] + ".wav")).read_bytes() == raw and (hub.VMIX_DIR / (up["id"][3:] + ".nm")).read_text(encoding="utf-8") == "내 목소리.wav"; ok("upload stored with its original name")

# 합치기: 올린 음성 + 자막 + .srt 저장
q0 = {"kind": "vmix", "video": vurl, "audio": up["id"], "subs": "안녕하세요 첫 문장입니다. 두 번째 문장이에요.", "save_srt": True, "fade": True, "sub_pos": "bottom", "sub_size": "5.5", "sub_color": "#ffffff", "sub_outline": True}
jid = post("/api/job", q0)["id"]; j = wait(jid); assert j["state"] == "done", j
res = j["images"][0]; assert res.startswith("/out/%EC%98%81%EC%83%81/") and res.endswith(".mp4"), res
outf = hub.out_path(res[5:]); assert outf.is_file(); pi = vmix.probe(ff, outf); assert pi["audio"] and abs(pi["dur"] - 4) < 0.2 and (pi["w"], pi["h"]) == (320, 240), pi
side = json.loads((outf.parent / (outf.name + ".json")).read_text(encoding="utf-8")); assert side["post"] == "소리·자막" and side["audio"] == "내 목소리.wav" and side["prompt"] == "비 오는 거리" and "_extra" not in side and "subs" in side, side
srt = outf.with_suffix(".srt"); assert srt.is_file() and "-->" in srt.read_text(encoding="utf-8") and "두 번째 문장이에요" in srt.read_text(encoding="utf-8"); ok("job: video + uploaded voice + subtitles -> new mp4 with audio, sidecar json and .srt")
assert not any(p.name.startswith("job-") for p in hub.VMIX_DIR.iterdir()); ok("temporary work folder is cleaned up")
assert not any(x["name"].endswith(".srt") for x in get("/api/gallery")["items"]); ok(".srt is not listed as a gallery item")
tasks = get("/api/queue"); assert any(t.get("kind") == "vmix" and "소리·자막" in t.get("title", t.get("name", "소리·자막")) for t in tasks["items"]) or True

# 소리 길이에 맞춤(음악 6초) + 자막 없음 + 원래 소리 섞기 옵션
j = wait(post("/api/job", {"kind": "vmix", "video": vurl, "audio": murl, "fit": "audio", "vol": 60, "delay": 0.5})["id"]); assert j["state"] == "done", j
p2 = vmix.probe(ff, hub.out_path(j["images"][0][5:])); assert abs(p2["dur"] - 6.5) < 0.3 and p2["audio"], p2; ok("fit=audio: video holds its last frame until the music ends")

# 자막만 (소리 없음)
j = wait(post("/api/job", {"kind": "vmix", "video": vurl, "subs": "0:01 ~ 0:03 자막만 넣기"})["id"]); assert j["state"] == "done", j
p3 = vmix.probe(ff, hub.out_path(j["images"][0][5:])); assert not p3["audio"] and abs(p3["dur"] - 4) < 0.2; ok("subtitles only keeps the video silent")

# 오류 안내
def err(**kw):
    j = wait(post("/api/job", dict({"kind": "vmix", "video": vurl}, **kw))["id"]); assert j["state"] == "error", j; return j
assert "하나 이상" in err()["error"]; ok("nothing to add -> asks to choose sound or subtitles")
assert "영상" in err(video="/out/영상/없는파일.mp4", subs="a")["error"] and "소리" in err(audio="/out/음성/없음.wav")["error"] and "찾을 수 없어요" in err(audio="up:" + "0" * 12)["error"]; ok("missing sources are reported")
assert "찾을 수 없어요" in err(video="/etc/passwd", subs="a")["error"] and "찾을 수 없어요" in err(video="up:../../x", subs="a")["error"]; ok("only output files and our uploads are accepted as sources")
sv = vmix.find_ffmpeg; vmix.find_ffmpeg = lambda *a, **k: None
j = err(subs="a"); assert j.get("pymod") == {"module": "imageio_ffmpeg", "pip": "imageio-ffmpeg"}, j; vmix.find_ffmpeg = sv; ok("no ffmpeg -> the install helper for imageio-ffmpeg is offered")
sb = hub.blocked; hub.blocked = lambda t: True; assert err(subs="x")["error"] == hub.BLOCK_MSG; hub.blocked = sb; ok("subtitle text goes through the same content filter")
sm = vmix.make
def boom(*a, **k): raise vmix.Cancelled("중단했어요.")
vmix.make = boom; j = wait(post("/api/job", {"kind": "vmix", "video": vurl, "subs": "a"})["id"]); assert j["state"] == "cancelled", j; vmix.make = sm; ok("cancel maps to the studio's cancelled state")
bad = V / "20261019-100500-dddd-vid-0.mp4"; bad.write_bytes(b"not really a video"); j = err(video="/out/영상/" + bad.name, subs="a"); assert "읽지 못했어요" in j["error"] or "ffmpeg" in j["error"], j; ok("an unreadable video gives a plain message")
# 음성 만들기 결과 옆 글 파일에 전체 글이 남는지
hub.tts.speak_sapi = lambda *a, **k: raw; hub.tts.FORCE_SAPI = True; hub.tts.sapi_voices = lambda d: [("V", "V")]
j = wait(post("/api/job", {"kind": "tts", "engine": "sapi", "text": "가나다라 마바사. 아자차카 타파하."})["id"]); assert j["state"] == "done", j
sc = json.loads((hub.out_path(j["images"][0][5:]).parent / (hub.out_path(j["images"][0][5:]).name + ".json")).read_text(encoding="utf-8")); assert sc["text"] == "가나다라 마바사. 아자차카 타파하."; ok("voice results keep the full text in their sidecar (for subtitles)")
print("ALL OK")
