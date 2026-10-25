# -*- coding: utf-8 -*-
"""소리 분리 엔진 — Demucs(Meta, MIT). 목소리·드럼·베이스·나머지(또는 기타·피아노까지)로 나눠요.
다른 엔진과 섞이지 않게 engine/demucs 에 전용 파이썬 환경을 따로 만들어요. 그 폴더를 지우면 깨끗이 사라져요.
분리 모델(약 80MB~320MB)은 처음 분리할 때 engine/demucs/models 로 내려받아요."""
import io
import json
import os
import shutil
import subprocess
import threading
import urllib.request
import zipfile
from pathlib import Path

NO_WIN = 0x08000000 if os.name == "nt" else 0
UV_URL = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
MODELS = {"htdemucs": "기본 — 4갈래(목소리·드럼·베이스·나머지), 빠름", "htdemucs_ft": "정확하게 — 4갈래, 4배 느림",
          "htdemucs_6s": "6갈래 — 기타·피아노까지(기타·피아노는 덜 정확)"}
STEMS = {"vocals": "목소리", "drums": "드럼", "bass": "베이스", "other": "나머지 악기", "guitar": "기타", "piano": "피아노", "no_vocals": "반주(목소리 뺀 것)"}
DEPS = ["dora-search", "einops", "julius>=0.2.3", "openunmix", "pyyaml", "tqdm", "soundfile", "numpy<2.3"]
JOB = {"state": "", "msg": ""}
_LOCK = threading.Lock()


def base(root):
    return Path(root) / "engine" / "demucs"


def py_of(root):
    v = base(root) / "venv"
    return v / "Scripts" / "python.exe" if os.name == "nt" else v / "bin" / "python"


def installed(root):
    return (base(root) / ".ready").exists() and py_of(root).exists()


def status(root):
    return {"installed": installed(root), "state": JOB.get("state", ""), "msg": JOB.get("msg", ""), "models": MODELS,
            "size": "엔진 약 5GB + 모델 80~320MB", "license": "MIT(상업 이용 가능)"}


def _env(root):
    b = base(root)
    e = dict(os.environ)
    e.update(UV_CACHE_DIR=str(b / "uv-cache"), UV_PYTHON_INSTALL_DIR=str(b / "python"), UV_PYTHON_PREFERENCE="only-managed", UV_LINK_MODE="copy",
             NO_COLOR="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TORCH_HOME=str(b / "models"), XDG_CACHE_HOME=str(b / "cache"))
    return e


def _run(cmd, env, log, label):
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
    b = base(root)
    b.mkdir(parents=True, exist_ok=True)
    log = open(b / "install.log", "w", encoding="utf-8")
    try:
        env, uv, py = _env(root), _uv(root), py_of(root)
        if not py.exists():
            _run([uv, "venv", "--python", "3.11", b / "venv"], env, log, "파이썬 환경 만드는 중…(처음엔 파이썬을 내려받아요)")
        _run([uv, "pip", "install", "--python", py, "--index-url", TORCH_INDEX, "torch==2.8.0", "torchaudio==2.8.0"], env, log, "그래픽카드용 PyTorch 받는 중…(약 3GB, 오래 걸려요)")
        _run([uv, "pip", "install", "--python", py, *DEPS], env, log, "분리 엔진 부품 설치 중…")
        _run([uv, "pip", "install", "--python", py, "--no-deps", "demucs==4.0.1"], env, log, "분리 엔진(Demucs) 설치 중…")
        shutil.copy2(Path(__file__).parent / "audio_worker.py", b / "worker.py")
        (b / ".ready").write_text("ok", encoding="utf-8")
        JOB.update(state="done", msg="설치했어요. 분리 모델은 처음 분리할 때 내려받아요.")
    except Exception as e:  # noqa: BLE001
        JOB.update(state="error", msg=(str(e) or type(e).__name__)[:300] + " (자세한 내용: engine\\demucs\\install.log — 다시 누르면 이어서 해요)")
    finally:
        log.close()


def uninstall(root):
    if JOB.get("state") == "running":
        return {"error": "설치 중에는 지울 수 없어요."}
    shutil.rmtree(base(root), ignore_errors=True)
    JOB.update(state="", msg="")
    return {"ok": not base(root).exists()}


def separate(root, wav, model, two, out_dir, say=None, cancel=None, popen=subprocess.Popen):
    """44.1kHz 스테레오 wav → out_dir 에 갈래별 wav. → [(갈래 이름, 경로)]"""
    if not installed(root):
        raise RuntimeError("소리 분리 엔진이 아직 없어요. 소리 분리·복원 화면의 [분리 엔진 설치]를 눌러 주세요.")
    b = base(root)
    shutil.copy2(Path(__file__).parent / "audio_worker.py", b / "worker.py")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "job.json"
    jp.write_text(json.dumps({"wav": str(wav), "model": model if model in MODELS else "htdemucs", "two": "vocals" if two else "", "out": str(out_dir)},
                             ensure_ascii=False), encoding="utf-8")
    p = popen([str(py_of(root)), str(b / "worker.py"), str(jp)], env=_env(root), cwd=str(b), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
              text=True, encoding="utf-8", errors="replace", creationflags=NO_WIN)
    tail, done = [], None
    for line in p.stdout:
        line = line.rstrip()
        if line.startswith("PROGRESS:"):
            try:
                pc, msg = line[9:].split(" ", 1)
                say and say(float(pc), msg)
            except ValueError:
                pass
        elif line.startswith("DONE:"):
            try:
                done = json.loads(line[5:])
            except ValueError:
                done = None
        elif line:
            tail = (tail + [line])[-20:]
        if cancel and cancel():
            p.kill()
            raise RuntimeError("중단했어요.")
    p.wait()
    if p.returncode or not done:
        err = next((t for t in reversed(tail) if t.startswith("ERR:")), "") or (tail[-1] if tail else f"코드 {p.returncode}")
        if "out of memory" in err.lower():
            err = "그래픽카드 메모리가 부족해요. 다른 작업을 끄거나 '기본' 모델로 해 주세요."
        raise RuntimeError("소리를 나누지 못했어요: " + err.replace("ERR:", "").strip()[:300])
    return [(d["stem"], out_dir / d["file"]) for d in done if (out_dir / d["file"]).is_file()]
