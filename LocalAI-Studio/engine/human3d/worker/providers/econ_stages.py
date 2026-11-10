"""ECON 단계 스크립트 — ECON 전용 환경(econ-venv)의 파이썬으로, ECON 폴더에서 실행해요(공식 코드가 상대 경로로 data/·configs/ 를 읽어요).

  run   공식 apps/infer.py 를 그대로 돌리되(runpy), 시작 전에 아래만 바꿔 끼워요. 공식 파일은 고치지 않아요.
        · 몸 모델 성별: PIXIE 의 SMPL-X 파일을 고른 성별의 것으로(자동·중립 = ECON 기본 SMPLX_NEUTRAL_2020.npz)
                       mesh_util.get_smpl_model 이 받은 성별을 무시하고 남성으로 만들던 것을 받은 성별로(추론 경로에서는 안 쓰이지만 같이 고쳐요)
        · 마지막 정리(poisson): '가장 큰 조각만 남기기'·'면 5만 개로 줄이기'를 하지 않은 원본을 결과로, ECON 원래 결과는 비교용으로 따로 저장
        · 색 입히기(query_color): 사진에서 안 보이는 뒤·옆을 '면 방향 무지개색' 대신 회색으로(뒷면 색이 없다는 것을 숨기지 않게)
        · Sapiens: 처음 불러올 때 Hugging Face 공간 전체(수십 GB)를 받는 것을 막고, 미리 받아 둔 파일만 써요
        · 단계 알림: 사람 찾기 → 몸 맞추기 → 표면 합치기 → 색 입히기 를 @@STAGE 로
        끝나면 결과를 LAIS 의 정사각형 입력 그림 좌표로 옮겨 meshes/000_reco.ply·obj, smplx/000_smplx.obj, smplx/gender.json 을 남겨요.

★ 실제 그래픽카드·실제 ECON 모델로 돌려 확인하지 못한 코드예요(미검증)."""
import argparse
import glob
import json
import os
import runpy
import shutil
import sys

import numpy as np

from worker import runtime as R

GENDER_KO = {"male": "남성", "female": "여성", "neutral": "중립"}
NEUTRAL_2020 = os.path.join("data", "HPS", "pixie_data", "SMPLX_NEUTRAL_2020.npz")      # ECON(PIXIE) 기본 몸 모델
SMPLX_V11 = os.path.join("data", "smpl_related", "models", "smplx")                      # SMPL-X v1.1 (ICON 계정으로 받는 models_smplx_v1_1.zip)
NEED_KEYS = ("f", "v_template", "shapedirs", "posedirs", "J_regressor", "kintree_table", "weights",
             "lmk_faces_idx", "lmk_bary_coords", "dynamic_lmk_faces_idx", "dynamic_lmk_bary_coords")
# 화질 단계 → ECON 설정. 일반 고품질 = ECON 공식 기본(Sapiens 2B). 실제로 지원되는 값만 써요.
MODES = {"high": {"normal_model": "2b", "use_ifnet": True}, "normal": {"normal_model": "2b", "use_ifnet": False},
         "low": {"normal_model": "1b", "use_ifnet": False}}
SAPIENS_FILES = {"0.3b": "sapiens_0.3b_normal_render_people_epoch_66_torchscript.pt2", "1b": "sapiens_1b_normal_render_people_epoch_115_torchscript.pt2",
                 "2b": "sapiens_2b_normal_render_people_epoch_70_torchscript.pt2", "fg-bg-1b": "sapiens_1b_seg_foreground_epoch_8_torchscript.pt2"}


def body_file(gender):
    """고른 성별 → ECON 이 쓸 SMPL-X 파일(ECON 폴더 기준 경로). 자동은 부르는 쪽에서 neutral 로 바꿔 와요."""
    return NEUTRAL_2020 if gender == "neutral" else os.path.join(SMPLX_V11, f"SMPLX_{gender.upper()}.npz")


def check_body(path, n_shape=200, n_exp=50):
    """PIXIE 의 SMPLX 클래스가 읽을 수 있는 파일인지(필요한 값·꼭짓점 10475개·체형 칸 300+표정 칸). 문제가 있으면 한국어 까닭, 없으면 None."""
    if not os.path.isfile(path):
        return f"파일이 없어요: {path}"
    try:
        d = np.load(path, allow_pickle=True)
    except Exception as e:  # noqa: BLE001
        return f"파일을 읽지 못했어요({os.path.basename(path)}): {e}"
    miss = [k for k in NEED_KEYS if k not in d.files]
    if miss:
        return f"{os.path.basename(path)} 에 필요한 값이 없어요: {', '.join(miss)} (SMPL-X v1.1 의 .npz 파일이 맞는지 확인해 주세요)"
    if tuple(d["v_template"].shape) != (10475, 3):
        return f"{os.path.basename(path)} 의 꼭짓점 수가 SMPL-X(10475)와 달라요: {d['v_template'].shape}"
    sd = d["shapedirs"].shape
    if len(sd) != 3 or sd[2] < 300 + n_exp or n_shape > 300:
        return f"{os.path.basename(path)} 의 체형·표정 칸이 모자라요({sd}). ECON 은 체형 300칸 + 표정 칸이 있는 SMPL-X v1.1(2020) 파일이 필요해요."
    return None


