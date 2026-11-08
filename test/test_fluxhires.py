"""FLUX·Krea 2·Chroma 하이레스 픽스: 그림으로 풀어 16의 배수로 키운 뒤 같은 모델로 다시 그리기, 업스케일 모델 선택, 기록."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def last(): return SUBMITTED[-1]
def nodes(wf, c): return [n["inputs"] for n in wf.values() if n["class_type"] == c]
base = {"kind": "gen", "gengine": "flux", "fx_model": "flux1-krea-dev_fp8_scaled.safetensors", "prompt": "a woman", "w": "832", "h": "1216", "seed": "3"}
j = job(base); assert len(nodes(last(), "KSampler")) == 1 and not nodes(last(), "ImageScale"); ok("off: one pass")
j = job({**base, "hires": "on", "hires_scale": "1.5", "hires_denoise": "0.35", "hires_steps": "10"}); g = last(); validate(g)
ks = nodes(g, "KSampler"); sc = nodes(g, "ImageScale")[0]
assert len(ks) == 2 and ks[1]["denoise"] == 0.35 and ks[1]["steps"] == 10 and ks[0]["denoise"] == 1.0 and ks[1]["model"] == ks[0]["model"]
assert sc["width"] == 1248 and sc["height"] == 1824 and sc["width"] % 16 == 0 and not nodes(g, "ImageUpscaleWithModel")
assert g[ks[1]["latent_image"][0]]["class_type"] == "VAEEncode"; ok("FLUX: decode → scale to multiples of 16 → encode → second KSampler with hires denoise/steps")
assert j.get("state") == "done", j
up = [n for n in hub.files("upscale_models")]
if up:
    job({**base, "hires": "on", "hires_upm": up[0]}); g = last(); assert nodes(g, "ImageUpscaleWithModel") and nodes(g, "UpscaleModelLoader")[0]["model_name"] == up[0]; ok("upscale model used when chosen")
k2 = [m for m in hub.files("diffusion_models") if "krea2" in m.lower()]
if k2:
    j = job({**base, "gengine": "krea2", "fx_model": k2[0], "hires": "on"}); g = last(); assert len(nodes(g, "KSampler")) == 2 and nodes(g, "ImageScale"), j; ok("Krea 2 also gets the second pass")
print("ALL OK")
