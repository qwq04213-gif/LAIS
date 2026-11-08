"""확장 설치: requirements 의 git+ 줄은 빼고 설치한다(git 이 없는 PC 대비)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, io, zipfile, time, urllib.request, pathlib
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("x-main/__init__.py", ""); z.writestr("x-main/requirements.txt", "numpy\ngit+https://github.com/a/b\n# c\ndill\n")
class R(io.BytesIO):
    def __enter__(s): return s
    def __exit__(s, *a): pass
orig = urllib.request.urlopen
urllib.request.urlopen = lambda url, *a, **k: R(buf.getvalue()) if "github.com" in (url if isinstance(url, str) else url.full_url) else orig(url, *a, **k)
calls = []
fake = pathlib.Path("/tmp/tt/fakepy.sh"); fake.write_text("#!/bin/sh\ncp \"$6\" /tmp/tt/req_used.txt\n"); fake.chmod(0o755)
hub.PY = fake
import subprocess
try:
    hub.NODE_JOBS[hub.SUBPACK_REPO] = {"state": "running", "msg": ""}
    import shutil; shutil.rmtree(hub._repo_dir(hub.SUBPACK_REPO), ignore_errors=True)
    hub._node_install(hub.SUBPACK_REPO)
finally: urllib.request.urlopen = orig
J = hub.NODE_JOBS[hub.SUBPACK_REPO]; assert J["state"] == "done", J
used = pathlib.Path("/tmp/tt/req_used.txt").read_text(); assert used.split() == ["numpy", "dill"], used; ok("git+ and comment lines are dropped before pip runs")
shutil.rmtree(hub._repo_dir(hub.SUBPACK_REPO), ignore_errors=True)
print("ALL OK")
# ReActor: 확인해 둔 커밋의 install.py 를 실행(요구 파일 설치 대신)
buf2 = io.BytesIO()
with zipfile.ZipFile(buf2, "w") as z:
    z.writestr("r-main/__init__.py", ""); z.writestr("r-main/install.py", "print('x')"); z.writestr("r-main/requirements.txt", "evil-pkg\n")
urllib.request.urlopen = lambda url, *a, **k: R(buf2.getvalue()) if "github.com" in (url if isinstance(url, str) else url.full_url) else orig(url, *a, **k)
fake2 = pathlib.Path("/tmp/tt/fakepy2.sh"); fake2.write_text("#!/bin/sh\nif [ \"$2\" = install.py ]; then pwd > /tmp/tt/ran_cwd.txt; echo \"$@\" > /tmp/tt/ran_args.txt; fi\n"); fake2.chmod(0o755)
hub.PY = fake2
try:
    hub.NODE_JOBS[hub.REACTOR_REPO] = {"state": "running", "msg": ""}
    shutil.rmtree(hub._repo_dir(hub.REACTOR_REPO), ignore_errors=True)
    hub._node_install(hub.REACTOR_REPO)
finally: urllib.request.urlopen = orig
J = hub.NODE_JOBS[hub.REACTOR_REPO]; assert J["state"] == "done", J
assert pathlib.Path("/tmp/tt/ran_args.txt").read_text().split() == ["-s", "install.py"] and pathlib.Path("/tmp/tt/ran_cwd.txt").read_text().strip().endswith("ComfyUI-ReActor"); ok("ReActor: its own install.py runs inside the extension folder (requirements.txt is not pip-installed directly)")
shutil.rmtree(hub._repo_dir(hub.REACTOR_REPO), ignore_errors=True)
print("ALL OK")
