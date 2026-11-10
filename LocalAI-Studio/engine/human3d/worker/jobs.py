"""worker 의 작업 관리: 한 번에 하나만(그래픽카드를 나눠 쓰지 않아요), 단계별 실행·기록, 중단,
메모리 부족 때 설정을 낮춰 최대 2번까지만 다시 시도, 끝나면 job.json(사용한 모델·시간·VRAM)·실패하면 diagnosis.json 을 남겨요.
중간 결과는 실패해도 지우지 않아요."""
import os
import threading
import time
import traceback
import uuid

from . import runtime as R

MAX_OOM_RETRY = 2


class Job:
    def __init__(self, job_dir, opts, provider):
        self.id = uuid.uuid4().hex[:12]
        self.dir, self.opts, self.provider = job_dir, dict(opts or {}), provider
        self.state, self.stage, self.frac, self.msg = "queued", None, 0.0, "대기 중"
        self.cancel, self.proc = False, None
        self.stages, self.notes, self.error, self.retries, self.tried = [], [], None, 0, []
        self.t0 = time.time()
        self.watch = R.VramWatch()
        self.gpu0 = R.gpu_info()
        self._lock = threading.Lock()
        self._log = open(os.path.join(job_dir, "job.log"), "a", encoding="utf-8")
        self.tail = []

    def log(self, text):
        line = time.strftime("%H:%M:%S ") + str(text)
        with self._lock:
            self._log.write(line + "\n")
            self._log.flush()
            self.tail.append(line)
            del self.tail[:-40]

    def _close_stage(self, state):
        if self.stages and self.stages[-1]["state"] == "running":
            s = self.stages[-1]
            s.update(state=state, sec=round(time.time() - s.pop("_t"), 1), vram_peak_mb=self.watch.take_peak() or None)

    def enter(self, stage):
        if stage == self.stage and self.stages and self.stages[-1]["state"] == "running":
            return
        self._close_stage("done")
        self.stage, self.frac = stage, 0.0
        self.watch.take_peak()
        self.stages.append({"id": stage, "state": "running", "_t": time.time(), "grid": self.opts.get("grid") if stage == "geometry" else None})
        self.log(f"── 단계 시작: {stage}")

    def set_progress(self, frac, msg=None):
        self.frac = max(0.0, min(1.0, frac))
        if msg:
            self.msg = msg

    def stage_done(self, res):
        if self.stages:
            if res.get("vram_mb"):
                self.stages[-1]["vram_proc_mb"] = res["vram_mb"]
            if res.get("notes"):
                self.stages[-1]["notes"] = res["notes"]
                self.notes += res["notes"]

    def view(self):
        st = [{k: v for k, v in s.items() if not k.startswith("_")} for s in self.stages]
        peaks = [s.get("vram_peak_mb") or 0 for s in st] + [self.watch.peak]
        return {"id": self.id, "state": self.state, "stage": self.stage, "stage_progress": round(self.frac, 4), "msg": self.msg,
                "elapsed": round(time.time() - self.t0, 1), "stages": st, "notes": self.notes, "error": self.error, "retries": self.retries,
                "opts": self.opts, "vram_now_mb": self.watch.now, "vram_total_mb": self.watch.total, "vram_peak_mb": max(peaks), "log_tail": self.tail[-12:]}

    def run(self):
        self.state, self.msg = "running", "시작"
        self.watch.start()
        self.log(f"작업 {self.id} 시작 · 엔진 {self.provider.name} · 설정 {self.opts} · GPU {self.gpu0}")
        try:
            for stage, fn in self.provider.stages():
                while True:
                    if self.cancel:
                        raise R.Cancelled()
                    self.enter(stage)
                    try:
                        self.stage_done(fn(self, self.log) or {})
                        break
                    except R.StageError as e:
                        if e.code != "oom" or self.retries >= MAX_OOM_RETRY:
                            raise
                        before = dict(self.opts)
                        how = self.provider.on_oom(self, self.stage)
                        self.tried.append({"stage": self.stage, "opts": before, "vram_peak_mb": self.watch.peak, "next": how})
                        if not how:
                            raise
                        self.retries += 1
                        self._close_stage("oom")
                        self.notes.append(how)
                        self.log(f"메모리 부족 → 다시 시도 {self.retries}/{MAX_OOM_RETRY}: {how}")
            self._close_stage("done")
            self.state, self.msg, self.frac = "done", "끝났어요", 1.0
        except R.Cancelled:
            self._close_stage("cancelled")
            self.state, self.error = "cancelled", {"code": "cancelled", "msg": "사용자가 중단했어요.", "stage": self.stage}
        except R.StageError as e:
            self._close_stage("error")
            self.state, self.error = "error", {"code": e.code, "msg": e.msg, "stage": e.stage or self.stage}
            self.log(f"실패({e.code}) — {e.msg}")
            self._diagnose(e.detail)
        except Exception as e:  # noqa: BLE001
            self._close_stage("error")
            self.state, self.error = "error", {"code": "stage_failed", "msg": str(e) or e.__class__.__name__, "stage": self.stage}
            self.log(traceback.format_exc())
            self._diagnose(traceback.format_exc())
        finally:
            self.watch.stop()
            self._meta()
            self.log(f"작업 끝: {self.state}")
            self._log.close()

    def _meta(self):
        v = self.view()
        R.write_json(os.path.join(self.dir, "job.json"), {
            "id": self.id, "state": self.state, "provider": self.provider.name, "provider_verified": self.provider.verified,
            "versions": self.provider.versions(), "opts": self.opts, "stages": v["stages"], "notes": self.notes, "error": self.error,
            "retries": self.retries, "vram_peak_mb": v["vram_peak_mb"], "vram_total_mb": self.watch.total, "gpu": self.gpu0,
            "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.t0)), "seconds": round(time.time() - self.t0, 1)})

    def _diagnose(self, detail):
        g = R.gpu_info()
        sug = []
        if self.error["code"] == "oom":
            sug = ["다른 프로그램(게임·브라우저·ComfyUI 작업)을 닫고 다시 해 보세요.",
                   f"형태 복원 격자를 더 낮춰 보세요(지금 {self.opts.get('grid')}).", "뒷면 후보 수를 1로 줄여 보세요."]
        R.write_json(os.path.join(self.dir, "diagnosis.json"), {
            "failed_stage": self.error["stage"], "code": self.error["code"], "message": self.error["msg"],
            "vram": {"peak_mb": self.watch.peak, "total_mb": self.watch.total, "used_before_mb": (self.gpu0 or {}).get("used_mb"),
                     "free_before_mb": (self.gpu0 or {}).get("free_mb"), "free_now_mb": (g or {}).get("free_mb")},
            "tried": self.tried, "opts": self.opts, "suggestions": sug, "last_output": (detail or "")[-4000:]})


class Store:
    def __init__(self, provider_of):
        self.provider_of, self.jobs, self.lock = provider_of, {}, threading.Lock()

    def busy(self):
        return next((j for j in self.jobs.values() if j.state in ("queued", "running")), None)

    def submit(self, job_dir, opts):
        with self.lock:
            b = self.busy()
            if b:
                return None, f"다른 인체 3D 작업({b.id})이 진행 중이에요."
            if not os.path.isdir(job_dir):
                return None, "작업 폴더가 없어요: " + str(job_dir)
            j = Job(job_dir, opts, self.provider_of((opts or {}).get("provider") or "sith"))
            self.jobs[j.id] = j
            for k in sorted(self.jobs, key=lambda k: self.jobs[k].t0)[:-20]:
                del self.jobs[k]
        threading.Thread(target=j.run, daemon=True).start()
        return j, None

    def cancel(self, jid):
        j = self.jobs.get(jid)
        if not j:
            return False
        j.cancel = True
        if j.proc is not None:
            R.kill_tree(j.proc)
        return True
