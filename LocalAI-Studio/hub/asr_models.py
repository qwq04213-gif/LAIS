# -*- coding: utf-8 -*-
"""대사 받아쓰기(음성 인식) 엔진 — OpenAI Whisper(오픈 소스, MIT).
음성 엔진(engine/tts)과 섞이지 않게 engine/asr/whisper 에 전용 파이썬 환경을 따로 만들어요. 그 폴더를 지우면 깨끗이 사라져요.
모델 파일(turbo 약 1.6GB / small 약 0.5GB)은 처음 받아쓸 때 engine/asr/models 로 내려받아요."""
import json
import os
import shutil
import subprocess
import threading
import urllib.request
import zipfile
import io
from pathlib import Path

NO_WIN = 0x08000000 if os.name == "nt" else 0
UV_URL = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
MODELS = {"turbo": "가장 정확 (약 1.6GB, VRAM 6GB 이상)", "small": "가볍게 (약 0.5GB)", "base": "아주 가볍게 (약 0.15GB, 정확도 낮음)"}
JOB = {"state": "", "msg": ""}
_LOCK = threading.Lock()


def base(root):
    return Path(root) / "engine" / "asr"


def py_of(root):
    v = base(root) / "whisper" / "venv"
    return v / "Scripts" / "python.exe" if os.name == "nt" else v / "bin" / "python"


def installed(root):
    return (base(root) / "whisper" / ".ready").exists() and py_of(root).exists()


def status(root):
    return {"installed": installed(root), "state": JOB.get("state", ""), "msg": JOB.get("msg", ""), "models": MODELS,
            "size": "엔진 약 5GB + 모델 0.15~1.6GB", "license": "MIT(상업 이용 가능)"}


def _env(root, ff=None):
    b = base(root)
    e = dict(os.environ)
    e.update(UV_CACHE_DIR=str(b / "uv-cache"), UV_PYTHON_INSTALL_DIR=str(b / "python"), UV_PYTHON_PREFERENCE="only-managed", UV_LINK_MODE="copy",
             NO_COLOR="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8", XDG_CACHE_HOME=str(b / "cache"))
    if ff:                                           # whisper 는 소리를 읽을 때 ffmpeg 를 불러요
        e["PATH"] = str(Path(ff).parent) + os.pathsep + e.get("PATH", "")
    return e


def _run(cmd, env, log, label, timeout=7200):
    JOB["msg"] = label
    p = subprocess.Popen([str(c) for c in cmd], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=NO_WIN)
    tail = []
    for line in p.stdout:
        if line.strip():
            tail = (tail + [line.rstrip()])[-30:]
            log.write(line)
            log.flush()
    p.wait()
    if p.returncode:
        raise RuntimeError(f"{label} 중 실패했어요: " + (tail[-1] if tail else f"코드 {p.returncode}")[:240])


def _uv(root):
    uv = base(root) / "uv" / ("uv.exe" if os.name == "nt" else "uv")
    if uv.exists():
        return uv
    if os.name != "nt":
        found = shutil.which("uv")
        if found:
            return Path(found)
        raise RuntimeError("uv 를 찾지 못했어요(윈도우에서는 자동으로 받아요).")
    JOB["msg"] = "설치 도구(uv) 받는 중…"
    uv.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(UV_URL, timeout=120) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        n = next((n for n in z.namelist() if n.lower().endswith("uv.exe")), None)
        if not n:
            raise RuntimeError("uv 압축 파일에서 uv.exe 를 찾지 못했어요.")
        uv.write_bytes(z.read(n))
    return uv


def install(root):
    with _LOCK:
        if JOB.get("state") == "running":
            return {"ok": True}
        if installed(root):
            return {"error": "이미 설치돼 있어요."}
        JOB.update(state="running", msg="시작해요…")
    threading.Thread(target=_install, args=(root,), daemon=True).start()
    return {"ok": True}


def _install(root):
    d = base(root) / "whisper"
    d.mkdir(parents=True, exist_ok=True)
    log = open(base(root) / "install-whisper.log", "w", encoding="utf-8")
    try:
        env, uv, py = _env(root), _uv(root), py_of(root)
        if not py.exists():
            _run([uv, "venv", "--python", "3.11", d / "venv"], env, log, "파이썬 환경 만드는 중…(처음엔 파이썬을 내려받아요)")
        _run([uv, "pip", "install", "--python", py, "--index-url", TORCH_INDEX, "torch==2.8.0"], env, log, "그래픽카드용 PyTorch 받는 중…(약 3GB, 오래 걸려요)")
        _run([uv, "pip", "install", "--python", py, "openai-whisper>=20240930"], env, log, "받아쓰기 엔진 설치 중…")
        shutil.copy2(Path(__file__).parent / "asr_worker.py", d / "worker.py")
        (d / ".ready").write_text("ok", encoding="utf-8")
        JOB.update(state="done", msg="설치했어요. 모델은 처음 받아쓸 때 내려받아요.")
    except Exception as e:  # noqa: BLE001
        JOB.update(state="error", msg=(str(e) or type(e).__name__)[:300] + " (자세한 내용: engine\\asr\\install-whisper.log — 다시 누르면 이어서 해요)")
    finally:
        log.close()


def uninstall(root):
    if JOB.get("state") == "running":
        return {"error": "설치 중에는 지울 수 없어요."}
    shutil.rmtree(base(root), ignore_errors=True)
    JOB.update(state="", msg="")
    return {"ok": not base(root).exists()}


def transcribe(root, audio, model, lang, ff, say=None, cancel=None, popen=subprocess.Popen):
    """소리 파일 → [{"s","e","text"}] (초 단위). say(진행 0~1, 글)로 알려요."""
    if not installed(root):
        raise RuntimeError("대사 받아쓰기 엔진이 아직 없어요. 영상 분석 화면의 [받아쓰기 엔진 설치]를 눌러 주세요.")
    d = base(root) / "whisper"
    shutil.copy2(Path(__file__).parent / "asr_worker.py", d / "worker.py")
    out = Path(audio).with_suffix(".asr.json")
    job = {"audio": str(audio), "model": model if model in MODELS else "turbo", "lang": lang or "", "out": str(out), "models": str(base(root) / "models")}
    jp = Path(audio).with_suffix(".job.json")
    jp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    p = popen([str(py_of(root)), str(d / "worker.py"), str(jp)], env=_env(root, ff), cwd=str(d), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
              text=True, encoding="utf-8", errors="replace", creationflags=NO_WIN)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        if line.startswith("PROGRESS:"):
            try:
                pc, msg = line[9:].split(" ", 1)
                say and say(float(pc), msg)
            except ValueError:
                pass
        elif line:
            tail = (tail + [line])[-20:]
        if cancel and cancel():
            p.kill()
            raise RuntimeError("중단했어요.")
    p.wait()
    jp.unlink(missing_ok=True)
    if p.returncode or not out.exists():
        msg = next((x for x in reversed(tail) if "Error" in x or "error" in x), tail[-1] if tail else f"코드 {p.returncode}")
        raise RuntimeError("대사를 받아쓰지 못했어요: " + msg[:300])
    segs = json.loads(out.read_text(encoding="utf-8"))
    out.unlink(missing_ok=True)
    return segs
