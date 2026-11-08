"""3.11: 조명 바꾸기·깊이 맵, 없는 모델 바로 받기(need), 작업 관리자는 스튜디오 것만, 탐색·실행 모드 알림 화면."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17968"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def job2(o):
    jid = post("/api/job", o)["id"]
    for _ in range(600):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return jid, j
        time.sleep(0.1)
def cls(c): return [v["inputs"] for v in SUBMITTED[-1].values() if v["class_type"] == c]
def png(c=(10, 120, 200)):
    b = io.BytesIO(); Image.new("RGB", (320, 240), c).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
# 1) 조명 바꾸기: 말로 편집(Qwen) 지시문
_, j = job2({"kind": "feat", "feature": "relight", "image": png(), "light": "golden", "dir": "right", "temp": "warm", "power": "strong", "keep": "on"}); assert j["state"] == "done", j
t = json.dumps(cls("TextEncodeQwenImage21")); assert "golden hour" in t and "from the right" in t and "warm color" in t and "Keep the person" in t and "clearly visible" in t, t
_, j = job2({"kind": "feat", "feature": "relight", "image": png(), "light": "custom", "custom": ""}); assert j["state"] == "error" and "조명" in j["error"]
_, j = job2({"kind": "feat", "feature": "relight", "image": png(), "light": "soft"}); assert "Keep the person" not in json.dumps(SUBMITTED[-1])
ok("relight builds a light-only edit instruction")
# 2) 깊이 맵: 흑백·색·앞쪽만(투명)
jid, j = job2({"kind": "feat", "feature": "depth", "image": png(), "out": "gray"}); assert j["state"] == "done" and cls("DepthAnythingV2Preprocessor"), j
im = Image.open(io.BytesIO(req(j["images"][0], raw=True))); assert im.size == (320, 240)
_, j = job2({"kind": "feat", "feature": "depth", "image": png(), "out": "color"}); assert Image.open(io.BytesIO(req(j["images"][0], raw=True))).mode == "RGB"
_, j = job2({"kind": "feat", "feature": "depth", "image": png(), "out": "cut", "near": "60", "feather": "3"}); im = Image.open(io.BytesIO(req(j["images"][0], raw=True))); assert im.mode == "RGBA", im.mode
meta = json.dumps(j); assert j["state"] == "done"
hub_f = {f["id"]: f for f in get("/api/features")}; assert "relight" in hub_f and "depth" in hub_f and not hub_f["depth"]["missing_nodes"]
STATE["missing"].add("DepthAnythingV2Preprocessor"); hub._CAPS["t"] = 0
_, j = job2({"kind": "feat", "feature": "depth", "image": png()}); assert j["state"] == "error" and "DepthAnythingV2Preprocessor" in j["error"], j
STATE["missing"].discard("DepthAnythingV2Preprocessor"); hub._CAPS["t"] = 0
ok("depth map: gray / color / cut-out, missing extension reported")
# 3) 없는 모델 → need
assert hub.need_ids("업스케일 모델이 없습니다. '설치와 모델' 탭에서 Real-ESRGAN 을 설치해 주세요.") == ["esrgan"]
assert hub.need_ids("없는 파일: TRELLIS.2 모델. '설치와 모델' 탭의 3D 분류에서 'TRELLIS.2' 를 설치해 주세요.") == ["trellis2"]
assert hub.need_ids("없는 파일: FLUX 모델. '설치와 모델' 탭에서 설치하거나", {"kind": "gen", "gengine": "chroma"}) == ["chroma-hd"]
assert hub.need_ids("영상 편집에는 ffmpeg 가 필요해요. 설치와 모델 > 내 PC 점검의 [빠진 부품 설치]") == [] and hub.need_ids("그냥 오류") == []
(M / "upscale_models/RealESRGAN_x4plus.pth").rename(M / "upscale_models/x.bak")
_, j = job2({"kind": "up", "image": png(), "scale": "2"}); assert j["state"] == "error" and j.get("need") == ["esrgan"], j
(M / "upscale_models/x.bak").rename(M / "upscale_models/RealESRGAN_x4plus.pth")
r = post("/api/install", {"ids": ["esrgan-anime"]}); assert r["ok"] and r["ids"] == ["esrgan-anime"], r
assert hub.expand_ids(["wan-s2v"])[:2] == ["wan-s2v", "wan-common"]
for t_ in get("/api/install"):
    if t_["state"] in ("queued", "running"): post("/api/install/cancel", {"id": t_["id"]})
ok("missing-model errors carry catalog ids; install returns the expanded ids")
# 4) 작업 관리자: 다른 프로그램은 빼요
hub._MON.update(t=time.time(), procs=[{"pid": 99999, "name": "C:/Games/game.exe", "mb": 3000}, {"pid": 99998, "name": "C:/x/engine/tts/qwen3/venv/Scripts/python.exe", "mb": 900}])
v = get("/api/monitor"); assert [o["who"] for o in v["others"]] == ["음성 엔진"], v["others"]
ok("task manager lists only the studio's engines")
# 5) 탐색·실행 모드 작업은 알림을 누르면 그 화면으로
STATE["json_replies"] = [json.dumps({"variants": [{"label": "a", "changes": {"style": "x"}}]})]
S = post("/api/explore/candidates", {"mode": "param", "base": {"gengine": "sdxl", "ckpt": "noobai_xl_v11.safetensors"}, "elements": {"subject": "cat"}, "param": "cfg", "values": "4 5"})
post("/api/explore/run", {"id": S["id"]}); time.sleep(0.3)
q = get("/api/queue"); rows = [i for i in q["items"] if i["label"].startswith("프롬프트 탐색")]; assert rows and all(i["view"] == "explore" and i["xp"] == S["id"] for i in rows), rows
STATE["agent_replies"] = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "relight_image", "arguments": {"image": "attached", "light": "neon", "direction": "left"}}}]}]
P = post("/api/agent/plan", {"model": "testmodel:latest", "messages": [{"role": "user", "content": "네온 조명으로"}], "image": png(), "base": {}})["plan"]
assert P["steps"][0]["summary"] == "조명 바꾸기 · 붙인 사진 · 네온사인", P
post("/api/agent/run", {"id": P["id"]})
for _ in range(300):
    pv = get("/api/agent/" + P["id"])
    if pv["state"] not in ("wait", "running"): break
    time.sleep(0.2)
assert pv["state"] == "done" and pv["steps"][0]["images"], pv
q = get("/api/queue"); assert any(i["view"] == "chat" for i in q["items"]), q["items"][:3]
STATE["agent_replies"] = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "relight_image", "arguments": {"image": "attached", "light": "custom"}}}]}, {"role": "assistant", "content": "?"}]
assert "plan" not in post("/api/agent/plan", {"model": "testmodel:latest", "messages": [{"role": "user", "content": "x"}], "image": png(), "base": {}})
ok("explore / agent jobs point notifications at their own screen; relight agent tool")
print("ALL OK")
