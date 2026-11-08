"""폴더 열기 관련 메시지는 콘솔에 찍지 않고 logs\\hub-debug.log 에만."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, io, contextlib
os.environ["TEST_HUB_PORT"] = "17903"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    hub.quiet_log("[폴더 창 앞으로]", "outputs", "성공")
assert buf.getvalue() == "", buf.getvalue()
t = (hub.LOGS / "hub-debug.log").read_text(encoding="utf-8"); assert "[폴더 창 앞으로] outputs 성공" in t
(hub.LOGS / "hub-debug.log").write_text("x" * 300000, encoding="utf-8"); hub.quiet_log("again"); assert (hub.LOGS / "hub-debug.log").stat().st_size < 1000
src = open(hub.__file__, encoding="utf-8").read()
assert 'log("[폴더 창' not in src.replace("quiet_log(", "") and 'log("[창 앞으로' not in src.replace("quiet_log(", ""); ok("folder-window messages go to a log file only; file stays small")
print("ALL OK")
