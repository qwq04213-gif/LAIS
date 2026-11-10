"""4.9.3 인체 3D — ECON 엔진(가짜 ECON 폴더로 흐름만): 몸 모델 성별 바꿔 끼우기(PIXIE 파일·get_smpl_model), 조각을 지우지 않는 마지막 정리,
뒤·옆 회색(무지개색 아님), Sapiens 공간 전체 받기 막기, 화질 단계 설정, 좌표 옮기기, 단계 알림, 성별 파일 검사(형식이 안 맞으면 멈춤),
ECON 어댑터 점검·메모리 부족 규칙, SMPL-X 폴더 자동 복사, ECON 설치 순서(가짜 명령), ICON 계정이 기록에 남지 않는지, 모델 받기(가짜 서버).
※ 실제 ECON·그래픽카드·PyTorch3D 는 쓰지 않아요(그 부분은 미검증)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import io, json, os, stat, subprocess, sys, tempfile, time, zipfile
from pathlib import Path
import numpy as np
sys.path.insert(0, BASE + "/LocalAI-Studio/hub"); sys.path.insert(0, BASE + "/LocalAI-Studio/engine/human3d")
from human3d import contracts as K, export as X, manager as MG
from worker import runtime as WR
from worker.providers import econ_stages as ES
from worker.providers.econ import EconProvider
ok = lambda m: print("PASS", m)
T = Path(tempfile.mkdtemp())
ENG = Path(BASE) / "LocalAI-Studio/engine/human3d"


def body_npz(path, n_dirs=400, drop=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    d = {"f": np.zeros((20908, 3), np.int64), "v_template": np.zeros((10475, 3), np.float32), "shapedirs": np.zeros((10475, 3, n_dirs), np.float32),
         "posedirs": np.zeros((10475, 3, 486), np.float32), "J_regressor": np.zeros((55, 10475), np.float32), "kintree_table": np.zeros((2, 55), np.int64),
         "weights": np.zeros((10475, 55), np.float32), "lmk_faces_idx": np.zeros(51, np.int64), "lmk_bary_coords": np.zeros((51, 3), np.float32),
         "dynamic_lmk_faces_idx": np.zeros((79, 17), np.int64), "dynamic_lmk_bary_coords": np.zeros((79, 17, 3), np.float32)}
    for k in drop:
        d.pop(k)
    np.savez(path, **d)


# 1) 순수 계산: 성별 파일 검사 · 좌표 옮기기 · 설정 파일
body_npz(T / "ok.npz"); body_npz(T / "short.npz", n_dirs=20); body_npz(T / "nolmk.npz", drop=("lmk_faces_idx", "dynamic_lmk_bary_coords"))
assert ES.check_body(str(T / "ok.npz")) is None and "모자라요" in ES.check_body(str(T / "short.npz")) and "lmk_faces_idx" in ES.check_body(str(T / "nolmk.npz")) and "없어요" in ES.check_body(str(T / "none.npz"))
unc = {"M_square": np.eye(3)[None], "M_crop": np.array([[[0.5, 0, 10], [0, 0.5, 20], [0, 0, 1]]])}          # 정사각형 → 잘린 그림: 반으로 줄이고 (10, 20) 옮김
k = 511 / 2
sq = np.array([[300, 400], [10, 1000]], float); cr = sq * 0.5 + [10, 20]
V = np.stack([cr[:, 0] / k - 1, 1 - cr[:, 1] / k, [0.1, -0.2]], 1)
out = ES.to_square(V, unc, 0, crop=512, square=1024)
exp = np.stack([(sq[:, 0] + 0.5) / 1024 * 2 - 1, 1 - (sq[:, 1] + 0.5) / 1024 * 2, np.array([0.1, -0.2]) * k / 0.5 * 2 / 1024], 1)
assert np.allclose(out, exp, atol=1e-5), (out, exp)
cfg_src = T / "econ.yaml"; cfg_src.write_text("name: econ\nvol_res: 256\nsapiens:\n  use: True\n  seg_model: fg-bg-1b\n  normal_model: 2b\nbni:\n  use_ifnet: False\n  texture_src: image\n  poisson_depth: 10\n", encoding="utf-8")
import yaml
for mode, nm, ifn in (("normal", "2b", False), ("high", "2b", True), ("low", "1b", False)):
    c = ES.write_cfg(str(cfg_src), str(T / f"c_{mode}.yaml"), mode, "/out"); r = yaml.safe_load((T / f"c_{mode}.yaml").read_text(encoding="utf-8"))
    assert r["sapiens"]["normal_model"] == nm and r["bni"]["use_ifnet"] is ifn and r["bni"]["poisson_depth"] == 10 and r["name"] == "econ" and r["vol_res"] == 256, (mode, r)
assert "use_ifnet: False" in cfg_src.read_text(encoding="utf-8")      # 공식 파일은 그대로
ok("pure parts: SMPL-X file check (keys, 10475 verts, 300+exp shape dirs), ECON-crop → LAIS-square coordinates incl. z scale, quality → config without touching the official file")

# 2) 가짜 ECON 폴더로 econ_stages run — 공식 infer 처럼 불러오고 부르는 가짜
E = T / "ECON"; SAP = T / "sapiens"
files = {
 "configs/econ.yaml": cfg_src.read_text(encoding="utf-8"),
 "lib/__init__.py": "", "lib/common/__init__.py": "", "lib/dataset/__init__.py": "", "lib/pixielib/__init__.py": "", "lib/pixielib/utils/__init__.py": "", "apps/__init__.py": "",
 "lib/common/imutils.py": "def process_image(*a, **k):\n    return {'uncrop_param': {'M_square': [[[1,0,0],[0,1,0],[0,0,1]]], 'M_crop': [[[0.5,0,10],[0,0.5,20],[0,0,1]]], 'box_shape': [512,512], 'square_shape': [1024,1024]}}\n",
 "lib/common/render.py": "SEEN = {}\ndef query_color(verts, faces, image, device, paint_normal=True):\n    SEEN['paint_normal'] = paint_normal\n    return [[0.5, 0.5, 0.5]] * len(verts)\n",
 "lib/common/train_util.py": "def init_loss():\n    return {}\n",
 "lib/common/BNI.py": "class BNI:\n    def __init__(self, *a, **k):\n        self.ok = True\n",
 "lib/pixielib/utils/config.py": "class _N: pass\ncfg = _N(); cfg.model = _N(); cfg.model.smplx_model_path = 'data/HPS/pixie_data/SMPLX_NEUTRAL_2020.npz'\n",
 "lib/dataset/mesh_util.py": '''import numpy as np
class _Smplx:
    made = []
    @staticmethod
    def create(**kw):
        _Smplx.made.append(kw["gender"]); return kw["gender"]
smplx = _Smplx
model_init_params = dict(gender="male", model_type="smplx")
def get_smpl_model(model_type, gender):
    return smplx.create(**model_init_params)
class Mesh:
    def __init__(self, v, f, colors=None): self.vertices, self.faces, self.colors = np.asarray(v, float), np.asarray(f, int), colors
    def split(self, only_watertight=False):
        lab = np.zeros(len(self.vertices), int); lab[len(self.vertices) // 2:] = 1
        return [Mesh(self.vertices[lab == c], self.faces[np.all(lab[self.faces] == c, 1)] - (len(self.vertices) // 2) * c) for c in (0, 1)]
    def export(self, path):
        with open(path, "w") as fo:
            for i, v in enumerate(self.vertices):
                c = self.colors[i] if self.colors is not None else None
                fo.write("v %f %f %f" % tuple(v) + (" %f %f %f" % tuple(c) if c is not None else "") + "\\n")
            for f in self.faces: fo.write("f %d %d %d\\n" % tuple(f + 1))
class trimesh:
    @staticmethod
    def Trimesh(v, f, process=False): return Mesh(v, f)
class _PCL:
    def __init__(self, m): self.m = m
class o3d:
    class io:
        @staticmethod
        def read_point_cloud(p): return _PCL(SOUP[0])
    class geometry:
        class TriangleMesh:
            @staticmethod
            def create_from_point_cloud_poisson(pcl, depth=10, n_threads=-1):
                class R: pass
                r = R(); r.vertices, r.triangles = pcl.m.vertices, pcl.m.faces; return r, None
SOUP = []
def poisson(mesh, obj_path, depth=10, face_count=50000, laplacian_remeshing=False):
    biggest = mesh.split()[0]          # ECON 원래: 가장 큰 조각만 + 면 줄이기
    biggest.export(obj_path); return biggest
''',
 "apps/sapiens.py": "from huggingface_hub import snapshot_download\nROOT = snapshot_download(repo_id='facebook/sapiens-normal', repo_type='space')\n",
 "apps/infer.py": '''import argparse, json, os, sys
import numpy as np
import yaml
from lib.dataset.mesh_util import *
from lib.common.render import query_color
from lib.common.train_util import init_loss
from lib.common.BNI import BNI
from lib.common.imutils import process_image
from lib.pixielib.utils.config import cfg as pixie_cfg
import lib.dataset.mesh_util as MUX
from apps.sapiens import ROOT as SAP_ROOT
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("-cfg"); ap.add_argument("-in_dir"); ap.add_argument("-out_dir"); ap.add_argument("-novis", action="store_true"); ap.add_argument("-loop_smpl", type=int)
    a = ap.parse_args(); c = yaml.safe_load(open(a.cfg))
    if os.environ.get("FAKE_ECON_OOM"):
        raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
    data = process_image(); init_loss(); BNI()
    obj = os.path.join(a.out_dir, "econ", "obj"); os.makedirs(obj, exist_ok=True)
    k = 511 / 2; pts = [(300, 400), (310, 400), (300, 410), (700, 900), (710, 900), (700, 910)]
    V = np.array([[(x * 0.5 + 10) / k - 1, 1 - (y * 0.5 + 20) / k, 0.05] for x, y in pts]); F = np.array([[0, 1, 2], [3, 4, 5]])
    full_path = os.path.join(obj, "000_0_full.obj")
    final = poisson(Mesh(V, F), full_path)
    SOUP_m = final
    final.colors = np.array(query_color(final.vertices, final.faces, None, "cuda")); final.export(full_path)
    Mesh(V[:3], F[:1]).export(os.path.join(obj, "000_smpl_00.obj"))
    json.dump({"pixie": pixie_cfg.model.smplx_model_path, "smpl_gender": get_smpl_model("smplx", sys.argv and os.environ.get("G", "female")), "made": MUX.smplx.made,
               "sap_root": SAP_ROOT, "cfg_normal": c["sapiens"]["normal_model"], "ifnet": c["bni"]["use_ifnet"], "novis": a.novis, "in_files": sorted(os.listdir(a.in_dir))},
              open(os.path.join(a.out_dir, "seen.json"), "w"))
'''}
for rel, txt in files.items():
    (E / rel).parent.mkdir(parents=True, exist_ok=True); (E / rel).write_text(txt, encoding="utf-8")
# poisson 바꿔 끼운 쪽이 o3d 로 다시 만들 '수프'를 가짜 o3d 가 돌려주게 — mesh.export 가 불릴 때 담아 둬요
(E / "lib/dataset/mesh_util.py").write_text((E / "lib/dataset/mesh_util.py").read_text(encoding="utf-8").replace("    def export(self, path):\n", "    def export(self, path):\n        SOUP[:] = [self] if path.endswith('_soups.ply') else SOUP\n"), encoding="utf-8")
body_npz(E / "data/HPS/pixie_data/SMPLX_NEUTRAL_2020.npz"); body_npz(E / "data/smpl_related/models/smplx/SMPLX_FEMALE.npz"); body_npz(E / "data/smpl_related/models/smplx/SMPLX_MALE.npz", n_dirs=20)
(SAP / "assets/checkpoints").mkdir(parents=True)
for f in (ES.SAPIENS_FILES["fg-bg-1b"], ES.SAPIENS_FILES["2b"]): (SAP / "assets/checkpoints" / f).write_bytes(b"x")
site = T / "site"; (site / "huggingface_hub").mkdir(parents=True)
(site / "huggingface_hub/__init__.py").write_text("CALLS = []\ndef snapshot_download(*a, **k):\n    CALLS.append(k)\n    raise RuntimeError('공간 전체를 받으면 안 돼요')\n", encoding="utf-8")
from PIL import Image
def job(name):
    jd = T / name; (jd / "images").mkdir(parents=True)
    im = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)); im.paste((200, 50, 50, 255), (300, 200, 700, 900)); im.save(jd / "images/000.png"); return jd
def run(jd, gender="female", mode="normal", extra_env=None, nm=""):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(site), str(ENG), BASE + "/LocalAI-Studio/hub", str(E)]), **(extra_env or {}))
    r = subprocess.run([sys.executable, "-m", "worker.providers.econ_stages", "run", "--job", str(jd), "--gender", gender, "--mode", mode, "--sapiens", str(SAP), "--normal_model", nm],
                       cwd=E, env=env, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr
jd = job("j1"); rc, out = run(jd)
assert rc == 0, out
seen = json.loads((jd / "econ/out/seen.json").read_text())
stages = [l.split(" ", 1)[1].strip() for l in out.splitlines() if l.startswith("@@STAGE ")]
assert [s for i, s in enumerate(stages) if i == 0 or stages[i - 1] != s] == ["keypoints", "smplx_init", "smplx_fit", "geometry", "texture"], stages
assert seen["pixie"].endswith("data/smpl_related/models/smplx/SMPLX_FEMALE.npz") and seen["smpl_gender"] == "female" and seen["made"] == ["female"], seen      # 성별이 실제로 적용(남성 고정 없음)
assert seen["sap_root"] == str(SAP) and seen["cfg_normal"] == "2b" and seen["ifnet"] is False and seen["novis"] and seen["in_files"] == ["000.png"]
reco = X.read_ply(jd / "meshes/000_reco.ply"); dflt = X.read_ply(jd / "meshes/000_econ_default.ply")
assert len(reco.V) == 6 and len(reco.F) == 2 and len(dflt.V) == 3, (len(reco.V), len(dflt.V))      # 조각을 지우지 않음 · ECON 원래 결과(가장 큰 조각)는 비교용으로 따로
assert np.allclose(reco.V[0, :2], [(300 + 0.5) / 1024 * 2 - 1, 1 - (400 + 0.5) / 1024 * 2], atol=1e-4) and (reco.C == 128).all()      # LAIS 좌표로 옮김 · 뒤·옆 회색
gj = json.loads((jd / "smplx/gender.json").read_text(encoding="utf-8")); rj = json.loads((jd / "meshes/recon.json").read_text(encoding="utf-8"))
assert gj["applied"] and gj["gender"] == "female" and gj["model_file"] == "SMPLX_FEMALE.npz" and gj["engine"] == "econ" and rj["poisson"]["components"] == 2 and rj["econ_default_kept"] and "회색" in rj["back_texture"]
sm = X.read_obj(jd / "smplx/000_smplx.obj"); assert len(sm.V) == 3 and np.allclose(sm.V[0, :2], reco.V[0, :2], atol=1e-4)
qin = np.asarray(Image.open(jd / "econ/in/000.png")); assert qin.shape == (1024, 1024, 3) and tuple(qin[5, 5]) == (128, 128, 128) and tuple(qin[500, 500]) == (200, 50, 50)
jd = job("j2"); rc, out = run(jd, gender="neutral", mode="high"); seen = json.loads((jd / "econ/out/seen.json").read_text())
assert rc == 0 and seen["pixie"].endswith("SMPLX_NEUTRAL_2020.npz") and seen["ifnet"] is True and json.loads((jd / "smplx/gender.json").read_text(encoding="utf-8"))["model_file"] == "SMPLX_NEUTRAL_2020.npz"
jd = job("j3"); rc, out = run(jd, gender="male")
assert rc != 0 and "@@ERROR no_smplx" in out and "남성" in out and "모자라요" in out and "바꿔 쓰지 않아요" in out and not (jd / "meshes").exists() and not (jd / "econ/out").exists(), out      # 형식이 안 맞는 남성 파일 → 중립으로 대신하지 않고 멈춤
jd = job("j4"); rc, out = run(jd, mode="low"); assert rc != 0 and "@@ERROR no_model" in out and "sapiens_1b_normal" in out      # 저메모리에 필요한 Sapiens 1B 가 없으면 멈춤
(SAP / "assets/checkpoints" / ES.SAPIENS_FILES["1b"]).write_bytes(b"x"); rc, out = run(jd, mode="low"); assert rc == 0 and json.loads((jd / "econ/out/seen.json").read_text())["cfg_normal"] == "1b"
jd = job("j5"); rc, out = run(jd, mode="low", nm="0.3b"); assert rc != 0 and "0.3b" in out
jd = job("j6"); rc, out = run(jd, extra_env={"FAKE_ECON_OOM": "1"}); assert rc != 0 and "@@ERROR oom" in out
ok("ECON run with a fake ECON tree: chosen SMPL-X really applied (PIXIE path + get_smpl_model), no keep-largest (ECON default kept for comparison), grey back, no full Sapiens space download, quality config, coordinates, stage order, refusals, OOM code")

# 3) ECON 어댑터: 점검 · SMPL-X 자동 복사 · 메모리 부족 규칙 · 없는 성별
home = T / "home"; os.environ["HUMAN3D_ECON_DIR"] = str(E); os.environ["HUMAN3D_ECON_PY"] = str(T / "nopy")
drop = T / "drop"; drop.mkdir(); body_npz(drop / "SMPLX_MALE.npz"); os.environ["HUMAN3D_DROP"] = str(drop)
ep = EconProvider({"home": str(home), "python": sys.executable})
f = ep.files(); assert f["genders"] == {"neutral": True, "female": True, "male": True} and ES.check_body(str(E / "data/smpl_related/models/smplx/SMPLX_MALE.npz")) is None      # LAIS 폴더의 남성 파일을 가져옴(크기가 달라서 바꿈)
assert not f["venv"] and not f["sapiens"]["2b"]
pf = ep.preflight(); c = {x["id"]: x for x in pf["checks"]}
assert not pf["ready"] and not c["econ_code"]["ok"] and "SiTH 기본 설치" in c["econ_code"]["fix"] and c["license"]["info"] and "비상업" in c["license"]["text"] and "12GB 초과" in c["econ_vram"]["text"] and pf["modes"] == ["normal", "high", "low"]
class J:
    def __init__(self, q, s=None): self.opts = {"quality": q, "sapiens": s}
assert ep.on_oom(J("normal", "2b"), "keypoints") is None and ep.on_oom(J("high", "2b"), "keypoints") is None and any("저메모리" in x for x in ep.oom_advice(J("normal")))
ep.sapiens = str(SAP); (SAP / "assets/checkpoints" / ES.SAPIENS_FILES["0.3b"]).write_bytes(b"x")
jl = J("low", "1b"); assert "0.3B" in ep.on_oom(jl, "keypoints") and jl.opts["sapiens"] == "0.3b" and ep.on_oom(jl, "keypoints") is None and any("SiTH" in x for x in ep.oom_advice(jl))
g, why = ep.gender_of(type("J", (), {"opts": {"gender": "auto"}})()); assert g == "neutral" and "ECON 기본" in why
WR.sync_smplx(str(T / "sith_dst")); assert (T / "sith_dst/SMPLX_MALE.npz").is_file() and not (T / "sith_dst/SMPLX_FEMALE.npz").exists()
src = (ENG / "worker/providers/sith.py").read_text(encoding="utf-8"); assert 'R.sync_smplx(os.path.join(s, "data", "body_models", "smplx"))' in src
ok("ECON adapter: preflight (licence notice, needs SiTH base, 12GB note, modes), SMPL-X auto-copied from the LAIS folder, normal/high never lower quality, low 1B→0.3B once, auto = ECON neutral")

# 4) ECON 설치 스크립트(가짜 명령): SiTH 기본 설치가 먼저, 순서, rembg 는 --no-deps, 검사 실패면 '완료' 아님
SH = ENG / "scripts/install_econ.sh"
def run_econ_install(envsh=True, check="ok", steps=None):
    h = Path(tempfile.mkdtemp()); stub = h / "stub"; stub.mkdir(); log = h / "calls.log"; home2 = h / "home"; home2.mkdir()
    cuda = h / "cuda"; (cuda / "bin").mkdir(parents=True); nv = cuda / "bin/nvcc"; nv.write_text('#!/bin/sh\necho "Cuda compilation tools, release 12.1, V12.1.105"\n'); nv.chmod(0o755)
    if envsh: (home2 / "env.sh").write_text(f'export PATH="{cuda}/bin:$PATH"\n')
    (home2 / "ECON/lib/common/libmesh").mkdir(parents=True); (home2 / "ECON/lib/common/libvoxelize").mkdir(parents=True); (home2 / "ECON/.git").mkdir()
    def mk(name, body):
        x = stub / name; x.write_text("#!/usr/bin/env bash\n" + body); x.chmod(x.stat().st_mode | stat.S_IEXEC)
    mk("pip", f'echo "pip $*" >> {log}\nexit 0\n')
    mk("python", f'echo "python $*" >> {log}\ncase "$*" in *worker.envcheck*) if [ "{check}" = ok ]; then echo "[ 됨 ] PyTorch3D 그래픽카드 그리기"; echo \'@@ENVCHECK {{"ok": true}}\'; exit 0; else echo "[안 됨] PyTorch3D"; '
       f'echo \'@@ENVCHECK {{"ok": false, "text": "PyTorch3D 가 그래픽카드에서 그리지 못해요"}}\'; exit 2; fi ;; *pytorch3d._C*|*"import rembg"*|*"import chumpy"*|*"torch.__version__"*) exit 1 ;; *json.loads*) exec python3 "$@" ;; esac\nexit 0\n')
    for n in ("git", "dpkg", "apt-get", "sudo", "nvidia-smi"): mk(n, f'echo "{n} $*" >> {log}\n' + ('echo 8.9\n' if n == "nvidia-smi" else "") + "exit 0\n")
    env = dict(os.environ, HUMAN3D_HOME=str(home2), HUMAN3D_TEST_BIN=str(stub), PATH=str(stub) + os.pathsep + os.environ["PATH"], HUMAN3D_INSTALL_STEPS=steps or "torch parts pytorch3d build rembg check")
    r = subprocess.run(["bash", str(SH)], capture_output=True, text=True, env=env, timeout=60)
    return r.returncode, r.stdout + r.stderr, (log.read_text() if log.exists() else "")
rc, out, calls = run_econ_install(envsh=False); assert rc == 1 and "SiTH" in out and "@@DONE" not in out and "pytorch3d" not in calls
rc, out, calls = run_econ_install(); assert rc == 0 and "@@DONE" in out, out
assert calls.index("torch==2.1.0") < calls.index("pins_econ_req.txt") < calls.index("facebookresearch/pytorch3d.git@v0.7.5") < calls.index("build_ext") < calls.index("YuliangXiu/rembg") < calls.index("worker.envcheck --set econ"), calls
assert "--no-build-isolation" in [l for l in calls.splitlines() if l.startswith("pip") and "pytorch3d.git" in l][0] and "--no-deps" in [l for l in calls.splitlines() if l.startswith("pip") and "rembg" in l][0]
assert "TORCH_CUDA_ARCH_LIST" in SH.read_text(encoding="utf-8") and "compute_cap" in SH.read_text(encoding="utf-8")
rc, out, calls = run_econ_install(check="fail"); assert rc == 1 and "@@DONE" not in out and "검사에 실패" in out and "그리지 못해요" in out
pins = (ENG / "scripts/pins_econ.txt").read_text(encoding="utf-8"); assert "numpy==1.23.5" in pins and "cupy-cuda12x==" in pins and "pytorch-lightning==1.9.5" in pins and "\ntorch==" not in pins
ok("ECON installer (stubbed): needs the SiTH base (CUDA env), torch → pinned parts → PyTorch3D (no build isolation, GPU arch) → libmesh/libvoxelize → rembg --no-deps → GPU check; failed check is not 'done'")

# 5) 모델 받기: ICON 로그인 실패를 알아채고, 풀어서 공식 자리로 · SMPL-X 는 SiTH 에도
sys.path.insert(0, str(ENG / "scripts")); import econ_fetch as EF
class Resp(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): return False
sent = []
def opener_html(req, timeout=0): sent.append(req.data); return Resp(b"<html><body>Login - Please enter username and password</body></html>")
d = T / "dl"; err = EF.fetch("smplx", "models_smplx_v1_1.zip", str(d / "a.zip"), "me@x.com", "p@ss w0rd", opener=opener_html)
assert err and "아이디·비밀번호" in err and "Register" in err and not (d / "a.zip").exists() and not (d / "a.zip.part").exists() and b"p%40ss+w0rd" in sent[0]
zb = io.BytesIO(); zf = zipfile.ZipFile(zb, "w")
for g in ("NEUTRAL", "FEMALE", "MALE"): zf.writestr(f"models/smplx/SMPLX_{g}.npz", b"npz-" + g.encode())
zf.close()
assert EF.fetch("smplx", "models_smplx_v1_1.zip", str(d / "models_smplx_v1_1.zip"), "u", "p", opener=lambda req, timeout=0: Resp(zb.getvalue())) is None
E2 = T / "E2"; (E2 / "data/smpl_related/models").mkdir(parents=True); os.replace(d / "models_smplx_v1_1.zip", E2 / "data/smpl_related/models/models_smplx_v1_1.zip")
copied = EF.unpack(str(E2), str(T / "sith_smplx"))
assert (E2 / "data/smpl_related/models/smplx/SMPLX_FEMALE.npz").is_file() and not (E2 / "data/smpl_related/models/models_smplx_v1_1.zip").exists() and sorted(copied) == ["SMPLX_FEMALE.npz", "SMPLX_MALE.npz", "SMPLX_NEUTRAL.npz"]
r = subprocess.run([sys.executable, str(ENG / "scripts/econ_fetch.py"), "--econ", str(E2), "--sapiens", str(T / "s2")], input="\n", capture_output=True, text=True, timeout=30)
assert r.returncode == 1 and "@@FAIL" in r.stdout and "ICON" in r.stdout
src = (ENG / "scripts/econ_fetch.py").read_text(encoding="utf-8"); assert "sys.stdin.readline()" in src and "allow_patterns" in src and "print(user" not in src and "print(pw" not in src
ok("model fetch: ICON login page detected (no half file left), credentials only form-encoded in the POST body, official unzip layout, SMPL-X also copied for SiTH, missing login stops")

# 6) 설치 관리: ECON 은 SiTH 기본 설치 + ICON 계정이 있어야 시작, 계정은 표준 입력으로만(기록·명령줄에 안 남음)
inst = T / "fake_installer.py"
inst.write_text('''import sys, os
name = os.path.basename(sys.argv[-1])
if name.endswith(".py"):
    line = sys.stdin.readline(); import json; d = json.loads(line)
    print("@@STEP 1/1 받는 중"); print("got user len", len(d["user"]), "pass len", len(d["pass"]))
    open(os.environ["FAKE_ARGS"], "a").write(" ".join(sys.argv) + "\\n")
else:
    print("@@STEP 1/1 " + name)
print("@@DONE")
''', encoding="utf-8")
os.environ.update(HUMAN3D_WORKER_CMD="x", HUMAN3D_INSTALL_CMD=f"{sys.executable} {inst}", FAKE_ARGS=str(T / "args.txt"))
logs = []
os.environ["HUMAN3D_FAKE_ECON_INSTALLED"] = "0"
assert MG.installed(T, "econ") is False and MG.installed(T, "sith") is True
assert "ICON" in MG.install(T, engine="econ", creds=None)["error"] and "ICON" in MG.install(T, engine="econ", creds={"user": "a", "pass": ""})["error"]
SECRET = "Pw-비밀-9876"
r = MG.install(T, log=lambda *a: logs.append(" ".join(map(str, a))), engine="econ", creds={"user": "me@x.com", "pass": SECRET}); assert r == {"ok": True}, r
for _ in range(100):
    time.sleep(0.1)
    if MG.STATE["install"]["state"] != "running": break
I = MG.install_view(); assert I["state"] == "done" and I["engine"] == "econ", I
blob = json.dumps(MG.STATE, default=str, ensure_ascii=False) + " ".join(logs) + (T / "args.txt").read_text(encoding="utf-8")
assert SECRET not in blob and "me@x.com" not in blob and "got user len 8 pass len 10" in " ".join(MG.STATE["install"]["log"]), blob[:500]
assert [n for n, _, _ in MG._steps(T, "econ")] == ["install_econ.sh", "econ_fetch.py"] and [n for n, _, _ in MG._steps(T, "sith")] == ["install_wsl.sh", "install_models.sh"]
os.environ.pop("HUMAN3D_INSTALL_CMD"); cmd = MG._steps(T, "econ")[1][2]; assert "econ-venv/bin/python" in " ".join(cmd) and "--smplx-copy" in " ".join(cmd) and SECRET not in " ".join(cmd)
assert str(MG.drop_dir(T)).endswith(os.path.join("models", "human3d", "smplx"))
ok("install manager: ECON needs the SiTH base and an ICON login; the login goes only to the fetch program's stdin — never logged, stored or put on a command line")
print("ALL OK")
