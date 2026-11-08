"""AI 음성 모델(XTTS·Chatterbox·Kokoro): 설치 단계, 실행 방식, 동의 확인, 목소리 샘플, 삭제."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, os, json, io, types, base64, pathlib, subprocess, importlib
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import tts_models as tm
ok = lambda m: print("PASS", m)
ROOT = hub.ROOT
st = {s["id"]: s for s in req("/api/tts/models")}
assert set(st) == {"qwen3", "xtts", "chatterbox", "kokoro"} and st["qwen3"]["clone"] and "Sohee" in st["qwen3"]["speakers"] and not st["qwen3"]["need_license"] and not any(s["installed"] for s in st.values()) and st["xtts"]["need_license"] and not st["kokoro"]["clone"]; ok("three models listed, none installed; XTTS needs license check, Kokoro cannot clone")
assert any(l["code"] == "ko" for l in st["xtts"]["langs"]) and any(l["code"] == "ko" for l in st["chatterbox"]["langs"]) and [l["code"] for l in st["kokoro"]["langs"]] == ["en"]; ok("Korean offered by XTTS and Chatterbox only")
# ── 설치 단계
cmds = []
def fake_run(cmd, env, job, log, label, timeout=0):
    cmds.append([str(c) for c in cmd]); job["msg"] = label
    if "venv" in cmd[1:2]:
        (pathlib.Path(str(cmd[-1])) / ("Scripts" if os.name == "nt" else "bin")).mkdir(parents=True, exist_ok=True); (pathlib.Path(str(cmd[-1])) / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")).write_text("x")
tm._run = fake_run; tm._ensure_uv = lambda root, job: pathlib.Path("/fake/uv")
def wait_state(eid):
    import time
    for _ in range(100):
        s = tm.JOBS.get(eid, {}).get("state")
        if s in ("done", "error"): return s
        time.sleep(0.05)
assert req("/api/tts/model/install", {"id": "xtts"}) == {"ok": True}; assert wait_state("xtts") == "done", tm.JOBS
c0 = cmds[0]; assert c0[:3] == ["/fake/uv", "venv", "--python"] and c0[3] == "3.11"; ok("environment: uv venv with Python 3.11 inside engine/tts/xtts")
assert "--index-url" in cmds[1] and "download.pytorch.org/whl/cu128" in " ".join(cmds[1]) and "torch==2.8.0" in cmds[1] and "torchaudio==2.8.0" in cmds[1]; ok("GPU PyTorch from the CUDA index, pinned")
assert cmds[2][-2:] == ["coqui-tts", "soundfile"]; ok("XTTS package installed after torch")
assert tm.installed(ROOT, "xtts") and (tm.edir(ROOT, "xtts") / "worker.py").exists(); ok("marker + worker copied → shows as installed")
env = tm._env(ROOT); assert all(str(base_) in env[k] for k, base_ in (("UV_CACHE_DIR", tm.base(ROOT)), ("UV_PYTHON_INSTALL_DIR", tm.base(ROOT)), ("HF_HOME", tm.base(ROOT)), ("TTS_HOME", tm.base(ROOT)))); ok("python, caches and models all land under engine/tts (nothing outside the program folder)")
cmds.clear(); assert req("/api/tts/model/install", {"id": "chatterbox"}) == {"ok": True}; wait_state("chatterbox")
flat = [" ".join(c) for c in cmds]; assert any("Perth/archive/ff1c8ac" in x for x in flat) and any("--no-deps" in x and "chatterbox/archive/5de7a54" in x for x in flat) and any("transformers==5.2.0" in x and "numpy<2" in x for x in flat); assert not any("git+" in x for x in flat); ok("Chatterbox: pinned GitHub zips (no git needed) + the repo's own dependency list")
# 실패 → 이어서
cmds.clear()
def boom(cmd, env, job, log, label, timeout=0):
    if any("kokoro>=" in str(x) for x in cmd): raise RuntimeError(label + " 중 실패했어요: no network")
    fake_run(cmd, env, job, log, label, timeout)
tm._run = boom; req("/api/tts/model/install", {"id": "kokoro"}); assert wait_state("kokoro") == "error"
s = {x["id"]: x for x in req("/api/tts/models")}["kokoro"]; assert not s["installed"] and s["partial"] and "install-kokoro.log" in tm.JOBS["kokoro"]["msg"] and "이어서" in tm.JOBS["kokoro"]["msg"]; ok("failed install → error with log name, marked partial so the same button continues")
tm._run = fake_run; cmds.clear(); req("/api/tts/model/install", {"id": "kokoro"}); assert wait_state("kokoro") == "done" and not any(c[1] == "venv" for c in cmds); ok("retry skips the environment step and finishes")
# ── 생성 (가짜 popen)
class FakeP:
    def __init__(s, cmd, **k):
        s.cmd = [str(c) for c in cmd]; s.returncode = 0; FakeP.last = s
        out = pathlib.Path(s.cmd[4]); jp = pathlib.Path(s.cmd[3]); s.job = json.loads(jp.read_text(encoding="utf-8")); out.write_bytes(b"RIFF" + b"\0" * 300)
        s.stdout = iter(["PROGRESS:모델 불러오는 중\n", "noise\n", "PROGRESS:음성 만드는 중\n"])
    def wait(s): return 0
    def kill(s): pass
orig_gen = tm.generate
tm.generate = lambda root, eid, job, out, say, cancel=None, popen=None: orig_gen(root, eid, job, out, say, cancel, FakeP)
w = lambda p: job({"kind": "tts", **p}, expect_ok=False)
j = w({"text": "안녕하세요", "engine": "xtts"}); assert "사용 조건" in j["error"]; ok("XTTS refuses without the license box")
j = w({"text": "안녕하세요", "engine": "xtts", "license_ok": "on", "language": "ko", "speaker": "Claribel Dervla", "speed": "2"}); assert j["state"] == "done" and j["images"][0].endswith(".wav"), j
c = FakeP.last; assert c.cmd[1].endswith("worker.py") and c.cmd[2] == "xtts" and c.job["text"] == "안녕하세요" and c.job["language"] == "ko" and c.job["speaker"] == "Claribel Dervla" and abs(c.job["speed"] - 1.15) < 1e-6 and not c.job["ref"]; ok("worker gets text via a JSON file (language, speaker, speed), env sets the license flag")
j = w({"text": "x", "engine": "xtts", "license_ok": "on", "language": "xx"}); assert FakeP.last.job["language"] == "ko"; ok("unknown language falls back")
j = w({"text": "x", "engine": "kokoro", "ref": "abcdef012345"}); assert "지원하지 않아요" in j["error"]; ok("Kokoro refuses a voice sample")
# ── 목소리 샘플
wav = b"RIFF" + b"\0\0\0\0" + b"WAVE" + b"\0" * 200000
up = req("/api/tts/ref", {"data": "data:audio/wav;base64," + base64.b64encode(wav).decode()}); assert up["ok"] and len(up["id"]) == 12; rid = up["id"]
assert "wav" in req("/api/tts/ref", {"data": base64.b64encode(b"ID3" + b"\0" * 200000).decode()})["error"]; assert "짧" in req("/api/tts/ref", {"data": base64.b64encode(b"RIFF\0\0\0\0WAVE").decode()})["error"]; ok("sample upload: wav only, too-short refused")
j = w({"text": "x", "engine": "chatterbox", "ref": rid, "language": "ko"}); assert "허락" not in (j.get("error") or ""); ok("voice sample works without a consent box")
j = w({"text": "x", "engine": "chatterbox", "ref": rid, "clone_ok": "on", "language": "ko", "emotion": "rich"}); assert j["state"] == "done" and FakeP.last.job["ref"].endswith(rid + ".wav") and FakeP.last.job["exaggeration"] == 0.8; ok("sample + consent → path passed to the worker; emotion mapped")
j = w({"text": "x", "engine": "chatterbox", "ref": "../../etc", "clone_ok": "on"}); assert "올바르지" in j["error"]; ok("sample id is validated (no path tricks)")
j = w({"text": "x", "engine": "chatterbox", "speaker": "../../x"}); assert j["state"] == "done" and FakeP.last.job["speaker"] == ""; ok("odd speaker names are dropped")
# ── 삭제
assert req("/api/tts/model/remove", {"id": "kokoro"})["ok"] and not tm.edir(ROOT, "kokoro").exists() and tm.edir(ROOT, "xtts").exists(); ok("remove deletes only that model's folder")
for e in ("xtts", "chatterbox"): req("/api/tts/model/remove", {"id": e})
assert not tm.base(ROOT).exists(); ok("last model removed → shared python/cache/models folder is cleaned up too")
# ── worker 스크립트(스텁 모듈로 호출 모양 확인)
import tts_worker
def stub(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m
calls = {}
class Dev: pass
stub("torch", cuda=types.SimpleNamespace(is_available=lambda: True))
class FakeTTS:
    speakers = ["Claribel Dervla", "Daisy Studios"]
    def __init__(s, name, progress_bar=False): calls["name"] = name
    def to(s, d): calls["dev"] = d; return s
    def tts_to_file(s, text, language, file_path, split_sentences, speed, **kw): calls["kw"] = (text, language, split_sentences, speed, kw); pathlib.Path(file_path).write_bytes(b"R" * 200)
stub("TTS"); stub("TTS.api", TTS=FakeTTS)
d = pathlib.Path("/tmp/tt/wk"); d.mkdir(exist_ok=True); (d / "j.json").write_text(json.dumps({"text": "안녕", "language": "ko", "speaker": "Daisy Studios", "ref": "", "speed": 1.1}), encoding="utf-8")
sys.argv = ["w", "xtts", str(d / "j.json"), str(d / "o.wav")]; tts_worker.main()
assert calls["name"] == "tts_models/multilingual/multi-dataset/xtts_v2" and calls["dev"] == "cuda" and calls["kw"] == ("안녕", "ko", True, 1.1, {"speaker": "Daisy Studios"}) and json.loads((d / "speakers.json").read_text(encoding="utf-8")) == FakeTTS.speakers; ok("worker/XTTS: model name, device, tts_to_file arguments, speaker list saved")
(d / "j.json").write_text(json.dumps({"text": "안녕", "language": "ko", "ref": "/x/r.wav", "speed": 1}), encoding="utf-8"); tts_worker.main(); assert calls["kw"][4] == {"speaker_wav": "/x/r.wav"}; ok("worker/XTTS: reference sample uses speaker_wav")
class FakeCB:
    sr = 24000
    @classmethod
    def from_pretrained(cls, device): calls["cb_dev"] = device; return cls()
    def generate(s, text, language_id, exaggeration=0.5, audio_prompt_path=None): calls["cb"] = (text, language_id, exaggeration, audio_prompt_path); return "WAV"
stub("chatterbox"); stub("chatterbox.mtl_tts", ChatterboxMultilingualTTS=FakeCB)
stub("torchaudio", save=lambda p, w, sr: pathlib.Path(p).write_bytes(b"R" * 200))
(d / "j.json").write_text(json.dumps({"text": "안녕", "language": "ko", "ref": "/x/r.wav", "exaggeration": 0.8}), encoding="utf-8"); sys.argv = ["w", "chatterbox", str(d / "j.json"), str(d / "o2.wav")]; tts_worker.main()
assert calls["cb"] == ("안녕", "ko", 0.8, "/x/r.wav") and calls["cb_dev"] == "cuda"; ok("worker/Chatterbox: from_pretrained(device) + generate(text, language_id, exaggeration, audio_prompt_path) + torchaudio.save")
import numpy as np
class FakePipe:
    def __init__(s, lang_code, repo_id): calls["kk"] = (lang_code, repo_id)
    def __call__(s, text, voice, speed): calls["kv"] = (voice, speed); yield ("g", "p", np.zeros(100, dtype="float32")); yield ("g", "p", np.zeros(50, dtype="float32"))
stub("kokoro", KPipeline=FakePipe); stub("soundfile", write=lambda p, a, sr: (calls.__setitem__("sf", (len(a), sr)), pathlib.Path(p).write_bytes(b"R" * 200)))
(d / "j.json").write_text(json.dumps({"text": "hello", "speaker": "bf_emma", "speed": 1.0}), encoding="utf-8"); sys.argv = ["w", "kokoro", str(d / "j.json"), str(d / "o3.wav")]; tts_worker.main()
assert calls["kk"] == ("b", "hexgrad/Kokoro-82M") and calls["kv"] == ("bf_emma", 1.0) and calls["sf"] == (150, 24000); ok("worker/Kokoro: KPipeline(lang_code, repo_id), voice, chunks joined at 24 kHz")
# Qwen3-TTS: 내장 목소리 / 목소리 따라 하기(내용 있음·없음), 긴 글 나눠 읽기
class FakeQ:
    @classmethod
    def from_pretrained(cls, repo, **kw): calls["q_repo"] = repo; calls["q_kw"] = kw; return cls()
    def generate_custom_voice(s, text, language, speaker, instruct=None): calls.setdefault("qc", []).append((text, language, speaker, instruct)); return [np.zeros(240, dtype="float32")], 24000
    def generate_voice_clone(s, text, language, ref_audio, ref_text=None, x_vector_only_mode=False): calls.setdefault("qv", []).append((text, language, ref_audio, ref_text, x_vector_only_mode)); return [np.zeros(240, dtype="float32")], 24000
stub("qwen_tts", Qwen3TTSModel=FakeQ); sys.modules["torch"].bfloat16 = "bf16"; sys.modules["torch"].float16 = "f16"; sys.modules["torch"].float32 = "f32"; sys.modules["torch"].cuda.is_bf16_supported = lambda: True
long = " ".join(["안녕하세요, 오늘은 날씨가 좋아요."] * 20)
(d / "j.json").write_text(json.dumps({"text": long, "language": "ko", "speaker": "Sohee", "emotion": "calm"}), encoding="utf-8"); sys.argv = ["w", "qwen3", str(d / "j.json"), str(d / "o4.wav")]; tts_worker.main()
assert calls["q_repo"].endswith("1.7B-CustomVoice") and calls["q_kw"]["attn_implementation"] == "sdpa" and calls["q_kw"]["dtype"] == "bf16" and len(calls["qc"]) >= 2 and all(c[1] == "Korean" and c[2] == "Sohee" and c[3] for c in calls["qc"])
assert "".join(c[0] for c in calls["qc"]).replace(" ", "") == long.replace(" ", ""); ok("worker/Qwen3: CustomVoice, Korean speaker, long text split into pieces without loss, emotion instruct")
(d / "j.json").write_text(json.dumps({"text": "안녕", "language": "en", "ref": "/x/r.wav", "ref_text": "hello there"}), encoding="utf-8"); tts_worker.main()
assert calls["q_repo"].endswith("1.7B-Base") and calls["qv"][-1] == ("안녕", "English", "/x/r.wav", "hello there", False)
(d / "j.json").write_text(json.dumps({"text": "안녕", "language": "ko", "ref": "/x/r.wav"}), encoding="utf-8"); tts_worker.main(); assert calls["qv"][-1][4] is True; ok("worker/Qwen3: clone with transcript, or speaker-embedding only without it")
print("ALL OK")
