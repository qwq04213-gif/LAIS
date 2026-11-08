"""3.12: 영상 분석·하이라이트(장면·대표 장면·무음·대사·장면 설명·계획·구간 편집·자막), 깊이 활용(저장·재사용·배경 흐림·효과·패럴랙스·3D 메시·영상 깊이·카메라 움직임)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, subprocess, struct, urllib.request
os.environ["TEST_HUB_PORT"] = "17971"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def job2(o):
    jid = post("/api/job", o)["id"]
    for _ in range(1200):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def png(w=320, h=240):
    import numpy as np
    a = np.zeros((h, w, 3), np.uint8); a[..., 0] = np.linspace(0, 255, w)[None, :]; a[60:180, 100:220] = (250, 250, 250)
    b = io.BytesIO(); Image.fromarray(a).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True); return float(r.stdout.strip() or 0)
# 테스트 영상: 빨강 2초(소리) · 파랑 2초(무음) · 초록 2초(소리) + 잡음 무늬
V = hub.OUT / "영상"; V.mkdir(parents=True, exist_ok=True); src = V / "test-src.mp4"
cmd = ["ffmpeg", "-y", "-v", "error"]
for c in ("red", "blue", "green"): cmd += ["-f", "lavfi", "-i", f"color=c={c}:s=320x240:d=2:r=24"]
cmd += ["-f", "lavfi", "-i", "sine=f=440:d=2", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2", "-f", "lavfi", "-i", "sine=f=660:d=2",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,noise=alls=10:allf=t[v];[3:a][4:a][5:a]concat=n=3:v=0:a=1[a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)]
subprocess.run(cmd, check=True)
SRC = "/out/%EC%98%81%EC%83%81/test-src.mp4"
# 받아쓰기 엔진은 흉내(진짜 Whisper 는 이 환경에서 못 돌려요)
hub.asr_models.installed = lambda root: True
hub.asr_models.transcribe = lambda root, wav, model, lang, ff, say=None, cancel=None: (say and say(0.5, "받아쓰는 중"), [{"s": 0.2, "e": 1.8, "text": "안녕하세요 빨강입니다"}, {"s": 4.1, "e": 5.8, "text": "초록 장면이에요"}])[1]
STATE["vision"] = ["testmodel:latest"]
# 1) 분석
j = job2({"kind": "vana", "op": "analyze", "video": SRC, "asr": True, "vision": "testmodel:latest", "sens": "0.3"}); assert j["state"] == "done" and j.get("vana"), j
A = get("/api/vana/" + j["vana"])
assert len(A["shots"]) == 3, [(s["start"], s["end"]) for s in A["shots"]]
assert abs(A["shots"][1]["start"] - 2.0) < 0.2 and A["meta"]["audio"] and A["src_ok"]
assert any(1.8 < a < 2.3 and 3.7 < b < 4.2 for a, b in A["silences"]), A["silences"]
assert "빨강" in A["shots"][0]["text"] and "초록" in A["shots"][2]["text"] and A["shots"][1]["text"] == "" and A["shots"][1]["silent"] > 1.5
assert A["shots"][0]["caption"] and A["shots"][0]["q"]["bright"] > 0
th = urllib.request.urlopen(B + f"/vana/{A['id']}/{A['shots'][0]['thumb']}"); assert th.headers["Content-Type"] == "image/jpeg"
try: urllib.request.urlopen(B + f"/vana/{A['id']}/..%2Fdata.json"); raise AssertionError("must 404")
except urllib.error.HTTPError: pass
assert get("/api/vana")["items"][0]["id"] == A["id"]
ok("analyze: 3 shots at the color cuts, silence, speech mapped to shots, captions, thumbnails")
# 2) 하이라이트 계획: 자동 / AI(검증)
r = post("/api/vana/plan", {"id": A["id"], "mode": "auto", "target": 4}); ids = [x["id"] for x in r["plan"]]
assert 1 not in ids and set(ids) <= {0, 2} and r["total"] <= 4.7, r
STATE["json_replies"] = [json.dumps({"pick": [{"id": 2, "start": 4.5, "end": 5.5, "reason": "초록"}, {"id": 0, "start": 0, "end": 99, "reason": "빨강"}, {"id": 77, "start": 1, "end": 2}]})]
r = post("/api/vana/plan", {"id": A["id"], "mode": "ai", "target": 10, "goal": "말하는 장면", "model": "testmodel:latest"})
assert [(x["id"], x["start"], x["end"]) for x in r["plan"]] == [(2, 4.5, 5.5), (0, 0.0, A["shots"][0]["end"])], r
assert "말하는 장면" in STATE["jsonreq"][-1]["messages"][-1]["content"] and "안녕하세요" in STATE["jsonreq"][-1]["messages"][-1]["content"]
ok("plan: auto skips the silent shot; AI picks clamped to shots, unknown ids dropped")
# 3) 구간 편집: 무음 빼기 + 자막(.srt) / 영상에 입히기
assert post("/api/vana/render", {"id": A["id"], "segs": [{"start": 5, "end": 99}]})["error"]
r = post("/api/vana/render", {"id": A["id"], "segs": [{"start": 0, "end": 2}, {"start": 2, "end": 4}, {"start": 4, "end": 6}], "drop_silence": True, "subs": "srt"}); assert r["ok"]
for _ in range(600):
    jj = get("/api/job/" + r["job"])
    if jj["state"] in ("done", "error"): break
    time.sleep(0.1)
assert jj["state"] == "done", jj
out = hub.out_path(urllib.request.unquote(jj["images"][0])[5:]); d = dur(out); assert 3.4 < d < 4.6, d
srt = out.with_suffix(".srt").read_text(encoding="utf-8"); assert "안녕하세요" in srt and "초록" in srt, srt
q = get("/api/queue"); assert any(i.get("view") == "vana" for i in q["items"])
r = post("/api/vana/render", {"id": A["id"], "segs": [{"start": 4, "end": 6}], "subs": "burn"})
for _ in range(600):
    jj = get("/api/job/" + r["job"])
    if jj["state"] in ("done", "error"): break
    time.sleep(0.1)
assert jj["state"] == "done" and 1.8 < dur(hub.out_path(urllib.request.unquote(jj["images"][0])[5:])) < 2.3, jj
ok("render: segments cut & joined, silent part dropped, subtitles remapped (.srt) and burned in")
# 4) 깊이: 저장·재사용, 배경 흐림·효과, ControlNet 메뉴용 파일 이름
P = png()
j = job2({"kind": "feat", "feature": "depth", "image": P, "out": "gray"}); assert j["state"] == "done" and "depth-" in j["images"][0] and "%EA%B9%8A%EC%9D%B4" in j["images"][0], j["images"]
n0 = len(SUBMITTED)
j = job2({"kind": "feat", "feature": "depth", "image": P, "out": "blur", "blur": "10"}); assert j["state"] == "done" and len(SUBMITTED) == n0 and any("저장된 깊이 맵" in w for w in j.get("warn", [])), j
for eff in ("gray", "fog", "dark"):
    j = job2({"kind": "feat", "feature": "depth", "image": P, "out": "fx", "effect": eff}); assert j["state"] == "done", j
j = job2({"kind": "feat", "feature": "depth", "image": P, "out": "gray", "depth_img": png(64, 48)}); assert j["state"] == "done" and len(SUBMITTED) == n0
ok("depth map saved to its own folder and reused (no re-estimation); blur and background effects")
# 5) 패럴랙스 · 3D 메시
j = job2({"kind": "feat", "feature": "parallax", "image": P, "motion": "orbit", "sec": "2", "fps": "12"}); assert j["state"] == "done" and j["images"][0].endswith(".mp4"), j
assert 1.7 < dur(hub.out_path(urllib.request.unquote(j["images"][0])[5:])) < 2.3
j = job2({"kind": "feat", "feature": "depth3d", "image": P, "grid": "64"}); assert j["state"] == "done" and j["images"][0].endswith(".glb"), j
g = hub.out_path(urllib.request.unquote(j["images"][0])[5:]).read_bytes(); assert struct.unpack("<I", g[:4])[0] == 0x46546C67
ok("parallax mp4 and depth relief mesh (.glb)")
# 6) 카메라 움직임 → 패럴랙스에 쓰기 · 영상 깊이(일관성)
pan = V / "pan.mp4"; subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=3:r=24", "-vf", "crop=320:240:'t*80':60", "-pix_fmt", "yuv420p", str(pan)], check=True)
j = job2({"kind": "vana", "op": "camera", "video": "/out/%EC%98%81%EC%83%81/pan.mp4"}); assert j["state"] == "done", j
js = next(u for u in j["images"] if u.endswith(".json")); data = json.loads(hub.out_path(urllib.request.unquote(js)[5:]).read_text(encoding="utf-8"))
assert data["track"][-1]["dx"] < -0.3 and "2D" in data["note"], data["track"][-1]
j2 = job2({"kind": "feat", "feature": "parallax", "image": P, "motion": "camera", "camera": js, "sec": "1", "fps": "12"}); assert j2["state"] == "done", j2
j = job2({"kind": "vana", "op": "vdepth", "video": SRC, "fps": "4", "width": "256", "smooth": "60"}); assert j["state"] == "done" and j["images"][0].endswith(".mp4") and "깜빡임" in j["msg"], j
ok("camera motion (2D) estimated from a panning video and reused for parallax; temporally smoothed depth video")
# 7) 실행 모드 도구
STATE["agent_replies"] = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "analyze_video", "arguments": {"video": SRC}}}]}]
Pl = post("/api/agent/plan", {"model": "testmodel:latest", "messages": [{"role": "user", "content": "이 영상 분석해 줘"}], "base": {}})["plan"]
post("/api/agent/run", {"id": Pl["id"]})
for _ in range(600):
    pv = get("/api/agent/" + Pl["id"])
    if pv["state"] not in ("wait", "running"): break
    time.sleep(0.2)
assert pv["state"] == "done" and pv["steps"][0].get("vana"), pv
ok("agent analyze_video → analysis id for the plan card link")
print("ALL OK")
