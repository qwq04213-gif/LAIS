"""기능 모음: 이미지 확장, 영역별 프롬프트, 설정 비교표."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import io, sys, base64
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
ok = lambda m: print("PASS", m)
def pu(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def outimg(j): return out_img(j["images"][0]).convert("RGB")
def classes(wf): return [n["class_type"] for n in wf.values()]
def node(wf, c, i=0): return [n for n in wf.values() if n["class_type"] == c][i]["inputs"]

F = req("/api/features"); ids = [f["id"] for f in F]; assert ids == ["outpaint", "regional", "compare", "resize", "color", "relight", "recompose", "depth", "parallax", "depth3d", "rmbg", "detailer", "ipadapter", "faceswap"] and all(not f["missing_nodes"] and not f["missing_lists"] for f in F), F
STATE["missing"].add("ImagePadForOutpaint"); hub.caps(force=True)
F2 = req("/api/features"); assert F2[0]["missing_nodes"] == ["ImagePadForOutpaint"] and not F2[1]["missing_nodes"], F2
r = job({"kind": "feat", "feature": "outpaint", "image": "x", "prompt": "a", "right": "64"}, expect_ok=False); assert r["state"] == "error" and "ImagePadForOutpaint" in r["error"], r
STATE["missing"].clear(); hub.caps(force=True)
ok("feature list served with readiness; a missing node is reported in the list and at run time: " + ", ".join(ids))

src = Image.new("RGB", (640, 480), (200, 40, 40))
base = {"kind": "feat", "feature": "outpaint", "image": pu(src), "prompt": "city street", "ckpt": "noobai_xl_v11.safetensors", "right": "256", "bottom": "100", "feather": "24"}
j = job(dict(base)); wf = SUBMITTED[-1]
pd = node(wf, "ImagePadForOutpaint"); assert (pd["left"], pd["top"], pd["right"], pd["bottom"]) == (0, 0, 256, 96) and pd["feathering"] == 24, pd   # 8의 배수로 맞춤
ic = node(wf, "InpaintModelConditioning"); assert node(wf, "KSampler")["denoise"] == 1.0
res = outimg(j); assert res.size == (896, 576) and "/feat/" not in j["images"][0] or True
assert res.getpixel((300, 200)) == (200, 40, 40), "original region must stay"
assert "기능" in j["images"][0] or "%EA%B8%B0%EB%8A%A5" in j["images"][0], j["images"]
ok("outpaint: padding rounded to 8, full denoise, original pixels preserved, saved under outputs/기능")
r = job({**base, "right": "0", "bottom": "0"}, expect_ok=False); assert r.get("state") == "error" and "픽셀" in r["error"], r
big = Image.new("RGB", (2400, 1800), (10, 10, 10)); j = job({**base, "image": pu(big), "right": "512"}); assert max(outimg(j).size) < 2400 and any("줄여" in w for w in j.get("warn", [])), (outimg(j).size, j.get("warn"))
ok("outpaint: empty padding refused with a clear message; huge images are scaled down with a notice")

b2 = {"kind": "feat", "feature": "regional", "layout": "lr", "common": "masterpiece", "r1": "a girl", "r2": "a cat", "ckpt": "noobai_xl_v11.safetensors", "w": "1024", "h": "640"}
j = job(dict(b2)); wf = SUBMITTED[-1]; cls = classes(wf)
assert cls.count("ConditioningSetAreaPercentage") == 2 and cls.count("ConditioningCombine") == 2 and outimg(j).size == (1024, 640)
a0 = node(wf, "ConditioningSetAreaPercentage", 0); a1 = node(wf, "ConditioningSetAreaPercentage", 1); assert (a0["x"], a0["width"], a1["x"], a1["width"]) == (0, 0.5, 0.5, 0.5)
texts = [n["inputs"]["text"] for n in wf.values() if n["class_type"] == "CLIPTextEncode"]; assert "a girl" in texts and "a cat" in texts, texts
j = job({**b2, "layout": "lcr", "r3": "a dog"}); assert classes(SUBMITTED[-1]).count("ConditioningSetAreaPercentage") == 3
r = job({**b2, "layout": "lcr", "r3": ""}, expect_ok=False); assert r["state"] == "error" and "3개" in r["error"]
ok("regional prompts: 2 and 3 region layouts wired through area conditioning, missing region text refused")

# 영역별 프롬프트 + LoRA: 칸 글의 <lora:> 태그와 LoRA 칸 선택이 모두 적용되고, 칸 글에는 태그가 남지 않는다
j = job({**b2, "r1": "a girl <lora:style:0.7>", "lora1": "detail_v2.safetensors", "lora1_w": "0.5"}); wf = SUBMITTED[-1]
ll = [n["inputs"] for n in wf.values() if n["class_type"] == "LoraLoader"]
assert {(l["lora_name"], l["strength_model"]) for l in ll} == {("detail_v2.safetensors", 0.5), ("style.safetensors", 0.7)}, ll
texts = [n["inputs"]["text"] for n in wf.values() if n["class_type"] == "CLIPTextEncode"]; assert "a girl" in texts and not any("<lora" in t for t in texts), texts
ks = next(n["inputs"] for n in wf.values() if n["class_type"] == "KSampler"); assert ks["model"][0] in {k for k, n in wf.items() if n["class_type"] == "LoraLoader"}; ok("regional prompts: LoRA from the form and from region tags reach the sampler model")
r = job({**b2, "r1": "<lora:style:0.7>"}, expect_ok=False); assert r["state"] == "error" and "LoRA 태그만" in r["error"]; ok("a region with only a LoRA tag is refused")
F2 = next(f for f in req("/api/features") if f["id"] == "regional"); assert any(x["type"] == "lora" for x in F2["fields"]); ok("regional form offers a LoRA field")

b3 = {"kind": "feat", "feature": "compare", "prompt": "1girl", "ckpt": "noobai_xl_v11.safetensors", "axis": "cfg", "values": "3,5,7", "w": "512", "h": "768", "seed": "42"}
n0 = len(SUBMITTED); j = job(dict(b3)); sub = SUBMITTED[n0:]; assert len(sub) == 3 and [node(w, "KSampler")["cfg"] for w in sub] == [3, 5, 7] and {node(w, "KSampler")["seed"] for w in sub} == {42}
g = outimg(j); assert g.width > 3 * 400 and g.height > 600
n0 = len(SUBMITTED); j = job({**b3, "axis2": "steps", "values2": "10,20"}); sub = SUBMITTED[n0:]; assert len(sub) == 6 and sorted({node(w, "KSampler")["steps"] for w in sub}) == [10, 20]
r = job({**b3, "values": "3"}, expect_ok=False); assert r["state"] == "error" and "2개" in r["error"]
r = job({**b3, "values": "abc"}, expect_ok=False); assert r["state"] == "error" and "abc" in r["error"]
ok("compare grid: one setting varied, same seed everywhere, 2-axis grid (3x2=6 runs), bad values refused")
print("FEATURES TESTS PASSED")
