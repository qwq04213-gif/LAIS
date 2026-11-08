"""갤러리 삭제 + 결과 폴더 날짜별 정리(이동만)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17891"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def code(path):
    try: return urllib.request.urlopen(B + path).status
    except urllib.error.HTTPError as e: return e.code
G = hub.OUT / "생성"; G.mkdir(parents=True, exist_ok=True); V = hub.OUT / "영상"; V.mkdir(exist_ok=True)
def mk(p, days_ago, vid=False):
    if vid: p.write_bytes(b"x"); p.with_name(p.name + ".json").write_text("{}")
    else: Image.new("RGB", (40, 40), (1, 2, 3)).save(p)
    t = time.time() - days_ago * 86400; os.utime(p, (t, t)); return p
mk(G / "a.png", 3); mk(G / "b.png", 3); mk(G / "c.png", 1); mk(G / "today.png", 0); mk(V / "v.mp4", 2, True)
post("/api/gallery/fav", {"file": "/out/생성/a.png", "on": True})
r = post("/api/gallery/organize", {"mode": "preview"}); assert r["total"] == 4 and sum(r["days"]["생성"].values()) == 3 and (G / "a.png").exists(); ok("preview counts per day, nothing moved")
r = post("/api/gallery/organize", {"mode": "run"}); assert r["moved"] == 4 and r["failed"] == 0
d3 = time.strftime("%Y-%m-%d", time.localtime(time.time() - 3 * 86400))
assert (G / d3 / "a.png").is_file() and (G / "today.png").is_file() and not (G / "a.png").exists() and (V / time.strftime("%Y-%m-%d", time.localtime(time.time() - 2 * 86400)) / "v.mp4.json").is_file(); ok("files moved into date folders (today's kept, video sidecar moves with it)")
g = get("/api/gallery"); assert g["total"] == 5 and any(urllib.parse.unquote(x["url"]) == f"/out/생성/{d3}/a.png" and x["fav"] for x in g["items"]); ok("gallery still lists them (with the favourite mark)")
assert code(f"/out/{urllib.parse.quote('생성')}/{d3}/a.png") == 200 and code(f"/thumb/{urllib.parse.quote('생성')}/{d3}/a.png") == 200 and code(f"/out/{urllib.parse.quote('생성')}/zz/a.png") != 200; ok("date-folder URLs and thumbnails are served; arbitrary subfolders are not")
assert post("/api/gallery/fav", {"file": f"/out/생성/{d3}/b.png", "on": True})["fav"]
before = {p.name for p in hub.OUT.rglob("*") if p.is_file()}
r = post("/api/gallery/organize", {"mode": "run"}); assert r["moved"] == 0 and {p.name for p in hub.OUT.rglob("*") if p.is_file()} == before; ok("running again moves nothing; no file ever disappears")
(G / "a.png").write_bytes(b"dup"); os.utime(G / "a.png", (time.time() - 3 * 86400,) * 2); post("/api/gallery/organize", {"mode": "run"}); assert (G / d3 / "a-2.png").is_file() and (G / d3 / "a.png").stat().st_size > 3; ok("name clash → renamed, never overwritten")
# 삭제
urls = [f"/out/생성/{d3}/a.png", f"/out/생성/{d3}/a-2.png"]
r = post("/api/gallery/delete", {"files": urls}); assert r["deleted"] == 2 and r["failed"] == 0 and not (G / d3 / "a.png").exists()
assert "생성/a.png" not in json.loads((hub.ROOT / "gallery.json").read_text(encoding="utf-8"))["favs"]; ok("delete removes the files and their favourite marks")
vd = time.strftime("%Y-%m-%d", time.localtime(time.time() - 2 * 86400)); r = post("/api/gallery/delete", {"files": [f"/out/영상/{vd}/v.mp4"]}); assert r["deleted"] == 1 and not (V / vd).exists(); ok("video delete also removes its settings file and the emptied date folder")
bad = post("/api/gallery/delete", {"files": ["/out/../x.png", "/out/생성/nope.png", "../../etc/passwd", "/out/기타/z.png", f"/out/생성/{d3}/b.png.json"]}); assert bad["deleted"] == 0 and bad["failed"] == 5 and (G / d3 / "b.png").exists(); ok("traversal / missing / non-media paths refused")
# 일괄 처리 입력으로 날짜 폴더 포함
r = post("/api/batch/scan", {"outsub": "생성"}); assert r["count"] >= 3, r; ok("batch 'result folder' source also sees date folders")
print("ALL OK")
