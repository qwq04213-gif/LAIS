"""4.3.1: 모델을 지워도 용량이 안 줄던 문제 — 지우기 전에 엔진이 파일을 놓게 하고(ComfyUI /free, Ollama 내리기),
Ollama 가 못 지우고 남긴 조각 정리, 그래도 안 비워지면 알려 주기, 저장 공간의 '대화 모델이 남긴 조각' 정리."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, urllib.request
os.environ["TEST_HUB_PORT"] = "17998"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
hub.RELEASE_WAIT = 0
CAT = {m["id"]: m for m in json.loads((Path(BASE) / "LocalAI-Studio/hub/models.json").read_text(encoding="utf-8"))["image"]}
files_of = lambda i: [f["dir"] + "/" + (f.get("name") or f["url"].rsplit("/", 1)[1]) for f in CAT[i]["files"]]
def touch(*fs, size=1):
    for f in fs:
        (M / f).parent.mkdir(parents=True, exist_ok=True)
        with open(M / f, "wb") as h: h.truncate(size)

# 1) 이미지 모델: 지우기 전에 ComfyUI 가 모델을 내려요, 비운 용량을 알려 줘요
touch(*files_of("depth-anything-3"), size=5000)
f0 = STATE["freed"]
r = post("/api/catalog/remove", {"id": "depth-anything-3"}); assert r["ok"] and r["freed"] == 5000 and r["pending"] == 0, r
assert STATE["freed"] == f0 + 1 and not (M / files_of("depth-anything-3")[0]).exists()
touch("loras/big.safetensors", size=3000)
r = post("/api/delete", {"dir": "loras", "name": "big.safetensors"}); assert r["ok"] and r["freed"] == 3000 and STATE["freed"] == f0 + 2, r
ok("image model delete: ComfyUI unloads first (/free), freed size reported")

# 2) 지웠는데 디스크 여유가 안 늘면(윈도우: 엔진이 파일을 잡고 있음) 알려 줘요
touch("loras/held.safetensors", size=300 << 20)
real = hub._disk_free; hub._disk_free = lambda p: 10 ** 9
r = post("/api/delete", {"dir": "loras", "name": "held.safetensors"}); assert r["ok"] and r["pending"] == 300 << 20 and r["freed"] == 0, r
hub._disk_free = real
ok("space not freed after delete (engine still holds the file) → pending reported so the screen can offer an engine restart")

# 3) 이미지 작업이 도는 중이면 지우지 않아요(쓰는 중인 모델은 지워도 용량이 안 줄어요)
touch("loras/busy.safetensors")
hub.JOBS["busy-x"] = {"state": "running"}
r = post("/api/delete", {"dir": "loras", "name": "busy.safetensors"}); assert "error" in r and "작업이" in r["error"] and (M / "loras/busy.safetensors").exists(), r
del hub.JOBS["busy-x"]
assert post("/api/delete", {"dir": "loras", "name": "busy.safetensors"})["ok"]
ok("no delete while an image job runs (clear message)")

# 4) 대화 모델: 올라가 있으면 먼저 내리고, Ollama 가 못 지우고 남긴 조각은 지워요(다른 모델이 쓰는 조각은 남겨요)
L = hub.LLM_DIR; bl = L / "blobs"; bl.mkdir(parents=True, exist_ok=True)
def man(name, digs):
    p = L / "manifests" / "registry.ollama.ai" / "library" / name.split(":")[0] / name.split(":")[1]; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"config": {"digest": "sha256:" + digs[0]}, "layers": [{"digest": "sha256:" + d} for d in digs[1:]]})); return p
for d, n in (("aa", 10), ("bb", 4000), ("cc", 20)): (bl / ("sha256-" + d)).write_bytes(b"x" * n)
man("keep:1b", ["aa", "cc"]); STATE["ollama_manifest"] = {"venice:old": str(man("venice:old", ["aa", "bb"]))}
g0 = len(GEN)
r = post("/api/delete", {"kind": "ollama", "name": "venice:old"}); assert r["ok"] and r["freed"] == 4000, r
assert not (bl / "sha256-bb").exists() and (bl / "sha256-aa").exists() and (bl / "sha256-cc").exists()
assert not any(x.get("keep_alive") == 0 for x in GEN[g0:])                       # 올라가 있지 않은 모델은 건드리지 않아요
man("testmodel:latest", ["cc"]); STATE["ollama_manifest"]["testmodel:latest"] = str(L / "manifests/registry.ollama.ai/library/testmodel/latest")
r = post("/api/delete", {"kind": "ollama", "name": "testmodel:latest"}); assert r["ok"], r
assert any(x.get("model") == "testmodel:latest" and x.get("keep_alive") == 0 for x in GEN[g0:]) and (bl / "sha256-cc").exists()   # keep:1b 가 같이 써요
ok("chat model delete: unloads a loaded model first, removes pieces only the deleted model used, keeps shared pieces")

# 5) 저장 공간: 어떤 대화 모델도 쓰지 않는 조각 표시·정리(확인 후)
(bl / "sha256-dd").write_bytes(b"x" * 700); (bl / "sha256-ee-partial").write_bytes(b"x" * 300)
old = time.time() - 3600
for n in ("sha256-dd", "sha256-ee-partial"): os.utime(bl / n, (old, old))
(bl / "sha256-ff-partial").write_bytes(b"x" * 50)                                 # 방금 받던 조각은 빼요
r = get("/api/disk"); assert r["llm_left"] == {"n": 2, "bytes": 1000}, r["llm_left"]
hub.TASKS.append({"kind": "ollama", "state": "running", "label": "x"})
assert "error" in post("/api/clean", {"what": "llm_orphans"}) and get("/api/disk")["llm_left"]["n"] == 0
hub.TASKS.pop()
r = post("/api/clean", {"what": "llm_orphans"}); assert r["ok"] and r["freed"] == 1000, r
assert (bl / "sha256-aa").exists() and (bl / "sha256-ff-partial").exists() and not (bl / "sha256-dd").exists()
(L / "manifests/registry.ollama.ai/library/keep/1b").write_text("{broken")       # 목록을 못 읽으면 아무것도 지우지 않아요
assert get("/api/disk")["llm_left"]["n"] == 0
ok("storage: leftover chat-model pieces listed and cleaned on request; skipped while pulling, recent pieces and unreadable lists keep everything")
print("ALL OK")
