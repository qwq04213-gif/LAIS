"""모델을 돌리기 전 사전 검사(LAIS 본체 쪽). 무엇이 준비됐고, 안 됐으면 무엇을 하면 되는지 한국어로 알려요.
'준비됨'은 파일·부품·그래픽카드가 있다는 뜻이지, 이 PC 에서 끝까지 돌아간다는 보장이 아니에요(실제로 만들어 봐야 알아요)."""
import shutil
from pathlib import Path

from . import contracts as K
from . import manager as M

MIN_VRAM_MB = 9500
MIN_DISK_GB = 25           # PyTorch·kaolin·모델 합쳐 약 15GB + 여유


def check(root, gpu=None, deep=True, log=None, engine="sith"):
    """gpu: 본체가 잰 그래픽카드 상태({used_mb, total_mb}) 또는 None. deep=True 면 worker 를 띄워 안쪽까지 봐요.
    돌려주는 값: {"ready", "stage"(wsl/install/models/ok), "checks": [{id, ok, text, fix, info?}], "worker": …}"""
    C = []
    add = lambda i, ok, text, fix="", **kw: C.append({"id": i, "ok": bool(ok), "text": text, "fix": "" if ok else fix, **kw})
    w = M.wsl_status()
    add("wsl", w["wsl"] and w["distro"] and w["version2"], w["text"], w["fix"])
    if gpu and gpu.get("total_mb"):
        free = gpu["total_mb"] - gpu.get("used_mb", 0)
        add("gpu", gpu["total_mb"] >= MIN_VRAM_MB, f"그래픽카드 전체 메모리 {gpu['total_mb'] / 1024:.1f}GB · 지금 쓸 수 있는 양 {free / 1024:.1f}GB",
            "10GB 이상을 권장해요. 그보다 작으면 격자를 낮춰도 실패할 수 있어요.")
    else:
        add("gpu", False, "NVIDIA 그래픽카드를 찾지 못했어요.", "NVIDIA 그래픽카드와 최신 드라이버가 필요해요.")
    try:
        free_gb = shutil.disk_usage(Path(root)).free / 2 ** 30
        C.append({"id": "disk", "ok": True, "info": True, "text": f"LAIS 드라이브 여유 공간 {free_gb:.0f}GB — 인체 3D 환경은 WSL(보통 C 드라이브)에 약 {MIN_DISK_GB}GB 를 써요."})
    except OSError:
        pass
    stage, worker = "wsl", None
    if C[0]["ok"]:
        inst = M.installed(root)
        add("install", inst, "인체 3D 기본 환경(파이썬·SiTH 코드)" + (" 설치됨" if inst else " 아직 설치 안 됨"), "[설치 시작] 을 눌러 주세요(약 15GB · 20~40분).")
        if engine == "econ":
            ei = M.installed(root, "econ")
            add("install_econ", ei, "ECON 환경" + (" 설치됨" if ei else " 아직 설치 안 됨"), "ICON 계정을 넣고 [ECON 설치 시작] 을 눌러 주세요(약 25GB · 1시간 남짓, PyTorch3D 컴파일 포함).")
            inst = inst and ei
        stage = "install"
        if inst and deep:
            h = M.start(root, log=log)
            if not h:
                add("worker", False, "인체 3D 프로그램(worker)을 띄우지 못했어요.", "logs\\human3d-worker.log 를 확인해 주세요. WSL 을 다시 시작(wsl --shutdown)하면 풀릴 때가 있어요.")
            else:
                add("worker", h.get("api") == K.API_VERSION, f"worker 실행 중 (판 {h.get('version')})", "LAIS 와 worker 의 판이 달라요. LAIS 를 다시 시작해 주세요.")
                try:
                    worker = M.Client(M.STATE["port"]).preflight(engine)
                    for c in worker.get("checks", []):
                        C.append({**c, "id": "w_" + c["id"]})
                    stage = "ok" if worker.get("ready") else "models"
                except Exception as e:  # noqa: BLE001
                    add("worker_pf", False, f"worker 점검 실패: {e}", "")
    ready = stage == "ok" and all(c["ok"] for c in C if not c.get("info") and c["id"] not in ("gpu", "w_vram", "w_vram_free", "w_smplx")) and bool(worker and worker.get("ready"))
    out = {"ready": ready, "stage": stage, "checks": C, "worker": {k: worker.get(k) for k in ("provider", "title", "verified", "versions", "paths", "gpu")} if worker else None,
           "verified": bool(worker and worker.get("verified")),
           "note": "SiTH 의 공식 시험 환경은 24GB 그래픽카드예요. 10~12GB 에서는 메모리를 아끼는 방식으로 돌리지만, 실제로 끝까지 돌아가는지는 이 PC 에서 한 번 만들어 봐야 알 수 있어요."}
    out["engine"] = engine
    out["modes"] = (worker or {}).get("modes") if worker else None
    out["drop"] = str(M.drop_dir(root))
    out["genders"] = (worker or {}).get("genders") if worker else None      # {male, female, neutral: 파일이 있는지} — 화면이 없는 성별을 못 고르게 해요
    out["env"] = (worker or {}).get("env") if worker else None
    if any(c["id"] == "w_smplx" and not c["ok"] for c in C):
        out["smplx"] = {"url": "https://smpl-x.is.tue.mpg.de", "folder": str(M.drop_dir(root)),
                        "files": [f"SMPLX_{g.upper()}.npz" for g, ok_ in ((worker or {}).get("genders") or {"neutral": False, "female": False, "male": False}).items() if not ok_],
                        "partial": any(((worker or {}).get("genders") or {}).values()),
                        "text": "SMPL-X 몸 모델은 만든 곳(막스 플랑크 연구소)에 가입하고 이용 약관에 동의해야 받을 수 있어서 자동으로 받지 않아요. "
                                "① 사이트에 가입·로그인 → ② Download 에서 'SMPL-X v1.1 (NPZ+PKL)' 받기 → ③ 압축을 풀어 models\\smplx 안의 SMPLX_FEMALE.npz · SMPLX_MALE.npz · SMPLX_NEUTRAL.npz 를 아래 폴더(LAIS 폴더 안)에 넣기 → ④ [다시 확인]. "
                                "LAIS 가 알아서 인체 3D 환경으로 옮겨요."}
    return out
