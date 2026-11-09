"""영상 생성(Wan 2.2 5B): 그래프, 작업, 파일 저장, Range 재생, 목록/설치 항목, 오류 안내."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, base64, io, time
os.environ["TEST_HUB_PORT"] = "17873"
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
# 모델 없음 → 안내
j = job({"kind": "vid", "prompt": "a cat walking"}); assert j["state"] == "error" and "Wan 2.2" in j["error"] and "설치" in j["error"], j; ok("missing Wan files -> clear install hint")
for d, f in (("diffusion_models", "wan2.2_ti2v_5B_fp16.safetensors"), ("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"), ("vae", "wan2.2_vae.safetensors")):
    (M / d / f).write_bytes(b"x")
l = get("/api/lists"); assert l["wan_ready"] and l["wanmodels"] == ["wan2.2_ti2v_5B_fp16.safetensors"], l
cat = get("/api/catalog")["image"]; w = [m for m in cat if m["id"] == "wan22-ti2v-5b"][0]; assert w["requires"] == ["wan-common"] and w["installed"]; ok("lists: wan_ready + catalog entry")
# 글→영상
n0 = len(SUBMITTED)
j = job({"kind": "vid", "prompt": "{red|blue} cat walking, cinematic", "dyn": "on", "sec": 3, "fps": 24, "seed": 7, "size": "832x480"})
assert j["state"] == "done", j; g = SUBMITTED[n0]
by = {n["class_type"]: n["inputs"] for n in g.values()}
L = by["Wan22ImageToVideoLatent"]; assert (L["width"], L["height"], L["length"]) == (832, 480, 73) and "start_image" not in L, L
assert by["CLIPLoader"]["type"] == "wan" and by["ModelSamplingSD3"]["shift"] == 8.0 and by["CreateVideo"]["fps"] == 24 and by["SaveVideo"]["format"] == "auto"
assert by["KSampler"]["sampler_name"] == "uni_pc" and by["KSampler"]["cfg"] == 5.0 and by["KSampler"]["seed"] == 7
assert "色调艳丽" in [n["inputs"]["text"] for n in g.values() if n["class_type"] == "CLIPTextEncode"][1]
url = j["images"][0]; assert url.endswith(".mp4") and "/%EC%98%81%EC%83%81/" in url, url
f = OUT_FILE = hub.out_path(url[5:]); assert f.is_file() and f.read_bytes()[4:8] == b"ftyp"
side = json.loads((Path(str(hub.out_path(url[5:])) + ".json")).read_text(encoding="utf-8")); assert side["frames"] == 73 and side["seed"] == 7 and side["prompt"].split()[0] in ("red", "blue")
ok("text-to-video: Wan graph (latent 832x480x73, wan clip, SD3 shift, CreateVideo->SaveVideo), mp4 + settings sidecar saved to outputs/영상")
# 서버: 재생(Range)
r = urllib.request.urlopen(B + url); assert r.headers["Content-Type"] == "video/mp4" and r.headers["Accept-Ranges"] == "bytes"; full = r.read()
rq = urllib.request.Request(B + url, headers={"Range": "bytes=4-11"}); r2 = urllib.request.urlopen(rq); assert r2.status == 206 and r2.read() == full[4:12] and r2.headers["Content-Range"] == f"bytes 4-11/{len(full)}"
rq = urllib.request.Request(B + url, headers={"Range": "bytes=-5"}); assert urllib.request.urlopen(rq).read() == full[-5:]
try: urllib.request.urlopen(urllib.request.Request(B + url, headers={"Range": "bytes=99999-"})); raise AssertionError
except urllib.error.HTTPError as e: assert e.code == 416
ok("video served with Range support (206/416)")
# 이미지→영상
im = Image.new("RGB", (600, 900), (10, 120, 200)); b = io.BytesIO(); im.save(b, "PNG")
n0 = len(SUBMITTED); j = job({"kind": "vid", "prompt": "she smiles", "image": "data:image/png;base64," + base64.b64encode(b.getvalue()).decode(), "keep_ratio": "on", "size": "832x480", "sec": 2})
assert j["state"] == "done", j; g = SUBMITTED[n0]; L = [n["inputs"] for n in g.values() if n["class_type"] == "Wan22ImageToVideoLatent"][0]
assert "start_image" in L and L["width"] < L["height"] and L["width"] % 32 == 0 and L["height"] % 32 == 0 and L["length"] == 49, L; ok("image-to-video: start image, follows portrait ratio (multiples of 32), 2s=49 frames")
# 오류
j = job({"kind": "vid", "prompt": ""}); assert j["state"] == "error" and "프롬프트" in j["error"]; ok("empty prompt rejected")
STATE["missing"].add("SaveVideo"); hub._CAPS["t"] = 0
j = job({"kind": "vid", "prompt": "x"}); assert j["state"] == "error" and "SaveVideo" in j["error"] and "update" in j["error"]; STATE["missing"].discard("SaveVideo"); hub._CAPS["t"] = 0; ok("old ComfyUI without video nodes -> update hint")
j = job({"kind": "vid", "prompt": "nsfw loli"}); assert j["state"] == "error"; ok("content block applies to video prompts")
print("ALL OK")
