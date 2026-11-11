# 로컬 AI 스튜디오 허브 — 인체 3D(시험판, 4.9~4.9.3) 남은 파일 정리
# 인체 3D 기능은 4.9.4 에서 뺐어요. 그때 WSL(우분투) 안과 LAIS 폴더에 깔린 것을 찾아서, 사용자가 고른 것만 지워요.
#   · 지우기 전에 화면에서 꼭 확인을 받아요. 결과물(outputs\3D-human)·직접 넣은 SMPL-X 파일·우분투 전체는 기본으로 고르지 않아요.
#   · 지우는 곳은 아래에 정해 둔 경로뿐이에요(다른 경로는 받지 않아요).
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

H3C_DISTRO = "Ubuntu-22.04"
H3C_HOME = "/root/lais-human3d"          # 인체 3D 설치 스크립트가 쓰던 곳(WSL 안)
H3C_PIP = "/root/.cache/pip"
H3C_CUDA_PKGS = ("cuda-compiler-12-1", "cuda-cudart-dev-12-1", "cuda-driver-dev-12-1", "cuda-libraries-dev-12-1")
H3C_LOCK = threading.Lock()
H3C_JOB = {"state": "idle", "msg": "", "results": []}


def h3c_local():
    """시험용: WSL 대신 이 PC 의 bash 로, 정해 둔 시험 폴더에서 돌려요(H3CLEAN_LOCAL=1)."""
    return os.environ.get("H3CLEAN_LOCAL") == "1"


def h3c_paths():
    """WSL 안의 경로들(시험에서는 바꿔 쓸 수 있어요)."""
    if h3c_local():
        return os.environ["H3CLEAN_HOME"], os.environ.get("H3CLEAN_PIP", "/nonexistent-pip")
    return H3C_HOME, H3C_PIP


def h3c_sh(script, timeout=120, env=None):
    """WSL(우분투) 안에서 root 로 bash 스크립트를 돌려요. 돌려주는 값: (종료 코드, 출력)."""
    if h3c_local():
        cmd = ["bash", "-c", script]
    elif os.name == "nt":
        cmd = ["wsl.exe", "-d", H3C_DISTRO, "-u", "root", "--", "bash", "-c", script]
    else:
        return 127, "윈도우가 아니에요"
    try:
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=dict(os.environ, **(env or {})), **kw)
        return r.returncode, (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "WSL 이 없어요"
    except subprocess.TimeoutExpired:
        return 124, "시간이 너무 오래 걸려 멈췄어요"


def h3c_distro():
    """Ubuntu-22.04 가 WSL 에 있는지."""
    if h3c_local():
        return os.environ.get("H3CLEAN_DISTRO", "1") == "1"
    if os.name != "nt":
        return False
    try:
        r = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, timeout=20, creationflags=0x08000000)
        out = r.stdout or b""
        text = out.decode("utf-16-le", "replace") if out[:200].count(b"\0") > 20 else out.decode("utf-8", "replace")
        return any(ln.strip().replace("\0", "").lower() == H3C_DISTRO.lower() for ln in text.splitlines())
    except Exception:  # noqa: BLE001
        return False


def h3c_lais_paths():
    """LAIS 폴더 안의 인체 3D 흔적."""
    return {"lais_code": [ROOT / "engine" / "human3d", HUB / "human3d"], "logs": [LOGS / "human3d-worker.log"],
            "smplx": [ROOT / "models" / "human3d"], "results": [OUT / "3D-human"]}


def h3c_size(p):
    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return dir_size(p) if p.is_dir() else 0


