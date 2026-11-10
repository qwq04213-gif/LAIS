"""ECON 모델 받기 — 공식 fetch_data.sh 와 같은 파일을 같은 자리에 받아요(ICON 사이트 계정 필요). econ-venv 의 파이썬으로 ECON 폴더에서 실행해요.

아이디·비밀번호는 표준 입력의 첫 줄(JSON {"user", "pass"})로만 받아요 — 명령줄·환경 변수·기록(log)에 남기지 않고, 파일로 저장하지 않아요.
공식 스크립트는 wget 명령줄에 비밀번호를 넣는데(다른 프로그램이 볼 수 있어요), 여기서는 파이썬이 직접 보내요.
비밀번호가 틀리거나 해당 모델에 'Register' 를 안 했으면 서버가 로그인 화면(HTML)을 돌려줘서, zip 이 아니면 그 까닭으로 멈춰요.
Sapiens(사람 분리·표면 방향)는 Hugging Face 공간에서 필요한 파일만 받아요(공간 전체는 수십 GB).

  echo '{"user":"…","pass":"…"}' | python econ_fetch.py --econ <ECON 폴더> --sapiens <받을 곳> [--smplx-copy <SiTH smplx 폴더>]
진행 "@@STEP n/N 글", 실패 "@@FAIL 까닭", 끝 "@@DONE". ★ 실제로 받아 확인하지 못했어요(미검증)."""
import argparse
import json
import os
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile

URL = "https://download.is.tue.mpg.de/download.php"
# (화면 이름, domain, sfile, 저장할 곳(ECON 기준), 대략 크기)
FILES = (("SMPL (남성·여성)", "smpl", "SMPL_python_v.1.0.0.zip", "data/smpl_related/models/SMPL_python_v.1.0.0.zip", "40MB"),
         ("SMPLify (중립 SMPL)", "smplify", "mpips_smplify_public_v2.zip", "data/smpl_related/models/mpips_smplify_public_v2.zip", "20MB"),
         ("SMPL-X v1.1", "smplx", "models_smplx_v1_1.zip", "data/smpl_related/models/models_smplx_v1_1.zip", "830MB"),
         ("ECON 자료·모델", "icon", "econ_data.zip", "data/econ_data.zip", "1GB 남짓"),
         ("PIXIE", "icon", "HPS/pixie_data.zip", "data/HPS/pixie_data.zip", "1GB 남짓"),
         ("PyMAF-X", "icon", "HPS/pymafx_data.zip", "data/HPS/pymafx_data.zip", "500MB 남짓"))
SAPIENS_REPO = "facebook/sapiens-normal"
SAPIENS_FILES = ("sapiens_1b_seg_foreground_epoch_8_torchscript.pt2", "sapiens_2b_normal_render_people_epoch_70_torchscript.pt2",
                 "sapiens_1b_normal_render_people_epoch_115_torchscript.pt2", "sapiens_0.3b_normal_render_people_epoch_66_torchscript.pt2")
TOTAL = len(FILES) + 2


def step(n, text):
    print(f"@@STEP {n}/{TOTAL} {text}", flush=True)


def fail(text):
    print("@@FAIL " + text, flush=True)
    sys.exit(1)


