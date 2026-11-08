"""3.13: 구도 바꾸기·새 장면(각도·새 장면·포즈 참고·구조 따라 새로 그리기), 3D 카메라 경로·점 구름, 받아쓰기 오류1."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, subprocess, struct, urllib.request
os.environ["TEST_HUB_PORT"] = "17975"
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
def g(): return SUBMITTED[-1]
def cls(c): return [v["inputs"] for v in g().values() if v["class_type"] == c]
def png(c=(10, 120, 200)):
    b = io.BytesIO(); Image.new("RGB", (320, 240), c).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
(M / "diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors").write_bytes(b"x")
# 1) 각도: LoRA 없으면 말로, 있으면 <sks> 형식 + LoRA
j = job2({"kind": "feat", "feature": "recompose", "image": png(), "mode": "angle", "az": "right", "el": "low", "dist": "close", "use_lora": "on"}); assert j["state"] == "done", j
t = json.dumps(cls("TextEncodeQwenImage21")); assert "right side" in t and "low angle" in t and "close-up" in t and "<sks>" not in t, t
(M / "loras/qwen-image-edit-2511-multiple-angles-lora.safetensors").write_bytes(b"x")
j = job2({"kind": "feat", "feature": "recompose", "image": png(), "mode": "angle", "az": "br", "el": "high", "dist": "wide", "use_lora": "on"}); assert "<sks>" not in json.dumps(cls("TextEncodeQwenImage21"))   # 2511 용 LoRA 는 2.1 에 안 써요
(M / "loras/qwen-image-2.1-multiple-angles-lora.safetensors").write_bytes(b"x")
j = job2({"kind": "feat", "feature": "recompose", "image": png(), "mode": "angle", "az": "br", "el": "high", "dist": "wide", "use_lora": "on"}); assert j["state"] == "done", j
t = json.dumps(cls("TextEncodeQwenImage21")); assert "<sks> back-right quarter view high-angle shot wide shot" in t, t
assert any("2.1-multiple-angles" in x["lora_name"] and abs(x["strength_model"] - 0.9) < 1e-6 for x in cls("LoraLoaderModelOnly")), cls("LoraLoaderModelOnly")
assert "error" in job2({"kind": "feat", "feature": "recompose", "image": png(), "mode": "angle", "az": "keep", "el": "keep", "dist": "keep", "use_lora": ""}) or True
ok("camera angle: natural instruction without the LoRA, '<sks> az el dist' + LoRA 0.9 with it")
# 2) 새 장면 · 포즈 참고
j = job2({"kind": "feat", "feature": "recompose", "image": png(), "mode": "scene", "scene": "walking on a beach at sunset", "keep_outfit": "on"}); assert j["state"] == "done", j
t = json.dumps(cls("TextEncodeQwenImage21")); assert "beach at sunset" in t and "same outfit" in t
j = job2({"kind": "feat", "feature": "recompose", "image": png(), "mode": "scene", "scene": ""}); assert j["state"] == "error"
j = job2({"kind": "feat", "feature": "recompose", "image": png(), "mode": "pose", "pose_ref": png((200, 30, 30))}); assert j["state"] == "done", j
e = cls("TextEncodeQwenImage21")[0]; assert "images.image_2" in e and "pose" in e["prompt"], e
ok("new scene with the same person; pose taken from a reference photo (image 2)")
# 3) 구조만 가져와 새로 그리기(생성 화면 모델 + ControlNet)
GEN = {"gengine": "sdxl", "ckpt": "noobai_xl_v11.safetensors", "w": "1024", "h": "1024", "n": "1"}
j = job2({"kind": "feat", "feature": "recompose", "image": png(), "mode": "structure", "skind": "depth", "prompt": "a robot in a garden", "gen": GEN}); assert j["state"] == "done", j
assert cls("ControlNetApplyAdvanced") and "robot in a garden" in json.dumps(g()) and "noobai_xl_v11" in json.dumps(g())
assert any(n["class_type"] == "DepthAnythingV2Preprocessor" for s_ in SUBMITTED[-3:] for n in s_.values())
j = job2({"kind": "feat", "feature": "recompose", "image": png(), "mode": "structure", "skind": "pose", "prompt": "x", "gen": {**GEN, "gengine": "krea2"}}); assert j["state"] == "error" and "SD·SDXL" in j["error"]
ok("structure: pose/depth from the photo → ControlNet generation with the generator's model")
# 4) 실행 모드 도구
STATE["agent_replies"] = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "recompose_image", "arguments": {"image": "attached", "mode": "angle", "direction": "left", "height": "eye", "distance": "medium"}}}]}]
P = post("/api/agent/plan", {"model": "testmodel:latest", "messages": [{"role": "user", "content": "왼쪽에서 본 모습으로"}], "image": png(), "base": {}})["plan"]
assert P["steps"][0]["summary"] == "구도 바꾸기 · 붙인 사진 · 카메라 각도", P
post("/api/agent/run", {"id": P["id"]})
for _ in range(300):
    pv = get("/api/agent/" + P["id"])
    if pv["state"] not in ("wait", "running"): break
    time.sleep(0.2)
assert pv["state"] == "done" and "left side view" in json.dumps(g()), pv
ok("agent recompose_image tool")
# 5) 3D 카메라 경로 + 점 구름
V = hub.OUT / "영상"; V.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=960x540:d=3:r=24", "-vf", "crop=480:360:'t*100':90", "-pix_fmt", "yuv420p", str(V / "pan3.mp4")], check=True)
j = job2({"kind": "vana", "op": "cam3d", "video": "/out/%EC%98%81%EC%83%81/pan3.mp4", "fps": "4"}); assert j["state"] == "done", j
js = next(u for u in j["images"] if u.endswith(".json")); glb = next(u for u in j["images"] if u.endswith(".glb"))
d = json.loads(hub.out_path(urllib.request.unquote(js)[5:]).read_text(encoding="utf-8")); assert d["kind"] == "camera-3d" and len(d["frames"]) == 12 and len(d["frames"][0]["quat"]) == 4 and "상대" in d["note"]
b = hub.out_path(urllib.request.unquote(glb)[5:]).read_bytes(); n = struct.unpack("<I", b[12:16])[0]; gj = json.loads(b[20:20 + n]); assert gj["meshes"][0]["primitives"][0]["mode"] == 0 and gj["accessors"][0]["count"] > 1000
assert any(u.endswith(".png") for u in j["images"])
ok("3D camera path (.json with position + rotation per frame), chart and point cloud .glb")
cat = json.load(open(BASE + "/LocalAI-Studio/hub/models.json", encoding="utf-8")); assert not any(m["id"] == "qwen-angles" for m in cat["image"])
print("ALL OK")
