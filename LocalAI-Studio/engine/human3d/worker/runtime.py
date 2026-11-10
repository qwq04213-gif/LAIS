"""worker 공용 도구: 단계 실행(별도 프로세스 — 끝나면 그래픽카드 메모리가 통째로 풀려요), VRAM 재기, 메모리 부족 판별.
단계 스크립트(providers/sith_stages.py)와 약속한 출력 줄:
  @@PROGRESS <0~1> <글>     진행
  @@STAGE <단계 이름>        같은 프로세스 안에서 단계가 넘어감
  @@VRAM <MB>               이 프로세스가 쓴 최대 VRAM(torch 가 잰 값)
  @@NOTE <글>               사용자에게 알릴 것(해상도를 낮췄다 등)
  @@ERROR <코드> <글>        실패 까닭"""
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

API_VERSION = 1
HOST = "127.0.0.1"
PORT = 17861
WORKER_STAGES = ("keypoints", "smplx_init", "smplx_fit", "back", "geometry", "texture")
GENDERS = ("male", "female", "neutral")          # SMPL-X 몸 모델 종류(파일: SMPLX_MALE/FEMALE/NEUTRAL.npz)
OOM_RX = re.compile(r"CUDA out of memory|OutOfMemoryError|CUDA error: out of memory|cudaErrorMemoryAllocation|std::bad_alloc|Unable to allocate|DefaultCPUAllocator", re.I)


class StageError(Exception):
    def __init__(self, code, msg, stage=None, detail=""):
        super().__init__(msg)
        self.code, self.msg, self.stage, self.detail = code, msg, stage, detail


class Cancelled(Exception):
    pass


def is_oom(text):
    return bool(OOM_RX.search(text or ""))


def gpu_info():
    """nvidia-smi 로 본 그래픽카드 상태(없으면 None). WSL 안에서도 돼요."""
    try:
        o = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,driver_version", "--format=csv,noheader,nounits"],
                                    text=True, timeout=6, stderr=subprocess.DEVNULL).strip().splitlines()[0]
        a = [x.strip() for x in o.split(",")]
        return {"name": a[0], "total_mb": int(float(a[1])), "used_mb": int(float(a[2])), "free_mb": int(float(a[3])), "driver": a[4] if len(a) > 4 else ""}
    except Exception:  # noqa: BLE001
        return None


