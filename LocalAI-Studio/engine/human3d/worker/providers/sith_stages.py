"""SiTH 단계 스크립트(단계마다 별도 프로세스로 실행 — 끝나면 모델과 그래픽카드 메모리가 통째로 풀려요).
실행 위치는 SiTH 폴더(공식 코드가 상대 경로로 data/·checkpoints/ 를 읽어요).

  keypoints  자세·관절점(RTMPose/DWPose 133점) → OpenPose JSON(images/000_keypoints.json)
  fit        SMPLer-X + SMPL-X 맞추기: 공식 fit.py 를 그대로 돌리되, 몸 모델의 성별만 고른 것으로 바꿔요(공식 코드는 남성 고정)
  back       뒷면 그리기: 후보를 한 장씩 그려(묶음 1) 자동으로 한 장 고름 → back_images/000_000.png
  recon      형태·색 복원: 512³ 격자 좌표를 그래픽카드에 통째로 올리지 않고 CPU 에서 조금씩 만들어 보냄 → meshes/000_reco.ply·obj

공식 hallucinate.py·reconstruct.py 와 같은 모델·같은 계산이고, 다른 점은
  · 좌표 격자를 CPU 에 두고 chunk 단위로만 GPU 에 보냄(공식 판은 512³×3 좌표 1.6GB 를 GPU 에 통째로 올림)
  · 뒷면 후보를 한 번에 한 장만 그림(공식 판은 8장을 한 묶음으로)
  · '가장 큰 조각만 남기기'(_repair_mesh)를 하지 않음 — 엔진이 만든 조각을 모두 그대로 저장
★ 실제 그래픽카드에서 돌려 확인하지 못한 코드예요(미검증)."""
import argparse
import json
import os
import sys

from worker import runtime as R


def _paths(job):
    return {"img": os.path.join(job, "images", "000.png"), "kp": os.path.join(job, "images", "000_keypoints.json"),
            "smplx": os.path.join(job, "smplx", "000_smplx.obj"), "back_dir": os.path.join(job, "back_images"),
            "back": os.path.join(job, "back_images", "000_000.png"), "mesh_dir": os.path.join(job, "meshes")}


# ───────────────────────────── 자세·관절점 ─────────────────────────────
def cmd_keypoints(a):
    import cv2
    import numpy as np
    from human3d import preprocess
    P = _paths(a.job)
    R.progress(0.05, "자세 검출기 준비")
    rgba = cv2.imread(P["img"], cv2.IMREAD_UNCHANGED)
    if rgba is None or rgba.ndim != 3 or rgba.shape[2] != 4:
        R.fail("stage_failed", "정사각형 입력 그림(images/000.png)을 읽지 못했어요.")
    al = rgba[:, :, 3:4].astype(np.float32) / 255.0
    bgr = (rgba[:, :, :3].astype(np.float32) * al + 127.0 * (1 - al)).astype(np.uint8)        # 투명한 곳은 회색으로
    try:
        from rtmlib import Wholebody
    except ImportError:
        R.fail("no_model", "자세 검출기(rtmlib)가 설치돼 있지 않아요. 설치를 다시 실행해 주세요.")
    kps = scores = None
    for dev in ("cuda", "cpu"):                          # 그래픽카드용 onnxruntime 이 없으면 CPU 로(몇 초 더 걸릴 뿐이에요)
        try:
            wb = Wholebody(mode="performance", to_openpose=False, backend="onnxruntime", device=dev)
            kps, scores = wb(bgr)
            break
        except Exception as e:  # noqa: BLE001
            print(f"자세 검출({dev}) 실패: {e!r}", flush=True)
    if kps is None:
        R.fail("stage_failed", "자세 검출기를 돌리지 못했어요(모델을 받지 못했을 수 있어요 — 인터넷 연결을 확인해 주세요).")
    kps, scores = np.asarray(kps, np.float64), np.clip(np.asarray(scores, np.float64), 0, 1)
    if kps.ndim != 3 or not len(kps) or kps.shape[1] != 133:
        R.fail("no_person", "사진에서 사람을 찾지 못했어요. 한 사람의 몸 전체가 잘 보이는 사진을 써 주세요.")
    area = [(np.ptp(k[s > 0.3, 0]) * np.ptp(k[s > 0.3, 1])) if (s > 0.3).sum() > 5 else 0 for k, s in zip(kps, scores)]
    i = int(np.argmax(area))
    if area[i] <= 0 or (scores[i][:17] > 0.3).sum() < 8:
        R.fail("no_person", "사람의 관절을 충분히 찾지 못했어요. 몸 전체가 가려지지 않은 사진을 써 주세요.")
    R.write_json(P["kp"], preprocess.wholebody_to_openpose(kps[i], scores[i]))
    R.write_json(os.path.join(a.job, "pose", "wholebody.json"), {"people": int(len(kps)), "picked": i, "keypoints": kps[i].tolist(), "scores": scores[i].tolist(),
                                                                "note": "COCO-WholeBody 133점(화소 좌표, 1024 기준)"})
    if len(kps) > 1:
        R.emit("NOTE", f"사진에 사람이 {len(kps)}명 보여서 가장 크게 나온 사람을 골랐어요.")
    R.progress(1.0, "관절점 저장")


