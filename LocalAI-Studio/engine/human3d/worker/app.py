"""인체 3D worker — 이 PC 안(127.0.0.1)에서만 듣는 작은 서버. LAIS 본체가 작업을 맡기고 진행을 물어봐요.

  GET  /health              살아 있는지·판
  GET  /preflight           돌릴 준비가 됐는지(그래픽카드·모델 파일·SMPL-X)
  POST /jobs                작업 시작 {job_dir, opts}
  GET  /jobs/<id>           진행 상태
  POST /jobs/<id>/cancel    중단
  GET  /jobs/<id>/result    결과 파일 목록

실행:  python -m worker.app [--port 17861] [--home ~/lais-human3d] [--provider 모듈:클래스]"""
import argparse
import importlib
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import runtime as R
from .jobs import Store

VERSION = "0.1"
CFG = {}
PROVIDERS = {}
STORE = None
T0 = time.time()


def provider_of(name):
    if CFG.get("provider_cls"):                       # 시험용: 바깥에서 준 어댑터 하나만
        name = "custom"
    if name not in PROVIDERS:
        if name == "custom":
            mod, cls = CFG["provider_cls"].split(":")
            PROVIDERS[name] = getattr(importlib.import_module(mod), cls)(CFG)
        elif name == "econ":
            from .providers.econ import EconProvider
            PROVIDERS[name] = EconProvider(CFG)
        else:
            from .providers.sith import SithProvider
            PROVIDERS[name] = SithProvider(CFG)
    return PROVIDERS[name]


def result_of(j):
    files = []
    for root, _, names in os.walk(j.dir):
        for n in names:
            p = os.path.join(root, n)
            files.append({"path": os.path.relpath(p, j.dir).replace(os.sep, "/"), "bytes": os.path.getsize(p)})
    return {"id": j.id, "state": j.state, "dir": j.dir, "files": sorted(files, key=lambda f: f["path"]), "job": j.view()}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def send(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except ValueError:
            return {}

    def do_GET(self):
        u = self.path.split("?")[0].rstrip("/")
        if u == "/health":
            b = STORE.busy()
            return self.send({"ok": True, "api": R.API_VERSION, "version": VERSION, "pid": os.getpid(), "busy": b.id if b else None,
                              "uptime": round(time.time() - T0), "home": CFG.get("home"), "python": sys.version.split()[0]})
        if u == "/preflight":
            try:
                name = (self.path.split("provider=")[1].split("&")[0] if "provider=" in self.path else "sith")
                p = provider_of(name)
                return self.send({**p.preflight(), "provider": p.name, "title": p.title, "verified": p.verified, "gpu": R.gpu_info()})
            except Exception as e:  # noqa: BLE001
                return self.send({"ready": False, "checks": [{"id": "worker", "ok": False, "text": f"점검 중 오류: {e}", "fix": ""}], "gpu": R.gpu_info()})
        if u.startswith("/jobs/"):
            parts = u.split("/")
            j = STORE.jobs.get(parts[2])
            if not j:
                return self.send({"error": "작업을 찾을 수 없어요."}, 404)
            return self.send(result_of(j) if len(parts) > 3 and parts[3] == "result" else j.view())
        self.send({"error": "not found"}, 404)

    def do_POST(self):
        u = self.path.split("?")[0].rstrip("/")
        p = self.body()
        if u == "/jobs":
            j, err = STORE.submit(str(p.get("job_dir") or ""), p.get("opts") or {})
            return self.send({"error": err}, 409) if err else self.send({"id": j.id, "state": j.state})
        if u.startswith("/jobs/") and u.endswith("/cancel"):
            return self.send({"ok": STORE.cancel(u.split("/")[2])})
        if u == "/shutdown":
            self.send({"ok": True})
            b = STORE.busy()
            if b:
                STORE.cancel(b.id)
            os._exit(0)
        self.send({"error": "not found"}, 404)


def main():
    global STORE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("HUMAN3D_PORT") or R.PORT))
    ap.add_argument("--home", default=os.environ.get("HUMAN3D_HOME") or os.path.expanduser("~/lais-human3d"))
    ap.add_argument("--provider", default=os.environ.get("HUMAN3D_PROVIDER") or "")
    a = ap.parse_args()
    CFG.update(home=a.home, python=sys.executable, provider_cls=a.provider)
    STORE = Store(provider_of)
    srv = ThreadingHTTPServer((R.HOST, a.port), H)          # 127.0.0.1 에만 — 밖에서는 접근할 수 없어요
    srv.daemon_threads = True
    print(f"human3d worker listening on {R.HOST}:{a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
