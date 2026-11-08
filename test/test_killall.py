"""작업 모두 강제 종료: 대기·실행 작업 모두 cancel, ComfyUI 대기열 비우기·중단."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, threading, time
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(u, d): return json.loads(urllib.request.urlopen(urllib.request.Request(B + u, json.dumps(d).encode(), {"Content-Type": "application/json"})).read())
J1 = {"id": "a1", "state": "running", "pid": "p1"}; J2 = {"id": "a2", "state": "queued"}; J3 = {"id": "a3", "state": "done"}
for J in (J1, J2, J3): hub.JOBS[J["id"]] = J
with hub._QCV: hub.QUEUE.append("a2")
i0, f0 = STATE["interrupts"], STATE["freed"]
r = post("/api/job/cancel_all", {}); assert r == {"ok": True, "n": 2}, r
assert J1["cancel"] and J2["state"] == "cancelled" and "a2" not in hub.QUEUE and J3["state"] == "done" and not J3.get("cancel")
for _ in range(30):
    if STATE["interrupts"] > i0 and STATE["freed"] > f0: break
    time.sleep(0.1)
assert STATE["interrupts"] > i0 and STATE["freed"] > f0, STATE; ok("cancel_all stops running + queued jobs, leaves finished ones, interrupts ComfyUI, then unloads models (VRAM)")
print("ALL OK")
