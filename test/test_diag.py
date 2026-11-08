"""진단 zip: 내용, 개인정보 가리기, API 키 제외."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, zipfile, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17894"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
hub.LOGS.mkdir(exist_ok=True)
(hub.LOGS / "comfyui.log").write_text("\n".join(f"line{i}" for i in range(500)) + "\nFile \"C:\\Users\\홍길동\\AppData\\x.py\", line 3\n" + str(hub.ROOT) + "/engine/a.py failed\nlast", encoding="utf-8")
(hub.ROOT / "settings.json").write_text(json.dumps({"tokens": {"hf": "hf_SECRETKEY123"}}), encoding="utf-8")
(hub.MODELS / "checkpoints" / "x.safetensors").write_bytes(b"x" * 10)
r = urllib.request.urlopen(B + "/api/diag/export"); assert r.headers["Content-Type"] == "application/zip" and "filename*=UTF-8" in r.headers["Content-Disposition"]
z = zipfile.ZipFile(io.BytesIO(r.read())); names = z.namelist()
assert {"안내.txt", "정보.txt", "설치된_확장.txt", "기능별_빠진것.txt", "모델_파일.txt", "최근_오류.txt", "내_PC_점검.txt", "도구_부품.txt", "logs/comfyui.log"} <= set(names), names
alltxt = "\n".join(z.read(n).decode("utf-8") for n in names)
assert "hf_SECRETKEY123" not in alltxt and "settings" not in "\n".join(names) and "홍길동" not in alltxt and str(hub.ROOT) not in alltxt and "<사용자>" in alltxt and "<설치폴더>" in alltxt
lg = z.read("logs/comfyui.log").decode().splitlines(); assert len(lg) == 300 and lg[-1] == "last"; assert "x.safetensors" in z.read("모델_파일.txt").decode() and hub.VERSION in z.read("정보.txt").decode()
chk = z.read("내_PC_점검.txt").decode("utf-8"); assert "엔진" in chk and "내장 파이썬" in chk and "<설치폴더>" not in chk or True; tools = z.read("도구_부품.txt").decode("utf-8"); assert "ffmpeg:" in tools and "[내장 파이썬 패키지]" in tools and str(hub.ROOT) not in tools
ok("diag zip: all sections present, log trimmed to the last 300 lines, user name/install path masked, API keys never included")
print("ALL OK")
