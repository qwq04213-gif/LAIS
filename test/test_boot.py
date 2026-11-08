"""2.4: 엔진 시작 옵션 확인 결과 캐시(main.py 가 같으면 --help 를 다시 안 불러요) + 시작 시간 기록."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, stat
os.environ["TEST_HUB_PORT"] = "17934"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
d = hub.ROOT / "fakepy"; d.mkdir(exist_ok=True)
cnt = d / "count.txt"; cnt.write_text("")
py = d / "py.sh"; py.write_text(f'#!/bin/sh\necho x >> {cnt}\necho "--fast fp16_accumulation"\n'); py.chmod(0o755)
hub.PY = py; hub.COMFY.mkdir(parents=True, exist_ok=True); (hub.COMFY / "main.py").write_text("# fake\n"); hub.LOGS.mkdir(exist_ok=True)
(hub.LOGS / "speed_args.json").unlink(missing_ok=True)
a1 = hub.speed_args(); a2 = hub.speed_args()
assert a1 == a2 == ["--fast", "fp16_accumulation"] and len(cnt.read_text().split()) == 1, (a1, a2, cnt.read_text()); ok("second start reuses the saved answer (ComfyUI asked only once)")
(hub.COMFY / "main.py").write_text("# fake changed\n"); hub.speed_args(); assert len(cnt.read_text().split()) == 2; ok("changed main.py → asked again")
print("ALL OK")
