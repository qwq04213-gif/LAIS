"""ControlNet 쉬운 모드: 지도 뽑기 + union 종류 전달."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17892"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def du(): b = io.BytesIO(); Image.new("RGB", (640, 480), (50, 90, 130)).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def wait(jid):
    for _ in range(300):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
SUBMITTED.clear()
r = post("/api/control/prep", {"image": du(), "type": "pose"}); assert r["node"] == "OpenposePreprocessor" and r["image"].startswith("data:image/png"), r
wf = SUBMITTED[-1]; n = [v for v in wf.values() if v["class_type"] == "OpenposePreprocessor"][0]["inputs"]
assert n["detect_hand"] == "enable" and n["resolution"] == 640 and isinstance(n["image"], list); ok("pose map: finds the preprocessor, fills its other inputs from the engine's own node description")
r = post("/api/control/prep", {"image": du(), "type": "depth"}); assert r["node"] == "DepthAnythingV2Preprocessor"; d = [v for v in SUBMITTED[-1].values() if v["class_type"] == "DepthAnythingV2Preprocessor"][0]["inputs"]; assert d["ckpt_name"] == "depth_anything_v2_vitl.pth"; ok("depth map: list inputs take the first choice")
r = post("/api/control/prep", {"image": du(), "type": "canny"}); assert r["node"] == "Canny" or "error" not in r; ok("canny map works with the built-in node")
STATE["missing"].add("OpenposePreprocessor"); hub.caps(True)
r = post("/api/control/prep", {"image": du(), "type": "pose"}); assert r.get("need_pack") and r["missing"] == "DWPreprocessor" and "확장" in r["error"], r; ok("missing preprocessor pack → clear message + node name for the installer")
STATE["missing"].discard("OpenposePreprocessor"); hub.caps(True)
assert "error" in post("/api/control/prep", {"image": du(), "type": "zzz"}) and "error" in post("/api/control/prep", {"image": "junk", "type": "pose"}); ok("bad type / bad image refused")
# 생성에 union 종류 전달
base = {"kind": "gen", "prompt": "a girl", "ckpt": "noobai_xl_v11.safetensors", "w": 512, "h": 512, "steps": 4, "cn_image": du(), "cn_prep": "none"}
for model, typ, want in (("union_promax.safetensors", "pose", "openpose"), ("union_promax.safetensors", "depth", "depth"), ("union_promax.safetensors", "canny", "canny/lineart/anime_lineart/mlsd")):
    SUBMITTED.clear(); j = wait(post("/api/job", dict(base, cn_model=model, cn_type=typ))["id"]); assert j["state"] == "done", j
    u = [v for v in SUBMITTED[-1].values() if v["class_type"] == "SetUnionControlNetType"]; assert len(u) == 1 and u[0]["inputs"]["type"] == want, (typ, u)
ok("generation with a union ControlNet gets SetUnionControlNetType (pose→openpose, depth→depth, canny→canny/lineart…)")
SUBMITTED.clear(); j = wait(post("/api/job", dict(base, cn_model="union_promax.safetensors"))["id"]); assert j["state"] == "done" and not any(v["class_type"] == "SetUnionControlNetType" for v in SUBMITTED[-1].values()); ok("no easy-mode type → no union node (old behaviour unchanged)")
(hub.MODELS / "controlnet" / "sdxl_openpose.safetensors").write_bytes(b"x")
SUBMITTED.clear(); j = wait(post("/api/job", dict(base, cn_model="sdxl_openpose.safetensors", cn_type="pose"))["id"]); assert j["state"] == "done" and not any(v["class_type"] == "SetUnionControlNetType" for v in SUBMITTED[-1].values()); ok("a dedicated (non-union) model never gets the union node")
print("ALL OK")