def square_input(job, out_dir):
    """LAIS 가 만든 정사각형 입력(배경 지움, RGBA) → ECON 입력(RGB, 투명한 곳은 회색). ECON 의 사진 읽기는 투명도를 버려요."""
    from PIL import Image
    im = Image.open(os.path.join(job, "images", "000.png")).convert("RGBA")
    bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
    bg.alpha_composite(im)
    os.makedirs(out_dir, exist_ok=True)
    bg.convert("RGB").save(os.path.join(out_dir, "000.png"))
    return im.size[0]


def write_cfg(src, dst, mode, out_dir, m=None):
    """공식 configs/econ.yaml 을 읽어 화질 단계 값만 바꾼 설정 파일을 작업 폴더에 써요(공식 파일은 그대로)."""
    import yaml
    with open(src, encoding="utf-8") as f:
        c = yaml.safe_load(f)
    m = m or MODES[mode]
    c.setdefault("sapiens", {})
    c["sapiens"].update(use=True, normal_model=m["normal_model"], seg_model="fg-bg-1b")
    c.setdefault("bni", {})
    c["bni"].update(use_ifnet=m["use_ifnet"], texture_src="image")
    c["results_path"] = out_dir
    with open(dst, "w", encoding="utf-8") as f:
        yaml.safe_dump(c, f, allow_unicode=True, sort_keys=False)
    return c


def to_square(V, uncrop, idx=0, crop=512, square=1024):
    """ECON 결과 좌표(잘라 낸 512 그림 기준, x 오른쪽·y 위·+z 앞, [-1,1]) → LAIS 정사각형 입력(square×square) 좌표.
    ECON: 그림 열 = (X+1)/2·(crop−1), 행 = (1−Y)/2·(crop−1) (grid_sample align_corners=True).  M_crop: 정사각형→잘린 그림, M_square: 입력→정사각형.
    LAIS: 화소 i 의 가운데가 X = (i+0.5)/S·2−1, 행 j 의 가운데가 Y = 1−(j+0.5)/S·2.  z 는 x 와 같은 비율로 늘려요."""
    V = np.asarray(V, np.float64)
    Mc = np.asarray(uncrop["M_crop"], np.float64)
    Mc = Mc[idx] if Mc.ndim == 3 else Mc
    Ms = np.asarray(uncrop["M_square"], np.float64)
    Ms = Ms[0] if Ms.ndim == 3 else Ms
    A = np.linalg.inv(Ms) @ np.linalg.inv(Mc)                # 잘린 그림 화소 → 입력 그림 화소
    k = (crop - 1) / 2.0
    px = np.stack([(V[:, 0] + 1) * k, (1 - V[:, 1]) * k, np.ones(len(V))], 1) @ A.T
    s = np.sqrt(abs(np.linalg.det(A[:2, :2])))              # 잘린 그림 1화소 = 입력 그림 s 화소
    out = np.empty_like(V)
    out[:, 0] = (px[:, 0] + 0.5) / square * 2 - 1
    out[:, 1] = 1 - (px[:, 1] + 0.5) / square * 2
    out[:, 2] = V[:, 2] * k * s * 2 / square
    return out.astype(np.float32)


