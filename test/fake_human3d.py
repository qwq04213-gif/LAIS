"""시험용 가짜 인체 3D 엔진: 그래픽카드·모델 없이 worker 의 흐름(단계·진행·메모리 부족 재시도·중단·결과 파일)만 확인해요.
입력 그림(images/000.png)의 윤곽을 앞뒤로 부풀린 닫힌 메시를 만들어요(앞 = 회색, 뒤 = 푸른색 → 사진 붙이기가 앞면만 바꾸는지 볼 수 있어요).
동작은 HUMAN3D_FAKE_MODE 파일의 글자로 바꿔요: ok / oom_once / oom_always / oom_above_256 / drop_arm / slow / two_pieces
모의 GPU: HUMAN3D_FAKE_VRAM 파일에 '사용 중 MB' 를 적으면 가짜 nvidia-smi(test/fake_bin)가 그 값을 알려요 — 실제 그래픽카드 측정이 아니에요."""
import json
import os
import time

import numpy as np
from PIL import Image

from human3d import export as X, preprocess
from worker import runtime as R
from worker.providers.sith import SithProvider


def mode():
    try:
        return open(os.environ["HUMAN3D_FAKE_MODE"], encoding="utf-8").read().strip()
    except (KeyError, OSError):
        return "ok"


def vram(mb):
    """모의 GPU 의 '사용 중' 값을 바꿔요(가짜 nvidia-smi 가 읽어요)."""
    p = os.environ.get("HUMAN3D_FAKE_VRAM")
    if p:
        with open(p, "w") as f:
            f.write(str(int(mb)))


def inflate(mask, res):
    """불 마스크(res×res) → 닫힌 메시(앞뒤 높이면이 가장자리에서 꼭짓점을 함께 써요)."""
    d = np.zeros(mask.shape, np.float32)
    cur = mask.copy()
    for _ in range(40):
        d += cur
        p = np.pad(cur, 1)
        cur = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:] & p[:-2, :-2] & p[:-2, 2:] & p[2:, :-2] & p[2:, 2:]      # 대각선 이웃까지(안쪽 꼭짓점 둘레의 네모가 모두 있게)
        if not cur.any():
            break
    t = np.sqrt(np.maximum(d - 1, 0)) * (2.0 / res) * 1.5
    ys, xs = np.where(mask)
    fid = np.full(mask.shape, -1, np.int64)
    fid[ys, xs] = np.arange(len(ys))
    inner = t[ys, xs] > 0
    bid = fid.copy()
    bid[ys[inner], xs[inner]] = len(ys) + np.arange(inner.sum())
    X3 = (xs + 0.5) / res * 2 - 1
    Y3 = 1 - (ys + 0.5) / res * 2
    V = np.concatenate([np.stack([X3, Y3, t[ys, xs]], 1), np.stack([X3[inner], Y3[inner], -t[ys, xs][inner]], 1)]).astype(np.float32)
    q = mask[:-1, :-1] & mask[1:, :-1] & mask[:-1, 1:] & mask[1:, 1:]
    qy, qx = np.where(q)
    F = []
    for I, flip in ((fid, False), (bid, True)):
        a, b, c, dd = I[qy, qx], I[qy + 1, qx], I[qy, qx + 1], I[qy + 1, qx + 1]
        tri = np.concatenate([np.stack([a, b, c], 1), np.stack([c, b, dd], 1)])
        F.append(tri[:, ::-1] if flip else tri)
    F = np.concatenate(F)
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    C = np.concatenate([np.tile([110, 110, 110], (len(ys), 1)), np.tile([60, 80, 160], (int(inner.sum()), 1))]).astype(np.uint8)
    return V, F.astype(np.int32), C


