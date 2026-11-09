"""저장 공간 점검: 합계가 맞고, 실제 경로·폴더 열기가 있고, 바깥 캐시를 환경 변수대로 찾는다."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, os, json, urllib.request, pathlib, tempfile
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
hf = pathlib.Path(tempfile.mkdtemp(prefix="hfhome-")); (hf / "hub" / "models--x").mkdir(parents=True); (hf / "hub" / "models--x" / "blob").write_bytes(b"H" * 5000); (hf / "token").write_text("secret")
os.environ["HF_HOME"] = str(hf)
(hub.MODELS / "insightface").mkdir(parents=True, exist_ok=True); (hub.MODELS / "insightface" / "inswapper_128.onnx").write_bytes(b"I" * 7000)
(hub.ROOT / "cache" / "thumbs").mkdir(parents=True, exist_ok=True); (hub.ROOT / "cache" / "thumbs" / "a.jpg").write_bytes(b"T" * 3000)
(hub.ROOT / "cache" / "nodes").mkdir(parents=True, exist_ok=True); (hub.ROOT / "cache" / "nodes" / "x.zip").write_bytes(b"Z" * 2000)
(hub.ROOT / "stray.bin").write_bytes(b"S" * 1234)
r = req("/api/disk")
inside = [i for i in r["items"] if i["inside"]]
assert r["used"] == hub.dir_size(hub.ROOT) and r["listed"] == sum(i["bytes"] for i in inside) == r["used"], (r["used"], r["listed"]); ok("rows add up exactly to the program-folder total")
k = {i["key"]: i for i in r["items"]}
assert k["m_other"]["bytes"] >= 7000 and k["cache"]["bytes"] >= 5000 and k["rest"]["bytes"] >= 1234; ok("model folders outside the known list, cache folder and leftovers are counted")
assert all(i["path"] for i in r["items"]) and r["root"] == str(hub.ROOT); ok("every row shows its real folder path")
e = {i["key"]: i for i in r["ext"]}; assert e["x_hf"]["path"] == str(hf / "hub") and e["x_hf"]["bytes"] == 5000 and "x_hf" not in {i["key"] for i in inside}; ok("HuggingFace cache found through HF_HOME, shown apart from (not added to) the folder total")
opened = []; hub.open_folder = lambda p, sel=None: opened.append(str(p))
assert req("/api/disk/open", {"key": "x_hf"})["ok"] and opened[-1] == str(hf / "hub"); assert req("/api/disk/open", {"key": "../etc"}).get("error"); ok("[폴더 열기] works for known keys only")
c = req("/api/clean", {"what": "x_hf"}); assert c["freed"] == 5000 and not any((hf / "hub").iterdir()) and (hf / "token").read_text() == "secret"; ok("cache clean empties the cache folder but never the login token")
c = req("/api/clean", {"what": "cache"}); assert c["freed"] >= 5000 and not (hub.ROOT / "cache" / "thumbs" / "a.jpg").exists(); ok("work cache clean")
assert req("/api/clean", {"what": "x_nothing"}).get("error"); ok("unknown clean target refused")
# 4.3: 작업 폴더도 보이고 정리돼요(결과물은 그대로)
import time as _t
(hub.VR_WORK / "k1" / "chunks").mkdir(parents=True, exist_ok=True); (hub.VR_WORK / "k1" / "pre.mp4").write_bytes(b"V" * 4000); (hub.VR_WORK / "k1" / "chunks" / "c1.mp4").write_bytes(b"V" * 1000)
hub.DEPTH_DIR.mkdir(parents=True, exist_ok=True); (hub.DEPTH_DIR / "a.png").write_bytes(b"D" * 500)
old, new = hub.M3D_DIR / "aaaaaaaaaaaa", hub.M3D_DIR / "bbbbbbbbbbbb"
for d in (old, new): d.mkdir(parents=True, exist_ok=True); (d / "meta.json").write_text("{}"); (d / "orig.png").write_bytes(b"P" * 800)
for f in old.iterdir(): os.utime(f, (_t.time() - 40 * 86400,) * 2)
(hub.COMFY / "input").mkdir(parents=True, exist_ok=True); (hub.COMFY / "input" / "hub_aaaa.mp4").write_bytes(b"M" * 900); (hub.COMFY / "input" / "mine.mp4").write_bytes(b"U" * 10)
(hub.ROOT / "cache" / "gif_1234.gif").write_bytes(b"G" * 100)
r = req("/api/disk"); keys = {i["key"]: i for i in r["items"]}
assert keys["vrestore"]["bytes"] == 5000 and keys["depth"]["bytes"] == 500 and keys["m3d"]["bytes"] >= 1600 and keys["vrestore"]["clean"] == "vrestore" and keys["m3d"]["clean"] == "m3d_old"
assert keys["cache"]["bytes"] < 5000                                   # 하위 작업 폴더는 두 번 세지 않아요
c = req("/api/clean", {"what": "vrestore"}); assert c["freed"] == 5000 and not any(hub.VR_WORK.rglob("*.mp4"))
c = req("/api/clean", {"what": "depth"}); assert c["freed"] == 500
c = req("/api/clean", {"what": "m3d_old"}); assert not old.exists() and new.exists() and c["freed"] >= 800
c = req("/api/clean", {"what": "input"}); assert not (hub.COMFY / "input" / "hub_aaaa.mp4").exists() and (hub.COMFY / "input" / "mine.mp4").exists()
c = req("/api/clean", {"what": "cache"}); assert not (hub.ROOT / "cache" / "gif_1234.gif").exists()
ok("work folders (video restore, depth, 3D sessions) listed separately and cleaned; only old 3D sessions; only our own temp inputs; leftover GIFs")
# 깊은 경로(윈도우 260자 제한 대비): 접두 처리 함수가 일반 경로를 망가뜨리지 않는지
assert hub._plain(hub._lp(str(hub.ROOT))) == os.path.abspath(str(hub.ROOT)); ok("long-path prefix helper round-trips")
(hub.ROOT / "stray.bin").unlink()
print("ALL OK")
