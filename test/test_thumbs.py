"""2.5: 갤러리 미리보기 캐시 — 처음 볼 때 만들기, 사진 지우면 같이 삭제, 바뀐 사진은 새로, 오래된 것은 상한 넘으면 정리."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, time, urllib.parse
os.environ["TEST_HUB_PORT"] = "17936"
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
ok = lambda m: print("PASS", m)
G = hub.OUT / "생성"; G.mkdir(parents=True, exist_ok=True)
def mk(n, c=(10, 20, 30), size=(400, 300)): Image.new("RGB", size, c).save(G / n)
def cache_files(): return sorted(f for f in hub.THUMB_DIR.rglob("*.jpg")) if hub.THUMB_DIR.is_dir() else []
def tget(n): return req("/thumb/" + urllib.parse.quote("생성/" + n), raw=True)
for n in ("a.png", "b.png", "c.png"): mk(n)
assert not cache_files(); ok("nothing is pre-generated")
j = tget("a.png"); im = Image.open(__import__("io").BytesIO(j)); assert max(im.size) <= 320
fs = cache_files(); assert len(fs) == 1 and "o" in fs[0].parts and fs[0].name.startswith("a.png."), fs; ok("first view creates a small thumbnail in a mirror folder")
assert tget("a.png") == j and len(cache_files()) == 1; ok("second view reuses it")
mk("a.png", (200, 0, 0)); os.utime(G / "a.png", (time.time() + 5, time.time() + 5)); tget("a.png"); fs = cache_files(); assert len(fs) == 1, fs; ok("a changed photo gets a new thumbnail and the old one is removed")
tget("b.png"); tget("c.png"); assert len(cache_files()) == 3
r = req("/api/gallery/delete", {"files": ["/out/" + urllib.parse.quote("생성/b.png")]}); assert r.get("deleted") == 1 and not (G / "b.png").exists()
assert [f.name.split(".")[0] for f in cache_files()] == ["a", "c"], cache_files(); ok("deleting a photo from the gallery deletes its thumbnail too")
(G / "c.png").unlink(); hub.thumb_sweep(); assert [f.name.split(".")[0] for f in cache_files()] == ["a"]; ok("sweep removes thumbnails whose photo disappeared (deleted outside the app)")
(hub.THUMB_DIR / "deadbeef.jpg").parent.mkdir(parents=True, exist_ok=True); (hub.THUMB_DIR / "deadbeef.jpg").write_bytes(b"x" * 10); hub.thumb_sweep(); assert not (hub.THUMB_DIR / "deadbeef.jpg").exists(); ok("old-style cache files are cleaned up")
for i in range(6): mk(f"z{i}.png", (i * 30, 5, 5), (900, 700)); tget(f"z{i}.png"); time.sleep(0.02)
tot = sum(f.stat().st_size for f in cache_files()); assert tot > 3000
hub.thumb_cap = lambda: int(tot * 0.6); hub.thumb_sweep(); left = cache_files(); assert sum(f.stat().st_size for f in left) <= tot * 0.6 and 0 < len(left) < 7, (tot, left)
assert all(f.name.startswith(("a.png", "z")) for f in left); assert (G / "z0.png").exists() and (G / "a.png").exists(); ok("over the size limit: oldest thumbnails go first, photos are never touched")
assert req("/api/prefs")["thumb_cache_mb"] == 500; r = req("/api/prefs", {"thumb_cache_mb": 1000}); assert r["prefs"]["thumb_cache_mb"] == 1000 and req("/api/prefs", {"thumb_cache_mb": 7}).get("error"); ok("size limit setting: 200/500/1000/2000 only")
print("ALL OK")
