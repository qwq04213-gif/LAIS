"""4.9.4: 인체 3D 시험판 걷어 내기 — ① 4.9.3 이 깔린 폴더에 업데이트하면 인체 3D 코드(30개)가 백업 후 지워지고 기존 3D 만들기는 남는지,
② '인체 3D 남은 파일' 정리가 고른 것만 지우는지(확인 없이는 안 지움 · 결과물·SMPL-X·우분투는 기본으로 안 고름 · 정해진 경로만), ③ 저장 공간 화면.
WSL 대신 이 PC 의 bash 로 정해 둔 시험 폴더에서 돌려요(H3CLEAN_LOCAL=1) — 실제 WSL·우분투 지우기는 미검증."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import base64, io, json, os, subprocess, sys, tempfile, zipfile
from pathlib import Path
os.environ["TEST_HUB_PORT"] = "17956"
T = Path(tempfile.mkdtemp())
WH = T / "wsl/root/lais-human3d"; WP = T / "wsl/root/.cache/pip"
os.environ.update(H3CLEAN_LOCAL="1", H3CLEAN_HOME=str(WH), H3CLEAN_PIP=str(WP), H3CLEAN_DISTRO="1")
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))

# ① 4.9.3 설치 폴더 → 이번 업데이트
inst = T / "inst"; inst.mkdir()
tar = subprocess.run(["git", "-C", BASE, "archive", "d8237d7", "LocalAI-Studio"], capture_output=True, check=True).stdout
subprocess.run(["tar", "-x", "-C", str(inst)], input=tar, check=True)
R = inst / "LocalAI-Studio"; (R / "engine/human3d/worker/__pycache__").mkdir(parents=True, exist_ok=True); (R / "engine/human3d/worker/__pycache__/app.cpython-310.pyc").write_bytes(b"x")
h3_files = sorted(str(p.relative_to(R)).replace(os.sep, "/") for p in R.rglob("*") if p.is_file() and ("human3d" in str(p.relative_to(R)) or p.name == "71-m3d-human.js") and "__pycache__" not in str(p))
assert len(h3_files) == 30 and (R / "hub/server/28_human3d.py").is_file(), h3_files
sys.path.insert(0, BASE + "/release-tools"); import build_update as BU, apply_update as AU
files = BU.collect(Path(BASE) / "LocalAI-Studio")
assert not [f for f in files if "human3d" in f and "h3clean" not in f] and "hub/server/29_h3clean.py" in files and "hub/server/27_m3d.py" in files and "hub/photoproj.py" in files
assert set(h3_files) <= set(AU.OBSOLETE), set(h3_files) - set(AU.OBSOLETE)
zb = io.BytesIO()
with zipfile.ZipFile(zb, "w") as z:
    man = {"format": 1, "version": "4.9.4", "notes": ["시험"], "files": [{"path": k, "sha256": BU.sha(v), "size": len(v)} for k, v in files.items()]}
    z.writestr("manifest.json", json.dumps(man)); [z.writestr("files/" + k, v) for k, v in files.items()]
AU.studio_running = lambda: False      # 시험용 가짜 허브가 떠 있어서
assert AU.main([str(R), "--yes"], payload=zipfile.ZipFile(io.BytesIO(zb.getvalue()))) == 0
left = [f for f in h3_files if (R / f).exists()]
assert not left and (R / "hub/server/27_m3d.py").is_file() and (R / "hub/photoproj.py").is_file() and (R / "hub/server/29_h3clean.py").is_file(), left
bk = sorted((R / "backup").iterdir())[-1]; assert (bk / "hub/server/28_human3d.py").is_file() and (bk / "engine/human3d/worker/app.py").is_file()      # 지운 것은 백업에 있어요(되돌리기 가능)
html = (R / "hub/web/index.html").read_text(encoding="utf-8"); assert 'data-v="m3d"' in html and 'data-v="human3d"' not in html and 'id="h3c-scan"' in html
assert not any("human3d" in p.read_text(encoding="utf-8") for p in (R / "hub/server").glob("*.py") if p.name != "29_h3clean.py") and (R / "VERSION.txt").read_text() == (Path(BASE) / "LocalAI-Studio/VERSION.txt").read_text()
ok("update over a 4.9.3 install: all 30 human-3D files backed up then removed, original 3D (m3d) kept, no server file still imports human3d")

# ② 정리 기능
(WH / "venv/lib").mkdir(parents=True); (WH / "venv/lib/big.bin").write_bytes(b"0" * 300_000); (WH / "SiTH/fit.py").parent.mkdir(parents=True); (WH / "SiTH/fit.py").write_text("x")
WP.mkdir(parents=True); (WP / "w.whl").write_bytes(b"0" * 50_000)
(TMP / "engine/human3d/worker").mkdir(parents=True); (TMP / "engine/human3d/worker/x.pyc").write_bytes(b"0" * 1000)
(TMP / "models/human3d/smplx").mkdir(parents=True); (TMP / "models/human3d/smplx/SMPLX_FEMALE.npz").write_bytes(b"0" * 2000)
(TMP / "outputs/3D-human/20261110-101010-abcd/result").mkdir(parents=True); (TMP / "outputs/3D-human/20261110-101010-abcd/result/human.glb").write_bytes(b"0" * 3000)
(TMP / "logs").mkdir(exist_ok=True); (TMP / "logs/human3d-worker.log").write_text("log")
S = get("/api/h3clean"); I = {i["id"]: i for i in S["items"]}
assert S["wsl"]["distro"] and S["wsl"]["checked"] and I["wsl_env"]["found"] and I["wsl_env"]["default"] and I["wsl_env"]["bytes"] >= 300_000 and I["pip_cache"]["default"] and I["pip_cache"]["bytes"] >= 50_000
assert not I["cuda"]["found"] and I["lais_code"]["default"] and I["logs"]["default"] and I["smplx"]["found"] and not I["smplx"]["default"] and I["results"]["found"] and not I["results"]["default"] and I["results"]["danger"]
assert "1개 작업" in I["results"]["label"] and I["ubuntu"]["danger"] and not I["ubuntu"]["default"] and "다른 파일·프로그램도" in I["ubuntu"]["note"]
assert "확인" in post("/api/h3clean", {"items": ["wsl_env"]})["error"] and WH.exists()                      # 확인 없이는 안 지움
assert "한 번 더" in post("/api/h3clean", {"items": ["ubuntu"], "confirm": True})["error"]                 # 우분투는 두 번 확인
assert "골라" in post("/api/h3clean", {"items": ["../../etc", "x"], "confirm": True})["error"]              # 모르는 항목은 받지 않음
r = post("/api/h3clean", {"items": [i["id"] for i in S["items"] if i["default"]], "confirm": True})
assert r["ok"] and r["freed"] >= 350_000 and not WH.exists() and not WP.exists() and not (TMP / "engine/human3d").exists() and not (TMP / "logs/human3d-worker.log").exists(), r
assert (TMP / "models/human3d/smplx/SMPLX_FEMALE.npz").is_file() and (TMP / "outputs/3D-human/20261110-101010-abcd/result/human.glb").is_file()      # 고르지 않은 것은 그대로
S = get("/api/h3clean"); I = {i["id"]: i for i in S["items"]}; assert not I["wsl_env"]["found"] and not I["lais_code"]["found"] and I["results"]["found"]
os.environ["H3CLEAN_HOME"] = str(T / "wsl/root/someone-else"); (T / "wsl/root/someone-else").mkdir(parents=True)
r = post("/api/h3clean", {"items": ["wsl_env"], "confirm": True}); assert not r["ok"] and "정해 둔 경로" in r["results"][0]["msg"] and (T / "wsl/root/someone-else").exists()      # 정해진 경로가 아니면 안 지움
os.environ["H3CLEAN_HOME"] = str(WH)
r = post("/api/h3clean", {"items": ["results", "smplx"], "confirm": True}); assert r["ok"] and not (TMP / "outputs/3D-human").exists() and not (TMP / "models/human3d").exists() and (TMP / "outputs").is_dir()
r = post("/api/h3clean", {"items": ["ubuntu", "wsl_env"], "confirm": True, "confirm_ubuntu": True}); assert r["ok"] and [x["id"] for x in r["results"]] == ["ubuntu"] and "WSL 기능 자체는" in r["results"][0]["msg"]
S = get("/api/h3clean"); assert not S["wsl"]["distro"] and not [i for i in S["items"] if i["found"]]
ok("cleanup: finds WSL env / pip cache / LAIS leftovers with sizes; deletes only what was chosen and confirmed; results·SMPL-X·Ubuntu never pre-selected; Ubuntu needs a 2nd confirmation; fixed paths only")

# ③ 화면
os.environ["H3CLEAN_DISTRO"] = "1"; (WH / "venv").mkdir(parents=True); (WH / "venv/a.bin").write_bytes(b"0" * 1000)
(TMP / "outputs/3D-human/j1").mkdir(parents=True); (TMP / "outputs/3D-human/j1/a.glb").write_bytes(b"1")
from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1400, "height": 1000}); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B); pg.wait_for_selector("#rail nav button[data-v=setup]")
    assert pg.locator("nav button[data-v=human3d]").count() == 0 and pg.locator("nav button[data-v=m3d]").count() == 1
    pg.click("nav button[data-v=setup]"); pg.click("#setup-nav button[data-pane=disk]"); pg.click("#h3c-scan"); pg.wait_for_selector("#h3c .h3c-list")
    assert pg.is_checked("#h3c input[value=wsl_env]") and not pg.is_checked("#h3c input[value=results]") and not pg.is_checked("#h3c input[value=ubuntu]")
    dialogs = []
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    pg.click("#h3c-go"); pg.wait_for_selector("#h3c-res .m3-checks li", timeout=30000)
    assert len(dialogs) == 1 and "인체 3D 환경" in dialogs[0] and "되돌릴 수 없어요" in dialogs[0] and not WH.exists() and (TMP / "outputs/3D-human/j1/a.glb").is_file()
    assert "정리했어요" in pg.inner_text("#h3c-st")
    b.close()
assert not errs, errs
ok("storage screen: no human-3D menu left, old 3D menu kept, leftovers listed with safe defaults, one confirmation lists what will be deleted")
print("ALL OK")
