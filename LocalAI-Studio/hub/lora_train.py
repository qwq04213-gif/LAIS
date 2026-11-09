# -*- coding: utf-8 -*-
"""LoRA 학습 엔진 — kohya-ss/sd-scripts (Apache-2.0).
ComfyUI 와 섞이지 않게 engine/lora 에 전용 파이썬 환경과 sd-scripts 코드를 따로 둬요. 그 폴더를 지우면 깨끗이 사라져요.
지금은 SD1.5 · SDXL 계열(Illustrious·Pony·NoobAI 포함) 체크포인트로 LoRA 를 만들어요."""
import io
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

NO_WIN = 0x08000000 if os.name == "nt" else 0
UV_URL = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
GH = os.environ.get("GITHUB_URL", "https://github.com")
SD_TAG = "v0.11.1"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
JOB = {"state": "", "msg": ""}
_LOCK = threading.Lock()

# 쉬운 설정: 사진 수에 맞춰 단계 수를 정해요(사진 한 장을 몇 번 보는지)
PRESETS = {"fast": {"label": "빠르게 (가볍게 맛보기)", "per_img": 60, "min": 600, "max": 1200, "dim": 16, "lr": 1.5e-4},
           "normal": {"label": "보통 (추천)", "per_img": 100, "min": 1000, "max": 2400, "dim": 32, "lr": 1e-4},
           "careful": {"label": "꼼꼼하게 (오래 걸려요)", "per_img": 160, "min": 1600, "max": 4000, "dim": 32, "lr": 8e-5}}


def base(root):
    return Path(root) / "engine" / "lora"


def repo(root):
    return base(root) / "sd-scripts"


def py_of(root):
    v = base(root) / "venv"
    return v / "Scripts" / "python.exe" if os.name == "nt" else v / "bin" / "python"


def installed(root):
    return (base(root) / ".ready").exists() and py_of(root).exists() and (repo(root) / "sdxl_train_network.py").exists()


def status(root):
    return {"installed": installed(root), "state": JOB.get("state", ""), "msg": JOB.get("msg", ""), "size": "약 7GB", "license": "Apache-2.0 (sd-scripts)",
            "presets": {k: v["label"] for k, v in PRESETS.items()}}


def _env(root):
    b = base(root)
    e = dict(os.environ)
    e.update(UV_CACHE_DIR=str(b / "uv-cache"), UV_PYTHON_INSTALL_DIR=str(b / "python"), UV_PYTHON_PREFERENCE="only-managed", UV_LINK_MODE="copy",
             NO_COLOR="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8", HF_HOME=str(b / "hf-home"), PYTHONUNBUFFERED="1")
    return e


