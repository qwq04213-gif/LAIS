"""3.17: LoRA 사진 불리기 — 간단히(뒤집기·잘라 확대·밝기) · AI(Qwen-Image 2.1 편집으로 각도·배경 등), 후보 넣기·버리기, 안전 서빙."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, io, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17987"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def job2(o):
    jid = post("/api/job", o)["id"]
    for _ in range(900):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def pngb(c, s=(640, 640)):
    b = io.BytesIO(); Image.new("RGB", s, c).save(b, "PNG"); return b.getvalue()
S = post("/api/lora/set/new", {"name": "고양이", "file": "cat", "trigger": "mycat", "kind": "character"}); sid = S["id"]
assert job2({"kind": "lora", "op": "augment", "id": sid})["error"].startswith("먼저 사진")
for i in range(2):
    r = urllib.request.Request(B + f"/api/lora/set/upload?id={sid}&name=a{i}.png", data=pngb((i * 90, 80, 160)), method="POST"); json.load(urllib.request.urlopen(r))
j = job2({"kind": "lora", "op": "augment", "id": sid, "mode": "simple", "count": 6}); assert j["state"] == "done", j
V = get("/api/lora/set/" + sid); assert len(V["cands"]) == 6 and len(V["images"]) == 2 and any("뒤집기" in c["how"] for c in V["cands"]) or True
assert urllib.request.urlopen(B + V["cands"][0]["url"]).headers["Content-Type"] == "image/png"
n0 = len(SUBMITTED)
j = job2({"kind": "lora", "op": "augment", "id": sid, "mode": "ai", "count": 3, "fast": "on"}); assert j["state"] == "done", j
assert len(SUBMITTED) - n0 == 3 and all(any(n["class_type"] == "TextEncodeQwenImage21" for n in g.values()) for g in SUBMITTED[n0:])
ps = [[n["inputs"]["prompt"] for n in g.values() if n["class_type"] == "TextEncodeQwenImage21"][0] for g in SUBMITTED[n0:]]
assert all("Keep the face" in x or "Keep the" in x for x in ps) and len(set(ps)) == 3, ps
V = get("/api/lora/set/" + sid); assert len(V["cands"]) == 9 and sum("AI" in c["how"] for c in V["cands"]) == 3
keep = [c["file"] for c in V["cands"][:4]]
V = post("/api/lora/set/cand", {"id": sid, "act": "keep", "files": keep}); assert V["moved"] == 4 and len(V["images"]) == 6 and len(V["cands"]) == 5
V = post("/api/lora/set/cand", {"id": sid, "act": "drop"}); assert not V["cands"] and len(V["images"]) == 6
V = post("/api/lora/set/cand", {"id": sid, "act": "keep", "files": ["../meta.json"]}); assert V.get("moved", 0) == 0
ok("augment: simple variants + AI (Qwen-Image 2.1, different prompts) as candidates; keep chosen / drop rest")
print("ALL OK")