# ───────────────────────────── 몸 맞추기(SMPL-X) ─────────────────────────────
def smplx_file(gender):
    return os.path.join("data", "body_models", "smplx", f"SMPLX_{gender.upper()}.npz")


def cmd_fit(a):
    """공식 fit.py 의 main() 을 그대로 써요. 다른 점은 하나: fit.py 181번째 줄이 SMPLX(..., gender='male') 로 고정돼 있어서,
    fit 모듈의 SMPLX 를 감싸 '고른 성별'로만 만들어지게 해요(공식 파일은 고치지 않아요 — 되돌리기 쉽고 판이 바뀌어도 알아챌 수 있게).
    고른 성별의 모델 파일이 없으면 다른 성별로 바꿔 쓰지 않고 멈춰요."""
    g = a.gender
    if g not in R.GENDERS:
        R.fail("stage_failed", f"모르는 성별 값이에요: {g}")
    if not os.path.isfile(smplx_file(g)):
        R.fail("no_smplx", f"SMPL-X {({'male': '남성', 'female': '여성', 'neutral': '중립'})[g]} 몸 모델 파일({os.path.basename(smplx_file(g))})이 없어요. 다른 성별 모델로 바꿔 쓰지 않아요 — 파일을 넣거나 다른 성별을 골라 주세요.")
    import fit as F                                   # SiTH/fit.py
    seen = {"asked": None, "used": None, "calls": 0, "n_vert": None}
    real = F.SMPLX

    def make(*args, **kw):
        seen["asked"] = kw.get("gender")
        kw["gender"] = g
        m = real(*args, **kw)
        seen["calls"] += 1
        seen["used"] = getattr(m, "gender", None)
        try:
            seen["n_vert"] = int(m.v_template.shape[0])
        except Exception:  # noqa: BLE001
            pass
        return m

    F.SMPLX = make
    ns = argparse.Namespace(input_path=os.path.join(a.job, "images"), output_path=os.path.join(a.job, "smplx"), size=1024, debug=True,
                            opt_orient=True, opt_pose=False, opt_betas=True)
    R.progress(0.02, "몸 어림 모델 불러오는 중")
    F.main(ns)
    R.report_vram()
    if seen["calls"] < 1:
        R.fail("stage_failed", "몸 맞추기가 SMPL-X 모델을 만들지 않았어요(SiTH 코드 판이 달라졌을 수 있어요). 성별을 적용하지 못해 멈췄어요.")
    if seen["used"] != g:
        R.fail("stage_failed", f"고른 성별({g})이 몸 모델에 적용되지 않았어요(실제 {seen['used']}). 멈췄어요.")
    if seen["n_vert"] not in (None, 10475):
        R.fail("stage_failed", f"SMPL-X 몸 모델의 꼭짓점 수가 예상(10475)과 달라요: {seen['n_vert']}")
    R.write_json(os.path.join(a.job, "smplx", "gender.json"), {"gender": g, "model_file": os.path.basename(smplx_file(g)), "applied": True, "vertices": seen["n_vert"],
                                                              "upstream_default": seen["asked"],
                                                              "note": "SiTH 공식 코드는 모든 사람에게 남성 몸 모델을 써요(학습 자료도 그렇게 맞춰졌어요). 다른 성별 모델로 맞춘 결과의 품질은 실제 사진으로 확인해야 해요."})


