"""2.4: 모델 받기 취소 — 기다리는 중/받는 중 취소, 받던 .part 만 삭제, 완성된 모델은 그대로."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, threading, time, http.server
os.environ["TEST_HUB_PORT"] = "17931"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length", str(8 << 20)); self.end_headers()
        try:
            for _ in range(8):
                self.wfile.write(b"x" * (1 << 20)); self.wfile.flush(); time.sleep(0.4)
        except OSError: pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 17932), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
hub.OPENER = hub.urllib.request.build_opener()
hub.TASKS.clear()
d = hub.MODELS / "checkpoints"; d.mkdir(parents=True, exist_ok=True)
keep = d / "done_model.safetensors"; keep.write_bytes(b"ok")

# 1. 기다리는 중 취소: 바로 취소 + 그 작업 .part 삭제
t1 = hub.add_task("A", kind="file", url="http://127.0.0.1:17932/a.bin", dir="checkpoints", name="a.bin")
hub.part_of(t1).write_bytes(b"half")
r = hub.cancel_task(t1["id"]); assert r.get("ok") and t1["state"] == "cancelled" and not hub.part_of(t1).exists(), (r, t1)
ok("queued task: cancelled at once and its .part is removed")
assert hub.cancel_task(t1["id"]).get("error") and hub.cancel_task("nope").get("error"); ok("finished/unknown task → friendly error")

# 2. 받는 중 취소: 다음 조각에서 멈추고 .part 삭제
threading.Thread(target=hub.worker, daemon=True).start()
t2 = hub.add_task("B", kind="file", url="http://127.0.0.1:17932/b.bin", dir="checkpoints", name="b.bin")
for _ in range(60):
    if t2["state"] == "running" and hub.part_of(t2).exists() and hub.part_of(t2).stat().st_size > 0: break
    time.sleep(0.1)
assert t2["state"] == "running"
assert hub.cancel_task(t2["id"]).get("ok")
for _ in range(80):
    if t2["state"] != "running": break
    time.sleep(0.1)
assert t2["state"] == "cancelled" and "임시 파일" in t2["msg"] and not hub.part_of(t2).exists() and not (d / "b.bin").exists(), t2
ok("running task: stops, state cancelled, .part removed, no final file")
assert keep.read_bytes() == b"ok"; ok("an already-installed model is untouched")

# 3. HTTP 경로
r = req("/api/install/cancel", {"id": "nope"}); assert r.get("error"); r = req("/api/install/cancel", {"all": True}); assert r.get("ok") and "n" in r; ok("POST /api/install/cancel works (id / all)")
print("ALL OK")
