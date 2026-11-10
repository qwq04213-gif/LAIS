#!/usr/bin/env bash
# 인체 3D(SiTH) 전용 환경 설치 — WSL2 Ubuntu 22.04 안에서 돌아요. LAIS 가 대신 실행해요(직접 칠 필요 없음).
#   · ComfyUI 의 파이썬은 건드리지 않아요. 여기(~/lais-human3d)에 따로 파이썬 환경을 만들어요.
#   · 여러 번 돌려도 돼요(이미 된 단계는 건너뛰어요).
#   · 진행은 "@@STEP <번호>/<전체> <글>" 줄로 알려요.
# ★ 실제 PC(WSL2 + NVIDIA)에서 끝까지 돌려 확인하지 못한 스크립트예요(미검증).
set -u
HOME_DIR="${HUMAN3D_HOME:-$HOME/lais-human3d}"
SITH_COMMIT="6401549"
TOTAL=8
step() { echo "@@STEP $1/$TOTAL $2"; }
die() { echo "@@FAIL $1"; exit 1; }
export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1
mkdir -p "$HOME_DIR" || die "설치 폴더를 만들지 못했어요: $HOME_DIR"
cd "$HOME_DIR"

step 1 "그래픽카드 확인"
if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi >/dev/null 2>&1; then
  die "WSL 안에서 그래픽카드가 보이지 않아요. 윈도우의 NVIDIA 드라이버를 최신으로 올리고 'wsl --update' 뒤 다시 해 주세요."
fi
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

step 2 "기본 도구 설치 (관리자 권한이 필요해요)"
NEED=""
for p in git wget python3.10-venv python3.10-dev build-essential ninja-build libgl1 libglib2.0-0 libegl1; do
  dpkg -s "$p" >/dev/null 2>&1 || NEED="$NEED $p"
done
if [ -n "$NEED" ]; then
  SUDO="sudo -n"; [ "$(id -u)" = "0" ] && SUDO=""
  $SUDO apt-get update -y >/dev/null 2>&1 && $SUDO apt-get install -y $NEED || die "기본 도구를 설치하지 못했어요:$NEED — LAIS 는 WSL 을 root 로 실행해 설치해요. 직접 돌린다면 'sudo bash install_wsl.sh' 로 해 주세요."
fi
command -v python3.10 >/dev/null 2>&1 || die "Ubuntu 22.04 의 python3.10 이 없어요. Ubuntu 22.04 배포판인지 확인해 주세요."

step 3 "SiTH 코드 받기"
if [ ! -d SiTH/.git ]; then
  git clone https://github.com/SiTH-Diffusion/SiTH SiTH || die "SiTH 코드를 받지 못했어요(인터넷 연결 확인)."
fi
( cd SiTH && git fetch -q origin 2>/dev/null; git checkout -q "$SITH_COMMIT" 2>/dev/null || echo "알림: 정해 둔 판($SITH_COMMIT)으로 맞추지 못해 받은 판을 그대로 써요." )

step 4 "파이썬 환경 만들기"
[ -x venv/bin/python ] || python3.10 -m venv venv || die "파이썬 환경을 만들지 못했어요."
. venv/bin/activate
python -m pip install -q --upgrade "pip<25" wheel "setuptools<70" || die "pip 준비 실패"

step 5 "PyTorch 2.1 (CUDA 12.1) 설치 — 약 2.5GB"
python -c "import torch,sys; sys.exit(0 if torch.__version__.startswith('2.1.0') else 1)" 2>/dev/null \
  || pip install -q torch==2.1.0 torchvision==0.16.0 --extra-index-url https://download.pytorch.org/whl/cu121 || die "PyTorch 설치 실패"
python -c "import torch; assert torch.cuda.is_available(), 'CUDA 를 쓸 수 없어요'; print('torch', torch.__version__, torch.cuda.get_device_name(0))" || die "PyTorch 가 그래픽카드를 쓰지 못해요."

step 6 "SiTH 부품 설치 (kaolin · diffusers 등) — 몇 분 걸려요"
python -c "import kaolin" 2>/dev/null || pip install -q kaolin==0.15.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.1.0_cu121.html || die "kaolin 설치 실패"
pip install -q numpy==1.24.1 huggingface-hub==0.22.2 diffusers==0.24.0 accelerate transformers==4.39.3 h5py trimesh matplotlib opencv-python smplx timm einops ninja pyyaml tqdm scikit-image pillow || die "SiTH 부품 설치 실패"
python -c "import tinyobjloader" 2>/dev/null || pip install -q "git+https://github.com/tinyobjloader/tinyobjloader.git@v2.0.0rc8#subdirectory=python" || die "tinyobjloader 설치 실패"

step 7 "nvdiffrast 설치 (CUDA 컴파일 도구가 필요해요)"
if ! python -c "import nvdiffrast" 2>/dev/null; then
  pip install -q "git+https://github.com/NVlabs/nvdiffrast.git" || die "nvdiffrast 설치 실패"
fi
# nvdiffrast 는 처음 쓸 때 CUDA 코드를 컴파일해요 → CUDA 12.1 컴파일러(nvcc)가 필요해요(드라이버만으로는 안 돼요).
if ! command -v nvcc >/dev/null 2>&1 && [ ! -x /usr/local/cuda/bin/nvcc ]; then
  pip install -q nvidia-cuda-nvcc-cu12==12.1.105 nvidia-cuda-runtime-cu12==12.1.105 2>/dev/null \
    || echo "알림: CUDA 컴파일러를 자동으로 넣지 못했어요. 형태 복원에서 'nvcc' 오류가 나면 CUDA Toolkit 12.1 을 WSL 에 설치해야 해요(진단 화면에 안내가 나와요)."
fi

step 8 "자세 검출기 설치 (rtmlib)"
python -c "import rtmlib" 2>/dev/null || pip install -q rtmlib onnxruntime || die "자세 검출기 설치 실패"
pip install -q onnxruntime-gpu 2>/dev/null || true      # 되면 그래픽카드로, 안 되면 CPU 로 돌아요

echo "@@DONE 환경 설치가 끝났어요. 이어서 모델을 받아요."
