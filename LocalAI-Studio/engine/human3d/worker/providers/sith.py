"""SiTH(ETH Zürich, CVPR 2024, MIT 라이선스) 어댑터.
공식 코드(https://github.com/SiTH-Diffusion/SiTH)를 <home>/SiTH 에 받아 두고, 단계마다 별도 프로세스로 돌려요.
  자세·관절점(RTMPose/DWPose → OpenPose 형식) → SMPLer-X + SMPL-X 맞추기(공식 fit.py 그대로) → 뒷면 그리기 → 형태·색 복원
뒷면 그리기·형태 복원은 공식 스크립트 대신 sith_stages.py 의 저메모리 판을 써요(같은 모델·같은 계산, 메모리만 아껴 씀).

★ 실제 그래픽카드·실제 모델로 끝까지 돌려 확인하지 못했어요(verified = False). 공식 시험 환경은 RTX 3090(24GB)이에요."""
import json
import os
import subprocess
import sys
import time

from .. import runtime as R
from .base import Provider

GRID_STEPS = (512, 384, 256)
SITH_REPO = "https://github.com/SiTH-Diffusion/SiTH"
SITH_COMMIT = "6401549"          # 설치 스크립트가 받는 판(코드를 읽고 맞춘 판)
SMPLX_NEED = ("SMPLX_NEUTRAL.npz", "SMPLX_FEMALE.npz", "SMPLX_MALE.npz")      # 고른 성별의 파일을 읽어요(공식 fit.py 는 남성 고정 — sith_stages.cmd_fit 이 고른 성별로 바꿔요)
GENDER_KO = {"male": "남성", "female": "여성", "neutral": "중립"}
SMPLX_ALL = ("SMPLX_NEUTRAL.npz", "SMPLX_MALE.npz", "SMPLX_FEMALE.npz", "SMPLX_NEUTRAL.pkl", "SMPLX_MALE.pkl", "SMPLX_FEMALE.pkl")
_PROBE = r"""
import json, sys
o = {"python": sys.version.split()[0]}
try:
    import torch
    o["torch"] = torch.__version__; o["cuda"] = bool(torch.cuda.is_available()); o["cuda_version"] = torch.version.cuda
    if o["cuda"]:
        o["gpu"] = torch.cuda.get_device_name(0); o["vram_mb"] = int(torch.cuda.get_device_properties(0).total_memory / 2**20)
        f, t = torch.cuda.mem_get_info(); o["free_mb"] = int(f / 2**20)
        try:
            x = torch.ones(8, device="cuda", dtype=torch.float16); o["fp16"] = bool((x * 2).sum().item() == 16)
        except Exception as e: o["fp16"] = False
        try:
            o["bf16"] = bool(torch.cuda.is_bf16_supported())
        except Exception: o["bf16"] = False
except Exception as e:
    o["torch_error"] = repr(e)
try:
    from worker import envcheck          # 부품을 전부 실제로 불러와 봐요(오류 글·어느 꾸러미에서 났는지까지)
    ec = envcheck.check()
    o["env"] = {k: v for k, v in ec.items() if k != "modules"}
    for k, m in ec["modules"].items():
        o[k] = m.get("version") if m["ok"] else None
        if not m["ok"]:
            o[k + "_error"] = m["error"]; o[k + "_culprit"] = m.get("culprit"); o[k + "_abi"] = m.get("abi"); o[k + "_trace"] = m.get("trace", "")[-700:]
except Exception as e:
    o["env"] = {"ok": False, "text": "부품 검사를 돌리지 못했어요: " + repr(e)[:200], "failed": [], "abi": False}
try:
    from worker import nvcheck          # nvdiffrast: 불러오기만이 아니라 CUDA 확장·컨텍스트·작은 래스터화까지 실제로 돌려 봐요
    o["nv"] = nvcheck.check()
except Exception as e:
    o["nv"] = {"ok": False, "kind": "not_installed", "text": "nvdiffrast 검사를 돌리지 못했어요.", "fix": "", "detail": repr(e)[:300]}
print("@@PROBE " + json.dumps(o))
"""


