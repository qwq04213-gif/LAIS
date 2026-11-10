# -*- coding: utf-8 -*-
"""개발용: 앱 폴더에서 update.bat(자체 압축 해제형 업데이트 파일)과 전체 zip 을 만들어요.

  python build_update.py --tree 앱폴더 --out 출력폴더 --notes notes.txt [--seed-base 이전버전폴더]

- 업데이트 파일에는 '앱 파일 전체'가 들어가요(수백 KB). 이전 버전이 무엇이든 같은 결과가 되고, 같은 파일은 건너뛰어요.
- history.json 에는 사용자가 고칠 수 있는 파일(profiles.json, models.json, wildcards)의 과거 배포본 해시를 모아 둬요.
  설치된 파일이 이 해시 중 하나와 같으면 '사용자가 안 고친 것'이라 안전하게 교체하고, 아니면 합치거나 .new 로 둬요.
"""
import argparse, base64, hashlib, io, json, sys, time, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
USER_FILES = {"hub/profiles.json": "json-id", "hub/models.json": "json-id"}   # 직접 고칠 수 있는 파일 -> 합치기 방식
USER_DIRS = ("wildcards/",)                                                    # 안의 파일은 고쳤으면 .new 로
SKIP_DIRS = {"__pycache__", ".ruff_cache", "engine", "models", "outputs", "logs", "downloads", "backup", "input", "temp"}
KEEP_ENGINE = ("engine", "human3d")
MARK = "::PAYLOAD_BEGIN"

BAT_HEAD = r"""@echo off
setlocal
title Local AI Studio - Update
set "SELF=%~f0"
set "ROOT=%~dp0."
if exist "%ROOT%\hub\hub.py" goto have_root
set "ROOT="
if exist "%LOCALAPPDATA%\LocalAI-Studio\path.txt" set /p ROOT=<"%LOCALAPPDATA%\LocalAI-Studio\path.txt"
if not defined ROOT goto no_root
if exist "%ROOT%\hub\hub.py" goto have_root
:no_root
echo.
echo  [!] Install folder not found.
echo      Put this file in the folder that contains start.bat, then run it again.
goto done
:have_root
set "PY=%ROOT%\engine\ComfyUI_windows_portable\python_embeded\python.exe"
if exist "%PY%" goto have_py
echo.
echo  [!] Engine python not found. Run install.bat first.
goto done
:have_py
chcp 65001 >nul
"%PY%" -I -X utf8 -c "import sys,io,base64,zipfile;d=open(sys.argv[1],'rb').read();m=d.rindex(b'\n::PAYLOAD_BEGIN');z=zipfile.ZipFile(io.BytesIO(base64.b64decode(d[d.index(b'\n',m+1)+1:])));sys.argv=sys.argv[1:];exec(compile(z.read('apply_update.py').decode('utf-8'),'apply_update.py','exec'),{'__name__':'__main__','PAYLOAD':z})" "%SELF%" "%ROOT%" %*
:done
echo.
pause
exit /b
"""


def sha(b):
    return hashlib.sha256(b).hexdigest()


def collect(tree):
    files = {}
    for p in sorted(tree.rglob("*")):
        rel = p.relative_to(tree)
        keep = rel.parts[:2] == KEEP_ENGINE and not any(x in SKIP_DIRS - {"engine"} for x in rel.parts)      # engine 안에서도 인체 3D worker 코드는 배포해요(모델·가상환경은 WSL 쪽에 있어 여기 없어요)
        if p.is_dir() or (any(x in SKIP_DIRS for x in rel.parts) and not keep) or p.suffix == ".pyc" or p.name.endswith((".new", ".upd-tmp")):
            continue
        files["/".join(rel.parts)] = p.read_bytes()
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--notes", required=True)
    ap.add_argument("--seed-base")
    ap.add_argument("--history", default=str(HERE / "history.json"))
    a = ap.parse_args()
    tree, out = Path(a.tree), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = collect(tree)
    up = files.get("hub/updater.py")      # 앱 안 업데이트가 쓰는 적용기 사본은 이 폴더의 apply_update.py 와 같아야 해요
    if up is not None and up != (HERE / "apply_update.py").read_bytes():
        sys.exit("hub/updater.py 가 apply_update.py 와 달라요. 복사해서 맞춘 뒤 다시 만들어 주세요.")
    version = files["VERSION.txt"].decode().strip()
    notes = [l.strip() for l in Path(a.notes).read_text(encoding="utf-8").splitlines() if l.strip()]

    hp = Path(a.history)
    hist = json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else {}
    if a.seed_base:   # 이전 배포본의 해시를 기록(처음 한 번)
        for rel, data in collect(Path(a.seed_base)).items():
            if rel in USER_FILES or rel.startswith(USER_DIRS):
                hist.setdefault(rel, [])
                if sha(data) not in hist[rel]:
                    hist[rel].append(sha(data))
    for rel, data in files.items():
        if rel in USER_FILES or rel.startswith(USER_DIRS):
            hist.setdefault(rel, [])
            if sha(data) not in hist[rel]:
                hist[rel].append(sha(data))
    hp.write_text(json.dumps(hist, indent=1, ensure_ascii=False), encoding="utf-8")

    entries = []
    for rel, data in files.items():
        e = dict(path=rel, sha256=sha(data), size=len(data))
        if rel in USER_FILES or rel.startswith(USER_DIRS):
            e.update(policy="user", known=hist.get(rel, []))
            if rel in USER_FILES:
                e["merge"] = USER_FILES[rel]
        entries.append(e)
    manifest = dict(format=1, version=version, built=time.strftime("%Y-%m-%d %H:%M:%S"), notes=notes, files=entries)

    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        z.writestr("apply_update.py", (HERE / "apply_update.py").read_bytes())
        for rel, data in files.items():
            z.writestr("files/" + rel, data)
    b64 = base64.b64encode(zb.getvalue()).decode()
    body = "\r\n".join(b64[i:i + 76] for i in range(0, len(b64), 76))
    bat = BAT_HEAD.replace("\r\n", "\n").replace("\n", "\r\n") + MARK + "\r\n" + body + "\r\n"
    bat.encode("ascii")   # 배치 파일 머리는 ASCII 만 (한글은 파이썬이 출력)
    ub = out / f"LocalAI-Studio-update-{version}.bat"
    ub.write_bytes(bat.encode("ascii"))

    # 새로 설치하는 사람을 위한 전체 zip (엔진/모델은 install.bat 이 받아요)
    with zipfile.ZipFile(out / f"LocalAI-Studio-{version}.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, data in files.items():
            z.writestr("LocalAI-Studio/" + rel, data)
    print(f"버전 {version}: 파일 {len(files)}개, {ub.name} {ub.stat().st_size:,}바이트, zip {(out / f'LocalAI-Studio-{version}.zip').stat().st_size:,}바이트")


if __name__ == "__main__":
    sys.exit(main())
