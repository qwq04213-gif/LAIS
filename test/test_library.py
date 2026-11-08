"""프롬프트 보관함 · 와일드카드 편집 · 이미지→프롬프트 · 기록 갤러리 백엔드."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, base64, io, time
os.environ["TEST_HUB_PORT"] = "17875"
sys.path.insert(0, BASE + "/test")
from mocks import *
import urllib.request, urllib.parse
ok = lambda m: print("PASS", m)
def post(path, o):
    r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
# ── 보관함
assert post("/api/prompts", {"action": "list"})["items"] == []
r = post("/api/prompts", {"action": "save", "name": "비 오는 거리", "text": "rainy street, neon", "negative": "blurry", "tags": ["배경", " "]}); assert len(r["items"]) == 1 and r["items"][0]["tags"] == ["배경"]
pid = r["items"][0]["id"]
r = post("/api/prompts", {"action": "save", "id": pid, "name": "비 오는 거리 v2", "text": "rainy street, neon, night"}); assert len(r["items"]) == 1 and r["items"][0]["name"].endswith("v2")
assert "error" in post("/api/prompts", {"action": "save", "text": "  "})
assert (hub.ROOT / "prompts.json").is_file()
assert post("/api/prompts", {"action": "delete", "id": pid})["items"] == []; ok("prompt library: save / overwrite by id / validate / delete, persisted to prompts.json")
# ── 와일드카드
assert "hair_color" in post("/api/wildcards", {"action": "list"})["items"]
assert post("/api/wildcards", {"action": "get", "name": "hair_color"})["text"].count("hair") == 3
post("/api/wildcards", {"action": "save", "name": "mood", "text": "happy\r\nsad\r\n"}); assert (hub.ROOT / "wildcards/mood.txt").read_text() == "happy\nsad\n"
assert "mood" in get("/api/lists")["wildcards"]
for bad in ("../x", "a/b", "", "x" * 80): assert "error" in post("/api/wildcards", {"action": "save", "name": bad, "text": "x"}), bad
post("/api/wildcards", {"action": "delete", "name": "mood"}); assert not (hub.ROOT / "wildcards/mood.txt").exists(); ok("wildcards: list / read / save / delete, path traversal rejected, shows up in lists")
# ── 이미지→프롬프트
im = Image.new("RGB", (400, 300), (200, 30, 30)); b = io.BytesIO(); im.save(b, "PNG"); du = "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
r = post("/api/describe", {"image": du}); assert "이미지를 볼 수 있는" in r["error"] and "Qwen2.5-VL" in r["error"], r
STATE["vision"] = {"qwen2.5vl:7b"}; hub._VIS.clear(); hub.llms_orig = hub.llms; hub.llms = lambda: ["testmodel:latest", "qwen2.5vl:7b"]
assert get("/api/vision")["models"] == ["qwen2.5vl:7b"]
n0 = len(GEN); r = post("/api/describe", {"image": du, "style": "tags"}); assert r["text"] == "1girl, red jacket, rain" and r["model"] == "qwen2.5vl:7b", r
body = GEN[n0]; assert body["model"] == "qwen2.5vl:7b" and body["stream"] is False and len(body["messages"][0]["images"]) == 1 and "tags" in body["messages"][0]["content"]
r = post("/api/describe", {"image": du, "style": "video"}); assert "video generator" in GEN[-1]["messages"][0]["content"]
assert "error" in post("/api/describe", {"image": "garbage"}); ok("image->prompt: picks a vision model, sends the image, strips <think>, 3 styles, clear error when no vision model")
hub.llms = hub.llms_orig
# ── 갤러리
def mk(sub, name, color, prompt=None):
    d = hub.OUT / sub; d.mkdir(parents=True, exist_ok=True); i = Image.new("RGB", (640, 480), color)
    i.save(d / name, "PNG", pnginfo=meta.pnginfo({"prompt": prompt, "sampler": "euler", "steps": 5, "cfg": 5, "seed": 1, "w": 640, "h": 480, "model": "m"}) if prompt else None); return d / name
a = mk("생성", "a.png", (255, 0, 0), "1girl, red jacket"); time.sleep(0.02)
c = mk("편집", "c.png", (0, 255, 0), "blue dress"); time.sleep(0.02)
v = hub.OUT / "영상"; v.mkdir(exist_ok=True); (v / "v.mp4").write_bytes(b"x" * 100); (v / "v.mp4.json").write_text(json.dumps({"prompt": "a cat walking"}))
os.utime(a, (time.time() - 50, time.time() - 50))
g = get("/api/gallery"); assert g["total"] == 3 and [x["name"] for x in g["items"]][0] in ("v.mp4", "c.png") and g["items"][-1]["name"] == "a.png", g
assert any(x["video"] for x in g["items"])
assert [x["name"] for x in get("/api/gallery?" + urllib.parse.urlencode({"q": "RED jacket"}))["items"]] == ["a.png"]
assert [x["name"] for x in get("/api/gallery?" + urllib.parse.urlencode({"q": "cat"}))["items"]] == ["v.mp4"]
assert [x["name"] for x in get("/api/gallery?" + urllib.parse.urlencode({"kind": "편집"}))["items"]] == ["c.png"]
ua = [x for x in g["items"] if x["name"] == "a.png"][0]["url"]; assert post("/api/gallery/fav", {"file": ua, "on": True})["fav"]
f = get("/api/gallery?fav=1"); assert [x["name"] for x in f["items"]] == ["a.png"] and f["items"][0]["fav"]
post("/api/gallery/fav", {"file": ua, "on": False}); assert get("/api/gallery?fav=1")["total"] == 0
assert "error" in post("/api/gallery/fav", {"file": "/out/../../etc/passwd", "on": True}); ok("gallery: newest first, filter by kind, search prompt (images + video sidecar), favorites")
t = urllib.request.urlopen(B + "/thumb/" + urllib.parse.quote("생성") + "/a.png"); d = t.read(); assert t.headers["Content-Type"] == "image/jpeg" and Image.open(io.BytesIO(d)).width == 320
assert list((hub.ROOT / "cache/thumbs").rglob("*.jpg")); 
try: urllib.request.urlopen(B + "/thumb/" + urllib.parse.quote("영상") + "/v.mp4"); raise AssertionError
except urllib.error.HTTPError as e: assert e.code == 404
ok("thumbnails: 320px JPEG cached on disk; videos not thumbnailed")
print("ALL OK")