class SithProvider(Provider):
    modes = ("normal", "low")          # SiTH 가 실제로 지원하는 화질 단계(고품질은 따로 없어요 — 기본이 공식 최고 설정이에요)
    name = "sith"
    title = "SiTH (ETH Zürich)"
    verified = False

    def __init__(self, cfg):
        super().__init__(cfg)
        self.home = cfg["home"]
        self.sith = os.environ.get("HUMAN3D_SITH_DIR") or os.path.join(self.home, "SiTH")
        self.py = cfg.get("python") or sys.executable
        self.diff = os.environ.get("HUMAN3D_SITH_DIFFUSION") or os.path.join(self.home, "models", "SiTH_diffusion")
        self._probe = (0, None)

    # ── 점검 ──
    def env(self):
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))        # engine/human3d
        hub = os.path.join(os.path.dirname(os.path.dirname(here)), "hub")                            # LocalAI-Studio/hub (human3d 꾸러미)
        e = dict(os.environ)
        e["PYTHONPATH"] = os.pathsep.join([here, hub, self.sith] + ([e["PYTHONPATH"]] if e.get("PYTHONPATH") else []))
        e["PYTHONUNBUFFERED"] = "1"
        e["HF_HOME"] = os.path.join(self.home, "hf")
        e.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:256")
        return e

    def probe(self, force=False):
        if not force and self._probe[1] is not None and time.time() - self._probe[0] < 120:
            return self._probe[1]
        try:
            out = subprocess.run([self.py, "-c", _PROBE], capture_output=True, text=True, timeout=180, env=self.env()).stdout
            o = json.loads(out.split("@@PROBE ", 1)[1].splitlines()[0])
        except Exception as e:  # noqa: BLE001
            o = {"torch_error": f"파이썬 환경을 확인하지 못했어요: {e}"}
        self._probe = (time.time(), o)
        return o

    def files(self):
        s = self.sith
        R.sync_smplx(os.path.join(s, "data", "body_models", "smplx"))          # LAIS 폴더 안에 넣어 둔 파일이 있으면 가져와요
        gd = {g: os.path.isfile(os.path.join(s, "data", "body_models", "smplx", f"SMPLX_{g.upper()}.npz")) for g in R.GENDERS}
        return {"code": os.path.isfile(os.path.join(s, "fit.py")) and os.path.isfile(os.path.join(s, "recon", "config.yaml")),
                "recon": os.path.isfile(os.path.join(s, "checkpoints", "recon_model.pth")),
                "smplerx": os.path.isfile(os.path.join(s, "checkpoints", "save_smplerx.pth")),
                "diffusion": os.path.isfile(os.path.join(self.diff, "unet", "config.json")),
                "genders": gd, "smplx": any(gd.values())}

    def preflight(self):
        f, p = self.files(), self.probe()
        smplx_dir = os.path.join(self.sith, "data", "body_models", "smplx")
        C = []
        add = lambda i, ok, text, fix="": C.append({"id": i, "ok": bool(ok), "text": text, "fix": "" if ok else fix})
        add("code", f["code"], "SiTH 코드" + (" 있음" if f["code"] else " 없음"), "설치를 다시 실행해 주세요.")
        add("torch", p.get("torch"), f"PyTorch {p.get('torch')}" if p.get("torch") else "PyTorch 를 불러오지 못해요", str(p.get("torch_error") or "설치를 다시 실행해 주세요."))
        add("cuda", p.get("cuda"), f"그래픽카드 사용 가능 — {p.get('gpu')} · {p.get('vram_mb')}MB · CUDA {p.get('cuda_version')}" if p.get("cuda") else "worker 가 그래픽카드(CUDA)를 쓰지 못해요",
            "윈도우의 NVIDIA 드라이버를 최신으로 올리고, WSL 을 다시 시작해 주세요(wsl --shutdown).")
        for m, ko in (("kaolin", "kaolin"), ("diffusers", "diffusers"), ("smplx", "smplx"), ("rtmlib", "자세 검출기(rtmlib)")):
            if p.get(m):
                add("mod_" + m, True, f"{ko} {p.get(m)}")
            else:                                     # 깔려 있어도 불러오지 못하면 '안 됨' — 까닭(판 안 맞음인지)과 어느 꾸러미에서 났는지를 같이 보여요
                abi, cul = p.get(m + "_abi"), p.get(m + "_culprit")
                add("mod_" + m, False, f"{ko} 을(를) 불러오지 못해요" + (" — 부품끼리 판이 안 맞아요(numpy)" if abi else "") + (f" · 문제가 난 곳: {cul}" if cul else ""),
                    "[설치 시작]을 다시 눌러 주세요(부품 판을 고정한 조합으로 다시 맞춰요). 그래도 같으면 아래 오류 글을 캡처해서 보내 주세요.")
                C[-1].update(detail=str(p.get(m + "_error") or "")[:300], trace=str(p.get(m + "_trace") or "")[-700:], abi=bool(abi), culprit=cul)
        env = p.get("env") or {}
        others = [k for k in (env.get("failed") or []) if k not in ("kaolin", "diffusers", "smplx", "rtmlib", "torch")]
        if others:
            add("mod_others", False, "불러오지 못하는 부품이 더 있어요: " + ", ".join(others), "[설치 시작]을 다시 눌러 주세요.")
            C[-1].update(detail="; ".join(f"{k}: {p.get(k + '_error')}" for k in others)[:400])
        nv = p.get("nv") or {"ok": False, "kind": "not_installed", "text": "nvdiffrast 를 확인하지 못했어요.", "fix": "설치를 다시 실행해 주세요."}
        nv_kind = {"not_installed": "설치 문제", "build": "설치 문제", "no_torch": "설치 문제", "no_cuda": "CUDA 실행 문제", "runtime": "CUDA 실행 문제", "wrong": "CUDA 실행 문제"}.get(nv.get("kind"), "")
        add("nvdiffrast", nv.get("ok"), nv.get("text") if nv.get("ok") else f"[{nv_kind}] {nv.get('text')}", nv.get("fix") or "설치를 다시 실행해 주세요.")
        C[-1].update(kind=nv.get("kind"), detail="" if nv.get("ok") else (nv.get("detail") or "")[-300:])
        add("recon", f["recon"], "형태 복원 모델(recon_model.pth)" + (" 있음" if f["recon"] else " 없음"), "설치(모델 받기)를 다시 실행해 주세요.")
        add("smplerx", f["smplerx"], "몸 어림 모델(save_smplerx.pth)" + (" 있음" if f["smplerx"] else " 없음"), "설치(모델 받기)를 다시 실행해 주세요.")
        add("diffusion", f["diffusion"], "뒷면 그리기 모델(SiTH_diffusion)" + (" 있음" if f["diffusion"] else " 없음"), "설치(모델 받기)를 다시 실행해 주세요.")
        gd = f["genders"]
        have = [GENDER_KO[g] for g in R.GENDERS if gd[g]]
        miss = [f"SMPLX_{g.upper()}.npz" for g in R.GENDERS if not gd[g]]
        add("smplx", all(gd.values()), "SMPL-X 몸 모델: " + ("·".join(have) + " 있음" if have else "없음 — 직접 가입해서 받아야 하는 파일이에요") + (f" (없는 파일: {', '.join(miss)})" if have and miss else ""),
            f"https://smpl-x.is.tue.mpg.de 에 가입·약관 동의 후 'SMPL-X v1.1 (NPZ+PKL)' 을 받아, 압축을 풀어 나온 models/smplx 안의 파일(남성·여성·중립 모두)을 {smplx_dir} 에 넣어 주세요. "
            "없는 성별은 고를 수 없어요(다른 성별 모델로 바꿔 쓰지 않아요).")
        vram = p.get("vram_mb") or 0
        if p.get("cuda"):
            free = p.get("free_mb") or 0
            add("vram", vram >= 9500, f"그래픽카드 전체 메모리 {vram / 1024:.1f}GB" + ("" if vram >= 9500 else " — 10GB 보다 작아요"), "10GB 이상을 권장해요. 격자를 낮춰도 실패할 수 있어요.")
            add("vram_free", free >= 8000, f"지금 실제로 쓸 수 있는 메모리 {free / 1024:.1f}GB (다른 프로그램이 {max(0, vram - free) / 1024:.1f}GB 사용 중)",
                "쓸 수 있는 메모리가 8GB 보다 적어요. 게임·브라우저·다른 AI 프로그램을 닫으면 늘어나요(인체 3D 를 시작하면 LAIS 의 대화·이미지 모델은 자동으로 내려요).")
            C.append({"id": "vram_note", "ok": True, "info": True,
                      "text": f"FP16 {'가능' if p.get('fp16') else '불가'} · BF16 {'가능' if p.get('bf16') else '불가'}. SiTH 의 공식 시험 환경은 24GB 이고, 10~12GB 에서 끝까지 돌아가는지는 아직 확인하지 못했어요(보장하지 않아요)."})
        ready = all(c["ok"] for c in C if c["id"] not in ("vram", "vram_free", "smplx")) and f["smplx"]      # 몸 모델은 하나라도 있으면 그 성별로는 돌릴 수 있어요
        return {"ready": ready, "checks": C, "versions": self.versions(), "vram": {"total_mb": vram or None, "free_mb": p.get("free_mb")}, "nvdiffrast": {k: nv.get(k) for k in ("ok", "kind", "pixels", "version")}, "paths": {"sith": self.sith, "smplx": smplx_dir, "diffusion": self.diff},
                "smplx_files": {"need": list(SMPLX_NEED), "all": list(SMPLX_ALL)}, "genders": gd, "env": {k: env.get(k) for k in ("ok", "text", "abi", "culprits", "numpy", "failed")}}

    def versions(self):
        p = self._probe[1] or {}
        v = {"engine": "SiTH", "repo": SITH_REPO, "commit": SITH_COMMIT, "diffusion": os.path.basename(self.diff)}
        v.update({k: p.get(k) for k in ("python", "torch", "cuda_version", "gpu", "kaolin", "diffusers", "transformers", "rtmlib") if p.get(k)})
        try:
            v["commit"] = subprocess.check_output(["git", "-C", self.sith, "rev-parse", "--short", "HEAD"], text=True, timeout=5, stderr=subprocess.DEVNULL).strip() or v["commit"]
        except Exception:  # noqa: BLE001
            pass
        return v

    # ── 단계 ──
    def _need(self, job, *keys):
        f = self.files()
        for k in keys:
            if not f[k]:
                raise R.StageError("no_model", {"code": "SiTH 코드가 없어요.", "recon": "형태 복원 모델이 없어요.", "smplerx": "몸 어림 모델이 없어요.", "diffusion": "뒷면 그리기 모델이 없어요."}[k], job.stage)

    def _mine(self, job, log, cmd, *args, timeout=3600, on_line=None):
        return R.run_stage([self.py, "-m", "worker.providers.sith_stages", cmd, "--job", job.dir, *[str(a) for a in args]], self.sith, self.env(), job, job.stage, log, on_line=on_line, timeout=timeout)

    def st_keypoints_mode(self, job, log):
        self.apply_mode(job)
        return self.st_keypoints(job, log)

    def st_keypoints(self, job, log):
        self._need(job, "code")
        return self._mine(job, log, "keypoints", timeout=900)

    def gender_of(self, job):
        """이 작업에 쓸 SMPL-X 성별. '자동'은 아직 성별 추정기가 없어서 중립 모델을 써요(남성으로 정하지 않아요)."""
        g = job.opts.get("gender") or "auto"
        if g == "auto":
            return "neutral", "성별 '자동': 사진에서 성별을 추정하는 기능은 아직 없어서 중립 몸 모델을 썼어요. 여성·남성을 직접 고르면 그 모델로 맞춰요."
        return g, None

    def st_smplx(self, job, log):
        """SMPLer-X 로 어림 → 관절점·실루엣에 맞춰 최적화(방향·체형·크기·위치). 공식 fit.py 를 그대로 쓰되 몸 모델의 성별만 고른 것으로(공식은 남성 고정).
        결과: smplx/000_smplx.obj, smplx/debug/000.json, smplx/gender.json. 고른 성별의 파일이 없으면 다른 성별로 바꾸지 않고 멈춰요."""
        self._need(job, "code", "smplerx")
        g, why = self.gender_of(job)
        if g not in R.GENDERS:
            raise R.StageError("stage_failed", f"모르는 성별 값이에요: {g}", job.stage)
        if not self.files()["genders"][g]:
            raise R.StageError("no_smplx", f"SMPL-X {GENDER_KO[g]} 몸 모델 파일(SMPLX_{g.upper()}.npz)이 없어요. 다른 성별 모델로 바꿔 쓰지 않아요 — 파일을 넣거나 다른 성별을 골라 주세요.", job.stage)
        job.opts["gender_used"] = g
        on = lambda line: job.enter("smplx_fit") if "Body Fitting" in line else None
        res = self._mine(job, log, "fit", "--gender", g, timeout=1800, on_line=on)
        res.setdefault("notes", [])
        if why:
            res["notes"].append(why)
        return res

    def st_back(self, job, log):
        self._need(job, "code", "diffusion")
        o = job.opts
        return self._mine(job, log, "back", "--model", self.diff, "--n", o.get("back_candidates", 4), "--steps", o.get("back_steps", 50), "--res", o.get("back_res", 512),
                          "--seed", o.get("seed", 0), "--fp16", int(bool(o.get("fp16", True))), "--offload", int(bool(o.get("offload", False))))

    def st_recon(self, job, log):
        self._need(job, "code", "recon")
        o = job.opts
        return self._mine(job, log, "recon", "--grid", o.get("grid", 512), "--chunk", o.get("chunk", 50000), "--subdivide", int(bool(o.get("subdivide", True))))

    def stages(self):
        return [("keypoints", self.st_keypoints_mode), ("smplx_init", self.st_smplx), ("back", self.st_back), ("geometry", self.st_recon)]

    # 메모리가 모자랄 때(화질 단계에 따라)
    #   일반 고품질(기본): 한 번에 보내는 점 수만 5만 → 2만(세밀함 그대로). 그래도 모자라면 멈추고 '저메모리'를 권해요 — 조용히 품질을 낮추지 않아요.
    #   저메모리: 처음부터 모델을 하나씩만 올리고(offload)·뒷면 후보 1장·점 수 2만으로 시작하고, 모자라면 격자 384 → 256 으로 낮춰요(알림).
    OOM_CHUNK = 20000

    def apply_mode(self, job):
        """작업을 시작할 때 화질 단계에 맞춰 설정을 정해요."""
        o = job.opts
        if (o.get("quality") or "normal") == "low" and not o.get("_mode_applied"):
            o.update(offload=True, back_candidates=1, chunk=min(int(o.get("chunk", 50000)), self.OOM_CHUNK), _mode_applied=True)

    def on_oom(self, job, stage):
        """메모리가 모자랐을 때 다음에 낮출 설정. 낮출 게 없으면 None(= 더 시도하지 않음)."""
        o = job.opts
        low = (o.get("quality") or "normal") == "low"
        if stage in ("geometry", "texture"):
            if o.get("chunk", 50000) > self.OOM_CHUNK:
                o["chunk"] = self.OOM_CHUNK
                return "형태 복원에서 한 번에 보내는 점 수를 2만으로 줄였어요(세밀함은 그대로)."
            if not low:
                return None
            g = o.get("grid", 512)
            lower = [x for x in GRID_STEPS if x < g]
            if lower:
                o["grid"] = lower[0]
                return f"저메모리: 형태 복원 격자를 {g} → {lower[0]} 로 낮췄어요(형상이 덜 세밀해져요)."
            return None
        if stage == "back":
            if not o.get("offload"):
                o["offload"] = True
                return "뒷면 그리기에서 모델을 하나씩만 그래픽카드에 올리게 했어요(느려지지만 메모리를 덜 써요, 결과는 같아요)."
            if low and o.get("back_candidates", 4) > 1:
                o["back_candidates"] = 1
                return "저메모리: 뒷면 후보를 1장으로 줄였어요."
        return None

    def oom_advice(self, job):
        if (job.opts.get("quality") or "normal") != "low":
            return ["'일반 고품질'에서 그래픽카드 메모리가 모자랐어요. 화질을 '저메모리'로 바꿔 다시 해 보세요(격자를 384·256 으로 낮춰 가며 해요).",
                    "다른 프로그램(게임·브라우저·ComfyUI)을 닫고 다시 해 보세요."]
        return ["가장 낮은 설정(격자 256·점 수 2만·뒷면 후보 1장)에서도 메모리가 모자랐어요. 이 그래픽카드로는 지금 방식으로 어려워요 — 진단 파일을 보내 주세요."]
        if stage == "back":
            if not o.get("offload"):
                o["offload"] = True
                return "뒷면 그리기에서 모델을 하나씩만 그래픽카드에 올리게 했어요(느려지지만 메모리를 덜 써요)."
            if o.get("back_candidates", 4) > 1:
                o["back_candidates"] = 1
                return "뒷면 후보를 1장으로 줄였어요."
        return None
