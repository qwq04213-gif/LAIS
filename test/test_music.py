"""음악 만들기(ACE-Step 1.5): 그래프, 저장, 에러 안내, 오디오 제공."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, urllib.request
os.environ["TEST_HUB_PORT"] = "17898"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def wait(jid):
    for _ in range(300):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def cls(wf, c): return [v["inputs"] for v in wf.values() if v["class_type"] == c]
j = wait(post("/api/job", {"kind": "music", "tags": "lo-fi, chill"})["id"]); assert j["state"] == "error" and "ACE-Step" in j["error"] and "설치" in j["error"], j; ok("no model → tells where to install")
(M / "checkpoints").mkdir(exist_ok=True); (M / "checkpoints" / "ace_step_1.5_turbo_aio.safetensors").write_bytes(b"x")
L = json.load(urllib.request.urlopen(B + "/api/lists")); assert L["musicmodels"] == ["ace_step_1.5_turbo_aio.safetensors"] and L["music_nodes"] is True and "ace_step_1.5_turbo_aio.safetensors" not in L["checkpoints"] and "ace_step_1.5_turbo_aio.safetensors" not in L["anymodels"]; ok("model listed; nodes reported present")
j = wait(post("/api/job", {"kind": "music", "tags": " "})["id"]); assert j["state"] == "error" and "어떤 음악" in j["error"]; ok("empty tags → asks for a description")
SUBMITTED.clear(); j = wait(post("/api/job", {"kind": "music", "tags": "k-pop, upbeat, female vocal", "lyrics": "[verse]\n안녕 오늘도", "seconds": 45, "bpm": 128, "language": "ko", "keyscale": "A minor", "timesignature": "4", "seed": 7})["id"])
assert j["state"] == "done" and len(j["images"]) == 1 and j["images"][0].endswith(".mp3") and "/%EC%9D%8C%EC%95%85/" in j["images"][0], j
g = SUBMITTED[-1]; t = cls(g, "TextEncodeAceStepAudio1.5")[0]
assert t["tags"].startswith("k-pop") and t["lyrics"].startswith("[verse]") and t["duration"] == 45 and t["bpm"] == 128 and t["language"] == "ko" and t["keyscale"] == "A minor" and t["timesignature"] == "4" and t["generate_audio_codes"] is True, t
assert cls(g, "EmptyAceStep1.5LatentAudio")[0]["seconds"] == 45; ks = cls(g, "KSampler")[0]; assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (8, 1.0, "euler", "simple")
sv = cls(g, "SaveAudioAdvanced")[0]; assert sv["format"] == "mp3" and sv["format.quality"] == "V0", sv; ok("graph: tags/lyrics/length/BPM/key/language wired; turbo defaults 8 steps CFG 1; mp3 with dotted quality key")
f = hub.OUT / "음악" / j["images"][0].split("/")[-1]; assert f.is_file() and f.read_bytes().startswith(b"ID3") and (f.parent / (f.name + ".json")).is_file()
info = json.loads((f.parent / (f.name + ".json")).read_text(encoding="utf-8")); assert info["prompt"].startswith("k-pop") and info["seconds"] == 45; ok("file and settings saved in outputs/음악")
r = urllib.request.urlopen(B + j["images"][0]); assert r.headers["Content-Type"] == "audio/mpeg" and r.read().startswith(b"ID3"); ok("served with an audio content type (the browser can play it)")
SUBMITTED.clear(); wait(post("/api/job", {"kind": "music", "tags": "piano", "instrumental": True, "lyrics": "should be ignored", "format": "flac", "no_codes": True})["id"]); g = SUBMITTED[-1]
assert cls(g, "TextEncodeAceStepAudio1.5")[0]["lyrics"] == "" and cls(g, "TextEncodeAceStepAudio1.5")[0]["generate_audio_codes"] is False and cls(g, "SaveAudioAdvanced")[0] == {"audio": cls(g, "SaveAudioAdvanced")[0]["audio"], "filename_prefix": "audio/hub", "format": "flac"}; ok("instrumental drops lyrics; flac has no quality key; codes can be turned off")
SUBMITTED.clear(); wait(post("/api/job", {"kind": "music", "tags": "x", "seconds": 99999, "bpm": 9999, "language": "zz", "keyscale": "zz", "timesignature": "9"})["id"]); t = cls(SUBMITTED[-1], "TextEncodeAceStepAudio1.5")[0]
assert t["duration"] == 300 and t["bpm"] == 240 and t["language"] == "ko" and t["keyscale"] == "C major" and t["timesignature"] == "4"; ok("out-of-range values are clamped to what the node accepts")
STATE["missing"].add("SaveAudioAdvanced"); hub.caps(True)
j = wait(post("/api/job", {"kind": "music", "tags": "piano"})["id"]); assert j["state"] == "error" and "SaveAudioAdvanced" in j["error"] and "업데이트" in j["error"], j; assert json.load(urllib.request.urlopen(B + "/api/lists"))["music_nodes"] is False; ok("old ComfyUI → update hint naming the node")
STATE["missing"].discard("SaveAudioAdvanced"); hub.caps(True)
g = json.load(urllib.request.urlopen(B + "/api/gallery")); mus = [i for i in g["items"] if i["kind"] == "음악"]; assert mus and all(i["type"] == "audio" for i in mus); ok("music files show in the gallery as audio")
print("ALL OK")