# ───────────────────────────── 뒷면 그리기 ─────────────────────────────
def _score_back(cands, front_rgba, res):
    """후보 점수: 앞 사진과 옷·피부 색 분포가 비슷할수록, 사람 바깥이 깨끗할수록 높아요(뒷면 윤곽은 앞을 좌우로 뒤집은 것).
    단순한 기준이라 '가장 그럴듯한 뒷모습'을 보장하지는 않아요 — 점수와 후보는 모두 남겨요."""
    import numpy as np
    from PIL import Image
    f = np.asarray(front_rgba.resize((res, res), Image.BILINEAR), np.float32)
    m = f[:, :, 3] > 127
    mb = m[:, ::-1]

    def hist(px):
        h, _ = np.histogramdd(px, bins=(6, 6, 6), range=((0, 256),) * 3)
        return h.ravel() / max(1.0, h.sum())

    hf = hist(f[:, :, :3][m])
    out = []
    for c in cands:
        im = np.asarray(c.convert("RGB").resize((res, res), Image.BILINEAR), np.float32)
        sim = float(np.minimum(hf, hist(im[mb])).sum()) if mb.any() else 0.0
        clean = 1.0 - min(1.0, float(im[~mb].std()) / 40.0) if (~mb).any() else 1.0
        gy, gx = np.gradient(im.mean(2))
        sharp = float(np.sqrt(gx ** 2 + gy ** 2)[mb].mean()) if mb.any() else 0.0
        out.append({"color_similarity": round(sim, 4), "background_clean": round(clean, 4), "sharpness": round(sharp, 3),
                    "score": round(0.6 * sim + 0.3 * clean + 0.1 * min(1.0, sharp / 12.0), 4)})
    return out


