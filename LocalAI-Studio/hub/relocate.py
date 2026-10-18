# -*- coding: utf-8 -*-
"""프로그램 위치 옮기기 / 다시 시작 도우미.

스튜디오가 꺼진 다음에 따로 실행돼요(Windows 는 실행 중인 프로그램 파일을 옮길 수 없어서).
그래서 표준 라이브러리만 쓰고, 스튜디오(hub.py)는 이 파일을 임시 폴더로 복사해서 실행해요.
  plan(src, dst)  옮기기 전에 검사(스튜디오에서 호출)
  run(job)        실제로 옮기고 새 위치에서 다시 켜기(도우미 프로세스에서 호출)
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

GB = 1 << 30


def _inside(child, parent):
    c, p = os.path.normcase(str(child)), os.path.normcase(str(parent)).rstrip("\\/")
    return c == p or c.startswith(p + os.sep)


def _stats(root):
    n = size = 0
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            try:
                size += os.lstat(os.path.join(dp, f)).st_size
                n += 1
            except OSError:
                pass
    return n, size


def _same_volume(a, b):
    b = Path(b)
    while not b.exists() and b != b.parent:
        b = b.parent
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


def plan(src, dst):
    """새 위치를 검사하고 어떻게 옮길지 돌려줘요. 안 되는 경우는 ValueError(한국어 안내)."""
    src = Path(src).resolve()
    dst_s = str(dst or "").strip().strip('"')
    if not dst_s:
        raise ValueError("새 위치를 적어 주세요.")
    dst = Path(dst_s)
    if not dst.is_absolute():
        raise ValueError("전체 경로로 적어 주세요. 예: E:\\sd\\LocalAI")
    dst = dst.resolve()
    if dst == src:
        raise ValueError("지금 있는 위치와 같아요.")
    if _inside(dst, src):
        raise ValueError("새 위치는 지금 폴더의 안쪽일 수 없어요.")
    kids = sorted(c.name for c in src.iterdir())
    if dst == src.parent:                    # 바깥 폴더로 한 단계 올리기
        mode = "flatten"
        clash = [n for n in kids if (dst / n).exists() or n == src.name]
        if clash:
            raise ValueError("바깥 폴더에 같은 이름이 이미 있어서 합칠 수 없어요: " + ", ".join(clash[:6]) +
                             ("…" if len(clash) > 6 else "") + "\n그 파일·폴더를 옮기거나 이름을 바꾼 뒤 다시 해 주세요.")
    else:
        if dst.exists():
            if not dst.is_dir():
                raise ValueError("그 경로는 폴더가 아니에요.")
            if any(dst.iterdir()):
                raise ValueError("새 위치 폴더가 비어 있지 않아요. 비어 있는 폴더(또는 아직 없는 폴더)를 골라 주세요.")
        elif not Path(dst.anchor).exists():
            raise ValueError("그 드라이브를 찾을 수 없어요: " + dst.anchor)
        mode = "move" if _same_volume(src, dst) else "copy"
    out = {"mode": mode, "src": str(src), "dst": str(dst), "items": len(kids)}
    if mode == "copy":
        n, size = _stats(src)
        anc = dst
        while not anc.exists():
            anc = anc.parent
        free = shutil.disk_usage(anc).free
        out.update(files=n, bytes=size, free=free)
        if free < size * 1.05 + GB:
            raise ValueError(f"새 위치의 빈 공간이 부족해요. 필요 {size / GB:.1f}GB 이상, 남은 공간 {free / GB:.1f}GB.")
    return out


def _kill(src, ppid):
    """이 폴더 안의 프로그램(ComfyUI·Ollama 등)과 스튜디오가 떠 있던 콘솔 창(cmd)을 끝내요. Windows 에서만."""
    if os.name != "nt":
        return
    s = str(src).replace("'", "''")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith('" + s + "\\', [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force"],
                       capture_output=True, timeout=90)
        if ppid:
            o = subprocess.run(["tasklist", "/FI", f"PID eq {ppid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=20).stdout.lower()
            if "cmd.exe" in o:
                subprocess.run(["taskkill", "/PID", str(ppid), "/F"], capture_output=True, timeout=20)
    except Exception:
        pass


def _retry(fn, tries=30):
    for i in range(tries):
        try:
            return fn()
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(1)


def _copy_tree(src, dst, L):
    n = 0
    for dp, dn, fn in os.walk(src):
        rel = Path(dp).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in fn:
            shutil.copy2(Path(dp) / f, dst / rel / f)
            n += 1
            if n % 2000 == 0:
                L(f"복사 {n}개…")


def _launch(job, where):
    """새 위치(또는 원래 위치)에서 스튜디오를 다시 켜요. 실패해도 옮기기 결과는 건드리지 않아요."""
    try:
        argv = job.get("launch")
        if argv:
            subprocess.Popen(argv, cwd=str(where), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, HUB_RESTARTED="1"))
        elif os.name == "nt":
            subprocess.Popen(["cmd", "/c", "start", "LocalAI Studio", "/D", str(where), str(Path(where) / "start.bat")], cwd=str(where), env=dict(os.environ, HUB_RESTARTED="1"))
    except Exception:
        pass


def _write(path, obj):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def run(job):
    """job: mode(restart/flatten/move/copy), src, dst, ppid, wait, log, result, path_txt, launch"""
    logp = Path(job["log"])
    logp.parent.mkdir(parents=True, exist_ok=True)

    def L(m):
        with open(logp, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + m + "\n")

    src, mode = Path(job["src"]), job["mode"]
    dst = Path(job.get("dst") or job["src"])
    L(f"== {mode}: {src} -> {dst}")
    time.sleep(job.get("wait", 3))
    _kill(src, job.get("ppid"))
    time.sleep(1 if job.get("wait", 3) else 0)
    moved, created = [], []
    try:
        if mode == "restart":
            _launch(job, src)
            _write(job["result"], {"ok": True, "mode": mode, "msg": "프로그램을 다시 시작했어요."})
            return True
        if mode in ("flatten", "move"):
            dst.mkdir(parents=True, exist_ok=True)
            for c in sorted(src.iterdir()):
                t = dst / c.name
                _retry(lambda c=c, t=t: shutil.move(str(c), str(t)))
                moved.append((c.name, t))
            L(f"{len(moved)}개 항목을 옮겼어요.")
            if not any(src.iterdir()):
                try:
                    _retry(src.rmdir, 8)
                except OSError:
                    L("안쪽 빈 폴더는 다른 프로그램이 잡고 있어서 지우지 못했어요(직접 지워도 돼요).")
            note = "바깥 폴더로 올렸어요." if mode == "flatten" else "새 위치로 옮겼어요."
        else:                                              # copy: 다른 드라이브. 원래 폴더는 그대로 둬요
            before = _stats(src)
            dst.mkdir(parents=True, exist_ok=True)
            for c in sorted(src.iterdir()):
                created.append(dst / c.name)
            _copy_tree(src, dst, L)
            after = _stats(dst)
            if before != after:
                raise RuntimeError(f"복사한 파일이 원본과 달라요(원본 {before[0]}개 {before[1]}바이트, 복사본 {after[0]}개 {after[1]}바이트).")
            note = "새 위치로 복사했어요. 원래 폴더는 그대로 남겼으니 잘 되는지 확인한 뒤 직접 지워도 돼요."
        if job.get("path_txt"):
            Path(job["path_txt"]).parent.mkdir(parents=True, exist_ok=True)
            Path(job["path_txt"]).write_text(str(dst), encoding="utf-8")
        _write(job["result"], {"ok": True, "mode": mode, "msg": note, "dst": str(dst)})
        L("완료")
        _launch(job, dst)
        return True
    except Exception as e:  # noqa: BLE001
        L(f"실패: {e!r} — 되돌리는 중")
        try:
            if mode in ("flatten", "move"):
                src.mkdir(parents=True, exist_ok=True)
                for name, t in reversed(moved):
                    if t.exists():
                        shutil.move(str(t), str(src / name))
                if mode == "move" and not any(dst.iterdir() if dst.exists() else []):
                    try:
                        dst.rmdir()
                    except OSError:
                        pass
            elif mode == "copy":
                for c in created:
                    shutil.rmtree(c, ignore_errors=True) if c.is_dir() else c.unlink(missing_ok=True)
        except Exception as e2:  # noqa: BLE001
            L(f"되돌리기도 실패: {e2!r}")
        _write(job["result"], {"ok": False, "mode": mode, "msg": f"옮기지 못했어요: {e}. 원래 위치에서 다시 켰어요."})
        _launch(job, src)
        return False


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        sys.exit(0 if run(json.load(f)) else 1)
