# -*- coding: utf-8 -*-
"""음성 모델 엔진(XTTS-v2 · Chatterbox · Kokoro) 설치·실행·삭제.
ComfyUI 와 섞이지 않도록 모델마다 따로 만든 전용 파이썬 환경(engine/tts/<이름>/venv)에 설치해요.
파이썬·캐시·모델도 모두 engine/tts 안에만 받아서, 그 폴더를 지우면 깨끗이 사라져요."""
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

NO_WIN = 0x08000000 if os.name == "nt" else 0
UV_URL = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
PERTH_ZIP = "https://github.com/resemble-ai/Perth/archive/ff1c8ac55a976971245cdd53c18d6131ca00d993.zip"
CBX_ZIP = "https://github.com/resemble-ai/chatterbox/archive/5de7a54aa4e5e2baadb0182dde554908b48b85c2.zip"

XTTS_LANGS = [("ko", "한국어"), ("en", "영어"), ("ja", "일본어"), ("zh-cn", "중국어"), ("es", "스페인어"), ("fr", "프랑스어"), ("de", "독일어"), ("it", "이탈리아어"), ("pt", "포르투갈어"),
              ("pl", "폴란드어"), ("tr", "터키어"), ("ru", "러시아어"), ("nl", "네덜란드어"), ("cs", "체코어"), ("ar", "아랍어"), ("hu", "헝가리어"), ("hi", "힌디어")]
CBX_LANGS = [("ko", "한국어"), ("en", "영어"), ("ja", "일본어"), ("zh", "중국어"), ("es", "스페인어"), ("fr", "프랑스어"), ("de", "독일어"), ("it", "이탈리아어"), ("pt", "포르투갈어"),
             ("ru", "러시아어"), ("ar", "아랍어"), ("hi", "힌디어"), ("tr", "터키어"), ("nl", "네덜란드어"), ("pl", "폴란드어"), ("sv", "스웨덴어"), ("da", "덴마크어"), ("fi", "핀란드어"),
             ("el", "그리스어"), ("he", "히브리어"), ("ms", "말레이어"), ("no", "노르웨이어"), ("sw", "스와힐리어")]

ENGINES = {
    "xtts": dict(title="XTTS-v2 — 한국어 포함 17개 언어, 목소리 따라 하기", size="엔진 약 6GB + 모델 약 2GB", license="비상업 용도만 허용(CPML)", license_url="https://tts-hub.github.io/cpml",
                 need_license=True, langs=XTTS_LANGS, clone=True, speakers=True, desc="내장 목소리 여러 개를 고르거나, 짧은 목소리 샘플(wav)을 올리면 그 목소리를 따라 읽어요."),
    "chatterbox": dict(title="Chatterbox 다국어 — 한국어 포함 23개 언어, 감정 조절", size="엔진 약 7GB + 모델 약 3GB", license="MIT(상업 이용 가능)", license_url="", need_license=False,
                       langs=CBX_LANGS, clone=True, speakers=False, desc="자연스러운 억양이 장점이에요. 목소리 샘플(wav)을 올리면 따라 하고, 없으면 기본 목소리로 읽어요. 만든 소리에는 사람 귀에 안 들리는 워터마크가 들어가요."),
    "kokoro": dict(title="Kokoro — 영어(미국·영국), 가볍고 빨라요", size="엔진 약 5GB + 모델 약 0.4GB", license="Apache-2.0(상업 이용 가능)", license_url="", need_license=False,
                   langs=[("en", "영어")], clone=False, speakers=True, desc="한국어는 지원하지 않아요. 영어 읽기만 빠르고 가볍게 하고 싶을 때 써요."),
}
KOKORO_VOICES = ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "am_adam", "am_michael", "bf_emma", "bf_isabella", "bm_george", "bm_lewis"]
JOBS = {}                      # 엔진 이름 → {"state","msg"}
_LOCK = threading.Lock()


def base(root):
    return Path(root) / "engine" / "tts"


def edir(root, eid):
    return base(root) / eid


def py_of(root, eid):
    v = edir(root, eid) / "venv"
    return v / "Scripts" / "python.exe" if os.name == "nt" else v / "bin" / "python"


def uv_path(root):
    return base(root) / "uv" / ("uv.exe" if os.name == "nt" else "uv")


def installed(root, eid):
    return (edir(root, eid) / ".ready").exists() and py_of(root, eid).exists()


