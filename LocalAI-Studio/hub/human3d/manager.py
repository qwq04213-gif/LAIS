"""worker 설치·실행 관리(LAIS 본체 쪽).
윈도우에서는 WSL2(Ubuntu 22.04) 안에서 worker 를 돌려요 — ComfyUI 의 파이썬은 건드리지 않아요.
  설치:  wsl -d <배포판> -u root -- bash <LAIS>/engine/human3d/scripts/install_wsl.sh  (이어서 install_models.sh)
  실행:  wsl -d <배포판> -u root -- <home>/venv/bin/python -m worker.app --port 17861
worker 코드는 LAIS 폴더(engine/human3d)의 것을 WSL 에서 그대로 읽어요(/mnt/c/...) — LAIS 를 업데이트하면 worker 도 같이 새 판이 돼요.
시험·리눅스에서는 HUMAN3D_WORKER_CMD(직접 실행할 명령)로 바꿀 수 있어요.
★ 윈도우 + WSL2 실제 환경에서 확인하지 못했어요(미검증)."""
import json
import os
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path

from . import contracts as K
from .worker_client import Client

DISTRO = "Ubuntu-22.04"
WSL_HOME = "/root/lais-human3d"          # root 로 돌려서 설치 때 비밀번호를 묻지 않게 해요
STATE = {"install": {"state": "idle", "msg": "", "step": 0, "total": 0, "log": [], "need_smplx": None}, "proc": None, "started": 0.0, "port": int(os.environ.get("HUMAN3D_PORT") or K.PORT)}
_LOCK = threading.Lock()


def is_windows():
    return os.name == "nt"


def wsl_path(p):
    """C:\\a\\b → /mnt/c/a/b (윈도우가 아니면 그대로)."""
    s = str(p)
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", s)
    if not m:
        return s.replace("\\", "/")
    return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/")


HUB_DIR = Path(__file__).resolve().parents[1]                 # LocalAI-Studio/hub


def drop_dir(root):
    """SMPL-X 몸 모델 파일을 넣는 곳(LAIS 폴더 안 — 윈도우 탐색기로 바로 열 수 있어요). worker 가 여기서 엔진 자리로 복사해요."""
    return Path(root) / "models" / "human3d" / "smplx"


def engine_dir(root=None):
    """worker 코드가 있는 곳(LocalAI-Studio/engine/human3d) — 설치 폴더가 아니라 이 코드가 놓인 곳 기준이에요."""
    return HUB_DIR.parent / "engine" / "human3d"


def _run(cmd, timeout=30):
    try:
        kw = {"creationflags": 0x08000000} if is_windows() else {}
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, **kw)
        out = r.stdout or b""
        text = out.decode("utf-16-le", "replace") if out[:200].count(b"\0") > 20 else out.decode("utf-8", "replace")      # wsl.exe 는 UTF-16 으로 말할 때가 있어요
        return r.returncode, text.replace("\0", "") + (r.stderr or b"").decode("utf-8", "replace").replace("\0", "")
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError as e:
        return 126, str(e)


def wsl_status():
    """WSL2 와 Ubuntu 22.04 가 있는지. {"windows", "wsl", "distro", "version2", "text", "fix"}"""
    if os.environ.get("HUMAN3D_WORKER_CMD"):
        return {"windows": is_windows(), "wsl": True, "distro": True, "version2": True, "custom": True, "text": "직접 지정한 worker 명령을 써요.", "fix": ""}
    if not is_windows():
        return {"windows": False, "wsl": False, "distro": False, "version2": False, "text": "윈도우가 아니에요(WSL 없이 HUMAN3D_WORKER_CMD 로 worker 를 지정해 주세요).", "fix": ""}
    code, out = _run(["wsl.exe", "-l", "-v"])
    if code == 127 or (code != 0 and not out.strip()):
        return {"windows": True, "wsl": False, "distro": False, "version2": False, "text": "WSL 이 설치돼 있지 않아요.",
                "fix": "시작 메뉴에서 'PowerShell' 을 관리자 권한으로 열고  wsl --install -d Ubuntu-22.04  를 실행한 뒤 PC 를 다시 시작해 주세요. (처음 실행 때 Ubuntu 가 사용자 이름·비밀번호를 물어요)"}
    row = next((ln for ln in out.splitlines() if DISTRO.lower() in ln.lower()), None)
    if not row:
        return {"windows": True, "wsl": True, "distro": False, "version2": False, "text": "WSL 은 있는데 Ubuntu 22.04 가 없어요.",
                "fix": "PowerShell 에서  wsl --install -d Ubuntu-22.04  를 실행해 주세요."}
    v2 = row.split()[-1] == "2"
    return {"windows": True, "wsl": True, "distro": True, "version2": v2, "text": "WSL2 · Ubuntu 22.04 있음" if v2 else "Ubuntu 22.04 가 WSL1 로 돼 있어요(그래픽카드를 쓰려면 WSL2 여야 해요).",
            "fix": "" if v2 else "PowerShell 에서  wsl --set-version Ubuntu-22.04 2  를 실행해 주세요."}


