import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, os, pathlib, tempfile, time
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
home = pathlib.Path(tempfile.mkdtemp(prefix="fakehome-"))
os.environ.pop("HF_HUB_CACHE", None); os.environ.pop("TORCH_HOME", None); os.environ.pop("PIP_CACHE_DIR", None); os.environ.pop("HF_HOME", None)
pathlib.Path.home = classmethod(lambda c: home)
os.environ.pop("LOCALAPPDATA", None)
hf = home / ".cache" / "huggingface" / "hub"; (hf / "models--a" / "snapshots" / "s").mkdir(parents=True); (hf / "models--a" / "blobs").mkdir(); (hf / "models--a" / "blobs" / "b1").write_bytes(b"B" * 4000)
os.symlink("../../blobs/b1", hf / "models--a" / "snapshots" / "s" / "w.bin")
(home / ".cache" / "huggingface" / "token").write_text("secret")
(home / ".cache" / "torch" / "hub").mkdir(parents=True); (home / ".cache" / "torch" / "hub" / "m.pth").write_bytes(b"T" * 2000)
(home / ".cache" / "pip").mkdir(parents=True, exist_ok=True); (home / ".cache" / "pip" / "x").write_bytes(b"P" * 1000)
s = req("/api/cachein"); assert not s["on"] and {i["key"]: i["src_size"] for i in s["items"]} == {"hf": 4000, "torch": 2000, "pip": 1000}, s; ok("status lists the three caches at their real places with sizes")
assert "HF_HUB_CACHE" not in os.environ; ok("env untouched while off")
r = req("/api/cachein/move", {})
assert r["ok"]
for _ in range(100):
    if req("/api/cachein")["state"] in ("done", "error"): break
    time.sleep(0.1)
s = req("/api/cachein"); assert s["state"] == "done", s; ok("move finished: " + s["msg"])
d = {i["key"]: i for i in s["items"]}; assert d["hf"]["dst_size"] == 4000 and d["torch"]["dst_size"] == 2000 and d["pip"]["dst_size"] == 1000; ok("files copied to engine/cache (sizes match)")
assert (pathlib.Path(d["hf"]["dst"]) / "models--a" / "snapshots" / "s" / "w.bin").is_symlink(); ok("symlinks inside the HuggingFace cache preserved")
assert not hf.exists() and not (home / ".cache" / "torch").exists() and not (home / ".cache" / "pip").exists(); ok("originals removed after verified copy")
assert (home / ".cache" / "huggingface" / "token").read_text() == "secret"; ok("HuggingFace login token left alone")
assert os.environ["HF_HUB_CACHE"] == d["hf"]["dst"] and os.environ["TORCH_HOME"] == d["torch"]["dst"] and os.environ["PIP_CACHE_DIR"] == d["pip"]["dst"]; ok("environment points at the new places (applies to ComfyUI/pip started by the studio)")
rep = req("/api/disk"); k = {i["key"]: i for i in rep["items"]}
assert k["cache_in"]["bytes"] == 7000 and rep["listed"] == rep["used"]; ok("disk check counts the new folder; rows still add up to the total")
assert not any(i["key"] == "x_hf" and i["bytes"] for i in rep["ext"]); ok("old location no longer reported as external")
c = req("/api/clean", {"what": "cache_in"}); assert c["freed"] == 7000 and hub.dir_size(hub.CACHE_IN) == 0 and (hub.CACHE_IN / "torch").is_dir(); ok("clean empties the cache contents but keeps the top folders")
req("/api/cachein", {"on": False}); assert "HF_HUB_CACHE" not in os.environ and "TORCH_HOME" not in os.environ; ok("turning off restores the original environment")
os.environ["HF_HUB_CACHE"] = "/user/own"; req("/api/cachein", {"on": True}); assert os.environ["HF_HUB_CACHE"] != "/user/own"; req("/api/cachein", {"on": False}); assert os.environ["HF_HUB_CACHE"] == "/user/own"; ok("user's own setting is restored, not erased"); os.environ.pop("HF_HUB_CACHE")
hub.JOBS["zz"] = {"state": "running"}; assert "진행 중" in req("/api/cachein/move", {})["error"]; del hub.JOBS["zz"]; ok("refused while a job runs")
# 다시 시작하면 이전 스튜디오가 정한 환경 값이 그대로 넘어온다 → 그걸 '바깥 캐시'로 착각해 이중으로 세면 안 된다
import subprocess, shutil
rs = pathlib.Path(tempfile.mkdtemp(prefix="restart-")); (rs / "engine/cache/huggingface/hub/models--x").mkdir(parents=True); (rs / "engine/cache/huggingface/hub/models--x/f").write_bytes(b"x" * 500)
env = dict(os.environ, STUDIO_ROOT=str(rs), HF_HUB_CACHE=str(rs / "engine/cache/huggingface/hub"), PYTHONPATH=BASE + "/LocalAI-Studio/hub", HOME=str(home))
out = subprocess.run([sys.executable, "-c", "import hub,json;r=hub.disk_report();print(json.dumps([[e['key'],e['path']] for e in r['ext']]),r['used'],r['listed'],hub.ORIG_ENV['HF_HUB_CACHE'])"], env=env, capture_output=True, text=True).stdout.split()
assert out[-1] == "None" and "huggingface" not in out[0] and out[1] == out[2], out; ok("after a restart the moved cache is counted once (not also as an outside cache)")
print("ALL OK")
