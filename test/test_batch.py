"""일괄(폴더) 처리 + 작업 대기열."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, shutil, threading
os.environ["TEST_HUB_PORT"] = "17888"
sys.path.insert(0, BASE + "/test")
from mocks import *
import base64, io, urllib.request
ok = lambda m: print("PASS", m)
def post(path, o):
    r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid, t=60):
    for _ in range(int(t * 10)):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
    raise AssertionError("timeout " + str(j))
def run(p): r = post("/api/job", dict(p, kind="batch")); assert "id" in r, r; return wait(r["id"])
SRC = TMP / "photos"; SRC.mkdir()
for i, (w, h) in enumerate([(400, 300), (300, 500), (640, 480)]): Image.new("RGB", (w, h), (30 * i, 90, 200)).save(SRC / f"p{i}.jpg")
(SRC / "notes.txt").write_text("x"); (SRC / "broken.png").write_bytes(b"not an image")
H = {p.name: p.read_bytes() for p in SRC.iterdir()}
OUTD = hub.OUT / "일괄"
# 1) 폴더 확인
r = post("/api/batch/scan", {"folder": str(SRC)}); assert r["count"] == 4 and r["folder"] == str(SRC), r      # p0..p2 + broken.png (확장자만 보고 세요)
assert "error" in post("/api/batch/scan", {"folder": "relative/dir"}) and "error" in post("/api/batch/scan", {"folder": str(TMP / "nope")}) and "error" in post("/api/batch/scan", {}); ok("scan: counts images, refuses missing / relative / empty folder")
# 2) 크기 변경: 깨진 파일은 실패로 기록하고 나머지는 계속
j = run({"op": "resize", "folder": str(SRC), "long_side": 200})
assert j["state"] == "done" and j["batch"]["ok"] == 3 and len(j["batch"]["failed"]) == 1 and j["batch"]["failed"][0][0] == "broken.png", j
outs = sorted(OUTD.glob("*_크기변경.png")); assert len(outs) == 3 and all(max(Image.open(f).size) == 200 for f in outs); assert "3장 완료, 1장 실패" in j["msg"]; ok("resize batch: 3 saved to outputs/일괄, corrupt file reported but doesn't stop the rest")
assert {p.name: p.read_bytes() for p in SRC.iterdir()} == H; ok("original files untouched (and nothing written into the source folder)")
j = run({"op": "resize", "folder": str(SRC), "long_side": 120, "fmt": "jpg"}); assert j["state"] == "done" and len(list(OUTD.glob("p*_크기변경.jpg"))) == 3; ok("JPEG output option")
j = run({"op": "resize", "folder": str(SRC), "long_side": 200}); assert len(list(OUTD.glob("*_크기변경-2.png"))) == 3 and len(outs) == 3; ok("re-running never overwrites earlier results (-2 suffix)")
r = post("/api/job", {"kind": "batch", "op": "resize", "folder": str(SRC)}); assert wait(r["id"])["state"] == "error"; ok("resize with nothing chosen → clear error")
r = post("/api/job", {"kind": "batch", "op": "resize", "folder": str(TMP / "photos" / "x"), "long_side": 10}); assert "error" in r; empty = TMP / "empty"; empty.mkdir(); assert "error" in post("/api/job", {"kind": "batch", "op": "resize", "folder": str(empty), "long_side": 10}); ok("bad / empty folder refused up front")
crop = run({"op": "resize", "folder": str(SRC), "crop": "1:1", "long_side": 100}); assert all(Image.open(f).size == (100, 100) for f in OUTD.glob("*_크기변경*.png") if f.stat().st_mtime > time.time() - 5 and Image.open(f).width <= 100) ; ok("crop to 1:1 + long side")
# 3) 배경 지우기
j = run({"op": "rmbg", "folder": str(SRC)}); assert j["state"] == "error" and "설치" in j["error"], j; ok("rmbg without the model installed → tells you to install it")
st = get("/api/rmbg/status"); assert st["ort"] and not any(m["installed"] for m in st["models"].values())
RMDIR = hub.MODELS / "rmbg"; RMDIR.mkdir(exist_ok=True)
real = Path(BASE + "/rmbg-test/u2netp.onnx")
assert real.is_file(), "put the real u2netp.onnx in /home/claude/rmbg-test"
shutil.copy(real, RMDIR / "u2netp.onnx"); assert get("/api/rmbg/status")["models"]["fast"]["installed"]
im = Image.new("RGB", (640, 480), (70, 120, 60)); d = ImageDraw.Draw(im) if (ImageDraw := __import__("PIL.ImageDraw", fromlist=["x"])) else None
d.ellipse((260, 80, 380, 200), fill=(230, 190, 160)); d.rectangle((240, 200, 400, 420), fill=(200, 30, 40)); im.save(SRC / "subject.png")
only = TMP / "one"; only.mkdir(); shutil.copy(SRC / "subject.png", only / "subject.png")
j = run({"op": "rmbg", "folder": str(only), "rmodel": "fast"}); assert j["state"] == "done", j
o = Image.open(OUTD / "subject_배경없음.png"); assert o.mode == "RGBA" and o.size == (640, 480); a = o.getchannel("A")
assert a.getpixel((320, 300)) > 200 and a.getpixel((5, 5)) < 30 and a.getpixel((630, 470)) < 30; ok("rmbg with the REAL u2netp model: subject opaque, background transparent (RGBA PNG)")
j = run({"op": "rmbg", "folder": str(only), "rmodel": "fast", "bg": "white", "fmt": "jpg"}); o = Image.open(OUTD / "subject_배경없음.jpg"); assert o.mode == "RGB" and sum(o.getpixel((5, 5))) > 720 and sum(o.getpixel((320, 300))) < 600; ok("rmbg with white fill → JPEG")
j = run({"op": "rmbg", "folder": str(only), "rmodel": "precise"}); assert j["state"] == "error" and "설치" in j["error"]; ok("model not installed for the chosen quality → error names install")
# 4) 업스케일(모커 ComfyUI)
j = run({"op": "upscale", "folder": str(only), "scale": "2"}); assert j["state"] == "done" and j["batch"]["ok"] == 1 and any(OUTD.glob("subject_업스케일x2*.png")), j; ok("upscale batch goes through ComfyUI per image")
big = TMP / "big"; big.mkdir(); Image.new("RGB", (3000, 3000)).save(big / "huge.png"); shutil.copy(SRC / "p0.jpg", big / "p0.jpg")
j = run({"op": "upscale", "folder": str(big), "scale": "4"}); assert j["state"] == "done" and j["batch"]["ok"] == 1 and "8192" in j["batch"]["failed"][0][1], j; ok("too-large image skipped with a reason, others continue")
# 5) 올려 둔 파일(stage)
b64 = lambda f: "data:image/png;base64," + base64.b64encode(Path(f).read_bytes()).decode()
r1 = post("/api/batch/upload", {"name": "a b.png", "image": b64(SRC / "subject.png")}); sid = r1["stage"]; r2 = post("/api/batch/upload", {"stage": sid, "name": "a b.png", "image": b64(SRC / "subject.png")})
assert r2["count"] == 2 and "error" in post("/api/batch/upload", {"stage": sid, "name": "x", "image": "junk"}) and "error" in post("/api/batch/upload", {"stage": "../x", "name": "x", "image": b64(SRC / "subject.png")}); ok("upload stage: unique names, junk / bad id refused")
j = run({"op": "resize", "stage": sid, "long_side": 50}); assert j["state"] == "done" and j["batch"]["ok"] == 2 and not (hub.BATCH_IN / sid).exists(); ok("processing an uploaded set; the temporary copies are cleaned up afterwards")
# 6) 중단
many = TMP / "many"; many.mkdir()
for i in range(60): Image.new("RGB", (1500, 1500), (i, 5, 5)).save(many / f"m{i:02d}.png")
r = post("/api/job", {"kind": "batch", "op": "resize", "folder": str(many), "long_side": 900}); time.sleep(0.4); post("/api/job/cancel", {"id": r["id"]}); j = wait(r["id"])
n = len(list(OUTD.glob("m*_크기변경.png"))); assert j["state"] == "cancelled" and 0 < n < 60 and str(n) in j["msg"], (j, n); ok(f"cancel mid-batch keeps the {n} finished files")
# ── 대기열 ──
gate, order = threading.Event(), []
orig = hub.do_batch
def slow(p, J):
    order.append(p["tag"])
    if p["tag"] == "first": gate.wait(20)
    return []
hub.do_batch = slow
try:
    ids = {t: post("/api/job", {"kind": "batch", "op": "resize", "folder": str(only), "long_side": 10, "tag": t})["id"] for t in ("first", "b", "c", "d")}
    time.sleep(0.5)
    q = get("/api/queue"); assert q["running"] == 1 and q["queued"] == 3, q
    labs = [(x["state"], x["pos"]) for x in q["items"]]; assert labs[:4] == [("running", 0), ("queued", 1), ("queued", 2), ("queued", 3)], labs
    assert "앞에 1개" in get("/api/job/" + ids["b"])["msg"] and "앞에 3개" in get("/api/job/" + ids["d"])["msg"]; ok("queue lists running + waiting in order; waiting jobs say how many are ahead")
    post("/api/queue/move", {"id": ids["d"], "to": "top"}); post("/api/queue/move", {"id": ids["b"], "to": "down"})
    assert [x["id"] for x in get("/api/queue")["items"] if x["state"] == "queued"] == [ids["d"], ids["c"], ids["b"]]; ok("reorder: top / down")
    assert "error" in post("/api/queue/move", {"id": ids["first"], "to": "up"}); ok("a running job can't be moved")
    post("/api/job/cancel", {"id": ids["c"]}); assert get("/api/job/" + ids["c"])["state"] == "cancelled"; assert [x["id"] for x in get("/api/queue")["items"] if x["state"] == "queued"] == [ids["d"], ids["b"]]; ok("cancel a waiting job: removed from the queue at once")
    gate.set()
    for t in ("first", "b", "d"): wait(ids[t])
    assert order == ["first", "d", "b"], order; ok("jobs ran in the reordered order; the cancelled one never started")
    q = get("/api/queue"); assert q["running"] == 0 and q["queued"] == 0 and {x["state"] for x in q["items"]} <= {"done", "error", "cancelled"} and any(x["state"] == "cancelled" for x in q["items"]); ok("finished jobs stay in the list (latest 8) for a while")
finally:
    hub.do_batch = orig
# 보통 작업도 대기열을 거침
r = post("/api/job", {"kind": "gen", "prompt": "a cat", "ckpt": "noobai_xl_v11.safetensors", "w": 512, "h": 512, "steps": 5}); j = wait(r["id"]); assert j["state"] == "done"; assert any("a cat" in x["label"] and x["label"].startswith("이미지 생성") for x in get("/api/queue")["items"]); ok("normal image jobs run through the same queue, with a readable label")
print("ALL OK")