def _run(cmd, env, log, label, cwd=None, timeout=7200):
    JOB["msg"] = label
    p = subprocess.Popen([str(c) for c in cmd], env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", creationflags=NO_WIN)
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


def _get_code(root):
    """sd-scripts 코드를 정해진 판(태그)으로 받아 풀어요(git 이 없어도 돼요)."""
    dest = repo(root)
    if (dest / "sdxl_train_network.py").exists():
        return
    JOB["msg"] = f"학습 코드(sd-scripts {SD_TAG}) 받는 중…"
    data = None
    for url in (f"{GH}/kohya-ss/sd-scripts/archive/refs/tags/{SD_TAG}.zip", f"{GH}/kohya-ss/sd-scripts/archive/refs/heads/main.zip"):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                data = r.read()
            break
        except Exception:  # noqa: BLE001
            continue
    if not data:
        raise RuntimeError("학습 코드(sd-scripts)를 받지 못했어요. 인터넷 연결을 확인해 주세요.")
    tmp = base(root) / "code-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(tmp)
    top = next(p for p in tmp.iterdir() if p.is_dir())
    shutil.rmtree(dest, ignore_errors=True)
    top.replace(dest)
    shutil.rmtree(tmp, ignore_errors=True)


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
        _get_code(root)
        if not py.exists():
            _run([uv, "venv", "--python", "3.10", b / "venv"], env, log, "파이썬 환경 만드는 중…(처음엔 파이썬을 내려받아요)")
        _run([uv, "pip", "install", "--python", py, "--index-url", TORCH_INDEX, "torch==2.8.0", "torchvision==0.23.0"], env, log,
             "그래픽카드용 PyTorch 받는 중…(약 3GB, 오래 걸려요)")
        _run([uv, "pip", "install", "--python", py, "-r", "requirements.txt"], env, log, "학습 부품 설치 중…", cwd=repo(root))
        (b / ".ready").write_text("ok", encoding="utf-8")
        JOB.update(state="done", msg="설치했어요.")
    except Exception as e:  # noqa: BLE001
        JOB.update(state="error", msg=(str(e) or type(e).__name__)[:300] + " (자세한 내용: engine\\lora\\install.log — 다시 누르면 이어서 해요)")
    finally:
        log.close()


def uninstall(root):
    if JOB.get("state") == "running":
        return {"error": "설치 중에는 지울 수 없어요."}
    shutil.rmtree(base(root), ignore_errors=True)
    JOB.update(state="", msg="")
    return {"ok": not base(root).exists()}


def plan_steps(n_img, preset):
    pr = PRESETS.get(preset) or PRESETS["normal"]
    return int(min(pr["max"], max(pr["min"], n_img * pr["per_img"])))


def dataset_toml(img_dir, res, repeats, keep_tokens=1, flip=False):
    d = str(img_dir).replace("\\", "/")
    return (f'[general]\nshuffle_caption = true\ncaption_extension = ".txt"\nkeep_tokens = {int(keep_tokens)}\n\n'
            f'[[datasets]]\nresolution = {int(res)}\nbatch_size = 1\nenable_bucket = true\nmin_bucket_reso = 256\nmax_bucket_reso = {int(res) * 2}\n\n'
            f'[[datasets.subsets]]\nimage_dir = "{d}"\nnum_repeats = {int(repeats)}\nflip_aug = {"true" if flip else "false"}\n')


def build_cmd(root, a):
    """학습 명령. a: family(sdxl/sd15), ckpt, work(폴더), name, steps, dim, alpha, lr, res, sample_every, sample_prompt, unet_only, seed, optimizer"""
    script = "sdxl_train_network.py" if a["family"] == "sdxl" else "train_network.py"
    w = Path(a["work"])
    cmd = [py_of(root), repo(root) / script,
           "--pretrained_model_name_or_path", a["ckpt"], "--dataset_config", w / "dataset.toml",
           "--output_dir", w / "out", "--output_name", a["name"], "--save_model_as", "safetensors",
           "--network_module", "networks.lora", "--network_dim", str(a["dim"]), "--network_alpha", str(a["alpha"]),
           "--learning_rate", str(a["lr"]), "--unet_lr", str(a["lr"]), "--max_train_steps", str(a["steps"]),
           "--optimizer_type", a.get("optimizer") or "AdamW8bit", "--lr_scheduler", "cosine", "--lr_warmup_steps", str(max(0, a["steps"] // 20)),
           "--mixed_precision", "bf16", "--save_precision", "fp16", "--gradient_checkpointing", "--cache_latents", "--sdpa",
           "--max_data_loader_n_workers", "0", "--seed", str(a.get("seed") or 42), "--save_every_n_steps", str(max(100, a["steps"] // 4)),
           "--logging_dir", w / "logs"]
    if a["family"] == "sdxl":
        cmd += ["--no_half_vae"]
    if a.get("unet_only", True):
        cmd += ["--network_train_unet_only"]
    else:
        cmd += ["--text_encoder_lr", str(a["lr"] / 2)]
    if a.get("sample_every") and a.get("sample_prompt"):
        (w / "sample_prompts.txt").write_text(a["sample_prompt"].replace("\n", " ") + f" --w {a['res']} --h {a['res']} --s 24 --l 6 --d 1234\n", encoding="utf-8")
        cmd += ["--sample_every_n_steps", str(a["sample_every"]), "--sample_prompts", w / "sample_prompts.txt", "--sample_sampler", "euler_a"]
    return cmd


STEP_RX = re.compile(r"(\d+)/(\d+)\s*\[")
LOSS_RX = re.compile(r"avr_loss[=:]\s*([0-9.]+)")


def train(root, cmd, work, say, cancel=None, popen=subprocess.Popen):
    """학습을 돌려요. say(진행 0~1, 단계, 전체, loss, 글). 끝나면 만든 safetensors 경로."""
    work = Path(work)
    (work / "out").mkdir(parents=True, exist_ok=True)
    log = open(work / "train.log", "w", encoding="utf-8")
    p = popen([str(c) for c in cmd], env=_env(root), cwd=str(repo(root)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
              encoding="utf-8", errors="replace", creationflags=NO_WIN)
    tail, loss, last = [], None, 0.0
    try:
        for line in p.stdout:
            log.write(line)
            s = line.strip()
            if s:
                tail = (tail + [s])[-40:]
            m = LOSS_RX.search(s)
            if m:
                loss = float(m.group(1))
            st = STEP_RX.findall(s)
            if "steps" in s and st:
                a, b = map(int, st[-1])
                if b and time.time() - last > 0.5:
                    say(a / b, a, b, loss, f"학습 중 {a}/{b}단계" + (f" · loss {loss:.4f}" if loss is not None else ""))
                    last = time.time()
            elif "caching latents" in s.lower():
                say(None, 0, 0, None, "사진을 미리 읽는 중(latent 캐시)")
            elif "loading" in s.lower() and "model" in s.lower():
                say(None, 0, 0, None, "기반 모델을 불러오는 중")
            if cancel and cancel():
                p.kill()
                raise RuntimeError("중단했어요.")
        p.wait()
    finally:
        log.close()
    outs = sorted((work / "out").glob("*.safetensors"), key=lambda f: f.stat().st_mtime)
    final = [f for f in outs if not re.search(r"-\d{6}\.safetensors$", f.name)]
    if p.returncode or not (final or outs):
        msg = next((x for x in reversed(tail) if "Error" in x or "error" in x or "out of memory" in x.lower()), tail[-1] if tail else f"코드 {p.returncode}")
        if "out of memory" in " ".join(tail).lower():
            msg = "그래픽카드 메모리가 부족해요. 해상도를 낮추거나(768·512) 다른 프로그램을 닫고 다시 해 보세요."
        raise RuntimeError("LoRA 를 만들지 못했어요: " + msg[:300] + " (자세한 내용: 학습 폴더의 train.log)")
    return (final or outs)[-1]
