"""worker(127.0.0.1:17861)와 주고받기. 표준 라이브러리만 써요."""
import json
import urllib.error
import urllib.request

from . import contracts as K


class WorkerError(Exception):
    pass


class Client:
    def __init__(self, port=K.PORT, host=K.HOST):
        self.base = f"http://{host}:{port}"

    def _call(self, path, data=None, timeout=10):
        req = urllib.request.Request(self.base + path, None if data is None else json.dumps(data).encode("utf-8"), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8")).get("error") or str(e)
            except Exception:  # noqa: BLE001
                msg = str(e)
            raise WorkerError(msg) from None
        except (OSError, ValueError) as e:
            raise WorkerError(f"인체 3D 프로그램(worker)에 연결하지 못했어요: {e}") from None

    def health(self, timeout=2):
        try:
            h = self._call("/health", timeout=timeout)
            return h if h.get("ok") else None
        except WorkerError:
            return None

    def preflight(self, provider="sith"):
        return self._call("/preflight?provider=" + provider, timeout=200)

    def submit(self, job_dir, opts):
        return self._call("/jobs", {"job_dir": str(job_dir), "opts": opts})

    def status(self, jid):
        return self._call("/jobs/" + jid)

    def cancel(self, jid):
        return self._call("/jobs/" + jid + "/cancel", {})

    def result(self, jid):
        return self._call("/jobs/" + jid + "/result")

    def shutdown(self):
        try:
            self._call("/shutdown", {}, timeout=3)
        except WorkerError:
            pass