class VramWatch:
    """작업하는 동안 1초마다 그래픽카드 메모리 사용량을 재서 최댓값을 남겨요(다른 프로그램 몫 포함)."""

    def __init__(self, every=1.0):
        self.every, self.peak, self.apeak, self.now, self.total, self.base = every, 0, 0, 0, 0, None
        self._stop = threading.Event()
        self._t = None

    def start(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def _run(self):
        while not self._stop.is_set():
            g = gpu_info()
            if g:
                self.now, self.total = g["used_mb"], g["total_mb"]
                self.base = g["used_mb"] if self.base is None else self.base
                self.peak = max(self.peak, g["used_mb"])
                self.apeak = max(self.apeak, g["used_mb"])
            self._stop.wait(self.every)

    def stop(self):
        self._stop.set()

    def take_peak(self):
        """지금까지의 최댓값을 돌려주고, 여기서부터 다시 재요."""
        p, self.peak = self.peak, self.now
        return p

    def attempt_start(self):
        """시도 하나(단계 한 번 실행)의 최댓값을 따로 재기 시작해요 — 단계 안에서 세부 단계가 바뀌어도 이어서 재요."""
        g = gpu_info()                                  # 앞 시도의 값이 넘어오지 않게 지금 값을 바로 다시 읽어요
        if g:
            self.now = g["used_mb"]
        self.apeak = self.now

    def attempt_peak(self):
        return max(self.apeak, self.now)


def kill_tree(proc):
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


TQDM_RX = re.compile(r"(\d{1,3})%\|")


def run_stage(cmd, cwd, env, job, stage, log, on_line=None, timeout=3600):
    """단계 하나를 별도 프로세스로 돌려요. job: jobs.Job(진행·취소 상태), log: 글 한 줄을 받는 함수.
    돌려주는 값: {"vram_mb": 프로세스가 쓴 최대(없으면 None), "notes": [...]} — 실패하면 StageError."""
    log(f"[{stage}] 실행: {' '.join(str(c) for c in cmd)}")
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen([str(c) for c in cmd], cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, **kw)
    job.proc = proc
    res = {"vram_mb": None, "notes": []}
    err = {"code": None, "msg": ""}
    tail = []
    t0 = time.time()

    def pump():
        buf = ""
        while True:
            ch = proc.stdout.read(1)
            if not ch:
                break
            if ch not in "\r\n":
                buf += ch
                continue
            line, buf = buf.strip(), ""
            if not line:
                continue
            if line.startswith("@@PROGRESS "):
                p = line.split(" ", 2)
                try:
                    job.set_progress(float(p[1]), p[2] if len(p) > 2 else None)
                except ValueError:
                    pass
            elif line.startswith("@@STAGE "):
                job.enter(line.split(" ", 1)[1].strip())
            elif line.startswith("@@VRAM "):
                try:
                    res["vram_mb"] = max(res["vram_mb"] or 0, int(float(line.split()[1])))
                except ValueError:
                    pass
            elif line.startswith("@@NOTE "):
                res["notes"].append(line[7:])
                log(f"[{job.stage}] 알림: {line[7:]}")
            elif line.startswith("@@ERROR "):
                p = line.split(" ", 2)
                err["code"], err["msg"] = p[1], p[2] if len(p) > 2 else ""
            else:
                m = TQDM_RX.search(line)
                if m:                                        # 원본 스크립트의 진행 막대(tqdm)
                    job.set_progress(min(100, int(m.group(1))) / 100.0)
                else:
                    tail.append(line)
                    del tail[:-60]
                    log(f"[{job.stage}] {line}")
                if on_line:
                    on_line(line)

    th = threading.Thread(target=pump, daemon=True)
    th.start()
    while proc.poll() is None:
        if job.cancel:
            kill_tree(proc)
            th.join(3)
            raise Cancelled()
        if time.time() - t0 > timeout:
            kill_tree(proc)
            raise StageError("stage_failed", f"{int(timeout / 60)}분이 지나도 끝나지 않아 멈췄어요.", stage)
        time.sleep(0.2)
    th.join(5)
    job.proc = None
    if job.cancel:
        raise Cancelled()
    if proc.returncode != 0:
        text = "\n".join(tail)
        if err["code"]:
            raise StageError(err["code"], err["msg"], job.stage, text)
        if is_oom(text) or proc.returncode in (-9, 137):
            raise StageError("oom", "그래픽카드(또는 시스템) 메모리가 모자라요.", job.stage, text)
        raise StageError("stage_failed", (tail[-1] if tail else f"종료 코드 {proc.returncode}")[:300], job.stage, text)
    return res


# ── 단계 스크립트 안에서 쓰는 도구 ─────────────────────────────────────────────
def emit(kind, *a):
    print("@@" + kind + " " + " ".join(str(x) for x in a), flush=True)


def progress(frac, msg=""):
    emit("PROGRESS", f"{max(0.0, min(1.0, frac)):.4f}", msg)


def fail(code, msg):
    emit("ERROR", code, msg)
    sys.exit(3)


def cuda_cleanup():
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:  # noqa: BLE001
        pass


def report_vram():
    try:
        import torch
        if torch.cuda.is_available():
            emit("VRAM", int(max(torch.cuda.max_memory_allocated(), torch.cuda.max_memory_reserved()) / 2 ** 20))
    except Exception:  # noqa: BLE001
        pass


def grid_chunks(res, chunk):
    """res³ 격자 좌표를 chunk 개씩 (시작 번호, numpy (n,3) float32) 로 내줘요 — 전체 격자를 한꺼번에 만들지 않아요.
    순서는 SiTH 와 같아요(x 가 가장 느리게, z 가 가장 빨리 변함: torch.meshgrid(indexing='ij') 를 편 순서)."""
    import numpy as np
    lin = np.linspace(-1.0, 1.0, res, dtype=np.float32)
    total = res ** 3
    for s in range(0, total, chunk):
        idx = np.arange(s, min(total, s + chunk), dtype=np.int64)
        yield s, np.stack([lin[idx // (res * res)], lin[(idx // res) % res], lin[idx % res]], 1)


def code_hash(*dirs):
    """worker 가 읽는 코드(.py)의 내용 지문. LAIS 를 업데이트했는데 예전 worker 가 그대로 떠 있는지 본체가 이걸로 알아채요."""
    import hashlib
    h = hashlib.sha1()
    for d in dirs:
        for root, sub, names in sorted(os.walk(d)):
            sub[:] = sorted(x for x in sub if x != "__pycache__")
            for n in sorted(names):
                if n.endswith(".py"):
                    p = os.path.join(root, n)
                    h.update(os.path.relpath(p, d).replace(os.sep, "/").encode())
                    with open(p, "rb") as f:
                        h.update(f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