def cmd_back(a):
    import numpy as np
    import torch
    from PIL import Image
    from diffusers import AutoencoderKL, ControlNetModel, DDPMScheduler, UNet2DConditionModel, UniPCMultistepScheduler
    from transformers import CLIPVisionModelWithProjection

    from diffusion.lib.ccprojection import CCProjection
    from diffusion.lib.pipeline import BackHallucinationPipeline
    from diffusion.lib.test_diffusion_dataset import TestDiffDataset
    P = _paths(a.job)
    if not torch.cuda.is_available():
        R.fail("no_cuda", "그래픽카드(CUDA)를 쓸 수 없어요.")
    all_dir = os.path.join(P["back_dir"], "all_images")
    os.makedirs(all_dir, exist_ok=True)
    R.progress(0.02, "뒷면 그리기 모델 불러오는 중")

    def build(dtype):
        mp = a.model
        vae = AutoencoderKL.from_pretrained(mp, subfolder="vae")
        clip = CLIPVisionModelWithProjection.from_pretrained(mp, subfolder="image_encoder")
        unet = UNet2DConditionModel.from_pretrained(mp, subfolder="unet")
        cn = ControlNetModel.from_pretrained(mp, subfolder="controlnet")
        proj = CCProjection.from_pretrained(mp, subfolder="projection", clip_image_encoder=clip)
        for m in (vae, clip, unet, cn, proj):
            m.requires_grad_(False)
            m.to(dtype=dtype)
        pipe = BackHallucinationPipeline(vae=vae, clip_image_encoder=clip, unet=unet, controlnet=cn, scheduler=DDPMScheduler.from_pretrained(mp, subfolder="scheduler"),
                                         refer_clip_proj=proj, torch_dtype=dtype)
        pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)
        pipe.set_progress_bar_config(disable=True)
        if a.offload:
            pipe.enable_model_cpu_offload()                 # 모델을 하나씩만 그래픽카드에(느리지만 메모리를 덜 써요)
        else:
            pipe = pipe.to("cuda")
        return pipe

    ds = TestDiffDataset(a.job, "data/smplx_uv.obj", size=a.res)        # 공식 코드와 같은 입력 준비(SMPL-X 의 UV 그림·마스크)
    item = ds[0]
    data = {k: (v.unsqueeze(0) if torch.is_tensor(v) else [v]) for k, v in item.items()}
    del ds
    dtype = torch.float16 if a.fp16 else torch.float32
    pipe = build(dtype)
    cands = []
    for j in range(a.n):
        gen = torch.Generator(device="cuda").manual_seed(a.seed + j)
        R.progress(0.1 + 0.8 * j / a.n, f"뒷면 후보 {j + 1}/{a.n} 그리는 중")
        try:
            with torch.inference_mode(), torch.autocast("cuda"):
                im = pipe.forward(data, num_inference_steps=a.steps, generator=gen, guidance_scale=3.5, controlnet_conditioning_scale=1.0, num_images_per_prompt=1)
        except torch.cuda.OutOfMemoryError:
            raise
        except RuntimeError as e:
            if j == 0 and dtype == torch.float16:           # 반정밀도(FP16)에서 자료형이 안 맞으면 원래 정밀도로 한 번만 다시
                print(f"FP16 실패 → FP32 로 다시: {e!r}", flush=True)
                R.emit("NOTE", "뒷면 그리기를 FP16 으로 돌리지 못해 FP32 로 돌렸어요(메모리를 더 써요).")
                del pipe
                R.cuda_cleanup()
                dtype = torch.float32
                pipe = build(dtype)
                with torch.inference_mode(), torch.autocast("cuda"):
                    im = pipe.forward(data, num_inference_steps=a.steps, generator=gen, guidance_scale=3.5, controlnet_conditioning_scale=1.0, num_images_per_prompt=1)
            else:
                raise
        arr = np.nan_to_num(np.asarray(im[0], np.float32))
        if arr.max() <= 0.001:
            R.emit("NOTE", f"뒷면 후보 {j + 1} 이 검게 나왔어요(계산 오류일 수 있어요).")
        pil = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
        pil.save(os.path.join(all_dir, "000_%03d.png" % j))
        cands.append(pil)
        R.cuda_cleanup()
    R.report_vram()
    del pipe
    R.cuda_cleanup()
    sc = _score_back(cands, Image.open(P["img"]).convert("RGBA"), a.res)
    best = max(range(len(sc)), key=lambda i: sc[i]["score"])
    cands[best].save(P["back"])
    R.write_json(os.path.join(P["back_dir"], "pick.json"), {"picked": best, "file": "all_images/000_%03d.png" % best, "candidates": sc, "seed": a.seed, "steps": a.steps,
                                                           "resolution": a.res, "dtype": str(dtype).replace("torch.", ""), "offload": bool(a.offload),
                                                           "note": "뒷면은 사진에 없는 부분을 AI 가 추정해 그린 것이에요. 실제 뒷모습과 다를 수 있어요."})
    R.progress(1.0, f"뒷면 후보 {a.n}장 중 {best + 1}번을 골랐어요")


