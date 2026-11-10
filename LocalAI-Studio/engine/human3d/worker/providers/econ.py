"""ECON(MPI, CVPR 2023) 어댑터 — SiTH 와 따로 도는 두 번째 엔진. 기본으로는 쓰지 않아요(사용자가 엔진을 ECON 으로 골랐을 때만).

공식 코드(https://github.com/YuliangXiu/ECON)는 '비상업 연구용' 라이선스라 LAIS 에 넣지 않고, 사용자 PC 에서 설치할 때 직접 받아요(<home>/ECON).
자기 전용 파이썬 환경(<home>/econ-venv, 파이썬 3.10 · PyTorch 2.1 · CUDA 12.1 · PyTorch3D)에서 돌아요 — SiTH 환경과 섞지 않아요.
모델(SMPL·SMPL-X·PIXIE·ECON)은 ICON 사이트 계정으로 받고(econ_fetch.py), Sapiens 는 필요한 파일만 받아요.

실행은 econ_stages.py run 하나(공식 apps/infer.py 를 그대로 돌리고 필요한 곳만 바꿔 끼움)가 단계를 차례로 알려 줘요.
★ 실제 그래픽카드·실제 ECON 모델로 돌려 확인하지 못했어요(verified = False). 공식 문서의 권장 그래픽카드 메모리는 12GB 초과예요."""
import json
import os
import subprocess
import time

from .. import runtime as R
from .base import Provider
from .sith import GENDER_KO

ECON_REPO = "https://github.com/YuliangXiu/ECON"
ECON_COMMIT = "d8f4e8b"
SAPIENS = {"0.3b": "sapiens_0.3b_normal_render_people_epoch_66_torchscript.pt2", "1b": "sapiens_1b_normal_render_people_epoch_115_torchscript.pt2",
           "2b": "sapiens_2b_normal_render_people_epoch_70_torchscript.pt2", "fg-bg-1b": "sapiens_1b_seg_foreground_epoch_8_torchscript.pt2"}
MODE_SAPIENS = {"high": "2b", "normal": "2b", "low": "1b"}          # econ_stages.MODES 와 같아요
MODE_KO = {"high": "고품질", "normal": "일반 고품질", "low": "저메모리"}


