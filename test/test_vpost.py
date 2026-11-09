"""영상 다듬기(프레임 늘리기·업스케일·WebP): 그래프, 누락 노드 안내, 결과 저장."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time
os.environ["TEST_HUB_PORT"] = "17898"
sys.path.insert(0, BASE + "/test")
from mocks import *
import urllib.request
ok = lambda m: print("PASS", m)
def post(path, o):
    r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def job(p, t=60):
    i = post("/api/job", p)["id"]
    for _ in range(t * 4):
        j = get("/api/job/" + i)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.25)
    raise AssertionError("timeout")
def nodes(g, c): return [n["inputs"] for n in g.values() if n["class_type"] == c]
(hub.OUT / "영상").mkdir(parents=True, exist_ok=True)
v = hub.OUT / "영상" / "20261019-010101-abcd-vid-0.mp4"; v.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 100)
(hub.OUT / "영상" / (v.name + ".json")).write_text(json.dumps({"kind": "vid", "prompt": "cat", "w": 832, "h": 480, "frames": 49, "fps": 16}), encoding="utf-8")
url = "/out/" + urllib.parse.quote("영상") + "/" + v.name
j = job({"kind": "vpost", "op": "bogus", "video": url}); assert j["state"] == "error" and "알 수 없는" in j["error"]
j = job({"kind": "vpost", "op": "webp", "video": "/out/영상/nope.mp4"}); assert j["state"] == "error" and "찾을 수 없" in j["error"]; ok("bad op / missing video -> clear errors")
j = job({"kind": "vpost", "op": "interp", "video": url}); assert j["state"] == "done", j; g = SUBMITTED[-1]
r = nodes(g, "RIFE VFI")[0]; assert r["multiplier"] == 2 and r["ckpt_name"] == "rife47.pth"; assert nodes(g, "CreateVideo")[0]["fps"] == 32, nodes(g, "CreateVideo")
assert j["images"][0].endswith(".mp4") and "/영상/" in urllib.parse.unquote(j["images"][0]); sv = hub.out_path(j["images"][0][5:])
meta = json.loads(open(str(sv) + ".json", encoding="utf-8").read()); assert meta["fps"] == 32 and meta["post"] == "프레임 늘리기" and meta["prompt"] == "cat" and meta["source"] == v.name, meta
assert not list((hub.COMFY / "input").glob("hub_*.mp4")), "temp video copied into ComfyUI input must be removed"
ok("interpolation: LoadVideo → GetVideoComponents → RIFE x2 → CreateVideo at double fps; settings json carries over; temp copy cleaned")
(hub.MODELS / "upscale_models").mkdir(parents=True, exist_ok=True); (hub.MODELS / "upscale_models" / "RealESRGAN_x2.pth").write_bytes(b"x")
j = job({"kind": "vpost", "op": "upscale", "video": url}); assert j["state"] == "done", j; g = SUBMITTED[-1]
assert nodes(g, "UpscaleModelLoader")[0]["model_name"] == "RealESRGAN_x2.pth" and nodes(g, "ImageUpscaleWithModel") and nodes(g, "CreateVideo")[0]["fps"][1] == 2
ok("upscale: model loader + ImageUpscaleWithModel on the frames, fps link kept")
for f in ("diffusion_models/seedvr2_7b_int8_convrot.safetensors", "vae/seedvr2_ema_vae_fp16.safetensors"):
    (hub.MODELS / f).parent.mkdir(parents=True, exist_ok=True); (hub.MODELS / f).write_bytes(b"x")
j = job({"kind": "vpost", "op": "upscale", "video": url, "upm": "SeedVR2 7B (AI 복원)"}); assert j["state"] == "done", j; g = SUBMITTED[-1]
assert not nodes(g, "UpscaleModelLoader") and nodes(g, "ImageScaleBy")[0]["scale_by"] == 2.0 and nodes(g, "UNETLoader")[0]["unet_name"].startswith("seedvr2_7b") and any("SeedVR2" in w for w in j["warn"])
ok("upscale with SeedVR2 7B: frames doubled then restored")
j = job({"kind": "vpost", "op": "webp", "video": url}); assert j["state"] == "done", j; g = SUBMITTED[-1]
assert nodes(g, "SaveAnimatedWEBP")[0]["fps"][1] == 2 and not nodes(g, "SaveVideo") and j["images"][0].endswith(".webp"); ok("webp: SaveAnimatedWEBP, saved as .webp in the video folder")
STATE["missing"].add("RIFE VFI"); hub.caps(force=True)
j = job({"kind": "vpost", "op": "interp", "video": url}); assert j["state"] == "error" and "RIFE VFI" in j["error"] and "ComfyUI-Frame-Interpolation" in j["error"] and "다시 시작" in j["error"], j
STATE["missing"].clear(); STATE["missing"].add("SaveAnimatedWEBP"); hub.caps(force=True)
j = job({"kind": "vpost", "op": "webp", "video": url}); assert j["state"] == "error" and "업데이트" in j["error"], j
ok("missing nodes: interpolation names the extension to install; core nodes say update ComfyUI")
print("ALL OK")