def dir_bytes(p):
    t = 0
    for dp, _dn, fn in os.walk(p):
        for f in fn:
            try:
                t += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return t


def status(root):
    out = []
    for eid, e in ENGINES.items():
        d = edir(root, eid)
        j = JOBS.get(eid) or {}
        sp = []
        sj = d / "speakers.json"
        if eid == "xtts" and sj.exists():
            try:
                sp = json.loads(sj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                sp = []
        if eid == "kokoro":
            sp = KOKORO_VOICES
        out.append(dict(id=eid, title=e["title"], size=e["size"], license=e["license"], license_url=e["license_url"], need_license=e["need_license"], desc=e["desc"],
                        langs=[dict(code=c, name=n) for c, n in e["langs"]], clone=e["clone"], speakers=sp, has_speakers=e["speakers"],
                        installed=installed(root, eid), partial=d.exists() and not installed(root, eid) and j.get("state") != "running",
                        disk=dir_bytes(d) if d.exists() else 0, state=j.get("state", ""), msg=j.get("msg", "")))
    return out


def _env(root):
    b = base(root)
    e = dict(os.environ)
    e.update(UV_CACHE_DIR=str(b / "uv-cache"), UV_PYTHON_INSTALL_DIR=str(b / "python"), UV_PYTHON_PREFERENCE="only-managed", UV_LINK_MODE="copy", NO_COLOR="1", PYTHONUTF8="1",
             HF_HOME=str(b / "hf-home"), TTS_HOME=str(b / "xtts-data"), XDG_DATA_HOME=str(b / "xtts-data"), TORCH_HOME=str(b / "torch-home"), PYTHONIOENCODING="utf-8")
    return e


def _run(cmd, env, job, log, label, timeout=3600):
    job["msg"] = label
    p = subprocess.Popen([str(c) for c in cmd], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=NO_WIN)
    t0, tail = time.time(), []
    for line in p.stdout:
        line = line.rstrip()
        if line:
            tail.append(line)
            tail = tail[-40:]
            log.write(line + "\n")
            log.flush()
        if time.time() - t0 > timeout:
            p.kill()
            raise RuntimeError(label + " — 시간이 너무 오래 걸려 멈췄어요.")
    p.wait()
    if p.returncode:
        raise RuntimeError(f"{label} 중 실패했어요: " + (tail[-1] if tail else f"코드 {p.returncode}")[:240])


def _ensure_uv(root, job):
    uv = uv_path(root)
    if uv.exists():
        return uv
    if os.name != "nt":
        found = shutil.which("uv")
        if found:
            return Path(found)
        raise RuntimeError("uv 를 찾지 못했어요(윈도우에서는 자동으로 받아요).")
    job["msg"] = "설치 도구(uv) 받는 중…"
    uv.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(UV_URL, timeout=120) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if n.lower().endswith("uv.exe"):
                uv.write_bytes(z.read(n))
                break
        else:
            raise RuntimeError("uv 압축 파일에서 uv.exe 를 찾지 못했어요.")
    return uv


def pkgs_for(eid):
    """(torch 다음에 설치할 단계들) — 각 단계는 uv pip install 인자 목록."""
    if eid == "xtts":
        return [["coqui-tts", "soundfile"]]
    if eid == "kokoro":
        return [["kokoro>=0.9.4", "soundfile"]]
    if eid == "chatterbox":
        return [[PERTH_ZIP], ["--no-deps", CBX_ZIP],
                ["numpy<2", "librosa==0.11.0", "s3tokenizer", "transformers==5.2.0", "diffusers==0.29.0", "conformer==0.3.2", "safetensors==0.5.3", "spacy-pkuseg",
                 "pykakasi==2.3.0", "pyloudnorm", "omegaconf", "huggingface_hub", "tokenizers", "einops", "scipy", "tqdm", "soundfile"]]
    raise KeyError(eid)


def install(root, eid):
    """백그라운드 설치. 이미 설치 중이면 그대로 둬요. 중간에 멈춰도 같은 버튼으로 이어서 해요."""
    if eid not in ENGINES:
        return {"error": "알 수 없는 음성 모델이에요."}
    with _LOCK:
        if (JOBS.get(eid) or {}).get("state") == "running":
            return {"ok": True}
        if installed(root, eid):
            return {"error": "이미 설치돼 있어요."}
        JOBS[eid] = {"state": "running", "msg": "시작해요…"}
    threading.Thread(target=_install, args=(root, eid), daemon=True).start()
    return {"ok": True}


def _install(root, eid):
    J = JOBS[eid]
    d = edir(root, eid)
    d.mkdir(parents=True, exist_ok=True)
    logf = open(base(root) / f"install-{eid}.log", "w", encoding="utf-8")
    try:
        env = _env(root)
        uv = _ensure_uv(root, J)
        py = py_of(root, eid)
        if not py.exists():
            _run([uv, "venv", "--python", "3.11", d / "venv"], env, J, logf, "파이썬 환경 만드는 중…(처음엔 파이썬을 내려받아요)")
        _run([uv, "pip", "install", "--python", py, "--index-url", TORCH_INDEX, "torch==2.8.0", "torchaudio==2.8.0"], env, J, logf, "그래픽카드용 PyTorch 받는 중…(약 3GB, 오래 걸려요)", 7200)
        for i, step in enumerate(pkgs_for(eid), 1):
            _run([uv, "pip", "install", "--python", py] + step, env, J, logf, f"모델 부품 설치 중… ({i}/{len(pkgs_for(eid))})", 5400)
        shutil.copy2(Path(__file__).parent / "tts_worker.py", d / "worker.py")
        (d / ".ready").write_text("ok", encoding="utf-8")
        J["state"], J["msg"] = "done", "설치했어요. 모델 파일은 처음 음성을 만들 때 내려받아요(시간이 걸려요)."
    except Exception as e:  # noqa: BLE001
        J["state"], J["msg"] = "error", (str(e) or e.__class__.__name__)[:300] + f" (자세한 내용: engine\\tts\\install-{eid}.log — 같은 버튼을 다시 누르면 이어서 해요)"
    finally:
        logf.close()


def uninstall(root, eid):
    if eid not in ENGINES:
        return {"error": "알 수 없는 음성 모델이에요."}
    if (JOBS.get(eid) or {}).get("state") == "running":
        return {"error": "설치 중에는 지울 수 없어요."}
    d = edir(root, eid)
    shutil.rmtree(d, ignore_errors=True)
    JOBS.pop(eid, None)
    left = d.exists()
    # 어느 모델도 안 남았으면 공용 파일(파이썬·캐시·uv·모델 저장소)도 정리해요
    if not any(installed(root, k) for k in ENGINES) and not any((JOBS.get(k) or {}).get("state") == "running" for k in ENGINES):
        shutil.rmtree(base(root), ignore_errors=True)
    return {"ok": not left, "error": "" if not left else "일부 파일을 지우지 못했어요(사용 중일 수 있어요). 음성 만들기가 끝난 뒤 다시 눌러 주세요."}


def generate(root, eid, job, out_wav, say, cancel=None, popen=subprocess.Popen):
    """전용 환경의 파이썬으로 worker 를 실행해 out_wav 를 만들어요. 진행 글은 say(msg)로 알려요."""
    if not installed(root, eid):
        raise RuntimeError("이 음성 모델이 아직 설치되지 않았어요. 위의 [설치] 버튼을 눌러 주세요.")
    d = edir(root, eid)
    shutil.copy2(Path(__file__).parent / "tts_worker.py", d / "worker.py")
    jp = Path(out_wav).with_suffix(".job.json")
    jp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    env = _env(root)
    if eid == "xtts":
        env["COQUI_TOS_AGREED"] = "1"        # 화면에서 사용 조건에 동의한 경우에만 여기까지 와요
    p = popen([str(py_of(root, eid)), str(d / "worker.py"), eid, str(jp), str(out_wav)], env=env, cwd=str(d), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
              encoding="utf-8", errors="replace", creationflags=NO_WIN)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        if line.startswith("PROGRESS:"):
            say(line[9:])
        elif line:
            tail = (tail + [line])[-25:]
        if cancel and cancel():
            p.kill()
            raise RuntimeError("중단했어요.")
    p.wait()
    try:
        jp.unlink()
    except OSError:
        pass
    if p.returncode or not Path(out_wav).exists():
        msg = next((x for x in reversed(tail) if "Error" in x or "error" in x), tail[-1] if tail else f"코드 {p.returncode}")
        raise RuntimeError("음성을 만들지 못했어요: " + msg[:300])
    return Path(out_wav).read_bytes()