def _wsl(*args):
    return ["wsl.exe", "-d", DISTRO, "-u", "root", "--", *args]


def worker_cmd(root, port):
    """worker 를 띄울 명령과 작업 폴더·환경."""
    custom = os.environ.get("HUMAN3D_WORKER_CMD")
    if custom:
        return shlex.split(custom, posix=not is_windows()) + ["--port", str(port)], str(engine_dir(root)), dict(os.environ, HUMAN3D_DROP=str(drop_dir(root)), PYTHONPATH=os.pathsep.join([str(engine_dir(root)), str(HUB_DIR)] + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])))
    eng = wsl_path(engine_dir(root))
    hub = wsl_path(HUB_DIR)
    sh = f"[ -f {WSL_HOME}/env.sh ] && . {WSL_HOME}/env.sh; cd {shlex.quote(eng)} && PYTHONPATH={shlex.quote(eng)}:{shlex.quote(hub)} HUMAN3D_HOME={WSL_HOME} HUMAN3D_DROP={shlex.quote(wsl_path(drop_dir(root)))} exec {WSL_HOME}/venv/bin/python -m worker.app --port {int(port)} --home {WSL_HOME}"
    return _wsl("bash", "-lc", sh), None, None


def job_path(p):
    """본체가 보는 작업 폴더 → worker 가 보는 경로."""
    return str(p) if os.environ.get("HUMAN3D_WORKER_CMD") or not is_windows() else wsl_path(p)


def running(port=None):
    return Client(port or STATE["port"]).health()