class EconProvider(Provider):
    name = "econ"
    title = "ECON (MPI · 시험 중)"
    verified = False
    modes = ("normal", "high", "low")

    def __init__(self, cfg):
        super().__init__(cfg)
        self.home = cfg["home"]
        self.econ = os.environ.get("HUMAN3D_ECON_DIR") or os.path.join(self.home, "ECON")
        self.py = os.environ.get("HUMAN3D_ECON_PY") or os.path.join(self.home, "econ-venv", "bin", "python")
        self.sapiens = os.path.join(self.home, "models", "sapiens-normal")
        self._probe = (0, None)

    def env(self):
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))        # engine/human3d
        hub = os.path.join(os.path.dirname(os.path.dirname(here)), "hub")
        e = dict(os.environ)
        e["PYTHONPATH"] = os.pathsep.join([here, hub, self.econ] + ([e["PYTHONPATH"]] if e.get("PYTHONPATH") else []))
        e["PYTHONUNBUFFERED"] = "1"
        e["HF_HOME"] = os.path.join(self.home, "hf")
        e["U2NET_HOME"] = os.path.join(self.home, "models", "u2net")      # rembg 가 받는 배경 지우기 모델 자리
        e.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:256")
        return e

    # ── 점검 ──
    def files(self):
        d = lambda *p: os.path.join(self.econ, *p)
        if os.path.isdir(self.econ):
            R.sync_smplx(d("data", "smpl_related", "models", "smplx"), ("SMPLX_FEMALE.npz", "SMPLX_MALE.npz"))      # 중립은 ECON 기본(PIXIE) 파일을 써요
        gd = {"neutral": os.path.isfile(d("data", "HPS", "pixie_data", "SMPLX_NEUTRAL_2020.npz")),
              "female": os.path.isfile(d("data", "smpl_related", "models", "smplx", "SMPLX_FEMALE.npz")),
              "male": os.path.isfile(d("data", "smpl_related", "models", "smplx", "SMPLX_MALE.npz"))}
        sap = {k: os.path.isfile(os.path.join(self.sapiens, "assets", "checkpoints", f)) for k, f in SAPIENS.items()}
        return {"code": os.path.isfile(d("apps", "infer.py")), "venv": os.path.isfile(self.py),
                "built": bool([x for x in os.listdir(d("lib", "common", "libmesh")) if x.endswith(".so")]) if os.path.isdir(d("lib", "common", "libmesh")) else False,
                "ckpt": os.path.isfile(d("data", "ckpt", "normal.ckpt")), "ifnet": os.path.isfile(d("data", "ckpt", "ifnet.ckpt")),
                "pixie": os.path.isfile(d("data", "HPS", "pixie_data", "pixie_model.tar")) or os.path.isdir(d("data", "HPS", "pixie_data")),
                "smpl_data": os.path.isdir(d("data", "smpl_related", "smpl_data")), "genders": gd, "sapiens": sap}

    def probe(self, force=False):
        if not force and self._probe[1] is not None and time.time() - self._probe[0] < 120:
            return self._probe[1]
        o = {"ok": False, "text": "ECON 전용 파이썬 환경이 없어요."}
        if os.path.isfile(self.py):
            try:
                out = subprocess.run([self.py, "-m", "worker.envcheck", "--set", "econ"], capture_output=True, text=True, timeout=300, env=self.env(), cwd=self.econ if os.path.isdir(self.econ) else None).stdout
                o = json.loads(out.split("@@ENVCHECK ", 1)[1].splitlines()[0])
            except Exception as e:  # noqa: BLE001
                o = {"ok": False, "text": f"ECON 환경을 확인하지 못했어요: {e}"}
        self._probe = (time.time(), o)
        return o

    def preflight(self):
        f, p = self.files(), self.probe()
        C = []
        add = lambda i, ok, text, fix="", **kw: C.append({"id": i, "ok": bool(ok), "text": text, "fix": "" if ok else fix, **kw})
        add("license", True, "ECON 은 막스 플랑크 연구소의 '비상업 연구용' 라이선스예요(상업·성인물 제작 금지, 배포 금지). 개인 비상업 용도로만 써 주세요.", info=True)
        C[-1]["info"] = True
        add("econ_code", f["code"] and f["venv"], "ECON 코드·전용 환경" + (" 있음" if f["code"] and f["venv"] else " 없음"), "인체 3D 화면에서 엔진을 ECON 으로 바꾸고 [ECON 설치 시작]을 눌러 주세요(SiTH 기본 설치가 먼저 돼 있어야 해요).")
        add("econ_build", f["built"], "ECON 부품 컴파일(libmesh·libvoxelize)" + (" 됨" if f["built"] else " 안 됨"), "[ECON 설치 시작]을 다시 눌러 주세요.")
        if f["venv"]:
            mods = p.get("modules") or {}
            bad = [k for k in (p.get("failed") or [])]
            add("econ_env", p.get("ok"), p.get("text") or "", p.get("fix") or "[ECON 설치 시작]을 다시 눌러 주세요.")
            if bad:
                C[-1]["detail"] = "; ".join(f"{(mods.get(k) or {}).get('name', k)}: {(mods.get(k) or {}).get('error', '')}" for k in bad)[:600]
        need = [("ckpt", "ECON 표면 방향 모델(normal.ckpt)"), ("ifnet", "ECON 메우기 모델(ifnet.ckpt)"), ("pixie", "PIXIE 몸 어림 모델"), ("smpl_data", "ECON 몸 모델 보조 자료(smpl_data)")]
        for k, ko in need:
            add("econ_" + k, f[k], ko + (" 있음" if f[k] else " 없음"), "ICON 사이트 계정으로 [ECON 모델 받기]를 해 주세요.")
        miss_sap = [k for k in ("fg-bg-1b", "2b", "1b") if not f["sapiens"][k]]
        add("econ_sapiens", not miss_sap, "Sapiens 모델(사람 분리·표면 방향)" + (" 있음" if not miss_sap else f" 없음: {', '.join(miss_sap)}"), "[ECON 모델 받기]를 다시 해 주세요(약 15GB).")
        gd = f["genders"]
        have = [GENDER_KO[g] for g in ("neutral", "female", "male") if gd[g]]
        add("econ_smplx", all(gd.values()), "ECON 몸 모델: " + ("·".join(have) + " 있음" if have else "없음") + ("" if all(gd.values()) else " (없는 성별은 고를 수 없어요)"),
            "중립은 PIXIE 자료(ECON 기본), 여성·남성은 SMPL-X v1.1 파일이에요 — [ECON 모델 받기]가 함께 받아요.")
        C.append({"id": "econ_vram", "ok": True, "info": True, "text": "ECON 공식 문서의 권장 그래픽카드 메모리는 12GB 초과예요. 12GB 에서 '일반 고품질'(Sapiens 2B)이 모자라면 '저메모리'(Sapiens 1B)를 골라 주세요. 실제로는 아직 확인하지 못했어요."})
        ready = all(c["ok"] for c in C if not c.get("info") and c["id"] != "econ_smplx") and any(gd.values())
        return {"ready": ready, "checks": C, "versions": self.versions(), "genders": gd, "modes": list(self.modes), "env": {k: p.get(k) for k in ("ok", "text", "failed", "numpy")},
                "paths": {"econ": self.econ, "sapiens": self.sapiens}}

    def versions(self):
        v = {"engine": "ECON", "repo": ECON_REPO, "commit": ECON_COMMIT, "license": "MPI non-commercial research"}
        try:
            v["commit"] = subprocess.check_output(["git", "-C", self.econ, "rev-parse", "--short", "HEAD"], text=True, timeout=5, stderr=subprocess.DEVNULL).strip() or v["commit"]
        except Exception:  # noqa: BLE001
            pass
        return v

    # ── 실행 ──
    def gender_of(self, job):
        g = job.opts.get("gender") or "auto"
        if g == "auto":
            return "neutral", "성별 '자동': ECON 기본 몸 모델(중립, SMPLX_NEUTRAL_2020)을 썼어요. 여성·남성을 직접 고르면 그 모델로 맞춰요."
        return g, None

    def st_run(self, job, log):
        f = self.files()
        if not (f["code"] and f["venv"]):
            raise R.StageError("no_model", "ECON 이 설치돼 있지 않아요.", job.stage)
        g, why = self.gender_of(job)
        if g not in R.GENDERS:
            raise R.StageError("stage_failed", f"모르는 성별 값이에요: {g}", job.stage)
        if not f["genders"][g]:
            raise R.StageError("no_smplx", f"ECON 용 {GENDER_KO[g]} 몸 모델 파일이 없어요. 다른 성별 모델로 바꿔 쓰지 않아요 — [ECON 모델 받기]를 하거나 다른 성별을 골라 주세요.", job.stage)
        mode = job.opts.get("quality") or "normal"
        job.opts["gender_used"] = g
        job.opts["sapiens"] = job.opts.get("sapiens") or MODE_SAPIENS.get(mode, "2b")
        res = R.run_stage([self.py, "-m", "worker.providers.econ_stages", "run", "--job", job.dir, "--gender", g, "--mode", mode, "--sapiens", self.sapiens,
                           "--normal_model", job.opts["sapiens"]], self.econ, self.env(), job, job.stage, log, timeout=5400)
        res.setdefault("notes", [])
        if why:
            res["notes"].append(why)
        res["notes"].append("ECON 은 뒷면 색을 만들지 않아요 — 사진에서 안 보이는 뒤·옆은 회색이에요(뒷면 텍스처는 다음 단계에서 만들 예정).")
        return res

    def stages(self):
        return [("keypoints", self.st_run)]

    def on_oom(self, job, stage):
        """일반 고품질·고품질은 조용히 낮추지 않아요(멈추고 권장 설정을 알려요). 저메모리만 Sapiens 1B → 0.3B 로 한 번 더 낮춰 봐요(알림)."""
        if (job.opts.get("quality") or "normal") != "low":
            return None
        if job.opts.get("sapiens") == "1b" and os.path.isfile(os.path.join(self.sapiens, "assets", "checkpoints", SAPIENS["0.3b"])):
            job.opts["sapiens"] = "0.3b"
            return "저메모리: 표면 방향 모델을 Sapiens 1B → 0.3B 로 낮췄어요(옷 주름 같은 세부가 덜 살아요)."
        return None

    def oom_advice(self, job):
        q = job.opts.get("quality") or "normal"
        if q != "low":
            return [f"'{MODE_KO.get(q, q)}'에서 그래픽카드 메모리가 모자랐어요. 화질을 '저메모리'(Sapiens 1B)로 바꿔 다시 해 보세요.", "다른 프로그램(게임·브라우저·ComfyUI)을 닫고 다시 해 보세요."]
        return ["가장 작은 설정(Sapiens 0.3B)에서도 메모리가 모자랐어요. 이 그래픽카드에서는 ECON 이 어려울 수 있어요 — 진단 파일을 보내 주세요.", "SiTH 엔진으로 만들어 보세요."]
