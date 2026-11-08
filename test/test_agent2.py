"""3.17: 실행 모드가 모든 기능을 부름(영상·음악·음성·업스케일·배경·얼굴·확장·깊이·3D·영상 복원·소리·자르기·잇기·소리 자막·LoRA) + 모호하면 되묻기(ask_user)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, subprocess, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17997"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def tc(name, args): return {"function": {"name": name, "arguments": args}}
def say(*calls, content=""): STATE.setdefault("agent_replies", []).append({"role": "assistant", "content": content, "tool_calls": list(calls)} if calls else {"role": "assistant", "content": content})
def png():
    b = io.BytesIO(); Image.new("RGB", (320, 240), (10, 120, 200)).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
BASE = {"gen": {"gengine": "sdxl", "ckpt": "noobai_xl_v11.safetensors", "w": "832", "h": "1216", "n": "1"}, "edit": {"engine": "qwen"},
        "vid": {"wan_ver": "5b", "size": "832x480", "sec": "3", "steps": "20"}, "music": {"mengine": "music", "seconds": "30"}, "tts": {"engine": "sapi"}, "up": {"upm": ""}}
def plan(text, **kw): return post("/api/agent/plan", {"model": "testmodel:latest", "messages": [{"role": "user", "content": text}], "base": BASE, **kw})
def run(P):
    assert post("/api/agent/run", {"id": P["id"]})["ok"]
    for _ in range(600):
        v = get("/api/agent/" + P["id"])
        if v["state"] not in ("wait", "running"): return v
        time.sleep(0.2)
# 되묻기
say(tc("ask_user", {"question": "어떤 느낌의 여성을 그릴까요?", "options": ["실사 인물 사진", "애니 일러스트", "카페 창가", "알아서 해 줘"]}))
r = plan("예쁜 여성 그려 줘"); assert r["reply"].startswith("어떤 느낌") and len(r["options"]) == 4 and "plan" not in r, r
assert "ask_user" in STATE["agentreq"][-1]["messages"][0]["content"] or "vague" in STATE["agentreq"][-1]["messages"][0]["content"]
ok("vague request → ask_user question with clickable options (no job)")
# 이미지 → 업스케일 → 배경 지우기 (previous 로 잇기)
say(tc("generate_image", {"prompt": "a cat"}), tc("upscale_image", {"image": "previous", "scale": 2}), tc("remove_background", {"image": "previous", "background": "white"}))
r = plan("고양이 그리고 2배로 키운 다음 배경 지워 줘"); P = r["plan"]; assert [s["summary"].split(" · ")[0] for s in P["steps"]] == ["이미지 만들기", "업스케일", "배경 지우기"], P
v = run(P); assert v["steps"][0]["state"] == v["steps"][1]["state"] == "done" and v["steps"][2]["job"], v   # 배경 모델은 테스트 환경에 없어서 받기 안내까지만
ok("chained image tools (generate → upscale → background) through the normal queue")
# 영상 만들기 · 음성
say(tc("make_video", {"prompt": "a cat walking", "seconds": 5, "orientation": "portrait"}), tc("make_speech", {"text": "안녕하세요"}))
r = plan("고양이 걷는 세로 영상 5초 만들고 안녕하세요 읽어 줘"); P = r["plan"]
jp = [hub.agent_job_more(hub.AGENT_PLANS[P["id"]], i, s, s["args"], BASE) for i, s in enumerate(hub.AGENT_PLANS[P["id"]]["steps"])]
assert jp[0]["kind"] == "vid" and jp[0]["size"] == "480x832" and jp[0]["sec"] == 5 and jp[0]["wan_ver"] == "5b" and jp[1] == {"engine": "sapi", "kind": "tts", "text": "안녕하세요"}
ok("video / speech jobs built from the screen settings")
# 영상·소리 도구: 실제 ffmpeg
vd = hub.OUT / "영상"; vd.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x120:r=12:d=4", "-f", "lavfi", "-i", "sine=f=300:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(vd / "c.mp4")], check=True)
V = "/out/" + urllib.parse.quote("영상") + "/c.mp4"
say(tc("trim_video", {"video": V, "start": 1, "end": 3}), tc("clean_audio", {"source": "previous", "loudness": "speech"}))
r = plan("1초부터 3초까지 자르고 그 소리 깨끗하게"); v = run(r["plan"]); assert v["state"] == "done", v
assert v["steps"][0]["images"][0].endswith(".mp4") and v["steps"][1]["images"][0].endswith(".wav")
say(tc("restore_video", {"video": V, "denoise": "medium", "stabilize": True}))
v = run(plan("이 영상 노이즈랑 흔들림 잡아 줘")["plan"]); assert v["state"] == "done" and any(u.endswith(".mp4") for u in v["steps"][0]["images"]), v
ok("trim → clean sound (previous video's audio), restore video — real ffmpeg")
# 검사
def tool_err(): return json.dumps([m for m in STATE["agentreq"][-1]["messages"] if m["role"] == "tool"], ensure_ascii=False)
say(tc("trim_video", {"video": V, "start": 3, "end": 1})); r = plan("x"); assert "plan" not in r and "끝은" in tool_err()
say(tc("join_videos", {"videos": [V]})); r = plan("x"); assert "두 개" in tool_err()
say(tc("train_lora", {"set": "없는세트"})); r = plan("x"); assert "학습 세트가 없어요" in tool_err()
S = post("/api/lora/set/new", {"name": "나비", "trigger": "nabi"})
say(tc("train_lora", {"set": "나비"})); r = plan("나비 로라 학습해 줘"); P = r["plan"]
assert hub.agent_job_more(hub.AGENT_PLANS[P["id"]], 0, hub.AGENT_PLANS[P["id"]]["steps"][0], hub.AGENT_PLANS[P["id"]]["steps"][0]["args"], BASE)["id"] == S["id"]
say(tc("make_music", {"description": "nude schoolgirl"})); r = plan("x"); assert hub.BLOCK_MSG in tool_err()
ok("checks: bad trim range, join needs 2+, unknown LoRA set lists real ones, blocked words")
print("ALL OK")
