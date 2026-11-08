"""FLUX.1 계열 ControlNet: 그래프, 안내 메시지, Chroma/Krea2 는 무시."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import json, sys, io, base64
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
ok = lambda m: print("PASS", m)
def last(): return SUBMITTED[-1]
def node(wf, c, i=0): return [n for n in wf.values() if n["class_type"] == c][i]["inputs"]
def classes(wf): return [n["class_type"] for n in wf.values()]
def png_url(im):
    b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
(M / "controlnet").mkdir(exist_ok=True)
(M / "controlnet" / "FLUX.1-dev-ControlNet-Union-Pro-2.0.safetensors").write_bytes(b"x"); (M / "controlnet" / "xinsir_sdxl.safetensors").write_bytes(b"x")
base = {"kind": "gen", "gengine": "flux", "fx_model": "flux1-krea-dev_fp8_scaled.safetensors", "prompt": "a woman", "w": "832", "h": "1216", "seed": "3", "cn_image": png_url(Image.new("RGB", (400, 600), (5, 5, 5)))}
j = job({**base, "cn_model": "FLUX.1-dev-ControlNet-Union-Pro-2.0.safetensors", "cn_strength": "0.7", "cn_end": "0.8", "cn_prep": "canny"}); g = last()
c = node(g, "ControlNetApplyAdvanced"); assert c["strength"] == 0.7 and c["end_percent"] == 0.8 and "SetUnionControlNetType" not in classes(g) and "Canny" in classes(g)
assert node(g, "ControlNetLoader")["control_net_name"].startswith("FLUX.1")
ks = node(g, "KSampler"); pid = [k for k, v in g.items() if v["class_type"] == "ControlNetApplyAdvanced"][0]
assert ks["positive"] == [pid, 0] and ks["negative"] == [pid, 1], (ks["positive"], pid)
assert g[c["positive"][0]]["class_type"] == "FluxGuidance" and g[c["negative"][0]]["class_type"] == "ConditioningZeroOut"
ok("FLUX ControlNet: applied after FluxGuidance/ZeroOut, no union type, canny prep")
j = job({**base, "cn_model": "xinsir_sdxl.safetensors"}, expect_ok=False); assert "FLUX 용이 아닌" in j["error"], j; ok("SDXL ControlNet picked in FLUX mode -> clear message")
j = job({**base, "gengine": "chroma", "fx_model": "Chroma1-HD.safetensors", "cn_model": "FLUX.1-dev-ControlNet-Union-Pro-2.0.safetensors"}); assert "ControlNetApplyAdvanced" not in classes(last()) and any("FLUX.1" in w for w in j.get("warn", [])), j; ok("Chroma ignores ControlNet with a note")
j = job({**base, "cn_model": ""}); assert "ControlNetApplyAdvanced" not in classes(last()); ok("no model -> plain FLUX graph")
print("ALL OK")
