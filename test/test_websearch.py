"""3.17: 웹 검색(SearXNG) — 상태·주소 저장, JSON 결과 + 페이지 본문 → 대화용 근거 글, 꺼짐·JSON 막힘 안내, 차단어, 대화 저장에 출처 남기기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
os.environ["TEST_HUB_PORT"] = "17989"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
MODE = {"json": True}
class S(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/search"):
            if not MODE["json"]: self.send_response(403); self.end_headers(); return
            port = self.server.server_address[1]
            res = [{"title": f"결과 {i}", "url": f"http://127.0.0.1:{port}/page{i}", "content": f"요약 {i}", "publishedDate": "2026-10-20T00:00:00"} for i in range(8)]
            res.append({"title": "dup", "url": f"http://127.0.0.1:{port}/page0"})
            b = json.dumps({"results": res}).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b); return
        b = ("<html><head><script>var x=1;</script><style>p{}</style></head><body><nav>메뉴 메뉴 메뉴 메뉴 메뉴 메뉴 메뉴 메뉴</nav><p>" + self.path + " 본문입니다. 서울의 오늘 날씨는 맑고 기온은 섭씨 20도 정도입니다.</p></body></html>").encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(b)
srv = ThreadingHTTPServer(("127.0.0.1", 0), S); threading.Thread(target=srv.serve_forever, daemon=True).start(); U = f"http://127.0.0.1:{srv.server_address[1]}"
st = get("/api/websearch"); assert st["ok"] is False and st["url"].endswith(":8899")
r = post("/api/websearch/query", {"q": "서울 날씨"}); assert r.get("off") and "꺼져" in r["error"]
assert post("/api/websearch/save", {"url": "nope"})["error"]
st = post("/api/websearch/save", {"url": U, "pages": 2}); assert st["ok"] and st["pages"] == 2
ok("status off → save address → on")
r = post("/api/websearch/query", {"q": "서울 날씨"}); assert len(r["results"]) == 6 and len({x["url"] for x in r["results"]}) == 6, r
assert "/page0 본문입니다" in r["context"] and "/page1 본문" in r["context"] and "/page2 본문" not in r["context"] and "요약 2" in r["context"]
assert "var x" not in r["context"] and "[1]" in r["context"] and r["results"][0]["date"] == "2026-10-20"
ok("results (deduped, n=6) + page text for top 2, scripts stripped, numbered for citations")
MODE["json"] = False
assert "json" in post("/api/websearch/query", {"q": "x"})["error"].lower()
MODE["json"] = True
assert post("/api/websearch/query", {"q": "nude schoolgirl"})["error"] == hub.BLOCK_MSG
assert post("/api/websearch/query", {"q": " "})["error"]
ok("JSON blocked / blocked words / empty")
c = post("/api/chats/save", {"msgs": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a [1]", "sources": [{"title": "t", "url": "http://x.org/a"}, {"url": "javascript:x"}],
                                      "plan": {"id": "p", "state": "done", "steps": [{"images": ["/out/a.png"]}]}, "after": "끝"}]})
m = get("/api/chats/" + c["id"])["msgs"][1]; assert m["sources"] == [{"title": "t", "url": "http://x.org/a", "date": ""}] and m["plan"]["steps"][0]["images"] == ["/out/a.png"] and m["after"] == "끝"
ok("chat save keeps sources, agent plan (with result images) and after-note")
print("ALL OK")
