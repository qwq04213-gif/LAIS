"""3.13 오류1: 받아쓰기 워커가 ffmpeg 없이(PATH 에 없어도) 허브가 뽑은 wav 를 읽어요."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import json, os, subprocess, sys, wave, struct, tempfile
d = tempfile.mkdtemp(); wav = os.path.join(d, "a.wav")
w = wave.open(wav, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(struct.pack("<16000h", *([1000] * 16000))); w.close()
job = os.path.join(d, "j.json"); out = os.path.join(d, "o.json")
json.dump({"audio": wav, "model": "turbo", "lang": "", "out": out, "models": d}, open(job, "w"))
env = dict(os.environ, PYTHONPATH=BASE + "/test/stubs", PATH="/nonexistent")
r = subprocess.run([sys.executable, BASE + "/LocalAI-Studio/hub/asr_worker.py", job], env=env, capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
segs = json.load(open(out, encoding="utf-8")); assert segs[0]["text"] == "안녕하세요" and segs[0]["e"] == 1.0, segs
print("PASS worker reads the 16 kHz wav itself (no ffmpeg needed)"); print("ALL OK")