# ───────────────────────────── 형태·색 복원 ─────────────────────────────
def cmd_recon(a):
    import pickle

    import kaolin as kal
    import numpy as np
    import nvdiffrast.torch as dr
    import torch
    from PIL import Image
    from torchvision import transforms

    from human3d import export as X
    from recon.models.evaluator import Evaluator
    from recon.models.ops.mesh.load_obj import load_obj
    from recon.utils.config import parse_options, parse_yaml_config
    P = _paths(a.job)
    if not torch.cuda.is_available():
        R.fail("no_cuda", "그래픽카드(CUDA)를 쓸 수 없어요.")
    dev = torch.device("cuda")
    res, chunk = int(a.grid), int(a.chunk)
    R.progress(0.01, "형태 복원 모델 불러오는 중")
    parser = parse_options()
    parse_yaml_config("recon/config.yaml", parser)
    cfg = parser.parse_args(["--resume", "checkpoints/recon_model.pth", "--grid_size", "8"])      # 8: 공식 코드가 GPU 에 만드는 격자를 아주 작게(우리는 그 격자를 쓰지 않아요)
    with open("data/smplx_watertight.pkl", "rb") as f:
        watertight = pickle.load(f)
    can_V, _ = load_obj("data/smplx_canonical.obj")
    ev = Evaluator(cfg, watertight, can_V)
    ev.eval()
    size = cfg.img_size
    tf = transforms.Compose([transforms.Resize((size, size), interpolation=transforms.InterpolationMode.BILINEAR), transforms.ToTensor()])
    front = tf(Image.open(P["img"]))
    rgb, mask = front[:3], front[3:]
    hole = (mask < 0.5).expand_as(rgb)
    rgb[hole] = 0.0
    back = torch.flip(tf(Image.open(P["back"]).convert("RGB")), [2])          # 뒷면 그림은 좌우를 뒤집어 앞과 같은 좌표로
    back[hole] = 0.0
    V, _ = load_obj(P["smplx"])
    # 앞·뒤 카메라에서 SMPL-X 의 어느 면이 보이는지(공식 test_dataset.render_visiblity 와 같은 계산 — 면마다 도는 반복문만 torch.unique 로 바꿈)
    Fw = watertight["smpl_F"].to(dev)
    cam = kal.render.camera.Camera.from_args(eye=torch.tensor([[0, 0, 3], [0, 0, -3]], dtype=torch.float32, device=dev), at=torch.zeros((2, 3), dtype=torch.float32, device=dev),
                                             up=torch.tensor([[0, 1, 0]], dtype=torch.float32, device=dev).repeat(2, 1), width=size, height=size, near=-512, far=512, fov_distance=1.0, device=dev)
    vc = cam.extrinsics.transform(V.to(dev))
    clip = (cam.projection_matrix()[0:1] @ kal.render.camera.up_to_homogeneous(vc)[..., None]).squeeze(-1)
    rast = dr.rasterize(ev.glctx, clip, Fw.int(), (1024, 1024), grad_db=False)
    fidx = (torch.flip(rast[0], dims=(1,))[..., -1].long() - 1)
    vis = torch.zeros((Fw.shape[0], 1), dtype=torch.float32)
    for i, val in ((0, 1.0), (1, -1.0)):
        ids = torch.unique(fidx[i])
        vis[ids[ids >= 0].cpu()] = val
    del rast, fidx, clip, vc
    notes = []
    with torch.inference_mode():
        f_img, b_img = ((rgb - 0.5) / 0.5)[None].to(dev), ((back - 0.5) / 0.5)[None].to(dev)
        smpl_v, vis_class = V[None].to(dev), vis[None].to(dev)
        fn, bn = ev.nrm_predictor(f_img), ev.nrm_predictor(b_img)
        ff, bf = ev.geo_model.compute_feat_map(f_img, b_img, fn, bn)
        del fn, bn
        R.cuda_cleanup()
        total = res ** 3
        vox = np.empty(total, np.float32)                     # 512³ = 512MB — 시스템 메모리에 둬요
        nchunk = (total + chunk - 1) // chunk
        for k, (s, pts) in enumerate(R.grid_chunks(res, chunk)):
            p = torch.from_numpy(pts)[None].to(dev, non_blocking=True)
            vox[s:s + len(pts)] = ev.geo_model.compute_sdf(p, ff, bf, smpl_v, vis_class)[0, :, 0].float().cpu().numpy()
            if k % 40 == 0:
                R.progress(0.03 + 0.85 * k / nchunk, f"형태 복원 중 (격자 {res}) {100 * k // nchunk}%")
        del ff, bf, p
        R.cuda_cleanup()
        R.progress(0.9, "표면 뽑는 중")
        verts = faces = None
        try:
            vt = torch.from_numpy(vox).view(1, res, res, res).to(dev)
            v, f = kal.ops.conversions.voxelgrids_to_trianglemeshes(vt, iso_value=0.0)
            verts, faces = ((v[0].reshape(1, -1, 3) - 0.5) / (res / 2)) - 1.0, f[0]
            del vt, v, f
        except torch.cuda.OutOfMemoryError:
            R.cuda_cleanup()
            try:
                from skimage import measure
            except ImportError:
                raise
            notes.append("표면 뽑기를 그래픽카드 대신 CPU 로 했어요(메모리 부족).")
            v, f, _, _ = measure.marching_cubes(vox.reshape(res, res, res), level=0.0)
            verts = torch.from_numpy((v / (res - 1) * 2 - 1).astype(np.float32))[None].to(dev)
            faces = torch.from_numpy(f.astype(np.int64)).to(dev)
        del vox
        if verts is None or verts.shape[1] == 0 or faces.shape[0] == 0:
            R.fail("stage_failed", "형태 복원 결과가 비어 있어요(표면을 찾지 못함). 몸 맞추기나 뒷면 그림이 잘못됐을 수 있어요.")
        if a.subdivide:
            try:
                verts, faces = kal.ops.mesh.subdivide_trianglemesh(verts, faces, iterations=1)
            except torch.cuda.OutOfMemoryError:
                R.cuda_cleanup()
                notes.append("메모리가 모자라 면 나누기(더 촘촘하게)를 건너뛰었어요.")
        R.emit("STAGE", "texture")
        R.progress(0.05, "색 입히는 중")
        tf_, tb_ = ev.tex_model.compute_feat_map(f_img, b_img)
        n = verts.shape[1]
        cols = np.empty((n, 3), np.float32)
        for s in range(0, n, chunk):
            cols[s:s + chunk] = ev.tex_model.compute_rgb(verts[:, s:s + chunk], tf_, tb_, smpl_v, vis_class)[0].float().cpu().numpy()
            R.progress(0.05 + 0.8 * min(n, s + chunk) / n, "색 입히는 중")
        Vn, Fn = verts[0].float().cpu().numpy(), faces.cpu().numpy().astype(np.int32)
    R.report_vram()
    del ev
    R.cuda_cleanup()
    os.makedirs(P["mesh_dir"], exist_ok=True)
    m = X.Mesh(Vn, Fn, np.clip(np.rint(cols * 255), 0, 255).astype(np.uint8))
    X.write_ply(os.path.join(P["mesh_dir"], "000_reco.ply"), m)                 # 엔진 원본(조각을 지우지 않은 그대로)
    R.progress(0.92, "원본 메시 저장 중")
    with open(os.path.join(P["mesh_dir"], "000_reco.obj"), "w", encoding="utf-8") as fo:
        fo.write("# SiTH reconstruction (vertex colors) — LAIS human3d, untouched engine output\n")
        np.savetxt(fo, np.concatenate([Vn, cols], 1), fmt="v %.6f %.6f %.6f %.4f %.4f %.4f")
        np.savetxt(fo, Fn + 1, fmt="f %d %d %d")
    R.write_json(os.path.join(P["mesh_dir"], "recon.json"), {"grid": res, "chunk": chunk, "subdivided": bool(a.subdivide) and not any("면 나누기" in x for x in notes),
                                                            "vertices": int(len(Vn)), "faces": int(len(Fn)), "notes": notes,
                                                            "coords": "x 오른쪽 · y 위 · z 앞(카메라 쪽), 범위 [-1, 1]. 사진 화소 x=(X+1)/2·크기, y=(1−Y)/2·크기 (직교 투영)"})
    for x in notes:
        R.emit("NOTE", x)
    if res < 512:
        R.emit("NOTE", f"형태 복원 격자 {res} 로 만들었어요(기본 512 보다 덜 세밀해요).")
    R.progress(1.0, f"꼭짓점 {len(Vn):,}개 · 면 {len(Fn):,}개")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keypoints")
    k.add_argument("--job", required=True)
    f = sub.add_parser("fit")
    f.add_argument("--job", required=True)
    f.add_argument("--gender", required=True)
    b = sub.add_parser("back")
    b.add_argument("--job", required=True)
    b.add_argument("--model", required=True)
    for n, d in (("n", 4), ("steps", 50), ("res", 512), ("seed", 0), ("fp16", 1), ("offload", 0)):
        b.add_argument("--" + n, type=int, default=d)
    r = sub.add_parser("recon")
    r.add_argument("--job", required=True)
    for n, d in (("grid", 512), ("chunk", 50000), ("subdivide", 1)):
        r.add_argument("--" + n, type=int, default=d)
    a = ap.parse_args()
    try:
        {"keypoints": cmd_keypoints, "fit": cmd_fit, "back": cmd_back, "recon": cmd_recon}[a.cmd](a)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        R.report_vram()
        if R.is_oom(repr(e)) or e.__class__.__name__ == "OutOfMemoryError":
            R.fail("oom", "그래픽카드 메모리가 모자라요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
