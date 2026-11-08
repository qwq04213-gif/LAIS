# -*- coding: utf-8 -*-
"""Blender(무료, GPL) 연동 — 3D 결과를 게임에 바로 쓸 수 있게 마무리해요(크기·바닥 기준점·LOD·FBX/OBJ/GLB 내보내기).
Blender 는 engine/blender 에 포터블(zip)로 따로 받아 두고, 화면 없이(-b) 뒤에서 실행해요. 그 폴더를 지우면 깨끗이 사라져요."""
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

NO_WIN = 0x08000000 if os.name == "nt" else 0
VER = "4.5.15"                                   # 4.5 LTS(2027년까지 지원) — 스크립트가 쓰는 기능이 바뀌지 않게 판을 고정해요
URL = f"https://download.blender.org/release/Blender4.5/blender-{VER}-windows-x64.zip"
SIZE = 398_649_826
JOB = {"state": "", "msg": "", "pct": 0}
_LOCK = threading.Lock()


def base(root):
    return Path(root) / "engine" / "blender"


def exe(root):
    """설치된 blender 실행 파일(없으면 None). 테스트·직접 설치를 위해 BLENDER_EXE 도 받아요."""
    env = os.environ.get("BLENDER_EXE")
    if env and Path(env).is_file():
        return Path(env)
    b = base(root)
    if not (b / ".ready").is_file():
        return None
    for name in ("blender.exe", "blender"):
        for f in sorted(b.glob(f"*/{name}")) + [b / name]:
            if f.is_file():
                return f
    return None


def status(root):
    return {"installed": bool(exe(root)), "version": VER, "state": JOB["state"], "msg": JOB["msg"], "pct": JOB["pct"],
            "size": "약 400MB(풀면 약 1.2GB)", "license": "GPL(무료)"}


def install(root):
    with _LOCK:
        if JOB["state"] == "running":
            return {"ok": True}
        if exe(root):
            return {"error": "이미 설치돼 있어요."}
        if os.name != "nt":
            return {"error": "자동 설치는 윈도우에서만 돼요. BLENDER_EXE 환경 변수로 설치된 blender 를 알려 주세요."}
        JOB.update(state="running", msg="시작해요…", pct=0)
    threading.Thread(target=_install, args=(root,), daemon=True).start()
    return {"ok": True}


def _install(root):
    b = base(root)
    b.mkdir(parents=True, exist_ok=True)
    z = b / f"blender-{VER}.zip.part"
    try:
        if not (b / f"blender-{VER}.zip").is_file():
            JOB["msg"] = f"Blender {VER} 받는 중…"
            req = urllib.request.Request(URL, headers={"User-Agent": "LocalAI-Studio"})
            with urllib.request.urlopen(req, timeout=120) as r, open(z, "wb") as fh:
                total = int(r.headers.get("Content-Length") or SIZE)
                got = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    got += len(chunk)
                    JOB["pct"] = round(got * 100 / max(total, 1))
            if z.stat().st_size < SIZE * 0.95:
                raise RuntimeError("받은 파일이 너무 작아요(중간에 끊겼어요). 다시 눌러 주세요.")
            z.replace(b / f"blender-{VER}.zip")
        JOB.update(msg="압축 푸는 중…", pct=100)
        with zipfile.ZipFile(b / f"blender-{VER}.zip") as zf:
            for m in zf.infolist():                     # 폴더 밖으로 나가는 이름은 건너뛰어요
                if m.filename.startswith("/") or ".." in Path(m.filename).parts:
                    continue
                zf.extract(m, b)
        (b / ".ready").write_text(VER, encoding="utf-8")
        f = exe(root)
        if not f:
            (b / ".ready").unlink(missing_ok=True)
            raise RuntimeError("압축은 풀었는데 blender.exe 를 찾지 못했어요.")
        JOB["msg"] = "점검 중…"
        r = check(root)
        if not r.get("ok"):
            raise RuntimeError("Blender 점검 실패: " + r.get("error", ""))
        (b / f"blender-{VER}.zip").unlink(missing_ok=True)
        JOB.update(state="done", msg=f"Blender {VER} 설치했어요.")
    except Exception as e:  # noqa: BLE001
        JOB.update(state="error", msg=(str(e) or type(e).__name__)[:300] + " (다시 누르면 이어서 해요)")


def uninstall(root):
    if JOB["state"] == "running":
        return {"error": "설치 중에는 지울 수 없어요."}
    shutil.rmtree(base(root), ignore_errors=True)
    JOB.update(state="", msg="", pct=0)
    return {"ok": not base(root).exists()}


def _run(root, args, timeout, cancel=None):
    f = exe(root)
    if not f:
        raise RuntimeError("Blender 가 아직 없어요. 3D 만들기 화면의 [Blender 설치]를 눌러 주세요.")
    cmd = [str(f), "-b", "--factory-startup", "-noaudio", "--python-exit-code", "3", *args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=NO_WIN)
    out, t0 = [], time.time()

    def pump():                                   # 출력은 따로 읽어요(Blender 가 한동안 아무것도 안 찍어도 중단·시간 초과를 볼 수 있게)
        for line in p.stdout:
            out.append(line.rstrip())
            del out[:-200]
    th = threading.Thread(target=pump, daemon=True)
    th.start()
    while p.poll() is None:
        if cancel and cancel():
            p.kill()
            raise InterruptedError("중단했어요.")
        if time.time() - t0 > timeout:
            p.kill()
            raise RuntimeError(f"Blender 가 {timeout // 60}분 안에 끝나지 않았어요.")
        time.sleep(0.3)
    th.join(5)
    return p.returncode, list(out)


def check(root):
    """설치 점검: 화면 없이 켜서 상자 하나를 만들고 GLB 로 내보내 봐요."""
    tmp = base(root) / "check"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        code, out = _run(root, ["--python", str(Path(__file__).with_name("blender_game.py")), "--", json.dumps({"selftest": str(tmp)})], 300)
        res = tmp / "result.json"
        if code == 0 and res.is_file() and json.loads(res.read_text(encoding="utf-8")).get("ok"):
            return {"ok": True}
        return {"ok": False, "error": next((x for x in reversed(out) if "Error" in x or "error" in x), out[-1] if out else f"코드 {code}")[:300]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def finish(root, glb, out_dir, opts, cancel=None):
    """GLB → out_dir 에 게임용 묶음(LOD·FBX·OBJ·텍스처) + result.json. opts: name, height, lods, formats, up"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    job = {"glb": str(glb), "out": str(out_dir), **opts}
    code, out = _run(root, ["--python", str(Path(__file__).with_name("blender_game.py")), "--", json.dumps(job, ensure_ascii=False)], 1800, cancel)
    res = out_dir / "result.json"
    if code != 0 or not res.is_file():
        ef = out_dir / "error.txt"
        if ef.is_file():
            raise RuntimeError("Blender 마무리 실패: " + ef.read_text(encoding="utf-8", errors="replace").strip()[:300])
        err = next((x for x in reversed(out) if x.startswith("HUBERR:")), "") or next((x for x in reversed(out) if "Error" in x), "") or (out[-1] if out else f"코드 {code}")
        raise RuntimeError("Blender 마무리 실패: " + err.replace("HUBERR:", "").strip()[:300])
    return json.loads(res.read_text(encoding="utf-8"))
