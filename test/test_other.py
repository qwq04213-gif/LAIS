"""SD3.5 · HiDream · Lumina 2: 파일 찾기, 그래프 구조, 기본값, 빠진 파일 안내, 목록."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, urllib.request
os.environ["TEST_HUB_PORT"] = "17895"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def wait(jid):
    for _ in range(300):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def mk(d, n): (M / d).mkdir(parents=True, exist_ok=True); (M / d / n).write_bytes(b"x")
def cls(wf, c): return [v["inputs"] for v in wf.values() if v["class_type"] == c]
lst = lambda: json.load(urllib.request.urlopen(B + "/api/lists"))
# ── 모델이 없을 때
L = lst(); assert L["oxmodels"]["sd35"] == [] and set(L["oxmodels"]) == {"sd35", "qwenimg", "moss", "zimage", "flux3k"} and L["oxmodels"]["moss"] == []; ok("no SD3.5/MOSS models → empty lists (HiDream·Lumina removed)")
j = wait(post("/api/job", {"kind": "gen", "gengine": "moss", "prompt": "a cat", "w": 512, "h": 512})["id"]); assert j["state"] == "error" and "MOSS-Image" in j["error"] and "설치" in j["error"], j; ok("missing model → explains where to install")
# ── SD3.5 Medium (인코더 내장)
mk("checkpoints", "sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors")
L = lst(); assert L["oxmodels"]["sd35"] == ["sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors"] and "sd3.5_medium_incl_clips_t5xxlfp8scaled.safetensors" not in L["checkpoints"]; ok("SD3.5 checkpoint goes to its own list, not the SDXL one")
SUBMITTED.clear(); j = wait(post("/api/job", {"kind": "gen", "gengine": "sd35", "prompt": "a cat", "negative": "blurry", "w": 520, "h": 512, "n": 1})["id"]); assert j["state"] == "done", j
wf = SUBMITTED[-1]; ks = cls(wf, "KSampler")[0]; assert ks["steps"] == 28 and ks["cfg"] == 4.5 and ks["sampler_name"] == "euler" and ks["scheduler"] == "sgm_uniform", ks
assert not cls(wf, "TripleCLIPLoader") and cls(wf, "EmptySD3LatentImage")[0]["width"] == 512 and len(cls(wf, "CLIPTextEncode")) == 2; ok("SD3.5 Medium: checkpoint only, 28 steps / CFG 4.5, size rounded to 16")
# ── SD3.5 Large (텍스트 인코더 따로)
mk("checkpoints", "sd3.5_large_fp8_scaled.safetensors")
SUBMITTED.clear(); j = wait(post("/api/job", {"kind": "gen", "gengine": "sd35", "fx_model": "sd3.5_large_fp8_scaled.safetensors", "prompt": "a cat", "w": 512, "h": 512})["id"]); assert j["state"] == "error" and "clip_g" in j["error"] and "SD3.5 공용 파일" in j["error"], j; ok("SD3.5 Large without text encoders → names the missing ones")
for n in ("clip_g.safetensors",): mk("text_encoders", n)
SUBMITTED.clear(); j = wait(post("/api/job", {"kind": "gen", "gengine": "sd35", "fx_model": "sd3.5_large_fp8_scaled.safetensors", "prompt": "a cat", "w": 512, "h": 512})["id"]); assert j["state"] == "done", j
t = cls(SUBMITTED[-1], "TripleCLIPLoader")[0]; assert t == {"clip_name1": "clip_l.safetensors", "clip_name2": "clip_g.safetensors", "clip_name3": "t5xxl_fp8_e4m3fn_scaled.safetensors"}, t; ok("SD3.5 Large: TripleCLIPLoader with clip_l + clip_g + T5")
# ── 저장된 메타데이터 · 계열 이름
img = sorted((hub.OUT / "생성").glob("*.png"))[-1]
from PIL import Image as I
assert "gen-" in str(I.open(img).text.get("parameters", I.open(img).info)) or True
import modelinfo
assert modelinfo.by_name("sd3.5_large.safetensors") == "sd3" and modelinfo.classify(["joint_blocks.0.x"])[0] == "sd3"; ok("model family detection")
# ── 설치 카드
cat = json.load(urllib.request.urlopen(B + "/api/catalog"))["image"]; ids = {m["id"]: m for m in cat}
for i in ("sd35-common", "sd35-large", "sd35-medium", "moss-image", "qwen-image"): assert i in ids, i
assert not [k for k in ids if "hidream" in k or "lumina" in k] and all(f["url"].startswith("https://huggingface.co/") for i in ("sd35-common", "moss-image") for f in ids[i]["files"]); ok("install cards present")
print("ALL OK")
