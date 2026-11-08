"""3.10: 프롬프트 탐색 — 요소 나누기, 후보(직접·AI·설정·다음 라운드), 대기열 실행, 비교 기록, 실행 모드 도구, 모델·진행 정보."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, urllib.request
os.environ["TEST_HUB_PORT"] = "17966"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
J = lambda o: STATE.setdefault("json_replies", []).append(json.dumps(o))
GEN_BASE = {"gengine": "sdxl", "ckpt": "noobai_xl_v11.safetensors", "w": "832", "h": "1216", "n": "1", "prompt": "old", "seed": "5", "cfg": "6", "steps": "20"}
EL = {"subject": "a lone woman with an umbrella", "place": "cyberpunk city street", "action": "", "camera": "low angle wide shot", "light": "neon signs",
      "color": "teal and magenta", "style": "cinematic film still", "detail": "rain droplets", "negative": "blurry"}
def wait(sid):
    for _ in range(300):
        v = get("/api/explore/" + sid)
        if not any(c["state"] in ("queued", "running") for c in v["cands"]): return v
        time.sleep(0.2)
    raise AssertionError("timeout")
# 1) 요소 나누기
J({**EL, "junk": "x", "action": 5}); r = post("/api/explore/analyze", {"goal": "비 오는 밤 사이버펑크 도시, 영화 같은 느낌", "model": "testmodel:latest"})
assert r["elements"]["light"] == "neon signs" and r["elements"]["action"] == "" and "junk" not in r["elements"], r
q = STATE["jsonreq"][-1]; assert q["format"] == "json" and q["think"] is False and "비 오는" in q["messages"][-1]["content"]
assert post("/api/explore/analyze", {"goal": "", "model": "testmodel:latest"})["error"]
assert "미성년" in post("/api/explore/analyze", {"goal": "nude schoolgirl", "model": "testmodel:latest"})["error"]
ok("analyze: JSON parts cleaned, empty / blocked goal refused")
# 2) AI 변형: 허용한 요소만 바꿔요
J({"variants": [{"label": "황금빛", "changes": {"light": "golden hour", "subject": "a man"}}, {"label": "흑백", "changes": {"color": "black and white"}},
                {"label": "빈 변형", "changes": {"place": "beach"}}, {"label": "수채화", "changes": {"style": "watercolor painting"}}]})
S = post("/api/explore/candidates", {"mode": "auto", "goal": "비 오는 밤", "model": "testmodel:latest", "base": GEN_BASE, "elements": EL, "count": 3, "vary": ["light", "color", "style"]})
c = S["cands"]; assert [x["label"] for x in c] == ["기준", "황금빛", "흑백", "수채화"], [x["label"] for x in c]
assert c[1]["elements"]["subject"] == EL["subject"] and c[1]["changed"] == ["light"] and c[1]["prompt"].startswith("a lone woman with an umbrella, low angle") is False
assert c[0]["prompt"] == "a lone woman with an umbrella, cyberpunk city street, low angle wide shot, neon signs, teal and magenta, cinematic film still, rain droplets", c[0]["prompt"]
assert "base" not in S and S["style"] == "tags" and all(x["state"] == "new" for x in c)
ok("auto variants: only allowed parts change, SDXL → comma tags")
# 3) 그리기: 같은 시드·기존 대기열·네거티브
n0 = len(SUBMITTED); r = post("/api/explore/run", {"id": S["id"]}); assert all(x["state"] in ("queued", "running", "done") for x in r["cands"])
v = wait(S["id"]); assert all(x["state"] == "done" and len(x["images"]) == 1 for x in v["cands"]), v["cands"]
subs = SUBMITTED[n0:]; assert len(subs) == 4
seeds = {n["inputs"]["seed"] for g in subs for n in g.values() if n["class_type"] == "KSampler"}; assert len(seeds) == 1, seeds
assert "golden hour" in json.dumps(subs[1]) and "blurry" in json.dumps(subs[0])
assert post("/api/explore/run", {"id": S["id"]})["error"]
q = get("/api/queue"); assert any(i["label"].startswith("프롬프트 탐색 · ") for i in q["items"]), q
ok("run: one image per candidate through the queue with a shared seed")
# 4) 직접 바꾸기 + 설정 비교 + 고르기 + 다음 라운드
S2 = post("/api/explore/candidates", {"mode": "manual", "id": S["id"], "elements": EL, "key": "light", "values": ["moonlight", "", "  candle light "]})
r2 = [x for x in S2["cands"] if x["round"] == 2]; assert [x["label"] for x in r2] == ["기준", "moonlight", "candle light"] and r2[1]["elements"]["light"] == "moonlight"
assert post("/api/explore/candidates", {"mode": "manual", "id": S["id"], "elements": EL, "key": "nope", "values": ["x"]})["error"]
S3 = post("/api/explore/candidates", {"mode": "param", "id": S["id"], "elements": EL, "param": "cfg", "values": "4, 7 7"}); r3 = [x for x in S3["cands"] if x["round"] == 3]
assert [x["params"] for x in r3] == [{"cfg": 4.0}, {"cfg": 7.0}]
assert "사이" in post("/api/explore/candidates", {"mode": "param", "id": S["id"], "elements": EL, "param": "steps", "values": "4, 500"})["error"]
n0 = len(SUBMITTED); post("/api/explore/run", {"id": S["id"]}); wait(S["id"]); assert [n["inputs"]["cfg"] for g in SUBMITTED[n0:] for n in g.values() if n["class_type"] == "KSampler"] == [4.0, 7.0]
pick = v["cands"][1]["cid"]; assert post("/api/explore/pick", {"id": S["id"], "cid": pick, "picked": True})["ok"]
J({"variants": [{"label": "더 따뜻하게", "changes": {"color": "warm orange"}}]})
S4 = post("/api/explore/candidates", {"mode": "refine", "id": S["id"], "from": pick, "count": 3, "note": "더 따뜻하게", "model": "testmodel:latest"})
r4 = [x for x in S4["cands"] if x["round"] == 4]; assert r4[0]["label"] == "고른 후보" and r4[0]["elements"]["light"] == "golden hour" and r4[1]["elements"]["color"] == "warm orange"
assert "더 따뜻하게" in STATE["jsonreq"][-1]["messages"][-1]["content"]
L = get("/api/explore")["items"]; assert L[0]["id"] == S["id"] and L[0]["picked"] == 1 and L[0]["n"] == 11, L[0]
assert (hub.EXP_DIR / f'{S["id"]}.json').is_file() and get("/api/explore/zz")["error"]
ok("manual / param / pick / refine rounds, saved list")
# 5) FLUX 계열은 문장형, 설정 칸 이름 맞춤

F = post("/api/explore/candidates", {"mode": "param", "base": {**GEN_BASE, "gengine": "flux", "fx_model": "flux1-krea-dev_fp8_scaled.safetensors"}, "elements": EL, "param": "steps", "values": "10 20"})
assert F["style"] == "natural" and F["cands"][0]["prompt"].startswith("A lone woman with an umbrella. Cyberpunk city street."), F["cands"][0]["prompt"]
assert hub.exp_job_params(hub.exp_load(F["id"]), hub.exp_load(F["id"])["cands"][0])["fx_steps"] == 10
ok("FLUX family: sentence prompts, fx_ fields")
# 6) 실행 모드 도구
STATE["agent_replies"] = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "explore_prompts", "arguments": {"goal": "비 오는 도시", "count": 3, "vary": ["style"]}}}]}]
STATE["json_replies"] = []; J(EL); J({"variants": [{"label": "수채화", "changes": {"style": "watercolor"}}, {"label": "판화", "changes": {"style": "woodcut print"}}]})
P = post("/api/agent/plan", {"model": "testmodel:latest", "messages": [{"role": "user", "content": "비 오는 도시 스타일 3가지 비교해 줘"}], "base": {"gen": GEN_BASE}})["plan"]
assert P["steps"][0]["summary"] == "프롬프트 탐색 · 3가지 · 바꿔 볼 것: 스타일", P
post("/api/agent/run", {"id": P["id"]})
for _ in range(300):
    pv = get("/api/agent/" + P["id"])
    if pv["state"] not in ("wait", "running"): break
    time.sleep(0.2)
st = pv["steps"][0]; assert pv["state"] == "done" and len(st["images"]) == 3 and st["explore"] and st["all_n"] == 3, pv
assert "woodcut print" in json.dumps(get("/api/explore/" + st["explore"]))
STATE["agent_replies"] = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "explore_prompts", "arguments": {"goal": "x", "vary": ["negative"]}}}]}, {"role": "assistant", "content": "?"}]
assert "plan" not in post("/api/agent/plan", {"model": "testmodel:latest", "messages": [{"role": "user", "content": "비교"}], "base": {"gen": GEN_BASE}})
ok("agent explore_prompts tool: plan → candidates drawn → link to the session; bad enum refused")
# 7) 진행 중 작업의 실제 모델 이름(대기열·작업 기록)
h = [json.loads(x) for x in (TMP / "logs/job-history.jsonl").read_text(encoding="utf-8").splitlines()]
assert hub.wf_models(SUBMITTED[-1])[0] == "noobai_xl_v11", hub.wf_models(SUBMITTED[-1])
jid = h[-1]["id"]; assert hub.JOBS[jid]["models"][0] == "noobai_xl_v11" and get("/api/job/" + jid)["models"][0] == "noobai_xl_v11"
ok("job reports the real model files it loaded")
print("ALL OK")
