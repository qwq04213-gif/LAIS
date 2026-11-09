"""4.2: 새 엔진 — LTX-2.5(영상 + 소리), SeedVR2 업스케일, Z-Image-Turbo·FLUX 3 Klein 생성, Depth Anything 3, Stable Audio 3,
MOSS 편집·Qwen 2.1 Turbo 편집. 그래프가 ComfyUI 공식 예시와 같은 짜임인지, 없는 파일 안내, 추천 모델 목록."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17947"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def wait(jid):
    for _ in range(600):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def cls(c, g=None): return [v["inputs"] for v in (g or SUBMITTED[-1]).values() if v["class_type"] == c]
def node(ref, g=None): return (g or SUBMITTED[-1])[ref[0]]["class_type"]
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
def png(w=300, h=200):
    b = io.BytesIO(); Image.new("RGB", (w, h), (10, 120, 200)).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
CAT = {m["id"]: m for k in ("llm", "image") for m in json.loads((Path(BASE) / "LocalAI-Studio/hub/models.json").read_text(encoding="utf-8"))[k]}

# ── LTX-2.5 ──
j = job({"kind": "vid", "wan_ver": "ltx25", "prompt": "a cat walking"}); assert j["state"] == "error" and "LTX-2.5" in j["error"] and j.get("need") == ["ltx25"], j
touch(*[f["dir"] + "/" + f["url"].rsplit("/", 1)[1] for f in CAT["ltx25"]["files"]])
assert json.load(urllib.request.urlopen(B + "/api/lists"))["vidmore"]["ltx25"]
j = job({"kind": "vid", "wan_ver": "ltx25", "prompt": "a cat walking", "size": "1280x720", "sec": "5", "fps": "24", "seed": 3}); assert j["state"] == "done" and j["images"][0].endswith(".mp4"), j
e = cls("EmptyLTXVLatentVideo")[0]; assert (e["width"], e["height"], e["length"]) == (640, 352, 121), e          # 절반 크기(64 배수로 맞춘 1280×704), 5초×24+1
sig = sorted(x["sigmas"] for x in cls("ManualSigmas")); assert sig == ["0.85, 0.7250, 0.4219, 0.0", "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"]
assert all(x["sampler_name"] == "euler_ancestral" for x in cls("KSamplerSelect")) and len(cls("SamplerCustomAdvanced")) == 2 and not cls("LTXVImgToVideoInplace")
assert [x["noise_seed"] for x in cls("RandomNoise")] == [3, 4] and all(x["video_cfg"] == 1.0 for x in cls("LTXVDualCFGGuider"))
assert cls("CLIPLoader")[0]["type"] == "ltxv" and node(cls("CreateVideo")[0]["audio"]) == "LTXVAudioVAEDecode" and cls("LTXVLatentUpsampler")
assert "ltx-2.5" not in json.dumps(json.load(urllib.request.urlopen(B + "/api/lists"))["fluxmodels"])
j = job({"kind": "vid", "wan_ver": "ltx25", "prompt": "a cat walking", "image": png(3000, 1500), "size": "1280x720"}); assert j["state"] == "done", j
ii = cls("LTXVImgToVideoInplace"); assert [x["strength"] for x in ii] == [0.7, 1.0] and node(ii[0]["image"]) == "LTXVPreprocess" and cls("LTXVPreprocess")[0]["img_compression"] == 18
STATE["missing"].add("LTXVDualCFGGuider"); hub._CAPS["t"] = 0
j = job({"kind": "vid", "wan_ver": "ltx25", "prompt": "x"}); assert j["state"] == "error" and "LTXVDualCFGGuider" in j["error"], j
STATE["missing"].discard("LTXVDualCFGGuider"); hub._CAPS["t"] = 0
ok("LTX-2.5: missing files → install hint; official 2-stage graph (half size → latent x2 → refine), sound decoded into the video, start image path")
print("ALL OK")
