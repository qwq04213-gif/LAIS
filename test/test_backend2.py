"""1차 업데이트: FLUX/Krea/Chroma, 중단, 폴더 열기, LoRA 무제한, 의존 설치, 버전."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import json, sys, time
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
ok = lambda m: print("PASS", m)
def last(): return SUBMITTED[-1]
def classes(wf): return [n["class_type"] for n in wf.values()]
def node(wf, c, i=0): return [n for n in wf.values() if n["class_type"] == c][i]["inputs"]
def nid(wf, c): return [k for k, v in wf.items() if v["class_type"] == c][0]

# ── lists / status ──
L = req("/api/lists")
assert L["flux_ready"] and L["chroma_ready"] and "flux1-krea-dev_fp8_scaled.safetensors" in L["fluxmodels"] and "Chroma1-HD.safetensors" in L["chromamodels"] and "Chroma1-HD.safetensors" not in L["fluxmodels"]
assert not any("qwen" in m.lower() for m in L["fluxmodels"]) and "ae.safetensors" in L["vaes"]; ok("lists: FLUX models/ready flags; Qwen model hidden from FLUX picker, every VAE listed")
assert req("/api/status")["version"]; ok("status carries version")

# ── FLUX / Krea ──
j = job({"kind": "gen", "gengine": "flux", "fx_model": "flux1-krea-dev_fp8_scaled.safetensors", "prompt": "a woman on a beach, {sunset|dawn} light", "dyn": "on", "w": "832", "h": "1216", "seed": "9",
         "fx_guidance": "4.2", "fx_steps": "24", "lora1": "style.safetensors", "lora1_w": "0.7", "lora2": "detail_v2.safetensors", "embed": "on", "n": "2"})
w = SUBMITTED[-2]; cl = classes(w)
assert out_img(j["images"][0]).size == (832, 1216) and len(j["images"]) == 2
assert node(w, "DualCLIPLoader")["type"] == "flux" and node(w, "DualCLIPLoader")["clip_name1"] == "clip_l.safetensors" and "t5xxl" in node(w, "DualCLIPLoader")["clip_name2"]
assert node(w, "FluxGuidance")["guidance"] == 4.2 and "ConditioningZeroOut" in cl and "EmptySD3LatentImage" in cl and "EmptyLatentImage" not in cl
k = node(w, "KSampler"); assert k["cfg"] == 1.0 and k["steps"] == 24 and k["sampler_name"] == "euler" and k["scheduler"] == "simple" and k["denoise"] == 1.0
assert k["positive"][0] == nid(w, "FluxGuidance") and k["negative"][0] == nid(w, "ConditioningZeroOut")
assert cl.count("LoraLoaderModelOnly") == 2 and "LoraLoader" not in cl and node(w, "VAELoader")["vae_name"] == "ae.safetensors"
assert "{" not in node(w, "CLIPTextEncode")["text"] and node(w, "CLIPTextEncode")["text"].startswith("a woman on a beach")
m = meta.read(req(j["images"][0], raw=True)); assert m["kind"] == "hub" and m["comfy"] is not None and "Distilled CFG: 4.2" in m["text"]["parameters"] and m["gen"]["params"]["model"] == "flux1-krea-dev_fp8_scaled.safetensors"
ok("FLUX/Krea: DualCLIP(flux)+FluxGuidance+ZeroOut negative, cfg 1, SD3 latent, 2 LoRAs (model-only), dynamic prompt, 2 images, PNG metadata")
j = job({"kind": "gen", "gengine": "flux", "fx_model": "flux1-krea-dev_fp8_scaled.safetensors", "prompt": "portrait", "init": png_url(Image.new("RGB", (900, 600), (9, 9, 9))), "init_denoise": "0.55", "w": "1024", "h": "1024"})
w = last(); assert "VAEEncode" in classes(w) and "EmptySD3LatentImage" not in classes(w) and node(w, "KSampler")["denoise"] == 0.55; ok("FLUX image-to-image")

# ── Chroma ──
j = job({"kind": "gen", "gengine": "chroma", "fx_model": "Chroma1-HD.safetensors", "prompt": "a woman", "fx_cfg": "3.5", "fx_steps": "26", "seed": "3"})
w = last(); assert node(w, "CLIPLoader")["type"] == "chroma" and "DualCLIPLoader" not in classes(w) and "FluxGuidance" not in classes(w) and "ConditioningZeroOut" not in classes(w)
k = node(w, "KSampler"); assert k["cfg"] == 3.5 and k["scheduler"] == "beta" and k["steps"] == 26
negs = [n["inputs"]["text"] for n in w.values() if n["class_type"] == "CLIPTextEncode"]; assert negs[0] == "a woman" and "low quality" in negs[1]
assert k["negative"][0] != k["positive"][0]; ok("Chroma: T5-only CLIPLoader(type=chroma), real negative prompt (default text), CFG 3.5, beta scheduler, no FluxGuidance")
j = job({"kind": "gen", "gengine": "chroma", "fx_model": "Chroma1-HD.safetensors", "prompt": "a woman", "negative": "my negative", "fx_scheduler": "bogus_sched"})
assert any("bogus_sched" in x for x in j["warn"]) and node(last(), "KSampler")["scheduler"] == "simple" and [n["inputs"]["text"] for n in last().values() if n["class_type"] == "CLIPTextEncode"][1] == "my negative"; ok("scheduler unknown to ComfyUI -> warn + simple; user negative kept")
j = job({"kind": "gen", "gengine": "chroma", "fx_model": "Chroma1-HD.safetensors", "prompt": "nude schoolgirl"}, expect_ok=False); assert "미성년" in j["error"]; ok("FLUX family: minor+sexual blocked")
(M / "text_encoders/clip_l.safetensors").rename(M / "text_encoders/_clip_l.bak")
j = job({"kind": "gen", "gengine": "flux", "fx_model": "flux1-krea-dev_fp8_scaled.safetensors", "prompt": "x"}, expect_ok=False); assert "설치" in j["error"] and not req("/api/lists")["flux_ready"] and req("/api/lists")["chroma_ready"]
j = job({"kind": "gen", "gengine": "chroma", "fx_model": "Chroma1-HD.safetensors", "prompt": "x"}); (M / "text_encoders/_clip_l.bak").rename(M / "text_encoders/clip_l.safetensors")
ok("missing CLIP-L: FLUX gives a clear install message, Chroma (T5 only) still works")

# ── unlimited LoRAs ──
body = {"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "1girl"}
names = [f"lora_{c}.safetensors" for c in "abcdefghij"]
for i, n in enumerate(names, 1): body[f"lora{i}"] = n; body[f"lora{i}_w"] = str(round(0.1 * i, 1))
body["lora11"] = names[0]  # duplicate is ignored
j = job(body); w = last(); ll = [n["inputs"] for n in w.values() if n["class_type"] == "LoraLoader"]
assert [x["lora_name"] for x in ll] == names and [x["strength_model"] for x in ll] == [round(0.1 * i, 1) for i in range(1, 11)], [x["lora_name"] for x in ll]; ok("SDXL: 10 LoRA slots (+1 duplicate dropped), applied in numeric order with their own strengths")
ord_ = hub.lora_slots({"lora10": "j", "lora2": "b", "lora1": "a", "lora3": "", "lora10_w": "0.5", "loraX": "z"}); assert ord_ == [("a", 0.8), ("b", 0.8), ("j", 0.5)], ord_; ok("lora_slots: numeric (not lexical) ordering, empty/odd keys ignored")
j = job({"kind": "gen", "gengine": "flux", "fx_model": "Chroma1-HD.safetensors", "gengine ": "x", **{k: v for k, v in body.items() if k.startswith("lora")}, "prompt": "x"}); assert classes(last()).count("LoraLoaderModelOnly") == 10; ok("FLUX family: same 10 LoRAs")

# ── cancel ──
def start(p): return req("/api/job", p)["id"]
def state(i): return req("/api/job/" + i)
def wait_state(i, want, t=15):
    for _ in range(int(t / 0.2)):
        s = state(i)
        if s["state"] in want: return s
        time.sleep(0.2)
    raise AssertionError(state(i))
STATE["slow_from"] = len(SUBMITTED); n_int = STATE["interrupts"]
i = start({"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "x"}); wait_state(i, ("running",)); time.sleep(1.2)
assert req("/api/job/cancel", {"id": i})["ok"]; s = wait_state(i, ("cancelled", "error", "done"))
assert s["state"] == "cancelled" and "중단" in s["error"] and STATE["interrupts"] == n_int + 1 and not s["images"]; ok("cancel a running job: ComfyUI /interrupt sent, state 'cancelled', no images")
# cancel in the middle of a 3-image batch -> keep the finished ones
STATE["slow_from"] = len(SUBMITTED) + 1; n_int = STATE["interrupts"]
i = start({"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "x", "n": "3", "embed": "on"}); time.sleep(3.0)
req("/api/job/cancel", {"id": i}); s = wait_state(i, ("cancelled", "error", "done"))
assert s["state"] == "done" and len(s["images"]) == 1 and any("1장" in x for x in s["warn"]), s; ok("cancel during a 3-image batch: finished image kept, warned '1장'")
# cancel flag stops multi-step jobs between steps (tile refine) without extra submissions
STATE["slow_from"] = None; before = len(SUBMITTED)
i = start({"kind": "up", "image": png_url(Image.new("RGB", (1500, 1000))), "scale": "2", "mode": "refine", "ckpt": "lustify_photo.safetensors"})
time.sleep(0.8); req("/api/job/cancel", {"id": i}); s = wait_state(i, ("cancelled", "done", "error"))
assert s["state"] == "cancelled" and len(SUBMITTED) - before < 8, (s, len(SUBMITTED) - before); ok("cancel a tile-refine job: stops before finishing all tiles")
assert "error" in req("/api/job/cancel", {"id": "nope"}); ok("cancel unknown job -> error, no crash")

# ── folder open ──
opened = []; hub.open_folder = lambda p, select=None: opened.append(p)
for which, expect in [("loras", M / "loras"), ("checkpoints", M / "checkpoints"), ("controlnet", M / "controlnet"), ("outputs", hub.OUT), ("llm", TMP / "models/llm"), ("wildcards", TMP / "wildcards")]:
    r = req("/api/open", {"which": which}); assert r["ok"] and Path(r["path"]) == expect and opened[-1] == expect, (which, r)
assert req("/api/open", {"which": "../../etc"})[0] == 400 and req("/api/open", {"which": "nonsense"})[0] == 400 and req("/api/open", {})["path"] == str(hub.OUT); ok("open-folder: model/outputs/llm/wildcards folders; unknown or traversal rejected; default=outputs")

# ── install with dependencies ──
assert hub.expand_ids(["krea-dev"]) == ["krea-dev", "flux-common"] and hub.expand_ids(["chroma-hd", "krea-dev"]) == ["chroma-hd", "krea-dev", "flux-common"] and hub.expand_ids(["nope"]) == []; ok("expand_ids: dependencies pulled in once, order stable, unknown ignored")
C = {m["id"]: m for m in req("/api/catalog")["image"]}; assert C["flux-common"]["installed"] and C["krea-dev"]["installed"] and C["chroma-hd"]["installed"]
fake = type("U", (), {"free": 500e9, "total": 1e12, "used": 5e11}); real = hub.shutil.disk_usage; hub.shutil.disk_usage = lambda p: fake
labels = []; orig = hub.add_task
hub.add_task = lambda label, **kw: (labels.append((label, kw.get("dir"), kw.get("url", "")[-40:])), orig(label, **{**kw, "kind": "noop"}))[1]
hub.download = lambda t: t.update(msg="이미 설치되어 있어요")
for f in [M / "diffusion_models/flux1-krea-dev_fp8_scaled.safetensors", M / "text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors"]: f.rename(f.with_suffix(".bak"))
r = req("/api/install", {"ids": ["krea-dev"]}); assert r.get("ok"), r
assert len(labels) == 2 and sorted(l[1] for l in labels) == ["diffusion_models", "text_encoders"], labels; ok("install krea-dev: queues the model + only the shared FLUX files that are missing")
hub.shutil.disk_usage = real
fake2 = type("U", (), {"free": 20e9, "total": 1e12, "used": 5e11}); hub.shutil.disk_usage = lambda p: fake2
n = len(labels); r = req("/api/install", {"ids": ["krea-dev"]}); assert "error" in r and "필요 약 17GB" in r["error"] and len(labels) == n, r; ok("disk check counts the dependency (17GB) and refuses when short")
print("\nBACKEND2 TESTS PASSED")