def install_patches(a, state):
    """공식 코드를 불러오기 전에 바꿔 끼워요(infer.py 가 'from ... import *' 로 이름을 가져가기 전에)."""
    import huggingface_hub
    sap_root = a.sapiens

    def no_space_download(*args, **kw):                      # apps/sapiens.py 가 처음 불러올 때 공간 전체를 받으려는 것을 막아요
        if kw.get("repo_id", args[0] if args else "") == "facebook/sapiens-normal":
            return sap_root
        return orig_snap(*args, **kw)

    orig_snap = huggingface_hub.snapshot_download
    huggingface_hub.snapshot_download = no_space_download

    import lib.common.imutils as IM
    orig_proc = IM.process_image

    def proc(*args, **kw):
        R.emit("STAGE", "keypoints")
        R.progress(0.1, "사람 찾기·자르기")
        out = orig_proc(*args, **kw)
        state["uncrop"] = {k: (v.detach().cpu().numpy() if hasattr(v, "detach") else v) for k, v in out["uncrop_param"].items()}
        R.emit("STAGE", "smplx_init")
        R.progress(0.2, "몸 모양 어림 (PIXIE)")
        return out

    IM.process_image = proc

    import lib.common.render as RD
    orig_qc = RD.query_color

    def qc(verts, faces, image, device, paint_normal=True):
        R.emit("STAGE", "texture")
        R.progress(0.3, "색 입히기")
        return orig_qc(verts, faces, image, device, paint_normal=False)      # 안 보이는 곳 = 회색

    RD.query_color = qc

    import lib.common.train_util as TU
    orig_init = TU.init_loss

    def init_loss(*args, **kw):
        R.emit("STAGE", "smplx_fit")
        R.progress(0.02, "몸 모양·자세 맞추기")
        return orig_init(*args, **kw)

    TU.init_loss = init_loss

    import lib.common.BNI as BN
    orig_bni_init = BN.BNI.__init__

    def bni_init(self, *args, **kw):
        R.emit("STAGE", "geometry")
        R.progress(0.1, "앞·뒤 표면 합치기 (d-BiNI)")
        return orig_bni_init(self, *args, **kw)

    BN.BNI.__init__ = bni_init

    import lib.dataset.mesh_util as MU
    MU.model_init_params["gender"] = a.gender                     # 공식은 'male' 고정

    def get_smpl_model(model_type, gender):                      # 공식은 받은 gender 를 무시하고 남성으로 만들어요
        return MU.smplx.create(**{**MU.model_init_params, "model_type": model_type, "gender": gender})

    MU.get_smpl_model = get_smpl_model
    orig_poisson = MU.poisson

    def poisson_keep_all(mesh, obj_path, depth=10, face_count=50000, laplacian_remeshing=False):
        R.progress(0.7, "표면 메우기 (Poisson)")
        orig_poisson(mesh, obj_path[:-4] + "_econ_default.obj", depth, face_count, laplacian_remeshing)      # ECON 원래 결과(가장 큰 조각·면 5만) — 비교용
        pcd_path = obj_path[:-4] + "_soups.ply"
        mesh.export(pcd_path)
        pcl = MU.o3d.io.read_point_cloud(pcd_path)
        m, _ = MU.o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcl, depth=depth, n_threads=-1)
        full = MU.trimesh.Trimesh(np.asarray(m.vertices), np.asarray(m.triangles), process=False)      # 조각을 지우지도, 면을 줄이지도 않아요
        full.export(obj_path)
        state["poisson"] = {"vertices": int(len(full.vertices)), "faces": int(len(full.faces)), "components": int(len(full.split(only_watertight=False)))}
        return full

    MU.poisson = poisson_keep_all

    from lib.pixielib.utils.config import cfg as pixie_cfg
    pixie_cfg.model.smplx_model_path = os.path.abspath(body_file(a.gender))
    state["body_path"] = pixie_cfg.model.smplx_model_path


def find_one(pattern):
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else None


