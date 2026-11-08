"""2.5.1: 모델 목록 캐시 — 폴더가 그대로면 다시 훑지 않고, 파일이 생기면 바로 반영."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, time
os.environ["TEST_HUB_PORT"] = "17938"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
calls = {"n": 0}; orig = hub._lists_build
def counted(): calls["n"] += 1; return orig()
hub._lists_build = counted
a = req("/api/lists"); n1 = calls["n"]; b = req("/api/lists"); c = req("/api/lists")
assert calls["n"] == n1 and a == b == c, calls; ok("same folders → built once, answers repeated from memory")
d = hub.MODELS / "loras"; d.mkdir(parents=True, exist_ok=True); (d / "newone.safetensors").write_bytes(b"x" * 100)
r = req("/api/lists"); assert calls["n"] == n1 + 1 and "newone.safetensors" in r["loras"], (calls, r["loras"]); ok("a new file shows up on the next request")
(d / "newone.safetensors").unlink(); r = req("/api/lists"); assert "newone.safetensors" not in r["loras"]; ok("a removed file disappears too")
hub.llms = lambda: ["fresh-model"]; assert req("/api/lists")["llm"] == ["fresh-model"] and calls["n"] <= n1 + 2; ok("chat model list is always fresh without rebuilding")
t = time.time(); [req("/api/lists") for _ in range(20)]; assert time.time() - t < 3; ok("20 repeated requests are fast")
print("ALL OK")