def h3c_scan():
    """남은 것 찾기. 돌려주는 값: {items: [{id, label, note, bytes, found, default, danger}], wsl, distro}."""
    items = []
    lp = h3c_lais_paths()
    nres = sum(1 for d in (OUT / "3D-human").iterdir() if d.is_dir()) if (OUT / "3D-human").is_dir() else 0
    for key, label, note, default in (("lais_code", "LAIS 폴더에 남은 인체 3D 코드", "업데이트가 지우고 남은 빈 폴더·임시 파일이에요.", True),
                                      ("logs", "인체 3D 프로그램 기록", "logs\\human3d-worker.log", True),
                                      ("smplx", "SMPL-X 넣는 폴더 (직접 받아 넣은 파일)", "다른 곳에 다시 쓸 수 있는 파일이라 기본으로 고르지 않아요.", False),
                                      ("results", f"인체 3D 결과물 ({nres}개 작업)", "outputs\\3D-human — 만든 결과물이라 기본으로 고르지 않아요. 지우면 되돌릴 수 없어요.", False)):
        b = sum(h3c_size(p) for p in lp[key])
        found = any(Path(p).exists() for p in lp[key])
        items.append({"id": key, "label": label, "note": note, "bytes": b, "found": found, "default": default and found, "danger": key == "results",
                      "paths": [str(p) for p in lp[key] if Path(p).exists()]})
    distro = h3c_distro()
    wsl = {"distro": distro, "checked": False}
    if distro:
        home, pip = h3c_paths()
        pk = " ".join(H3C_CUDA_PKGS)
        script = (f'H="{home}"; P="{pip}"; '
                  'if [ -d "$H" ]; then echo "HOME $(du -sb "$H" 2>/dev/null | cut -f1)"; else echo "HOME -"; fi; '
                  'if [ -d "$P" ]; then echo "PIP $(du -sb "$P" 2>/dev/null | cut -f1)"; else echo "PIP -"; fi; '
                  f'for p in {pk}; do dpkg -s "$p" >/dev/null 2>&1 && echo "CUDA $p"; done; '
                  '[ -d /usr/local/cuda-12.1 ] && echo "CUDADIR $(du -sb /usr/local/cuda-12.1 2>/dev/null | cut -f1)"; '
                  'pgrep -f "lais-human3d.*worker.app|worker.app.*lais-human3d" >/dev/null && echo RUNNING; true')
        code, out = h3c_sh(script, timeout=180)
        val = {}
        cuda = []
        for ln in out.splitlines():
            p = ln.split()
            if len(p) >= 2 and p[0] in ("HOME", "PIP", "CUDADIR"):
                val[p[0]] = int(p[1]) if p[1].isdigit() else None
            elif len(p) == 2 and p[0] == "CUDA":
                cuda.append(p[1])
        wsl.update(checked=code == 0, running="RUNNING" in out, error=None if code == 0 else out.strip()[-300:])
        items.insert(0, {"id": "wsl_env", "label": "인체 3D 환경 (WSL 안)", "note": f"{home} — 파이썬 환경·SiTH·ECON·받은 모델(Sapiens·SMPL-X 사본 포함)",
                         "bytes": val.get("HOME") or 0, "found": val.get("HOME") is not None, "default": val.get("HOME") is not None, "danger": False})
        items.insert(1, {"id": "pip_cache", "label": "설치 때 받은 임시 파일 (WSL 안 pip 캐시)", "note": pip, "bytes": val.get("PIP") or 0,
                         "found": val.get("PIP") is not None, "default": val.get("PIP") is not None, "danger": False})
        items.insert(2, {"id": "cuda", "label": "CUDA 12.1 컴파일러 (WSL 안)", "note": "인체 3D 설치가 넣은 꾸러미만 지워요: " + (", ".join(cuda) or "없음"),
                         "bytes": val.get("CUDADIR") or 0, "found": bool(cuda), "default": bool(cuda), "danger": False, "pkgs": cuda})
        items.append({"id": "ubuntu", "label": f"우분투({H3C_DISTRO}) 통째로 지우기", "danger": True, "found": True, "default": False, "bytes": None,
                      "note": "인체 3D 를 위해 설치한 우분투 전체를 지워요(WSL 의 'unregister'). 우분투 안의 다른 파일·프로그램도 모두 사라져요. 다른 용도로 쓰고 있다면 고르지 마세요."})
    return {"items": items, "wsl": wsl, "job": H3C_JOB}


