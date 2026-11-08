"""태그 자동완성: 기본 태그, 내 프롬프트, LoRA 트리거, 와일드카드, CSV(별칭)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17895"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def q(s): return json.loads(urllib.request.urlopen(B + "/api/tags?q=" + urllib.parse.quote(s)).read())["items"]
assert q("a") == [] and q("") == []
r = q("blue ha"); assert r and r[0]["t"].startswith("blue ha") and len(r) <= 10, r
assert any(x["t"] == "blue hair" for x in q("blue hai"))
assert all(x["t"].lower() != "blue hair" for x in q("blue hair"))   # 이미 다 쓴 것은 제안 안 함
ok("builtin tags: prefix match, min 2 chars, <=10, exact typed tag not suggested")
assert any(x["t"] == "long hair" for x in q("long_ha")); ok("underscore input normalized")
hub.PROMPTS_FILE.write_text(json.dumps([{"id": "1", "title": "t", "text": "zzqx special, (zzqx kitten:1.3), <lora:abc:0.8>", "negative": ""}]), encoding="utf-8")
r = q("zzqx"); assert {x["t"] for x in r} >= {"zzqx special", "zzqx kitten"} and r[0]["c"] == "내 프롬프트", r
assert all("lora" not in x["t"] for x in q("lora:")); ok("saved prompts feed suggestions (weights/LoRA tags stripped)")
(hub.ROOT / "wildcards").mkdir(exist_ok=True); (hub.ROOT / "wildcards" / "qqcolor.txt").write_text("red\nblue", encoding="utf-8")
assert any(x["t"] == "__qqcolor__" and x["c"] == "와일드카드" for x in q("__qqc")); ok("wildcards")
(hub.ROOT / "tags").mkdir(exist_ok=True)
(hub.ROOT / "tags" / "my.csv").write_text("kumo_sky,0,5000,cloudy_sky|alias2\nsome_char,4,99,\"scn,scx\"\n", encoding="utf-8")
assert any(x["t"] == "kumo sky" for x in q("kumo")); assert any(x["t"] == "some char" and x["c"] == "캐릭터" for x in q("scx"))
ok("csv folder: danbooru-style, category and alias mapping")
(hub.MODELS / "loras").mkdir(parents=True, exist_ok=True); (hub.MODELS / "loras" / "x.safetensors").write_bytes(b"x" * 10)
(hub.LORA_USER).write_text(json.dumps({"x.safetensors": {"trigger": ["mytrigword"]}}), encoding="utf-8")
assert any(x["t"] == "mytrigword" and x["c"] == "LoRA 트리거" for x in q("mytrig")); ok("LoRA trigger words (user-entered)")
print("ALL OK")
