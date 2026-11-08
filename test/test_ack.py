import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys; sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
assert req("/api/prefs")["ack"] is False
assert req("/api/prefs", {"ack": True})["prefs"]["ack"] is True and req("/api/prefs")["ack"] is True; ok("consent ack is stored on the server (survives a new browser window)")
assert "token" not in str(req("/api/prefs")).lower() and "key" not in str(req("/api/prefs")).lower(); ok("prefs never expose keys")
req("/api/prefs", {"ack": "no"}); assert req("/api/prefs")["ack"] is True; ok("ack can only be set true")
print("ALL OK")
