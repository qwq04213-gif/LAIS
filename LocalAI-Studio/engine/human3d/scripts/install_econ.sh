#!/usr/bin/env bash
# ECON 전용 환경 설치 — WSL2 Ubuntu 22.04 안에서 돌아요. LAIS 가 대신 실행해요(직접 칠 필요 없음).
#   · SiTH 기본 설치(install_wsl.sh)가 먼저 돼 있어야 해요(CUDA 12.1 컴파일러·env.sh 를 같이 써요).
#   · SiTH 환경(venv)과 섞지 않고 econ-venv 를 따로 만들어요. ComfyUI 는 건드리지 않아요.
#   · ECON 공식 판은 파이썬 3.8·PyTorch 1.13·CUDA 11.6 이지만, 그 CUDA 는 RTX 40 계열을 정식 지원하지 않아서
#     SiTH 와 같은 파이썬 3.10·PyTorch 2.1·CUDA 12.1 에 맞춰 부품 판을 고정했어요(scripts/pins_econ.txt).
#   · ECON 코드는 '비상업 연구용' 라이선스라 LAIS 에 넣지 않고 여기서 공식 저장소에서 받아요.
#   · 여러 번 돌려도 돼요(된 단계는 건너뛰어요). 진행 "@@STEP n/N 글", 실패 "@@FAIL 까닭", 끝 "@@DONE".
# ★ 실제 PC 에서 끝까지 돌려 확인하지 못한 스크립트예요(미검증). PyTorch3D 컴파일은 20~40분 걸려요.
set -u
HOME_DIR="${HUMAN3D_HOME:-$HOME/lais-human3d}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(dirname "$HERE")"
ECON_COMMIT="d8f4e8b"
PYTORCH3D_TAG="v0.7.5"
STEPS="${HUMAN3D_INSTALL_STEPS:-base code venv torch parts pytorch3d build rembg check}"
TOTAL=$(echo $STEPS | wc -w)
N=0
step() { N=$((N + 1)); echo "@@STEP $N/$TOTAL $1"; }
die() { echo "@@FAIL $1"; exit 1; }
want() { case " $STEPS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1
SUDO="sudo -n"; [ "$(id -u)" = "0" ] && SUDO=""
cd "$HOME_DIR" 2>/dev/null || die "인체 3D 기본 설치(SiTH)가 먼저 필요해요. 엔진을 SiTH 로 두고 [설치 시작]부터 해 주세요."
[ -f "$HOME_DIR/env.sh" ] || die "CUDA 12.1 컴파일러 설정(env.sh)이 없어요. SiTH [설치 시작]을 먼저 끝까지 해 주세요."
. "$HOME_DIR/env.sh"
command -v nvcc >/dev/null 2>&1 && nvcc --version | grep -q "release 12.1" || die "CUDA 12.1 컴파일러(nvcc)를 찾지 못했어요. SiTH [설치 시작]을 다시 눌러 주세요."
PINS="$HOME_DIR/pins_econ.txt"
[ -f "$HERE/pins_econ.txt" ] && cp "$HERE/pins_econ.txt" "$PINS"

if want base; then
  step "기본 도구 확인 (eigen·ffmpeg)"
  NEED=""
  for p in libeigen3-dev ffmpeg git python3.10-venv python3.10-dev build-essential; do dpkg -s "$p" >/dev/null 2>&1 || NEED="$NEED $p"; done
  if [ -n "$NEED" ]; then $SUDO apt-get update -y >/dev/null 2>&1 && $SUDO apt-get install -y $NEED || die "기본 도구를 설치하지 못했어요:$NEED"; fi
fi

if want code; then
  step "ECON 코드 받기 (비상업 연구용 라이선스)"
  if [ ! -d ECON/.git ]; then git clone https://github.com/YuliangXiu/ECON ECON || die "ECON 코드를 받지 못했어요(인터넷 연결 확인)."; fi
  ( cd ECON && git fetch -q origin 2>/dev/null; git checkout -q "$ECON_COMMIT" 2>/dev/null || echo "알림: 정해 둔 판($ECON_COMMIT)으로 맞추지 못해 받은 판을 그대로 써요." )
fi

if want venv; then
  step "ECON 전용 파이썬 환경 만들기"
  [ -x econ-venv/bin/python ] || python3.10 -m venv econ-venv || die "ECON 파이썬 환경을 만들지 못했어요."
fi
[ -f econ-venv/bin/activate ] && . econ-venv/bin/activate
[ -n "${HUMAN3D_TEST_BIN:-}" ] && export PATH="$HUMAN3D_TEST_BIN:$PATH"
[ -f "$PINS" ] && export PIP_CONSTRAINT="$PINS"
if want venv; then python -m pip install -q --upgrade "pip<25" wheel "setuptools>=64,<70" ninja cython || die "pip·setuptools 준비 실패"; fi

if want torch; then
  step "PyTorch 2.1 (CUDA 12.1) 설치 — 약 2.5GB"
  python -c "import torch,sys; sys.exit(0 if torch.__version__.startswith('2.1.0') else 1)" 2>/dev/null \
    || PIP_CONSTRAINT= pip install -q torch==2.1.0 torchvision==0.16.0 --extra-index-url https://download.pytorch.org/whl/cu121 || die "PyTorch 설치 실패"
  python -c "import torch; assert torch.cuda.is_available()" || die "PyTorch 가 그래픽카드를 쓰지 못해요."
fi

if want parts; then
  step "ECON 부품 설치 (판 고정)"
  [ -f "$PINS" ] && { grep -vE '^\s*#|^\s*$' "$PINS" > "$HOME_DIR/pins_econ_req.txt"; pip install -q -r "$HOME_DIR/pins_econ_req.txt" || die "ECON 부품을 설치하지 못했어요(인터넷 연결 확인)."; }
  python -c "import chumpy" 2>/dev/null || pip install -q --no-build-isolation chumpy==0.70 || echo "알림: chumpy 를 넣지 못했어요(예전 SMPL .pkl 읽기용 — ECON 추론에는 보통 안 써요)."
fi

if want pytorch3d; then
  step "PyTorch3D $PYTORCH3D_TAG 컴파일 — 20~40분 걸려요"
  if ! python -c "import pytorch3d.renderer, pytorch3d._C" 2>/dev/null; then
    CC_ARCH="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' ')"
    export FORCE_CUDA=1 TORCH_CUDA_ARCH_LIST="${CC_ARCH:-8.6}" MAX_JOBS="${MAX_JOBS:-4}"
    echo "그래픽카드 계산 능력 $TORCH_CUDA_ARCH_LIST 로 컴파일해요(동시 작업 $MAX_JOBS — 메모리가 모자라면 MAX_JOBS 를 줄여요)."
    pip install --no-build-isolation "git+https://github.com/facebookresearch/pytorch3d.git@$PYTORCH3D_TAG" \
      || die "PyTorch3D 를 컴파일하지 못했어요. 위쪽의 오류 줄(nvcc·g++·메모리 부족 'Killed')을 캡처해서 보내 주세요."
  fi
fi

if want build; then
  step "ECON 부품 컴파일 (libmesh·libvoxelize)"
  ( cd ECON/lib/common/libmesh && python setup.py build_ext --inplace >/dev/null ) || die "ECON libmesh 를 컴파일하지 못했어요."
  ( cd ECON/lib/common/libvoxelize && python setup.py build_ext --inplace >/dev/null ) || die "ECON libvoxelize 를 컴파일하지 못했어요."
fi

if want rembg; then
  step "배경 지우기(rembg — ECON 용 개조판) 설치"
  # 개조판은 서버용 부품(fastapi·uvicorn 등)까지 판을 고정해서 그대로 깔면 다른 부품과 부딪혀요. 꾸러미만 넣고, 쓰는 부품은 pins_econ.txt 에 있어요.
  python -c "import rembg" 2>/dev/null || pip install -q --no-deps "git+https://github.com/YuliangXiu/rembg.git" || die "rembg 를 설치하지 못했어요."
fi

if want check; then
  step "ECON 부품 맞춤 검사 (불러오기 + 그래픽카드에서 실제로 그리기)"
  OUT="$(cd ECON && PYTHONPATH="$ENGINE_DIR:$HOME_DIR/ECON${PYTHONPATH:+:$PYTHONPATH}" python -m worker.envcheck --set econ 2>&1)"; RC=$?
  echo "$OUT" | grep -E '^\[( 됨 |안 됨)\]' | head -20
  if [ $RC -ne 0 ]; then
    TXT="$(echo "$OUT" | grep '^@@ENVCHECK ' | tail -1 | python -c 'import sys,json; d=json.loads(sys.stdin.read()[11:] or "{}"); print(d.get("text") or "")' 2>/dev/null)"
    die "ECON 환경 검사에 실패해서 설치를 끝내지 않았어요. ${TXT:-위의 [안 됨] 줄을 확인해 주세요.} 위에 나온 오류 글을 캡처해서 보내 주세요."
  fi
fi
echo "@@DONE ECON 환경 설치가 끝났어요. 이어서 모델을 받아요(ICON 계정 필요)."