def code_hash():
    """지금 LAIS 폴더에 있는 worker 코드의 지문(worker 의 runtime.code_hash 와 같은 계산)."""
    import hashlib
    d = engine_dir() / "worker"
    h = hashlib.sha1()
    files = []
    for root, sub, names in sorted(os.walk(d)):
        sub[:] = sorted(x for x in sub if x != "__pycache__")
        for n in sorted(names):
            if n.endswith(".py"):
                files.append(Path(root) / n)
    for p in files:
        h.update(str(p.relative_to(d)).replace(os.sep, "/").encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def start(root, port=None, wait=40, log=None):
    """worker 가 안 떠 있으면 띄우고, 응답할 때까지 기다려요. 돌려주는 값: health(dict) 또는 None."""
    port = port or STATE["port"]
    with _LOCK:
        h = running(port)
        if h and h.get("code") != code_hash() and not h.get("busy") and not os.environ.get("HUMAN3D_KEEP_WORKER"):
            # LAIS 를 업데이트했는데 예전 코드로 뜬 worker 가 남아 있어요(WSL 안의 프로그램은 LAIS 를 꺼도 살아 있어요) → 내리고 새로 띄워요.
            # 코드 지문(code)이 아예 없는 worker(4.9.1 이전)도 예전 것이에요 — 실제로 4.9.1 worker 가 4.9.2 에서 남아 성별 없이 몸을 맞췄어요.
            if log:
                log("[인체 3D] worker 코드가 바뀌어서 다시 띄워요")
            Client(port).shutdown()
            for _ in range(30):
                if not running(port):
                    break
                time.sleep(0.2)
            h = None
        if h:
            return h
        cmd, cwd, env = worker_cmd(root, port)
        logs = Path(root) / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        out = open(logs / "human3d-worker.log", "ab")
        try:
            kw = {"creationflags": 0x08000000} if is_windows() else {"start_new_session": True}
            STATE["proc"] = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
        except OSError as e:
            if log:
                log("[인체 3D] worker 실행 실패", repr(e))
            return None
        STATE["started"], STATE["port"] = time.time(), port
    t0 = time.time()
    while time.time() - t0 < wait:
        h = running(port)
        if h:
            return h
        if STATE["proc"].poll() is not None:
            break
        time.sleep(0.4)
    return None


def stop(port=None):
    Client(port or STATE["port"]).shutdown()
    p = STATE.get("proc")
    if p is not None:
        try:
            p.wait(5)
        except Exception:  # noqa: BLE001
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass
    STATE["proc"] = None


def installed(root, engine="sith"):
    """엔진 환경이 설치돼 있는지 — 빠른 확인. ECON 은 SiTH 기본 환경 위에 따로 깔아요."""
    if os.environ.get("HUMAN3D_WORKER_CMD"):
        return engine != "econ" or os.environ.get("HUMAN3D_FAKE_ECON_INSTALLED", "1") == "1"
    if not is_windows():
        return False
    if engine == "econ":
        args = ("test", "-x", f"{WSL_HOME}/econ-venv/bin/python", "-a", "-f", f"{WSL_HOME}/ECON/apps/infer.py")
    else:
        args = ("test", "-x", f"{WSL_HOME}/venv/bin/python", "-a", "-f", f"{WSL_HOME}/SiTH/fit.py")
    code, _ = _run(_wsl(*args), timeout=40)
    return code == 0


def _steps(root, engine):
    """(이름, 화면 말, 명령, 표준 입력으로 보낼 것 없음) — 엔진별 설치 순서."""
    scripts = engine_dir(root) / "scripts"
    custom = os.environ.get("HUMAN3D_INSTALL_CMD")
    if engine == "econ":
        names = (("install_econ.sh", "ECON 환경 설치"), ("econ_fetch.py", "ECON 모델 받기"))
    else:
        names = (("install_wsl.sh", "환경 설치"), ("install_models.sh", "모델 받기"))
    out = []
    for name, label in names:
        if custom:
            cmd = shlex.split(custom) + [str(scripts / name)]
        elif name.endswith(".py"):
            sh = (f"cd {WSL_HOME}/ECON && PYTHONPATH={shlex.quote(wsl_path(engine_dir(root)))} HF_HOME={WSL_HOME}/hf {WSL_HOME}/econ-venv/bin/python {shlex.quote(wsl_path(scripts / name))} "
                  f"--econ {WSL_HOME}/ECON --sapiens {WSL_HOME}/models/sapiens-normal --smplx-copy {WSL_HOME}/SiTH/data/body_models/smplx")
            cmd = _wsl("bash", "-lc", sh)
        else:
            cmd = _wsl("env", f"HUMAN3D_HOME={WSL_HOME}", "bash", wsl_path(scripts / name))
        out.append((name, label, cmd))
    return out


def install(root, log=None, engine="sith", creds=None):
    """환경 설치 → 모델 받기를 뒤에서 차례로 돌려요. 진행은 install_view() 로 봐요.
    creds(ECON 의 ICON 계정)는 모델 받기 프로그램의 표준 입력으로만 보내요 — 기록·파일·명령줄에 남기지 않아요."""
    I = STATE["install"]
    with _LOCK:
        if I["state"] == "running":
            return {"error": "이미 설치하고 있어요."}
        w = wsl_status()
        if not (w["wsl"] and w["distro"] and w["version2"]):
            return {"error": w["text"] + " " + w["fix"]}
        if engine == "econ":
            if not installed(root, "sith"):
                return {"error": "ECON 은 SiTH 기본 설치(CUDA 컴파일러) 위에 깔아요. 엔진을 SiTH 로 두고 [설치 시작]부터 끝내 주세요."}
            if not (creds and creds.get("user") and creds.get("pass")):
                return {"error": "ECON 모델을 받으려면 ICON 사이트(https://icon.is.tue.mpg.de) 아이디·비밀번호가 필요해요."}
        I.update(state="running", msg="설치 준비 중", step=0, total=0, log=[], need_smplx=None, t0=time.time(), engine=engine)
    steps = _steps(root, engine)
    secret = json.dumps({"user": creds.get("user"), "pass": creds.get("pass")}) + "\n" if creds else None
    creds = None

    def work():
        nonlocal secret
        try:
            for name, label, cmd in steps:
                kw = {"creationflags": 0x08000000} if is_windows() else {}
                feed = name.endswith(".py")
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE if feed else subprocess.DEVNULL,
                                     text=True, encoding="utf-8", errors="replace", **kw)
                if feed:
                    try:
                        p.stdin.write(secret or "{}\n")
                        p.stdin.close()
                    except OSError:
                        pass
                    secret = None                                # 한 번 보낸 뒤 바로 잊어요
                fail = None
                for line in p.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    I["log"].append(line)
                    del I["log"][:-200]
                    if line.startswith("@@STEP "):
                        m = re.match(r"@@STEP (\d+)/(\d+) (.*)", line)
                        if m:
                            I.update(step=int(m.group(1)), total=int(m.group(2)), msg=f"{label} {m.group(1)}/{m.group(2)} — {m.group(3)}")
                    elif line.startswith("@@FAIL "):
                        fail = line[7:]
                    elif line.startswith("@@NEED_SMPLX "):
                        I["need_smplx"] = line[13:]
                if p.wait() != 0 or fail:
                    I.update(state="error", msg=f"{label} 실패: " + (fail or (I["log"][-1] if I["log"] else f"종료 코드 {p.returncode}")))
                    return
            I.update(state="done", msg="설치가 끝났어요." + (" SMPL-X 몸 모델만 직접 넣어 주세요." if I["need_smplx"] else ""))
        except Exception as e:  # noqa: BLE001
            I.update(state="error", msg=f"설치 중 오류: {e}")
        finally:
            secret = None
            if log:
                log("[인체 3D 설치]", I.get("engine"), I["state"], I["msg"])

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


def install_view():
    I = STATE["install"]
    return {"engine": I.get("engine", "sith"), "state": I["state"], "msg": I["msg"], "step": I["step"], "total": I["total"], "need_smplx": I["need_smplx"], "log": I["log"][-15:],
            "pct": round(100 * I["step"] / I["total"]) if I["total"] else 0}


def smplx_windows_path():
    """SMPL-X 파일을 넣을 폴더를 윈도우 탐색기에서 여는 경로."""
    return rf"\\wsl$\{DISTRO}" + (WSL_HOME + "/SiTH/data/body_models/smplx").replace("/", "\\")


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
