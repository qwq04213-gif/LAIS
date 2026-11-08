"""설정 백업/복원."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17887"
sys.path.insert(0, BASE + "/test")
from mocks import *
import urllib.request
ok = lambda m: print("PASS", m)
def post(path, o):
    r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
R = hub.ROOT
post("/api/prompts", {"action": "save", "id": "a1", "name": "고양이", "text": "a cat", "tags": ["x"]})
post("/api/prompts", {"action": "save", "id": "a2", "name": "강아지", "text": "a dog"})
post("/api/wildcards", {"action": "save", "name": "color", "text": "red\nblue"})
(R / "gallery.json").write_text(json.dumps({"favs": ["생성/a.png"]}), encoding="utf-8")
(R / "lora_user.json").write_text(json.dumps({"lora_a.safetensors": {"trigger": ["tok"], "kind": "character"}}), encoding="utf-8")
d = get("/api/backup/export")
assert d["app"] == "LocalAI-Studio" and len(d["prompts"]) == 2 and d["wildcards"]["color"] == "red\nblue" and d["favs"] == ["생성/a.png"] and d["lora_user"]["lora_a.safetensors"]["kind"] == "character" and d["version"]; ok("export bundles prompts / wildcards / favorites / LoRA info")
# 새 PC 처럼 비우고 복원
for f in ("prompts.json", "gallery.json", "lora_user.json"): (R / f).unlink()
(R / "wildcards" / "color.txt").unlink()
r = post("/api/backup/import", {"data": d, "mode": "merge"}); c = r["counts"]
assert c == {"prompts": 2, "favs": 1, "lora_user": 1, "wildcards": 1, "chats": 0}, c
assert len(post("/api/prompts", {"action": "list"})["items"]) == 2 and (R / "wildcards/color.txt").read_text(encoding="utf-8") == "red\nblue" and json.loads((R / "lora_user.json").read_text(encoding="utf-8"))["lora_a.safetensors"]["trigger"] == ["tok"]; ok("restore into an empty install brings everything back")
# 합치기: 있는 건 그대로
post("/api/prompts", {"action": "save", "id": "a1", "name": "고양이", "text": "CHANGED"}); (R / "wildcards/color.txt").write_text("mine", encoding="utf-8")
r = post("/api/backup/import", {"data": d, "mode": "merge"}); assert r["counts"] == {"prompts": 0, "favs": 0, "lora_user": 0, "wildcards": 0, "chats": 0}, r
assert {x["id"]: x["text"] for x in post("/api/prompts", {"action": "list"})["items"]}["a1"] == "CHANGED" and (R / "wildcards/color.txt").read_text(encoding="utf-8") == "mine"; ok("merge keeps what already exists")
# 덮어쓰기: 같은 항목만 바꾸고 나머지는 지우지 않음
post("/api/prompts", {"action": "save", "id": "zz", "name": "extra", "text": "keep me"}); (R / "wildcards/other.txt").write_text("o", encoding="utf-8")
r = post("/api/backup/import", {"data": d, "mode": "overwrite"}); assert r["counts"]["prompts"] == 2 and r["counts"]["wildcards"] >= 1, r
it = {x["id"]: x["text"] for x in post("/api/prompts", {"action": "list"})["items"]}; assert it["a1"] == "a cat" and it["zz"] == "keep me" and (R / "wildcards/other.txt").exists(); ok("overwrite replaces same items, deletes nothing else")
snap = Path(r["saved_to"]); assert snap.is_dir() and (snap / "prompts.json").is_file() and (snap / "wildcards" / "color.txt").read_text(encoding="utf-8") == "mine"; ok("current files copied to backups/ before changing")
# 나쁜 입력
assert "error" in post("/api/backup/import", {"data": {"app": "x"}}) and "error" in post("/api/backup/import", {"data": [1]})
bad = dict(d, wildcards={"../evil": "x", "ok_name": "y"}, favs=["../../x", 5, "생성/b.png"], lora_user={"n": {"trigger": ["t"], "kind": "zzz"}, 3: "q"}, prompts=[1, {"text": ""}, {"text": "fine"}])
r = post("/api/backup/import", {"data": bad, "mode": "merge"}); assert not (R.parent / "evil.txt").exists() and not (R / "wildcards" / ".." / "evil.txt").exists() and (R / "wildcards/ok_name.txt").exists(); assert json.loads((R / "gallery.json").read_text(encoding="utf-8"))["favs"] == ["생성/a.png", "생성/b.png"], (R / "gallery.json").read_text(encoding="utf-8")
LU = json.loads((R / "lora_user.json").read_text(encoding="utf-8"))["n"]; assert LU.get("trigger") == ["t"] and LU.get("kind", "") == ""; ok("malformed / path-traversal entries are skipped, not trusted")
print("ALL OK")
