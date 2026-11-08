"""Install/download/guard/static-route regression tests (carried over from v1 after the hub.py restructure)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import hashlib, json, os, sys, time, urllib.request
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)

# static assets + guards
for path, needle in [("/", b"<html"), ("/app.js", b"use strict"), ("/app.css", b"--table")]:
    d = req(path, raw=True); assert needle in d, path
ok("static: index.html / app.js / app.css served")
assert req("/", headers={"Origin": "http://evil.example"})[0] == 403 and req("/api/status", headers={"Host": "evil.example"})[0] == 403; ok("foreign Origin / Host blocked")
assert req("/../hub.py")[0] in (403, 404) and req("/out/../../hub.py")[0] == 404; ok("no path traversal via static or /out/")
# chat guards
body = req("/api/chat", {"messages": [{"role": "user", "content": "nude loli"}]}, raw=True); assert b"error" in body and "미성년".encode() in body
body = req("/api/chat", {"model": "m", "messages": [{"role": "user", "content": "hi"}]}, raw=True).decode()
txt = "".join(json.loads(l)["message"]["content"] for l in body.splitlines() if l.strip()); assert txt == "안녕하세요", txt; ok("chat: minor+sexual blocked; stream passthrough (thinking chunk tolerated)")
assert hub.blocked("17살 여고생 누드") and hub.blocked("a 15 year old naked girl") and not hub.blocked("a child playing in the park") and not hub.blocked("18 year old woman nude"); ok("safety filter unit checks")

# downloads
def wait_tasks():
    for _ in range(150):
        t = req("/api/install")
        if all(x["state"] in ("done", "error") for x in t): return t
        time.sleep(0.2)
    raise AssertionError("tasks stuck")
r = req("/api/install", {"custom": {"url": "http://127.0.0.1:19999/dl?id=7", "dir": "loras", "token": "KEY"}, "ollama": "huihui_ai/qwen3-abliterated:8b"}); assert r.get("ok")
t = wait_tasks(); assert all(x["state"] == "done" for x in t), t
f = M / "loras/civitai_style_v2.safetensors"; assert f.exists() and f.read_bytes() == PAYLOAD; ok("custom download: Content-Disposition filename + full content; ollama pull task")
assert not list((M / "loras").glob("*.part")) and all("url" not in x and "token" not in x for x in t); ok("no .part leftovers; token/url not exposed")
f.unlink(); part = M / "loras" / (hashlib.sha1(b"http://127.0.0.1:19999/dl?id=8").hexdigest()[:12] + ".part"); part.write_bytes(PAYLOAD[:1_000_000])
req("/api/install", {"custom": {"url": "http://127.0.0.1:19999/dl?id=8", "dir": "loras"}}); wait_tasks(); assert (M / "loras/civitai_style_v2.safetensors").read_bytes() == PAYLOAD; ok("resume from partial download")
req("/api/install", {"custom": {"url": "http://127.0.0.1:19999/html", "dir": "loras"}}); t = wait_tasks(); assert t[-1]["state"] == "error" and "웹페이지" in t[-1]["msg"]; ok("HTML login page detected")
n = len(req("/api/install")); req("/api/install", {"custom": {"url": "http://127.0.0.1:19999/x", "dir": "../../evil"}}); assert len(req("/api/install")) == n; ok("path traversal in dir rejected")
req("/api/install", {"custom": {"url": "http://127.0.0.1:19999/dl?id=9", "dir": "embeddings"}}); wait_tasks(); assert (M / "embeddings/civitai_style_v2.safetensors").exists(); ok("embeddings folder accepted")
big = req("/api/install", {"ids": ["qwen3-32b", "qwen-edit", "cydonia-24b"] * 1}); print("INFO big install ->", big)
C = req("/api/catalog"); ids = [m["id"] for m in C["llm"] + C["image"]]; assert {"controlnet-union", "sdxl-vae-fix", "noobai-vpred", "ultrasharp", "exaone35-8b", "mistral-small-24b"} <= set(ids); ok("catalog has the new entries: " + str(len(ids)))
print("\nINSTALL/GUARD TESTS PASSED")