def fetch(domain, sfile, dest, user, pw, opener=None):
    """로그인 정보를 POST 로 보내 받아요(이어 받기 지원). 받은 것이 zip 이 아니면 지우고 까닭을 돌려줘요."""
    if os.path.isfile(dest) and zipfile.is_zipfile(dest):
        return None
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.isfile(part) else 0
    body = urllib.parse.urlencode({"username": user, "password": pw}).encode()
    req = urllib.request.Request(f"{URL}?domain={domain}&sfile={urllib.parse.quote(sfile)}&resume=1", data=body)
    if have:
        req.add_header("Range", f"bytes={have}-")
    try:
        with (opener or urllib.request.urlopen)(req, timeout=120) as r, open(part, "ab" if have and getattr(r, "status", 200) == 206 else "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
    except Exception as e:  # noqa: BLE001
        return f"받지 못했어요({sfile}): {e}"
    if not zipfile.is_zipfile(part):
        head = open(part, "rb").read(400).lower()
        os.remove(part)
        if b"<html" in head or b"login" in head or b"password" in head:
            return f"{sfile}: ICON 아이디·비밀번호가 맞지 않거나, 사이트에서 이 모델에 'Register now' 를 누르지 않았어요(SMPL·SMPL-X·SMPLify·PIXIE 모두 등록해야 해요)."
        return f"{sfile}: 받은 파일이 zip 이 아니에요."
    os.replace(part, dest)
    return None


def unpack(econ, smplx_copy=None):
    """fetch_data.sh 와 같은 자리로 풀어요. 받은 zip 은 다 푼 뒤 지워요(공식 스크립트와 같아요)."""
    d = lambda *p: os.path.join(econ, *p)
    m = d("data", "smpl_related", "models")
    if os.path.isfile(d(m, "SMPL_python_v.1.0.0.zip")):
        zipfile.ZipFile(d(m, "SMPL_python_v.1.0.0.zip")).extractall(m)
        os.makedirs(d(m, "smpl"), exist_ok=True)
        for a, b in (("basicModel_f_lbs_10_207_0_v1.0.0.pkl", "SMPL_FEMALE.pkl"), ("basicmodel_m_lbs_10_207_0_v1.0.0.pkl", "SMPL_MALE.pkl")):
            if os.path.isfile(d(m, "smpl", "models", a)):
                os.replace(d(m, "smpl", "models", a), d(m, "smpl", b))
        os.remove(d(m, "SMPL_python_v.1.0.0.zip"))
    if os.path.isfile(d(m, "mpips_smplify_public_v2.zip")):
        zipfile.ZipFile(d(m, "mpips_smplify_public_v2.zip")).extractall(m)
        src = d(m, "smplify_public", "code", "models", "basicModel_neutral_lbs_10_207_0_v1.0.0.pkl")
        if os.path.isfile(src):
            os.replace(src, d(m, "smpl", "SMPL_NEUTRAL.pkl"))
        os.remove(d(m, "mpips_smplify_public_v2.zip"))
    if os.path.isfile(d(m, "models_smplx_v1_1.zip")):
        zipfile.ZipFile(d(m, "models_smplx_v1_1.zip")).extractall(d("data", "smpl_related"))
        os.remove(d(m, "models_smplx_v1_1.zip"))
    if os.path.isfile(d("data", "econ_data.zip")):
        zipfile.ZipFile(d("data", "econ_data.zip")).extractall(d("data"))
        if os.path.isdir(d("data", "smpl_data")):
            if os.path.isdir(d("data", "smpl_related", "smpl_data")):
                shutil.rmtree(d("data", "smpl_related", "smpl_data"))
            os.replace(d("data", "smpl_data"), d("data", "smpl_related", "smpl_data"))
        os.remove(d("data", "econ_data.zip"))
    for z in ("pixie_data.zip", "pymafx_data.zip"):
        if os.path.isfile(d("data", "HPS", z)):
            zipfile.ZipFile(d("data", "HPS", z)).extractall(d("data", "HPS"))
            os.remove(d("data", "HPS", z))
    copied = []
    if smplx_copy:                                           # 같은 SMPL-X v1.1 파일을 SiTH 에도 넣어 줘요(따로 받지 않아도 되게)
        os.makedirs(smplx_copy, exist_ok=True)
        for g in ("NEUTRAL", "FEMALE", "MALE"):
            src = d(m, "smplx", f"SMPLX_{g}.npz")
            if os.path.isfile(src) and not os.path.isfile(os.path.join(smplx_copy, f"SMPLX_{g}.npz")):
                shutil.copy2(src, smplx_copy)
                copied.append(f"SMPLX_{g}.npz")
    return copied


def sapiens(dst):
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=SAPIENS_REPO, repo_type="space", local_dir=dst, allow_patterns=[f"assets/checkpoints/{f}" for f in SAPIENS_FILES])
    return [f for f in SAPIENS_FILES if not os.path.isfile(os.path.join(dst, "assets", "checkpoints", f))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--econ", required=True)
    ap.add_argument("--sapiens", required=True)
    ap.add_argument("--smplx-copy", default="")
    a = ap.parse_args()
    line = sys.stdin.readline()
    try:
        cred = json.loads(line or "{}")
    except ValueError:
        cred = {}
    user, pw = str(cred.get("user") or ""), str(cred.get("pass") or "")
    del line, cred
    if not user or not pw:
        fail("ICON 사이트 아이디·비밀번호가 필요해요(https://icon.is.tue.mpg.de 에 가입하고 SMPL·SMPL-X·SMPLify·PIXIE 에 'Register now').")
    for n, (ko, dom, sf, dest, size) in enumerate(FILES, 1):
        step(n, f"{ko} 받기 (약 {size})")
        err = fetch(dom, sf, os.path.join(a.econ, dest), user, pw)
        if err:
            fail(err)
    step(len(FILES) + 1, "받은 파일 풀기")
    copied = unpack(a.econ, a.smplx_copy or None)
    if copied:
        print("SiTH 에도 넣었어요: " + ", ".join(copied), flush=True)
    step(len(FILES) + 2, "Sapiens 모델 받기 (약 15GB — 오래 걸려요)")
    try:
        miss = sapiens(a.sapiens)
    except Exception as e:  # noqa: BLE001
        fail(f"Sapiens 모델을 받지 못했어요: {e}")
    if miss:
        fail("Sapiens 모델 파일 일부를 찾지 못했어요(Hugging Face 의 파일 자리가 바뀌었을 수 있어요): " + ", ".join(miss))
    print("@@DONE ECON 모델 받기가 끝났어요.", flush=True)


if __name__ == "__main__":
    main()
