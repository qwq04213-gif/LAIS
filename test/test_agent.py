"""3.9: 대화 실행 모드 — 도구 호출 → 검사 → 계획 → [실행] → 기존 대기열, 기록 파일."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17962"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def tc(name, args): return {"function": {"name": name, "arguments": args}}
def say(*calls, content=""): STATE.setdefault("agent_replies", []).append({"role": "assistant", "content": content, "tool_calls": list(calls)} if calls else {"role": "assistant", "content": content})
def png():
    b = io.BytesIO(); Image.new("RGB", (320, 240), (10, 120, 200)).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
BASE = {"gen": {"gengine": "sdxl", "ckpt": "noobai_xl_v11.safetensors", "w": "832", "h": "1216", "n": "1", "prompt": "old", "seed": "5", "init": "data:x"},
        "edit": {"engine": "sdxl", "q_steps": "20"}}
def plan(text, **kw): return post("/api/agent/plan", {"model": "testmodel:latest", "messages": [{"role": "user", "content": text}], "base": BASE, **kw})
def wait(pid):
    for _ in range(300):
        v = get("/api/agent/" + pid)
        if v["state"] not in ("wait", "running"): return v
        time.sleep(0.2)
    raise AssertionError("timeout")

# 1) 그냥 대화
say(content="안녕하세요! 무엇을 만들까요?"); r = plan("안녕"); assert r["reply"].startswith("안녕하세요") and "plan" not in r, r
assert {t["function"]["name"] for t in STATE["agentreq"][-1]["tools"]} >= {"queue_status", "recent_results", "generate_image", "edit_image", "explore_prompts", "relight_image", "analyze_video", "recompose_image", "ask_user", "make_video", "make_music", "make_speech", "upscale_image", "remove_background", "swap_face", "fix_face_hands", "extend_image", "depth_map", "parallax_video", "image_to_3d", "restore_video", "separate_audio", "clean_audio", "trim_video", "join_videos", "add_sound_subtitles", "train_lora"} and STATE["agentreq"][-1]["think"] is False
ok("no tool → plain reply; tool list sent")
# 2) 조회 도구는 바로 실행하고 결과를 모델에 돌려줘서 답을 받아요
say(tc("queue_status", {})); say(content="지금 대기 중인 작업은 없어요.")
r = plan("대기열 뭐 남았어?"); assert r["reply"] == "지금 대기 중인 작업은 없어요." and r["info"][0]["tool"] == "queue_status", r
last = STATE["agentreq"][-1]["messages"]; assert last[-1]["role"] == "tool" and json.loads(last[-1]["content"])["waiting"] == 0
ok("read-only tool executed and fed back")
# 3) 생성 계획 → 실행 → 기존 생성 작업
say(tc("generate_image", {"prompt": "rainy cyberpunk city at night, cinematic", "count": 2}), content="두 장 그릴게요.")
r = plan("비 오는 밤 사이버펑크 도시 두 장 그려 줘"); P = r["plan"]; assert P["state"] == "wait" and P["steps"][0]["summary"].startswith("이미지 만들기 · 2장 · 832×1216"), r
n0 = len(SUBMITTED); assert post("/api/agent/run", {"id": P["id"]})["ok"]
v = wait(P["id"]); assert v["state"] == "done" and len(v["steps"][0]["images"]) == 2, v
assert len(SUBMITTED) - n0 == 2 and "rainy cyberpunk" in json.dumps(SUBMITTED[-1]) and "noobai_xl_v11" in json.dumps(SUBMITTED[-1])
assert post("/api/agent/run", {"id": P["id"]}).get("error"), "second run must be refused"
ok("generate plan runs through the normal queue with screen settings")
gen_img = v["steps"][0]["images"][0]
# 4) 잘못된 값은 실행 전에 거부(범위 밖·모르는 값·모르는 도구·결과 폴더 밖 경로) — 모델에 오류를 돌려주고 다시 기회
for bad in ({"prompt": "x", "count": 9}, {"prompt": "x", "steps": 50}, {"count": 2}):
    say(tc("generate_image", bad)); say(content="다시 알려 주세요.")
    r = plan("그려 줘"); assert "plan" not in r and r["reply"] == "다시 알려 주세요.", (bad, r)
    assert "error" in json.loads(STATE["agentreq"][-1]["messages"][-1]["content"])
say(tc("run_shell", {"cmd": "del *"})); say(content="그건 못 해요."); r = plan("다 지워"); assert "plan" not in r
say(tc("edit_image", {"instruction": "make it red", "image": "/out/../../hub/hub.py"})); say(content="?"); r = plan("고쳐"); assert "plan" not in r
say(tc("edit_image", {"instruction": "make it red", "image": "attached"})); say(content="?"); r = plan("고쳐"); assert "plan" not in r     # 붙인 사진이 없어요
say(tc("generate_image", {"prompt": "nude schoolgirl"})); say(content="?"); r = plan("그려"); assert "plan" not in r
for _ in range(4): say(tc("generate_image", {"prompt": "x", "count": 0}))
r = plan("그려"); assert "plan" not in r and "count" in r["reply"] and r.get("rejected"), r
STATE["agent_replies"] = []
ok("invalid args / unknown tool / path escape / missing attachment / blocked text rejected")
# 5) 생성 → 편집 두 단계, 편집은 앞 단계 결과를 받아요. 칠해서 편집(sdxl)은 말로 편집(qwen)으로 바꿔요
say(tc("generate_image", {"prompt": "a red car"}), tc("edit_image", {"instruction": "make it blue", "image": "previous", "fast": True}))
r = plan("차 그리고 파란색으로 바꿔 줘"); P = r["plan"]; assert [s["tool"] for s in P["steps"]] == ["generate_image", "edit_image"], r
post("/api/agent/run", {"id": P["id"]}); v = wait(P["id"]); assert v["state"] == "done" and all(s["state"] == "done" for s in v["steps"]), v
g = SUBMITTED[-1]; assert any(n["class_type"] in ("TextEncodeQwenImage21",) for n in g.values()) and "make it blue" in json.dumps(g)
ok("two-step plan: edit uses previous result, engine forced to instruction editing")
# 6) 붙인 사진 편집 + 최근 결과 주소 편집
say(tc("edit_image", {"instruction": "watercolor style", "image": "attached"})); r = plan("수채화로", image=png()); P = r["plan"]
post("/api/agent/run", {"id": P["id"]}); assert wait(P["id"])["state"] == "done"
say(tc("recent_results", {"count": 2})); say(content="최근 결과 2개예요.")
r = plan("최근 결과 보여 줘"); files = r["info"][0]["result"]["files"]; assert len(files) == 2 and files[0]["address"].startswith("/out/"), r
say(tc("edit_image", {"instruction": "add snow", "image": gen_img})); r = plan("첫 결과에 눈 내리게"); assert r["plan"]["steps"][0]["summary"].startswith("이미지 편집 · 결과 "), r
ok("attached photo + gallery address")
# 7) 취소: 기다리는 계획 취소 → 실행 불가
P = r["plan"]; assert post("/api/agent/cancel", {"id": P["id"]})["ok"] and post("/api/agent/run", {"id": P["id"]}).get("error")
ok("cancel waiting plan")
# 8) 도구 호출을 못 하는 모델
STATE["notools"] = {"plainmodel"}; r = post("/api/agent/plan", {"model": "plainmodel", "messages": [{"role": "user", "content": "그려 줘"}], "base": BASE}); assert "도구 호출" in r["error"], r
ok("model without tools → guidance")
# 9) 기록: logs/agent.log, logs/job-history.jsonl
lg = (TMP / "logs/agent.log").read_text(encoding="utf-8"); assert '"ev": "plan"' in lg and '"ev": "run"' in lg and "run_shell" in lg
h = [json.loads(x) for x in (TMP / "logs/job-history.jsonl").read_text(encoding="utf-8").splitlines()]; assert any(x.get("agent") == P["id"] or x.get("agent") for x in h) and all("state" in x and "kind" in x for x in h), h[-1]
ok("agent log + persistent job history")
print("ALL OK")