def cmd_run(a):
    from human3d import export as X
    if a.gender not in GENDER_KO:
        R.fail("stage_failed", f"모르는 성별 값이에요: {a.gender}")
    if a.mode not in MODES:
        R.fail("stage_failed", f"모르는 화질 값이에요: {a.mode}")
    why = check_body(body_file(a.gender))
    if why:
        R.fail("no_smplx", f"SMPL-X {GENDER_KO[a.gender]} 몸 모델을 ECON 에 쓸 수 없어요 — {why}. 다른 성별 모델로 바꿔 쓰지 않아요.")
    m = dict(MODES[a.mode])
    if a.normal_model:                                       # 저메모리에서 메모리가 모자라 다시 할 때 더 작은 Sapiens 로
        m["normal_model"] = a.normal_model
    for key in (m["normal_model"], "fg-bg-1b"):
        f = os.path.join(a.sapiens, "assets", "checkpoints", SAPIENS_FILES[key])      # apps/sapiens.py 가 <받은 곳>/assets/checkpoints 에서 읽어요
        if not os.path.isfile(f):
            R.fail("no_model", f"Sapiens 모델 파일이 없어요: {SAPIENS_FILES[key]} — 인체 3D 화면에서 ECON 모델 받기를 다시 해 주세요.")
    work = os.path.join(a.job, "econ")
    in_dir, out_dir = os.path.join(work, "in"), os.path.join(work, "out")
    S = square_input(a.job, in_dir)
    write_cfg(os.path.join("configs", "econ.yaml"), os.path.join(work, "econ_cfg.yaml"), a.mode, out_dir, m)
    state = {}
    R.emit("STAGE", "keypoints")
    R.progress(0.02, "ECON 모델 불러오는 중")
    install_patches(a, state)
    sys.argv = ["apps.infer", "-cfg", os.path.join(work, "econ_cfg.yaml"), "-in_dir", in_dir, "-out_dir", out_dir, "-novis", "-loop_smpl", str(a.loop_smpl)]
    runpy.run_module("apps.infer", run_name="__main__", alter_sys=True)
    R.report_vram()
    if "uncrop" not in state:
        R.fail("no_person", "ECON 이 사진에서 사람을 찾지 못했어요.")
    obj = os.path.join(out_dir, "econ", "obj")
    full = find_one(os.path.join(obj, "000_0_full.obj"))
    if not full:
        R.fail("stage_failed", "ECON 이 최종 메시(000_0_full.obj)를 만들지 못했어요. 작업 폴더의 econ/out 을 확인해 주세요.")
    mesh = X.read_obj(full)
    if not len(mesh.F):
        R.fail("stage_failed", "ECON 결과 메시가 비어 있어요.")
    V = to_square(mesh.V, state["uncrop"], 0, square=S)
    C = mesh.C if mesh.C is not None else np.full((len(V), 3), 128, np.uint8)
    os.makedirs(os.path.join(a.job, "meshes"), exist_ok=True)
    out = X.Mesh(V, mesh.F, C)
    X.write_ply(os.path.join(a.job, "meshes", "000_reco.ply"), out)
    with open(os.path.join(a.job, "meshes", "000_reco.obj"), "w", encoding="utf-8") as fo:
        fo.write("# ECON reconstruction (vertex colors, LAIS square-image coords) — LAIS human3d, no keep-largest / no decimation\n")
        np.savetxt(fo, np.concatenate([V, C / 255.0], 1), fmt="v %.6f %.6f %.6f %.4f %.4f %.4f")
        np.savetxt(fo, mesh.F + 1, fmt="f %d %d %d")
    dflt = find_one(os.path.join(obj, "000_0_full_econ_default.obj"))
    if dflt:
        d = X.read_obj(dflt)
        X.write_ply(os.path.join(a.job, "meshes", "000_econ_default.ply"), X.Mesh(to_square(d.V, state["uncrop"], 0, square=S), d.F, d.C))
    smpl = find_one(os.path.join(obj, "000_smpl_00.obj"))
    os.makedirs(os.path.join(a.job, "smplx"), exist_ok=True)
    if smpl:
        sm = X.read_obj(smpl)
        sv = to_square(sm.V, state["uncrop"], 0, square=S)      # infer.py 가 최종 메시와 같은 좌표(y 위)로 저장해 둬요
        with open(os.path.join(a.job, "smplx", "000_smplx.obj"), "w", encoding="utf-8") as fo:
            np.savetxt(fo, sv, fmt="v %.6f %.6f %.6f")
            np.savetxt(fo, sm.F + 1, fmt="f %d %d %d")
    R.write_json(os.path.join(a.job, "smplx", "gender.json"), {
        "gender": a.gender, "model_file": os.path.basename(state.get("body_path", "")), "applied": os.path.basename(state.get("body_path", "")) == os.path.basename(body_file(a.gender)),
        "vertices": 10475, "engine": "econ", "upstream_default": "SMPLX_NEUTRAL_2020.npz",
        "note": "ECON(PIXIE)은 원래 중립 몸 모델(SMPLX_NEUTRAL_2020)을 써요. 여성·남성은 SMPL-X v1.1 파일로 바꿔 맞춘 것이라, PIXIE 가 중립 기준으로 어림한 체형에서 시작해 맞추기로 조정돼요(품질은 실제 사진으로 확인 필요)."})
    R.write_json(os.path.join(a.job, "meshes", "recon.json"), {"engine": "econ", "mode": a.mode, "settings": m, "poisson": state.get("poisson"),
                                                              "econ_default_kept": bool(dflt), "uncrop": {k: np.asarray(v).tolist() for k, v in state["uncrop"].items() if k in ("M_crop", "M_square", "box_shape", "square_shape")},
                                                              "back_texture": "없음 — 사진에서 안 보이는 뒤·옆은 회색이에요(ECON 은 뒷면 색을 만들지 않아요)",
                                                              "coords": "LAIS 정사각형 입력 좌표로 옮김: x 오른쪽 · y 위 · z 앞, 범위 [-1, 1]"})
    for name in ("png",):
        src = os.path.join(out_dir, "econ", name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(a.job, "econ", "png_copy"), dirs_exist_ok=True)
    R.progress(1.0, f"꼭짓점 {len(V):,}개 · 면 {len(mesh.F):,}개")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--job", required=True)
    r.add_argument("--gender", required=True)
    r.add_argument("--mode", default="normal")
    r.add_argument("--sapiens", required=True)
    r.add_argument("--loop_smpl", type=int, default=50)
    r.add_argument("--normal_model", default="")
    a = ap.parse_args()
    try:
        cmd_run(a)
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
