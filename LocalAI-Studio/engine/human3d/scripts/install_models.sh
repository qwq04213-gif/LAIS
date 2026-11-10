#!/usr/bin/env bash
# SiTH 모델 받기(공개 모델만). SMPL-X 몸 모델은 가입·약관 동의가 필요해서 자동으로 받지 않아요 — 안내만 해요.
# 받은 파일은 ~/lais-human3d 안에만 둬요(깃허브·업데이트 파일에 들어가지 않아요).
# ★ 실제 PC 에서 끝까지 돌려 확인하지 못한 스크립트예요(미검증).
set -u
HOME_DIR="${HUMAN3D_HOME:-$HOME/lais-human3d}"
TOTAL=4
step() { echo "@@STEP $1/$TOTAL $2"; }
die() { echo "@@FAIL $1"; exit 1; }
cd "$HOME_DIR/SiTH" 2>/dev/null || die "SiTH 코드가 없어요. 먼저 환경 설치를 해 주세요."
. "$HOME_DIR/venv/bin/activate" || die "파이썬 환경이 없어요. 먼저 환경 설치를 해 주세요."
export HF_HOME="$HOME_DIR/hf"
mkdir -p checkpoints data/body_models/smplx "$HOME_DIR/models"

get() {      # get <주소> <저장할 곳> — 받다 끊기면 이어 받아요
  if [ -s "$2" ] && [ ! -f "$2.part" ]; then echo "이미 있음: $2"; return 0; fi
  touch "$2.part"
  wget -c -q --show-progress --progress=dot:giga "$1" -O "$2" && rm -f "$2.part"
}

step 1 "형태 복원 모델 (recon_model.pth)"
get https://files.ait.ethz.ch/projects/SiTH/recon_model.pth checkpoints/recon_model.pth || die "형태 복원 모델을 받지 못했어요(인터넷 연결 확인)."

step 2 "몸 어림 모델 (save_smplerx.pth)"
get https://files.ait.ethz.ch/projects/SiTH/save_smplerx.pth checkpoints/save_smplerx.pth || die "몸 어림 모델을 받지 못했어요."

step 3 "뒷면 그리기 모델 (hohs/SiTH_diffusion)"
if [ ! -f "$HOME_DIR/models/SiTH_diffusion/unet/config.json" ]; then
  python - <<PY || die "뒷면 그리기 모델을 받지 못했어요."
from huggingface_hub import snapshot_download
snapshot_download("hohs/SiTH_diffusion", local_dir="$HOME_DIR/models/SiTH_diffusion", local_dir_use_symlinks=False)
PY
fi

step 4 "자세 검출 모델 미리 받기"
python - <<'PY' || echo "알림: 자세 검출 모델은 처음 쓸 때 받아요(인터넷이 필요해요)."
import numpy as np
from rtmlib import Wholebody
Wholebody(mode="performance", to_openpose=False, backend="onnxruntime", device="cpu")(np.zeros((256, 256, 3), np.uint8))
PY

if [ ! -f data/body_models/smplx/SMPLX_MALE.npz ]; then
  echo "@@NEED_SMPLX $(pwd)/data/body_models/smplx"
fi
echo "@@DONE 모델 받기가 끝났어요."
