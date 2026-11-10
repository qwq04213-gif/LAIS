#!/usr/bin/env bash
# 인체 3D(SiTH) 전용 환경 설치 — WSL2 Ubuntu 22.04 안에서 돌아요. LAIS 가 대신 실행해요(직접 칠 필요 없음).
#   · ComfyUI 의 파이썬은 건드리지 않아요. 여기(~/lais-human3d)에 따로 파이썬 환경을 만들어요.
#   · 여러 번 돌려도 돼요(이미 된 단계는 건너뛰어요).
#   · 진행은 "@@STEP <번호>/<전체> <글>" 줄로, 실패는 "@@FAIL <까닭과 해결 방법>" 으로 알려요. 끝까지 되면 "@@DONE".
#   · 순서가 중요해요: PyTorch → CUDA 12.1 컴파일러(nvcc) → nvdiffrast(컴파일) → 실제 그리기 검사.
#     nvdiffrast 0.4 는 설치할 때 CUDA 코드를 컴파일해요. 그래서 컴파일러가 먼저 있어야 하고, 지금 환경의 PyTorch 로 빌드하도록
#     공식 안내대로 --no-build-isolation 을 붙여요(https://github.com/NVlabs/nvdiffrast).
# ★ 실제 PC(WSL2 + NVIDIA)에서 끝까지 돌려 확인하지 못한 스크립트예요(미검증).
set -u
HOME_DIR="${HUMAN3D_HOME:-$HOME/lais-human3d}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(dirname "$HERE")"                      # engine/human3d (worker 꾸러미가 있는 곳)
SITH_COMMIT="6401549"
CUDA_VER="12.1"
CUDA_PKG="12-1"
STEPS="${HUMAN3D_INSTALL_STEPS:-gpu base sith venv torch cuda parts nvdiffrast pose check}"      # 시험에서는 일부 단계만 돌려요
TOTAL=$(echo $STEPS | wc -w)
N=0
step() { N=$((N + 1)); echo "@@STEP $N/$TOTAL $1"; }
die() { echo "@@FAIL $1"; exit 1; }
want() { case " $STEPS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1
SUDO="sudo -n"; [ "$(id -u)" = "0" ] && SUDO=""
mkdir -p "$HOME_DIR" || die "설치 폴더를 만들지 못했어요: $HOME_DIR"
cd "$HOME_DIR"
# 부품 판 고정: 이 뒤의 모든 pip 설치가 pins.txt 의 판을 넘지 못하게 해요(numpy 2 용 부품이 섞이면 kaolin 등을 못 불러와요).
# 설치 폴더 경로에 빈칸이 있을 수 있어서(PIP_CONSTRAINT 는 빈칸으로 나눠 읽어요) 빈칸 없는 곳에 복사해 써요.
PINS="$HOME_DIR/pins.txt"
if [ -f "$HERE/pins.txt" ]; then cp "$HERE/pins.txt" "$PINS" && export PIP_CONSTRAINT="$PINS"; fi

if want gpu; then
  step "그래픽카드 확인"
  if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi >/dev/null 2>&1; then
    die "WSL 안에서 그래픽카드가 보이지 않아요. 윈도우의 NVIDIA 드라이버를 최신으로 올리고 PowerShell 에서 'wsl --update' 를 한 뒤 다시 해 주세요."
  fi
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
fi

if want base; then
  step "기본 도구 설치 (관리자 권한이 필요해요)"
  NEED=""
  for p in git wget ca-certificates python3.10-venv python3.10-dev build-essential ninja-build libgl1 libglib2.0-0 libegl1; do
    dpkg -s "$p" >/dev/null 2>&1 || NEED="$NEED $p"
  done
  if [ -n "$NEED" ]; then
    $SUDO apt-get update -y >/dev/null 2>&1 && $SUDO apt-get install -y $NEED || die "기본 도구를 설치하지 못했어요:$NEED — LAIS 는 WSL 을 root 로 실행해 설치해요. 직접 돌린다면 'sudo bash install_wsl.sh' 로 해 주세요."
  fi
  command -v python3.10 >/dev/null 2>&1 || die "Ubuntu 22.04 의 python3.10 이 없어요. Ubuntu 22.04 배포판인지 확인해 주세요."
  command -v g++ >/dev/null 2>&1 || die "C++ 컴파일러(g++)가 없어요. 'sudo apt-get install -y build-essential' 뒤 다시 해 주세요."
fi

if want sith; then
  step "SiTH 코드 받기"
  if [ ! -d SiTH/.git ]; then
    git clone https://github.com/SiTH-Diffusion/SiTH SiTH || die "SiTH 코드를 받지 못했어요(인터넷 연결 확인)."
  fi
  ( cd SiTH && git fetch -q origin 2>/dev/null; git checkout -q "$SITH_COMMIT" 2>/dev/null || echo "알림: 정해 둔 판($SITH_COMMIT)으로 맞추지 못해 받은 판을 그대로 써요." )
fi

if want venv; then
  step "파이썬 환경 만들기"
  [ -x venv/bin/python ] || python3.10 -m venv venv || die "파이썬 환경을 만들지 못했어요."
fi
if [ -f venv/bin/activate ]; then . venv/bin/activate; fi
[ -n "${HUMAN3D_TEST_BIN:-}" ] && export PATH="$HUMAN3D_TEST_BIN:$PATH"      # 시험용 가짜 명령
if want venv; then
  python -m pip install -q --upgrade "pip<25" wheel "setuptools>=64,<70" ninja || die "pip·setuptools·wheel·ninja 준비 실패"
fi

if want torch; then
  step "PyTorch 2.1 (CUDA $CUDA_VER) 설치 — 약 2.5GB"
  python -c "import torch,sys; sys.exit(0 if torch.__version__.startswith('2.1.0') else 1)" 2>/dev/null \
    || pip install -q torch==2.1.0 torchvision==0.16.0 --extra-index-url https://download.pytorch.org/whl/cu121 || die "PyTorch 설치 실패(인터넷 연결·디스크 공간 확인)"
  python -c "import torch; assert torch.cuda.is_available(), 'CUDA 를 쓸 수 없어요'; print('torch', torch.__version__, torch.cuda.get_device_name(0))" \
    || die "PyTorch 가 그래픽카드를 쓰지 못해요. 윈도우의 NVIDIA 드라이버를 최신으로 올리고 'wsl --shutdown' 뒤 다시 해 주세요."
fi

# ── CUDA 12.1 컴파일러(nvcc) — nvdiffrast 를 컴파일하려면 꼭 있어야 해요(그래픽카드 드라이버만으로는 안 돼요) ──
nvcc_ok() {          # $1 = CUDA 폴더. 그 안의 nvcc 가 실제로 돌고 12.1 판인지
  [ -n "$1" ] && [ -x "$1/bin/nvcc" ] && "$1/bin/nvcc" --version 2>/dev/null | grep -q "release $CUDA_VER"
}
find_cuda() {        # 쓸 수 있는 CUDA 12.1 폴더를 찾아 CUDA_HOME 에 넣어요
  for d in "${CUDA_HOME:-}" "/usr/local/cuda-$CUDA_VER" "/usr/local/cuda" "$HOME_DIR/cuda"; do
    if nvcc_ok "$d"; then CUDA_HOME="$d"; return 0; fi
  done
  return 1
}
cuda_from_apt() {    # NVIDIA 공식 저장소(WSL 용)에서 컴파일러와 머리 파일만 받아요(전체 툴킷보다 훨씬 작아요)
  local extra="${1:-}"
  wget -q "https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb" -O /tmp/cuda-keyring.deb \
    && $SUDO dpkg -i /tmp/cuda-keyring.deb >/dev/null \
    && $SUDO apt-get update -y >/dev/null 2>&1 \
    && $SUDO apt-get install -y "cuda-compiler-$CUDA_PKG" "cuda-cudart-dev-$CUDA_PKG" "cuda-driver-dev-$CUDA_PKG" $extra
}
cuda_from_pip() {    # 관리자 권한이 없을 때: 파이썬 꾸러미로 받은 컴파일러를 CUDA 폴더 모양으로 엮어요
  pip install -q "nvidia-cuda-nvcc-cu12==12.1.105" "nvidia-cuda-runtime-cu12==12.1.105" || return 1
  local sp; sp="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" || return 1
  [ -x "$sp/nvidia/cuda_nvcc/bin/nvcc" ] || return 1
  mkdir -p "$HOME_DIR/cuda/include" "$HOME_DIR/cuda/lib64"
  ln -sfn "$sp/nvidia/cuda_nvcc/bin" "$HOME_DIR/cuda/bin"
  ln -sfn "$sp/nvidia/cuda_nvcc/nvvm" "$HOME_DIR/cuda/nvvm"
  for f in "$sp"/nvidia/cuda_runtime/include/* "$sp"/nvidia/cuda_nvcc/include/*; do [ -e "$f" ] && ln -sfn "$f" "$HOME_DIR/cuda/include/"; done
  for f in "$sp"/nvidia/cuda_runtime/lib/*; do [ -e "$f" ] && ln -sfn "$f" "$HOME_DIR/cuda/lib64/"; done
  [ -e "$HOME_DIR/cuda/lib64/libcudart.so" ] || ln -sfn "$HOME_DIR/cuda/lib64/libcudart.so.12" "$HOME_DIR/cuda/lib64/libcudart.so"
}
use_cuda() {         # CUDA_HOME 을 이번 설치와 나중의 worker 실행 양쪽에 알려요
  export CUDA_HOME CUDA_PATH="$CUDA_HOME" PATH="$CUDA_HOME/bin:$PATH" LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}" CXX="${CXX:-g++}"
  { echo "# 인체 3D worker 가 읽는 환경(설치 스크립트가 만들어요)"; echo "export CUDA_HOME=\"$CUDA_HOME\""; echo "export CUDA_PATH=\"$CUDA_HOME\"";
    echo "export PATH=\"$CUDA_HOME/bin:\$PATH\""; echo "export LD_LIBRARY_PATH=\"$CUDA_HOME/lib64:\${LD_LIBRARY_PATH:-}\""; } > "$HOME_DIR/env.sh"
}
CUDA_FAIL="CUDA $CUDA_VER 컴파일러(nvcc)를 준비하지 못해서 여기서 멈췄어요(nvdiffrast 를 컴파일할 수 없어요). 해결: ① 인터넷 연결을 확인하고 [설치 시작]을 다시 눌러 보세요. ② 그래도 안 되면 PowerShell 에서 'wsl -d Ubuntu-22.04 -u root' 로 들어가 'apt-get update && apt-get install -y wget' 뒤, https://developer.nvidia.com/cuda-12-1-0-download-archive 에서 Linux → x86_64 → WSL-Ubuntu → 2.0 → deb (network) 의 명령을 그대로 실행하고(마지막 줄은 'apt-get install -y cuda-toolkit-12-1'), [설치 시작]을 다시 눌러 주세요."

if want cuda; then
  step "CUDA $CUDA_VER 컴파일러 준비 (nvdiffrast 를 컴파일하는 데 필요해요)"
  if ! find_cuda; then
    echo "CUDA $CUDA_VER 컴파일러가 없어서 받아요(NVIDIA 공식 저장소)."
    cuda_from_apt || echo "알림: NVIDIA 저장소에서 받지 못했어요. 파이썬 꾸러미로 시도해요."
    if ! find_cuda; then cuda_from_pip || true; fi
    find_cuda || die "$CUDA_FAIL"
  fi
  use_cuda
  command -v nvcc >/dev/null 2>&1 || die "$CUDA_FAIL"
  nvcc --version | grep -q "release $CUDA_VER" || die "$CUDA_FAIL"
  [ -f "$CUDA_HOME/include/cuda_runtime.h" ] || echo "알림: $CUDA_HOME/include 에 cuda_runtime.h 가 안 보여요. 컴파일이 실패하면 머리 파일 꾸러미를 더 받아요."
  echo "nvcc: $(command -v nvcc) · $(nvcc --version | grep release) · CUDA_HOME=$CUDA_HOME"
else
  find_cuda && use_cuda
fi

if want parts; then
  step "SiTH 부품 설치 (kaolin · diffusers 등) — 몇 분 걸려요"
  # 먼저 숫자 계산 부품을 고정한 판으로 맞춰요(이미 다른 판이 깔려 있으면 이 판으로 바꿔요 — 예전 설치가 남긴 섞인 판을 바로잡아요)
  [ -f "$PINS" ] && { pip install -q -r "$PINS" || die "부품(numpy·scipy 등)을 고정한 판으로 설치하지 못했어요(인터넷 연결 확인)."; }
  pip show kaolin >/dev/null 2>&1 || pip install -q kaolin==0.15.0 -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.1.0_cu121.html || die "kaolin 설치 실패"
  pip install -q numpy==1.24.1 huggingface-hub==0.22.2 diffusers==0.24.0 accelerate transformers==4.39.3 h5py trimesh matplotlib opencv-python smplx timm einops ninja pyyaml tqdm scikit-image pillow scipy || die "SiTH 부품 설치 실패"
  python -c "import tinyobjloader" 2>/dev/null || pip install -q "git+https://github.com/tinyobjloader/tinyobjloader.git@v2.0.0rc8#subdirectory=python" || die "tinyobjloader 설치 실패"
fi

nv_check() {         # 실제로 그래픽카드에서 삼각형을 그려 봐요(불러오기만으로는 통과시키지 않아요)
  PYTHONPATH="$ENGINE_DIR${PYTHONPATH:+:$PYTHONPATH}" python -m worker.nvcheck
}
nv_build() {
  pip install -q --force-reinstall --no-deps "git+https://github.com/NVlabs/nvdiffrast.git" --no-build-isolation
}
if want nvdiffrast; then
  step "nvdiffrast 설치 (CUDA 코드 컴파일) 와 실제 그리기 검사"
  # 컴파일러가 준비되지 않았으면 nvdiffrast 설치를 시작하지 않아요
  { [ -n "${CUDA_HOME:-}" ] && command -v nvcc >/dev/null 2>&1 && nvcc --version 2>/dev/null | grep -q "release $CUDA_VER"; } || die "$CUDA_FAIL"
  python -c "import torch" 2>/dev/null || die "PyTorch 가 없어서 nvdiffrast 를 만들 수 없어요. [설치 시작]을 다시 눌러 주세요."
  python -c "import setuptools, wheel, ninja" 2>/dev/null || pip install -q "setuptools>=64,<70" wheel ninja || die "setuptools·wheel·ninja 를 설치하지 못했어요."
  python -c "import setuptools, wheel, ninja" 2>/dev/null || die "setuptools·wheel·ninja 가 파이썬 환경에 없어요."
  if nv_check >/dev/null 2>&1; then
    echo "nvdiffrast 가 이미 정상이에요."
  else
    if ! nv_build; then
      echo "알림: nvdiffrast 컴파일이 실패했어요. CUDA 머리 파일을 더 받고 한 번 더 해 봐요."
      cuda_from_apt "cuda-libraries-dev-$CUDA_PKG" >/dev/null 2>&1 || true
      nv_build || die "nvdiffrast 를 컴파일하지 못했어요. 위쪽의 오류 줄(nvcc·g++·없는 머리 파일 이름)을 확인해 주세요. 해결: PowerShell 에서 'wsl -d Ubuntu-22.04 -u root' 로 들어가 'apt-get install -y cuda-toolkit-$CUDA_PKG' 를 실행한 뒤 [설치 시작]을 다시 눌러 주세요."
    fi
  fi
  NV_OUT="$(nv_check 2>&1)"; NV_RC=$?
  echo "$NV_OUT" | tail -3
  if [ $NV_RC -ne 0 ]; then
    NV_TEXT="$(echo "$NV_OUT" | grep '^@@NVCHECK ' | tail -1 | python -c 'import sys,json; d=json.loads(sys.stdin.read()[10:] or "{}"); print((d.get("text") or "") + " " + (d.get("fix") or ""))' 2>/dev/null)"
    die "nvdiffrast 를 설치했지만 그래픽카드에서 실제로 그리는 검사에 실패해서 설치를 끝내지 않았어요. ${NV_TEXT:-자세한 내용은 위의 줄을 확인해 주세요.}"
  fi
fi

if want pose; then
  step "자세 검출기 설치 (rtmlib)"
  pip show rtmlib >/dev/null 2>&1 || pip install -q rtmlib onnxruntime || die "자세 검출기 설치 실패"
  # 자세 검출은 CPU 로 돌려요(몇 초). 그래픽카드용 onnxruntime 은 numpy·CUDA 판을 흔들 수 있어서 넣지 않아요.
fi

env_check() {        # 부품을 전부 실제로 불러와 봐요(깔려 있다는 것만으로는 통과시키지 않아요)
  PYTHONPATH="$ENGINE_DIR${PYTHONPATH:+:$PYTHONPATH}" python -m worker.envcheck
}
if want check; then
  step "부품 맞춤 검사 (전부 실제로 불러와 봐요)"
  EC_OUT="$(env_check 2>&1)"; EC_RC=$?
  if [ $EC_RC -ne 0 ] && [ -f "$PINS" ]; then
    echo "$EC_OUT" | grep '^\[안 됨\]' | head -8
    echo "알림: 불러오지 못하는 부품이 있어서, 고정한 판으로 다시 깔고 한 번 더 확인해요."
    pip install -q --force-reinstall --no-deps -r "$PINS" || true
    EC_OUT="$(env_check 2>&1)"; EC_RC=$?
  fi
  if [ $EC_RC -ne 0 ]; then
    echo "$EC_OUT" | tail -40
    EC_TEXT="$(echo "$EC_OUT" | grep '^@@ENVCHECK ' | tail -1 | python -c 'import sys,json; d=json.loads(sys.stdin.read()[11:] or "{}"); print(d.get("text") or "")' 2>/dev/null)"
    die "설치는 했지만 부품을 불러오는 검사에 실패해서 설치를 끝내지 않았어요. ${EC_TEXT:-위의 [안 됨] 줄을 확인해 주세요.} 위에 나온 오류 글을 캡처해서 보내 주세요."
  fi
  echo "$EC_OUT" | grep '^@@ENVCHECK ' | tail -1 | python -c 'import sys,json; d=json.loads(sys.stdin.read()[11:] or "{}"); print(d.get("text") or "")' 2>/dev/null
fi

echo "@@DONE 환경 설치가 끝났어요. 이어서 모델을 받아요."
