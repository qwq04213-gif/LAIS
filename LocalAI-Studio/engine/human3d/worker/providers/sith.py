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
SMPLX_NEED = ("SMPLX_MALE.npz",)                                   # fit.py 가 실제로 읽는 파일
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
for m in ("kaolin", "nvdiffrast", "diffusers", "transformers", "smplx", "trimesh", "cv2", "rtmlib", "onnxruntime", "accelerate"):
    try:
        mod = __import__(m); o[m] = getattr(mod, "__version__", "ok")
    except Exception as e:
        o[m] = None; o[m + "_error"] = repr(e)[:200]
print("@@PROBE " + json.dumps(o))
"""


class SithProvider(Provider):
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
        return {"code": os.path.isfile(os.path.join(s, "fit.py")) and os.path.isfile(os.path.join(s, "recon", "config.yaml")),
                "recon": os.path.isfile(os.path.join(s, "checkpoints", "recon_model.pth")),
                "smplerx": os.path.isfile(os.path.join(s, "checkpoints", "save_smplerx.pth")),
                "diffusion": os.path.isfile(os.path.join(self.diff, "unet", "config.json")),
                "smplx": all(os.path.isfile(os.path.join(s, "data", "body_models", "smplx", n)) for n in SMPLX_NEED)}

    def preflight(self):
        f, p = self.files(), self.probe()
        smplx_dir = os.path.join(self.sith, "data", "body_models", "smplx")
        C = []
        add = lambda i, ok, text, fix="": C.append({"id": i, "ok": bool(ok), "text": text, "fix": "" if ok else fix})
        add("code", f["code"], "SiTH 코드" + (" 있음" if f["code"] else " 없음"), "설치를 다시 실행해 주세요.")
        add("torch", p.get("torch"), f"PyTorch {p.get('torch')}" if p.get("torch") else "PyTorch 를 불러오지 못해요", str(p.get("torch_error") or "설치를 다시 실행해 주세요."))
        add("cuda", p.get("cuda"), f"그래픽카드 사용 가능 — {p.get('gpu')} · {p.get('vram_mb')}MB · CUDA {p.get('cuda_version')}" if p.get("cuda") else "worker 가 그래픽카드(CUDA)를 쓰지 못해요",
            "윈도우의 NVIDIA 드라이버를 최신으로 올리고, WSL 을 다시 시작해 주세요(wsl --shutdown).")
        for m, ko in (("kaolin", "kaolin"), ("nvdiffrast", "nvdiffrast"), ("diffusers", "diffusers"), ("smplx", "smplx"), ("rtmlib", "자세 검출기(rtmlib)")):
            add("mod_" + m, p.get(m), f"{ko} {p.get(m) or '없음'}", str(p.get(m + "_error") or "설치를 다시 실행해 주세요."))
        add("recon", f["recon"], "형태 복원 모델(recon_model.pth)" + (" 있음" if f["recon"] else " 없음"), "설치(모델 받기)를 다시 실행해 주세요.")
        add("smplerx", f["smplerx"], "몸 어림 모델(save_smplerx.pth)" + (" 있음" if f["smplerx"] else " 없음"), "설치(모델 받기)를 다시 실행해 주세요.")
        add("diffusion", f["diffusion"], "뒷면 그리기 모델(SiTH_diffusion)" + (" 있음" if f["diffusion"] else " 없음"), "설치(모델 받기)를 다시 실행해 주세요.")
        add("smplx", f["smplx"], "SMPL-X 몸 모델" + (" 있음" if f["smplx"] else " 없음 — 직접 가입해서 받아야 하는 파일이에요"),
            f"https://smpl-x.is.tue.mpg.de 에 가입·약관 동의 후 'SMPL-X v1.1 (NPZ+PKL)' 을 받아, 압축을 풀어 나온 models/smplx 안의 파일을 {smplx_dir} 에 넣어 주세요.")
        vram = p.get("vram_mb") or 0
        if p.get("cuda"):
            add("vram", vram >= 9500, f"그래픽카드 메모리 {vram}MB" + ("" if vram >= 9500 else " — 10GB 보다 작아요"), "10GB 이상을 권장해요. 격자를 낮춰도 실패할 수 있어요.")
            C.append({"id": "vram_note", "ok": True, "info": True,
                      "text": f"지금 비어 있는 메모리 {p.get('free_mb')}MB · FP16 {'가능' if p.get('fp16') else '불가'} · BF16 {'가능' if p.get('bf16') else '불가'}. SiTH 의 공식 시험 환경은 24GB 이고, 10~12GB 에서는 아직 확인하지 못했어요."})
        ready = all(c["ok"] for c in C if c["id"] != "vram")
        return {"ready": ready, "checks": C, "versions": self.versions(), "paths": {"sith": self.sith, "smplx": smplx_dir, "diffusion": self.diff},
                "smplx_files": {"need": list(SMPLX_NEED), "all": list(SMPLX_ALL)}}

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
                raise R.StageError("no_smplx" if k == "smplx" else "no_model", {"code": "SiTH 코드가 없어요.", "recon": "형태 복원 모델이 없어요.", "smplerx": "몸 어림 모델이 없어요.",
                                                                              "diffusion": "뒷면 그리기 모델이 없어요.", "smplx": "SMPL-X 몸 모델 파일이 없어요."}[k], job.stage)

    def _mine(self, job, log, cmd, *args, timeout=3600):
        return R.run_stage([self.py, "-m", "worker.providers.sith_stages", cmd, "--job", job.dir, *[str(a) for a in args]], self.sith, self.env(), job, job.stage, log, timeout=timeout)

    def st_keypoints(self, job, log):
        self._need(job, "code")
        return self._mine(job, log, "keypoints", timeout=900)

    def st_smplx(self, job, log):
        """공식 fit.py 그대로: SMPLer-X 로 어림 → 관절점·실루엣에 맞춰 최적화(방향·체형·크기·위치). 결과: smplx/000_smplx.obj, smplx/debug/000.json"""
        self._need(job, "code", "smplerx", "smplx")
        on = lambda line: job.enter("smplx_fit") if "Body Fitting" in line else None
        return R.run_stage([self.py, "fit.py", "-i", os.path.join(job.dir, "images"), "-o", os.path.join(job.dir, "smplx"), "--size", "1024", "--opt_orient", "--opt_betas", "--debug"],
                           self.sith, self.env(), job, job.stage, log, on_line=on, timeout=1800)

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
        return [("keypoints", self.st_keypoints), ("smplx_init", self.st_smplx), ("back", self.st_back), ("geometry", self.st_recon)]

    def on_oom(self, job, stage):
        """메모리가 모자랐을 때 다음에 낮출 설정. 낮출 게 없으면 None(= 더 시도하지 않음)."""
        o = job.opts
        if stage in ("geometry", "texture"):
            if o.get("chunk", 50000) > 20000 and not o.get("_chunk_cut"):
                o["chunk"], o["_chunk_cut"] = 20000, True
                return "형태 복원에서 한 번에 보내는 점 수를 2만으로 줄였어요(세밀함은 그대로)."
            g = o.get("grid", 512)
            lower = [x for x in GRID_STEPS if x < g]
            if lower:
                o["grid"] = lower[0]
                return f"형태 복원 격자를 {g} → {lower[0]} 로 낮췄어요(덜 세밀해요)."
            return None
        if stage == "back":
            if not o.get("offload"):
                o["offload"] = True
                return "뒷면 그리기에서 모델을 하나씩만 그래픽카드에 올리게 했어요(느려지지만 메모리를 덜 써요)."
            if o.get("back_candidates", 4) > 1:
                o["back_candidates"] = 1
                return "뒷면 후보를 1장으로 줄였어요."
        return None
