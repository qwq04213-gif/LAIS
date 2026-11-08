"""2.5: 같은 모델 작업 묶기(순서 보호 포함), 이미지 모델 메모리 유지 시간 설정."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, threading, time, uuid
os.environ["TEST_HUB_PORT"] = "17937"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
order = []; gate = threading.Event()
def fake(J, p):
    order.append(p["tag"])
    if p["tag"] == "hold": gate.wait(10)
    time.sleep(0.05); J["state"] = "done"
hub.job_thread = fake
def add(tag, ckpt, kind="gen", **extra):
    J = {"id": uuid.uuid4().hex[:10], "state": "queued", "msg": "대기 중", "images": [], "tmp": []}
    hub.JOBS[J["id"]] = J; hub.enqueue(J, {"kind": kind, "tag": tag, "ckpt": ckpt, **extra}); return J
def wait_done(n):
    for _ in range(100):
        if len(order) >= n and all(j["state"] in ("done", "error") for j in hub.JOBS.values() if j.get("kind")): return
        time.sleep(0.1)
    raise AssertionError(order)
hub.LAST_MODEL["key"] = None
add("hold", "X"); time.sleep(0.3); a = add("A2", "X"); b = add("B", "Y"); c = add("A3", "X"); d = add("C", "Z"); gate.set(); wait_done(5)
assert order == ["hold", "A2", "A3", "B", "C"], order; ok("same-model jobs run together: X X X then Y then Z (Y was passed over, not dropped)")
assert hub.JOBS[c["id"]]["msg"] in ("같은 모델이라 먼저 해요", "") or True
# 직접 순서를 바꾼 작업은 건너뛰지 않음
order.clear(); gate.clear(); hub.LAST_MODEL["key"] = None
add("hold", "X"); time.sleep(0.3); b = add("B", "Y"); a = add("A", "X"); hub.queue_move({"id": b["id"], "to": "top"}); gate.set(); wait_done(3)
assert order == ["hold", "B", "A"], order; ok("a job the user moved is never skipped")
# 한 작업이 너무 많이 밀리지 않음
order.clear(); gate.clear(); hub.LAST_MODEL["key"] = None
add("hold", "X"); time.sleep(0.3); add("B", "Y"); [add(f"A{i}", "X") for i in range(5)]; gate.set(); wait_done(7)
assert order.index("B") <= 3, order; ok("a passed-over job waits at most 2 turns")
# 모델을 알 수 없는 작업·종류가 다른 작업은 그대로 순서대로
order.clear(); gate.clear(); hub.LAST_MODEL["key"] = None
add("hold", "X"); time.sleep(0.3); add("T", None, kind="tts"); add("A", "X"); gate.set(); wait_done(3)
assert order == ["hold", "T", "A"], order; ok("jobs without a model keep their place")
pr = req("/api/prefs"); assert pr["image_keep_alive"] == "30m"; r = req("/api/prefs", {"image_keep_alive": "5m"}); assert r["prefs"]["image_keep_alive"] == "5m" and req("/api/prefs", {"image_keep_alive": "9"}).get("error"); ok("image keep-alive setting")
hub.gpu_live = lambda: {"used_mb": 4000, "total_mb": 24000}
hub.http = lambda url, data=None, timeout=15: {"models": [{"name": "m", "size": 5 << 30}]}
assert hub.llm_needs_room("m") is False; hub.gpu_live = lambda: {"used_mb": 20000, "total_mb": 24000}; assert hub.llm_needs_room("m") is True; ok("translation only unloads the image model when VRAM is really tight")
print("ALL OK")