class FakeProvider(SithProvider):
    name = "fake"
    title = "가짜 엔진(시험용)"
    verified = False

    def preflight(self):
        gd = {"male": True, "female": mode() != "no_female", "neutral": True}
        return {"ready": True, "checks": [{"id": "code", "ok": True, "text": "가짜 엔진 준비됨", "fix": ""}, {"id": "smplx", "ok": all(gd.values()), "text": "가짜 몸 모델", "fix": "여성 파일을 넣어 주세요"}],
                "versions": self.versions(), "paths": {"smplx": "/tmp/smplx"}, "genders": gd}

    def files(self):
        return {"code": True, "recon": True, "smplerx": True, "diffusion": True, "smplx": True, "genders": {"male": True, "female": mode() != "no_female", "neutral": True}}

    def versions(self):
        return {"engine": "fake", "commit": "test"}

    def st_keypoints(self, job, log):
        job.set_progress(0.5, "가짜 관절점")
        kp = json.load(open(os.environ["HUMAN3D_FAKE_KP"], encoding="utf-8"))          # 원본 화소 좌표의 133점
        fr = json.load(open(os.path.join(job.dir, "input", "frame.json"), encoding="utf-8"))
        k = np.array(kp, np.float64)
        k[:, 0] = k[:, 0] * fr["scale"] + fr["ox"]
        k[:, 1] = k[:, 1] * fr["scale_y"] + fr["oy"]
        R.write_json(os.path.join(job.dir, "images", "000_keypoints.json"), preprocess.wholebody_to_openpose(k))
        return {}

    def st_smplx(self, job, log):
        g, why = self.gender_of(job)
        if not self.files()["genders"][g]:
            raise R.StageError("no_smplx", f"SMPL-X 몸 모델 파일(SMPLX_{g.upper()}.npz)이 없어요. 다른 성별 모델로 바꿔 쓰지 않아요", job.stage)
        job.opts["gender_used"] = g
        job.set_progress(0.3)
        job.enter("smplx_fit")
        m = np.asarray(Image.open(os.path.join(job.dir, "images", "000.png")).getchannel("A").resize((96, 96))) > 127
        V, F, _ = inflate(m, 96)
        os.makedirs(os.path.join(job.dir, "smplx", "debug"), exist_ok=True)
        with open(os.path.join(job.dir, "smplx", "000_smplx.obj"), "w") as f:
            f.write("".join("v %f %f %f\n" % tuple(v) for v in V) + "".join("f %d %d %d\n" % tuple(t + 1) for t in F))
        R.write_json(os.path.join(job.dir, "smplx", "debug", "000.json"), {"betas": [0.0] * 10})
        if mode() != "no_gender_record":
            R.write_json(os.path.join(job.dir, "smplx", "gender.json"), {"gender": g, "model_file": f"SMPLX_{g.upper()}.npz", "applied": True, "vertices": 10475, "upstream_default": "male"})
        return {"notes": [why] if why else []}

    def st_back(self, job, log):
        n = job.opts.get("back_candidates", 4)
        d = os.path.join(job.dir, "back_images", "all_images")
        os.makedirs(d, exist_ok=True)
        for j in range(n):
            if mode() == "slow":
                for _ in range(40):
                    if job.cancel:
                        raise R.Cancelled()
                    time.sleep(0.1)
            job.set_progress((j + 1) / n, f"뒷면 후보 {j + 1}/{n}")
            Image.new("RGB", (64, 64), (60, 80, 160 + j)).save(os.path.join(d, "000_%03d.png" % j))
        Image.new("RGB", (64, 64), (60, 80, 160)).save(os.path.join(job.dir, "back_images", "000_000.png"))
        R.write_json(os.path.join(job.dir, "back_images", "pick.json"), {"picked": 0, "candidates": [{"score": 1.0}] * n})
        return {"vram_mb": 5000}

    def st_recon(self, job, log):
        md, grid = mode(), job.opts.get("grid", 512)
        chunk = job.opts.get("chunk", 50000)
        vram(3000 + grid * 16 + chunk // 100)                  # 모의 사용량: 격자·점 수가 클수록 많이(512·5만 = 11692MB)
        time.sleep(0.35)
        if md == "oom_always" or (md == "oom_once" and grid == 512 and chunk > 20000) or (md == "oom_above_256" and grid > 256):
            vram(900)
            raise R.StageError("oom", "가짜 메모리 부족", "geometry", "RuntimeError: CUDA out of memory.")
        res = 320 if grid == 512 else 192
        m = np.asarray(Image.open(os.path.join(job.dir, "images", "000.png")).getchannel("A").resize((res, res), Image.BILINEAR)) > 127
        if md == "drop_arm":                                   # 왼팔 아래(그림의 오른쪽 바깥)를 지워요
            m[:, int(res * 0.64):] = False
        V, F, C = inflate(m, res)
        if md == "two_pieces":
            V2, F2, C2 = inflate(np.pad(np.ones((6, 6), bool), ((2, res - 8), (2, res - 8))), res)
            F, V, C = np.concatenate([F, F2 + len(V)]), np.concatenate([V, V2]), np.concatenate([C, C2])
        job.set_progress(0.8)
        job.enter("texture")
        os.makedirs(os.path.join(job.dir, "meshes"), exist_ok=True)
        X.write_ply(os.path.join(job.dir, "meshes", "000_reco.ply"), X.Mesh(V, F, C))
        with open(os.path.join(job.dir, "meshes", "000_reco.obj"), "w") as f:
            f.write("".join("v %f %f %f %f %f %f\n" % (*v, *(c / 255.0)) for v, c in zip(V, C)) + "".join("f %d %d %d\n" % tuple(t + 1) for t in F))
        vram(900)
        return {"vram_mb": 9000, "notes": [f"형태 복원 격자 {grid} 로 만들었어요(기본 512 보다 덜 세밀해요)."] if grid < 512 else []}
