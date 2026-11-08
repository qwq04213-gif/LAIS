"""테스트 2개씩 동시 실행: python3 runpar.py test_a test_b ...  (자체 고정 포트를 쓰는 테스트는 따로 차례로)"""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, subprocess, sys, threading, queue
SERIAL = {"test_hub", "test_install", "test_nodes", "ui_test"}
names = [n.removesuffix(".py") for n in sys.argv[1:]]
res = {}
def run(n, slot):
    env = dict(os.environ, TEST_SLOT=str(slot), TMPDIR=os.environ.get("TMPDIR", "/tmp/tt"))
    with open(f"/tmp/r_{n}.log", "w") as f:
        r = subprocess.run([sys.executable, n + ".py"], cwd=BASE + "/test", stdout=f, stderr=subprocess.STDOUT, env=env, timeout=600)
    tail = open(f"/tmp/r_{n}.log").read().strip().splitlines()[-1:] or [""]
    res[n] = r.returncode == 0 and any(w in tail[0].lower() for w in ("ok", "pass"))
    print(("OK   " if res[n] else "FAIL ") + n, flush=True)
q = queue.Queue(); [q.put(n) for n in names if n not in SERIAL]
def worker(slot):
    while True:
        try: n = q.get_nowait()
        except queue.Empty: return
        run(n, slot)
ts = [threading.Thread(target=worker, args=(s,)) for s in (0, 1)]; [t.start() for t in ts]; [t.join() for t in ts]
for n in names:
    if n in SERIAL: run(n, 0)
print("DONE", sum(res.values()), "/", len(res))