def h3c_clean(p):
    """고른 것만 지워요. p = {items: [...], confirm: True, confirm_ubuntu: True(우분투를 고른 경우)}."""
    ids = [x for x in (p.get("items") or []) if x in ("wsl_env", "pip_cache", "cuda", "lais_code", "logs", "smplx", "results", "ubuntu")]
    if not ids:
        return {"error": "지울 것을 골라 주세요."}
    if p.get("confirm") is not True:
        return {"error": "확인을 받지 못해서 지우지 않았어요."}
    if "ubuntu" in ids and p.get("confirm_ubuntu") is not True:
        return {"error": "우분투 전체를 지우려면 한 번 더 확인이 필요해요."}
    if not H3C_LOCK.acquire(blocking=False):
        return {"error": "이미 정리하고 있어요."}
    res = []
    try:
        H3C_JOB.update(state="running", msg="정리하는 중", results=res)
        home, pip = h3c_paths()
        if "ubuntu" in ids:                  # 우분투를 통째로 지우면 그 안의 것은 따로 지울 필요가 없어요
            ids = [x for x in ids if x not in ("wsl_env", "pip_cache", "cuda")]
        if any(x in ids for x in ("wsl_env", "pip_cache", "cuda", "ubuntu")) and h3c_distro():
            h3c_sh(f'pkill -f "lais-human3d.*worker.app|worker.app.*lais-human3d" 2>/dev/null; sleep 1; true', timeout=30)      # 돌고 있던 인체 3D 프로그램부터 꺼요
        for key in ids:
            ok, msg, freed = True, "", 0
            try:
                if key in ("wsl_env", "pip_cache"):
                    target = home if key == "wsl_env" else pip
                    if not (target.rstrip("/").endswith("/lais-human3d") or target.rstrip("/").endswith("/.cache/pip")):
                        raise RuntimeError("정해 둔 경로가 아니라서 지우지 않았어요: " + target)
                    code, out = h3c_sh(f'T="{target}"; S=$(du -sb "$T" 2>/dev/null | cut -f1); rm -rf -- "$T" && [ ! -e "$T" ] && echo "FREED ${{S:-0}}"', timeout=900)
                    m = re.search(r"FREED (\d+)", out)
                    ok, freed = code == 0 and m is not None, int(m.group(1)) if m else 0
                    msg = "지웠어요." if ok else "지우지 못했어요: " + out.strip()[-200:]
                elif key == "cuda":
                    pk = " ".join(H3C_CUDA_PKGS)
                    code, out = h3c_sh(f'S=$(du -sb /usr/local/cuda-12.1 2>/dev/null | cut -f1); L=""; for p in {pk}; do dpkg -s "$p" >/dev/null 2>&1 && L="$L $p"; done; '
                                       'if [ -n "$L" ]; then DEBIAN_FRONTEND=noninteractive apt-get remove -y $L >/dev/null 2>&1 || exit 3; fi; echo "FREED ${S:-0}"', timeout=900)
                    m = re.search(r"FREED (\d+)", out)
                    ok, freed = code == 0, int(m.group(1)) if m else 0
                    msg = "CUDA 12.1 컴파일러 꾸러미를 지웠어요." if ok else "지우지 못했어요(apt-get remove 실패)."
                elif key == "ubuntu":
                    if h3c_local():
                        code, out = (0, "") if os.environ.get("H3CLEAN_UNREGISTER_OK", "1") == "1" else (1, "실패")
                        if code == 0:
                            os.environ["H3CLEAN_DISTRO"] = "0"
                    else:
                        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
                        r = subprocess.run(["wsl.exe", "--unregister", H3C_DISTRO], capture_output=True, timeout=600, **kw)
                        code = r.returncode
                    ok = code == 0
                    msg = f"우분투({H3C_DISTRO})를 지웠어요. WSL 기능 자체는 윈도우에 남아 있어요." if ok else "우분투를 지우지 못했어요."
                else:
                    for t in h3c_lais_paths()[key]:
                        t = Path(t)
                        allowed = [ROOT / "engine" / "human3d", HUB / "human3d", LOGS / "human3d-worker.log", ROOT / "models" / "human3d", OUT / "3D-human"]
                        if t not in allowed:
                            raise RuntimeError("정해 둔 경로가 아니라서 지우지 않았어요: " + str(t))
                        if t.exists():
                            freed += h3c_size(t)
                            (shutil.rmtree(t) if t.is_dir() else t.unlink())
                    msg = "지웠어요."
            except Exception as e:  # noqa: BLE001
                ok, msg = False, f"지우지 못했어요: {e}"
            res.append({"id": key, "ok": ok, "msg": msg, "freed": freed})
            log("[인체 3D 정리]", key, "성공" if ok else "실패", msg)
        H3C_JOB.update(state="done", msg="정리를 마쳤어요.")
        return {"ok": all(r["ok"] for r in res), "results": res, "freed": sum(r["freed"] for r in res)}
    finally:
        H3C_LOCK.release()
