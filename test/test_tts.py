"""음성 만들기: 윈도우 내장 음성·Edge 호출 방식, 입력 검사, 저장."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, json, time, urllib.request, pathlib, subprocess
sys.path.insert(0, BASE + "/test")
from mocks import *
import tts
ok = lambda m: print("PASS", m)
D = pathlib.Path("/tmp/tt/ttscache"); D.mkdir(parents=True, exist_ok=True)
class R:
    def __init__(s, rc=0, out=b"", err=b""): s.returncode, s.stdout, s.stderr = rc, out, err
calls = []
def fake_run(cmd, **k):
    calls.append(cmd)
    if "list" in cmd: return R(0, "Microsoft Heami Desktop|ko-KR\r\nMicrosoft Zira Desktop|en-US\r\n".encode())
    if "speak" in cmd:
        out = pathlib.Path(cmd[cmd.index("-Out") + 1]); out.write_bytes(b"RIFF" + b"\0" * 200)
        assert pathlib.Path(cmd[cmd.index("-TextFile") + 1]).read_text(encoding="utf-8") == "안녕하세요 ✓"
        return R(0)
    if "edge_tts" in cmd:
        pathlib.Path(cmd[cmd.index("--write-media") + 1]).write_bytes(b"ID3" + b"\0" * 200); return R(0)
    return R(1, b"", b"boom")
v = tts.sapi_voices(D, fake_run, force=True, is_windows=True); assert v == [("Microsoft Heami Desktop", "ko-KR"), ("Microsoft Zira Desktop", "en-US")], v; ok("Windows voices are listed from PowerShell output")
assert tts.sapi_voices(D, fake_run, is_windows=False) == []; ok("non-Windows → no built-in voices (no crash)")
assert (D / "sapi.ps1").read_bytes()[:3] == b"\xef\xbb\xbf"; ok("script is written with a BOM so Korean works in Windows PowerShell")
w = tts.speak_sapi("안녕하세요 ✓", "Microsoft Heami Desktop", 2, 80, D, fake_run); assert w[:4] == b"RIFF"
c = calls[-1]; assert c[c.index("-Voice") + 1] == "Microsoft Heami Desktop" and c[c.index("-Rate") + 1] == "2" and c[c.index("-Volume") + 1] == "80"; ok("SAPI: text goes through a UTF-8 file (no quoting problems), voice/rate/volume passed")
tts.edge_ready = lambda: True
m = tts.speak_edge("안녕하세요 ✓", "ko-KR-SunHiNeural", 10, -20, 0, D, fake_run)
c = calls[-1]; assert m[:3] == b"ID3" and "--rate=+10%" in c and "--volume=-20%" in c and "--pitch=+0Hz" in c and c[c.index("--voice") + 1] == "ko-KR-SunHiNeural"; ok("Edge: command line built correctly")
try: tts.speak_sapi("x", "", 0, 100, D, lambda *a, **k: R(1, b"", "오류".encode())); assert 0
except RuntimeError as e: assert "읽지 못했어요" in str(e); ok("failure → readable message")
tts.edge_ready = lambda: False
try: tts.speak_edge("x", "v", 0, 0, 0, D, fake_run); assert 0
except RuntimeError as e: assert "부품" in str(e); ok("Edge part missing → asks to install it")
# 허브 경유(작업 큐)
tts.edge_ready = lambda: True; tts.FORCE_SAPI = True
tts.sapi_voices = lambda *a, **k: [("Microsoft Heami Desktop", "ko-KR")]
tts.speak_sapi = lambda text, voice, rate, vol, cd, run=None: b"RIFF" + b"\0" * 300
tts.speak_edge = lambda text, voice, rate, vol, pitch, cd, run=None, py=None: b"ID3" + b"\0" * 300
V = json.load(urllib.request.urlopen(B + "/api/tts/voices")); assert V["sapi_ok"] and V["edge_ok"] and any(x["name"] == "ko-KR-SunHiNeural" for x in V["edge"]); ok("voices endpoint")
wait = lambda p: job(p, expect_ok=False)
for eng, ext in (("sapi", ".wav"), ("edge", ".mp3")):
    s = wait({"kind": "tts", "text": "안녕하세요", "engine": eng, "voice": "x"}); assert s["state"] == "done" and s["images"][0].endswith(ext) and "/음성/" in urllib.request.unquote(s["images"][0]), s
    r = urllib.request.urlopen(B + s["images"][0]); assert r.headers["Content-Type"].startswith("audio/"); ok(f"{eng}: job saves {ext} under 음성 and serves it as audio")
s = wait({"kind": "tts", "text": "   "}); assert s["state"] == "error" and "글" in s["error"]; ok("empty text refused")
s = wait({"kind": "tts", "text": "가" * 5001}); assert s["state"] == "error" and "5000" in s["error"]; ok("too long refused")
g = json.load(urllib.request.urlopen(B + "/api/gallery")) if True else None
assert not any(str(x.get("file", "")).endswith((".wav",)) for x in (g if isinstance(g, list) else g.get("items", []))); ok("audio files never show up in the image gallery")
print("ALL OK")
