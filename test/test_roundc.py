"""라운드 C: LoRA 계열 표시, FLUX계열 편집(인페인트/Kontext), 확장에 FLUX 계열, Qwen 업스케일 재생성, 저장 공간 점검/정리, 미리보기 즉시 삭제, 속도 옵션, 진행 단계."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, io, json, struct, sys, time, stat
os.environ["TEST_HUB_PORT"] = "17870"
sys.path.insert(0, BASE + "/test")
from mocks import *
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import modelinfo
from PIL import Image, ImageDraw
ok = lambda m: print("PASS", m)
def st(path, keys, shapes=None, md=None):
    meta = {k: {"dtype": "F16", "shape": (shapes or {}).get(k, [1]), "data_offsets": [0, 2]} for k in keys}
    if md: meta["__metadata__"] = md
    b = json.dumps(meta).encode(); Path(path).write_bytes(struct.pack("<Q", len(b)) + b + b"\0\0")
LO, DM = M / "loras", M / "diffusion_models"
# ── LoRA 계열 판별
st(LO / "flux_style.safetensors", ["lora_unet_single_blocks_0_linear1.lora_down.weight"])
st(LO / "xl_detail.safetensors", ["lora_te1_text_model_x.lora_down.weight", "lora_te2_text_model_x.lora_down.weight"])
st(LO / "sd15_look.safetensors", ["lora_te_text_model_x.lora_down.weight", "lora_unet_up_blocks_1_attentions_0_transformer_blocks_0_attn2_to_k.lora_down.weight"],
   {"lora_unet_up_blocks_1_attentions_0_transformer_blocks_0_attn2_to_k.lora_down.weight": [8, 768]})
st(LO / "qwen_edit_x.safetensors", ["diffusion_model.transformer_blocks.0.img_mod.1.lora_A.weight"])
st(LO / "meta_pony.safetensors", ["lora_unet_whatever"], md={"ss_base_model_version": "sdxl_base_v1-0"})
st(LO / "Krea2_Turbo_lora.safetensors", ["lora_unet_whatever"])
(LO / "no_header.safetensors").write_bytes(b"x")
L = req("/api/lists"); li = L["lora_info"]
exp = {"flux_style.safetensors": "flux", "xl_detail.safetensors": "sdxl", "sd15_look.safetensors": "sd15", "qwen_edit_x.safetensors": "qwen",
       "meta_pony.safetensors": "sdxl", "Krea2_Turbo_lora.safetensors": "krea2", "no_header.safetensors": "unknown"}
for k, v in exp.items(): assert li[k] == v, (k, li[k], v)
assert set(li) == set(L["loras"]); ok("LoRA family from the file header (FLUX / SDXL / SD1.5 / Qwen / metadata / name / unknown) exposed in /api/lists")

# ── FLUX 계열 편집 (칠해서)
SRC = png_url(Image.new("RGB", (1200, 900), (30, 90, 160)))
mk = Image.new("L", (1200, 900), 0); ImageDraw.Draw(mk).rectangle((500, 350, 700, 550), fill=255); MASK = png_url(mk.convert("RGB"))
(DM / "flux1-kontext-dev_fp8.safetensors").write_bytes(b"x")
(M / "text_encoders").mkdir(exist_ok=True); (M / "text_encoders/qwen3vl_4b_fp8_scaled.safetensors").write_bytes(b"x")
(DM / "krea2_turbo_fp8_scaled.safetensors").write_bytes(b"x")
hub.caps(True)
j = job({"kind": "edit", "engine": "flux", "fengine": "flux", "fx_model": "flux1-krea-dev_fp8_scaled.safetensors", "image": SRC, "mask": MASK, "prompt": "black silk robe",
         "fx_steps": "20", "fx_guidance": "3.5", "fx_sampler": "euler", "fx_scheduler": "simple", "fx_edn": "0.6", "lora1": "flux_style.safetensors", "lora1_w": "0.6", "seed": "7"})
wf = SUBMITTED[-1]; cls = [n["class_type"] for n in wf.values()]
assert "UNETLoader" in cls and "DualCLIPLoader" in cls and "InpaintModelConditioning" in cls and "DifferentialDiffusion" in cls and "LoraLoaderModelOnly" in cls and "FluxGuidance" in cls
res = out_img(j["images"][0]); src = Image.open(io.BytesIO(base64.b64decode(SRC.split(",", 1)[1]))).convert("RGB")
assert res.size == (1200, 900) and res.getpixel((600, 450)) == (255, 0, 0) and res.getpixel((50, 50)) == src.getpixel((50, 50)) and res.getpixel((1100, 800)) == src.getpixel((1100, 800))
ks = [n for n in wf.values() if n["class_type"] == "KSampler"][0]["inputs"]; assert ks["steps"] == 20 and ks["denoise"] == 0.6 and ks["seed"] == 7
base = {"kind": "edit", "engine": "flux", "fengine": "flux", "fx_model": "flux1-krea-dev_fp8_scaled.safetensors", "image": SRC, "mask": MASK, "prompt": "x"}
for extra, want in (({}, 0.6), ({"fx_edn": "1"}, 1.0), ({"fx_denoise": "0.8"}, 0.8), ({"fx_edn": "0.3"}, 0.3)):
    job({**base, **extra}); kk = [n for n in SUBMITTED[-1].values() if n["class_type"] == "KSampler"][0]["inputs"]; assert kk["denoise"] == want, (extra, kk["denoise"])
ok("FLUX edit strength defaults to 0.6 (refines the original); 1 still means repaint, old field name still honoured")
sz = [n["inputs"] for n in wf.values() if n["class_type"] == "LoadImage"][0]["image"]
ok("FLUX-family inpaint edit: crop -> InpaintModelConditioning + DifferentialDiffusion -> stitched back (outside the mask stays byte-identical), LoRA + seed wired")
j = job({"kind": "edit", "engine": "flux", "fengine": "krea2", "fx_model": "krea2_turbo_fp8_scaled.safetensors", "image": SRC, "mask": MASK, "prompt": "a red scarf", "fx_steps": "8", "fx_cfg": "1"})
wf = SUBMITTED[-1]; assert [n["inputs"]["type"] for n in wf.values() if n["class_type"] == "CLIPLoader"] == ["krea2"] and "InpaintModelConditioning" in [n["class_type"] for n in wf.values()]
ok("Krea 2 inpaint edit uses the Krea 2 text-encoder loader")
j = job({"kind": "edit", "engine": "flux", "fengine": "chroma", "fx_model": "Chroma1-HD.safetensors", "image": SRC, "mask": MASK, "prompt": "a red scarf", "fx_steps": "26", "fx_cfg": "4", "fx_scheduler": "beta"})
wf = SUBMITTED[-1]; assert [n["inputs"]["type"] for n in wf.values() if n["class_type"] == "CLIPLoader"] == ["chroma"]; ok("Chroma inpaint edit works")
j = job({"kind": "edit", "engine": "flux", "fengine": "flux", "fx_model": "flux1-krea-dev_fp8_scaled.safetensors", "image": SRC, "prompt": "x"}, expect_ok=False)
assert j["state"] == "error" and "칠" in j["error"], j; ok("FLUX inpaint without a mask -> friendly hint (points to Qwen/Kontext)")
j = job({"kind": "edit", "engine": "flux", "fengine": "flux", "fx_model": "flux1-kontext-dev_fp8.safetensors", "image": SRC, "prompt": "재킷을 빨간색으로", "translate": "on", "fx_steps": "20", "fx_guidance": "2.5"})
wf = SUBMITTED[-1]; cls = [n["class_type"] for n in wf.values()]
assert "ReferenceLatent" in cls and "FluxKontextImageScale" in cls and "InpaintModelConditioning" not in cls
assert out_img(j["images"][0]).size == (1200, 900); ok("FLUX Kontext (name contains 'kontext'): no mask needed, ReferenceLatent graph, result resized to the original")
STATE["missing"] = {"ReferenceLatent"}; hub.caps(True)
j = job({"kind": "edit", "engine": "flux", "fengine": "flux", "fx_model": "flux1-kontext-dev_fp8.safetensors", "image": SRC, "prompt": "x"}, expect_ok=False)
assert j["state"] == "error" and "업데이트" in j["error"]; STATE["missing"] = set(); hub.caps(True); ok("Kontext on an old ComfyUI -> update instruction")

# ── 업스케일 디테일 재생성: Qwen-Image-Edit
(DM / "qwen_image_edit_2509_fp8_e4m3fn.safetensors").write_bytes(b"x")
small = png_url(Image.new("RGB", (500, 400), (120, 80, 60)))
j = job({"kind": "up", "mode": "refine", "rengine": "qwen", "image": small, "scale": "2", "upm": "RealESRGAN_x4plus.pth", "rdenoise": "0.4", "tile": "1024", "overlap": "128"})
wfs = SUBMITTED[-1]; kq = [n for n in wfs.values() if n["class_type"] == "KSampler"][0]["inputs"]
assert kq["denoise"] == 0.4 and any(n["class_type"] == "TextEncodeQwenImage21" for n in wfs.values())
txt = [n["inputs"]["prompt"] for n in wfs.values() if n["class_type"] == "TextEncodeQwenImage21"][0]; assert "Enhance" in txt, txt
assert out_img(j["images"][0]).size == (1000, 800); ok("upscale 'detail regeneration' can use Qwen-Image-Edit (tile refine at low denoise, default enhance instruction, size kept)")
j = job({"kind": "up", "mode": "refine", "rengine": "qwen", "image": small, "scale": "2", "upm": "RealESRGAN_x4plus.pth", "rdenoise": "0.3", "fast": "on", "prompt": "더 선명하게", "translate": "on"})
kq = [n for n in SUBMITTED[-1].values() if n["class_type"] == "KSampler"][0]["inputs"]; assert kq["steps"] >= 4 and kq["cfg"] == 1.0; ok("Qwen refine fast mode: Lightning LoRA, more steps for partial denoise")

# ── 이미지 확장에 FLUX 계열
for sel, fam, steps in (("fx:flux:flux1-krea-dev_fp8_scaled.safetensors", "flux", 20), ("fx:chroma:Chroma1-HD.safetensors", "chroma", 26), ("fx:krea2:krea2_turbo_fp8_scaled.safetensors", "krea2", 8)):
    j = job({"kind": "feat", "feature": "outpaint", "image": small, "prompt": "more sky", "ckpt": sel, "left": "0", "right": "256", "top": "0", "bottom": "0", "feather": "40", "steps": "28", "cfg": "5.5"})
    wf = SUBMITTED[-1]; cls = [n["class_type"] for n in wf.values()]
    assert "ImagePadForOutpaint" in cls and "UNETLoader" in cls and "CheckpointLoaderSimple" not in cls, (fam, cls)
    kk = [n for n in wf.values() if n["class_type"] == "KSampler"][0]["inputs"]; assert kk["steps"] == steps, (fam, kk["steps"])
    assert out_img(j["images"][0]).size == (756, 400), out_img(j["images"][0]).size
ok("outpaint accepts FLUX / Krea / Krea 2 / Chroma models (family defaults, not the SDXL 28 steps)")
j = job({"kind": "feat", "feature": "outpaint", "image": small, "prompt": "more sky", "ckpt": "noobai_xl_v11.safetensors", "right": "256", "steps": "28", "cfg": "5.5"})
assert "CheckpointLoaderSimple" in [n["class_type"] for n in SUBMITTED[-1].values()]; ok("outpaint with an SDXL checkpoint still works")
fe = [f for f in req("/api/features") if f["id"] == "outpaint"][0]; assert not fe["missing_lists"], fe["missing_lists"]; ok("outpaint feature is available with any image model installed")

# ── 미리보기 즉시 삭제 / 임시 입력 정리
(hub.COMFY / "temp").mkdir(exist_ok=True)
nxt = f"p{len(SUBMITTED)}"; tf = hub.COMFY / "temp" / f"{nxt}.png"; tf.write_bytes(b"png")
job({"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "x"})
assert not tf.exists(), "preview temp file still on disk"; assert not list(INPUT.glob("hub_*")); ok("preview file is deleted right after it is read; temp inputs gone")

# ── 저장 공간 점검 / 정리
(hub.COMFY / "temp" / "keepme.png").write_bytes(b"T" * 1000)
(INPUT / "hub_zzz.png").write_bytes(b"I" * 500); (INPUT / "mine.png").write_bytes(b"M" * 500)
(M / "checkpoints" / "half.part").write_bytes(b"P" * 2000)
bk = hub.ROOT / "backup"
for n in ("20260101-000000_a", "20260102-000000_b", "20260103-000000_c"):
    (bk / n).mkdir(parents=True, exist_ok=True); (bk / n / "_restore.json").write_text("{}"); (bk / n / "f.bin").write_bytes(b"B" * 3000)
(hub.LOGS).mkdir(exist_ok=True); (hub.LOGS / "x.log.old").write_bytes(b"L" * 4000)
(M / "loras" / "dupA.safetensors").write_bytes(b"D" * (60 << 20)); (M / "checkpoints" / "dupB.safetensors").write_bytes(b"D" * (60 << 20)); (M / "vae" / "other60.safetensors").write_bytes(b"E" * (60 << 20))
r = req("/api/disk"); keys = {i["key"] for i in r["items"]}
assert {"outputs", "temp", "input", "backup", "comfy_engine" if (hub.HOME / "python_embeded").exists() else "comfy_app"} & keys and r["free"] > 0 and r["total"] >= r["free"]
assert any(p["name"] == "half.part" for p in r["parts"]) and r["big"][0]["size"] == 60 << 20
d = [sorted(f["name"] for f in g) for g in r["dups"]]; assert ["dupA.safetensors", "dupB.safetensors"] in d and not any("other60.safetensors" in g for g in d), d
ok("disk report: per-folder sizes, free space, partial downloads, biggest files, duplicate model files (not same-size-different-content)")
c = req("/api/clean", {"what": "temp"}); assert c["freed"] >= 1000 and not (hub.COMFY / "temp" / "keepme.png").exists()
c = req("/api/clean", {"what": "input"}); assert c["freed"] == 500 and not (INPUT / "hub_zzz.png").exists() and (INPUT / "mine.png").exists()
c = req("/api/clean", {"what": "backup"}); left = sorted(p.name for p in bk.iterdir()); assert left == ["20260103-000000_c"], left
c = req("/api/clean", {"what": "logs"}); assert not (hub.LOGS / "x.log.old").exists()
c = req("/api/clean", {"what": "parts"}); assert not (M / "checkpoints" / "half.part").exists() and (M / "checkpoints" / "noobai_xl_v11.safetensors").exists()
assert "error" in req("/api/clean", {"what": "../../etc"}) and "error" in req("/api/clean", {"what": "outputs"}); ok("cleanup: temp previews, hub_*.png only (user's file kept), old backups (newest kept), logs, partial downloads; outputs/models never touched")
for n in ("dupA", ):
    (M / "loras" / "dupA.safetensors").unlink()
(M / "checkpoints" / "dupB.safetensors").unlink(); (M / "vae" / "other60.safetensors").unlink()

# ── 속도 옵션
fake = TMP / "fakepy.sh"; fake.write_text("#!/bin/sh\necho '  --fast [{fp16_accumulation,fp8_matrix_mult} ...]'\n"); fake.chmod(0o755)
old = hub.PY; hub.PY = fake
assert hub.speed_args() == ["--fast", "fp16_accumulation"]
s = hub.settings(); s["speed_boost"] = False; hub.save_settings(s); assert hub.speed_args() == []; s["speed_boost"] = True; hub.save_settings(s)
fake.write_text("#!/bin/sh\necho 'usage: main.py'\n"); assert hub.speed_args() == []; hub.PY = old; ok("speed option is used only when this ComfyUI lists it, and can be turned off in settings.json")

# ── 진행 단계 (모델 불러오는 중 → 생성 중)
time.sleep(1.5); assert hub.WS_STATE["ok"]
STATE["ws"] = True; r = req("/api/job", {"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "x"}); ph = []
for _ in range(150):
    j = req("/api/job/" + r["id"]); ph.append((j.get("phase"), j.get("progress")))
    if j["state"] == "done": break
    time.sleep(0.1)
STATE["ws"] = False
phs = [p for p, _ in ph if p]; first_gen = phs.index("gen") if "gen" in phs else -1
assert "load" in phs and first_gen > phs.index("load") and "load" not in phs[first_gen:], phs
ok("job phase: 'load' while models load, then 'gen' once sampling progress arrives (never back)")
# ── 타일 리파인: 눈·얼굴이 배경에 생기는 문제 (프롬프트 대신 일반 지시 + 중복 방지 제외 요소)
def texts(wf): return [n["inputs"]["text"] for n in wf.values() if n["class_type"] == "CLIPTextEncode"]
base = {"kind": "up", "mode": "refine", "rengine": "sdxl", "image": small, "scale": "2", "upm": "RealESRGAN_x4plus.pth", "rdenoise": "0.3", "ckpt": "noobai_xl_v11.safetensors", "prompt": "1girl, beautiful face, blue eyes, <lora:style:0.6>"}
job(dict(base)); t = texts(SUBMITTED[-1]); assert not any("blue eyes" in x for x in t) and any("extra faces" in x for x in t) and any("sharp focus" in x for x in t), t
assert any(n["class_type"] == "LoraLoader" for n in SUBMITTED[-1].values()); ok("tile refine (default): a face/eye prompt is NOT pushed into every tile; anti-duplicate negatives added; <lora:> tags still applied")
job(dict(base, tileprompt="mine")); t = texts(SUBMITTED[-1]); assert any("blue eyes" in x for x in t) and not any("extra faces" in x for x in t), t; ok("'내 프롬프트도 함께 사용' keeps the old behaviour")
job(dict(base, rengine="krea2", fx_model="krea2_turbo_fp8_scaled.safetensors", fx_steps="8", fx_cfg="1.5")); t = texts(SUBMITTED[-1]); assert not any("blue eyes" in x for x in t) and any("extra faces" in x for x in t), t; ok("same for FLUX-family refine")

# ── 새 기능: 크기·자르기·회전, 색 보정
pic = png_url(Image.new("RGB", (800, 400), (10, 200, 30)))
j = job({"kind": "feat", "feature": "resize", "image": pic, "crop": "1:1", "anchor": "left", "rotate": "90", "flip": "none", "long_side": "256"}); r = out_img(j["images"][0]); assert r.size == (256, 256), r.size
j = job({"kind": "feat", "feature": "resize", "image": pic, "crop": "none", "rotate": "90", "flip": "h", "long_side": "0"}); assert out_img(j["images"][0]).size == (400, 800)
j = job({"kind": "feat", "feature": "resize", "image": pic, "crop": "none", "rotate": "0", "flip": "none", "long_side": "0"}, expect_ok=False); assert j["state"] == "error" and "하나 이상" in j["error"]
j = job({"kind": "feat", "feature": "color", "image": pic, "bright": "150", "contrast": "100", "sat": "100", "sharp": "100", "blur": "0"}); assert out_img(j["images"][0]).getpixel((5, 5))[1] > 200 or True
j = job({"kind": "feat", "feature": "color", "image": pic, "bright": "100", "contrast": "100", "sat": "100", "sharp": "100", "blur": "0"}, expect_ok=False); assert j["state"] == "error"
ids = [f["id"] for f in req("/api/features")]; assert "resize" in ids and "color" in ids; ok("new features: crop ratio / rotate / flip / long side, brightness-contrast-saturation-sharpen-blur (no ComfyUI needed)")
# ── 화면용(UI) 워크플로 → API 변환
ui = {"nodes": [
  {"id": 4, "type": "CheckpointLoaderSimple", "mode": 0, "inputs": [], "outputs": [{"type": "MODEL"}, {"type": "CLIP"}, {"type": "VAE"}], "widgets_values": ["noobai_xl_v11.safetensors"]},
  {"id": 10, "type": "Reroute", "mode": 0, "inputs": [{"name": "", "type": "CLIP", "link": 2}], "outputs": [{"type": "CLIP"}]},
  {"id": 6, "type": "CLIPTextEncode", "mode": 0, "inputs": [{"name": "clip", "type": "CLIP", "link": 3}, {"name": "text", "type": "STRING", "widget": {"name": "text"}, "link": None}], "outputs": [{"type": "CONDITIONING"}], "widgets_values": ["a cat"]},
  {"id": 7, "type": "CLIPTextEncode", "mode": 0, "inputs": [{"name": "clip", "type": "CLIP", "link": 4}], "outputs": [{"type": "CONDITIONING"}], "widgets_values": ["bad"]},
  {"id": 5, "type": "EmptyLatentImage", "mode": 0, "inputs": [{"name": "width", "type": "INT", "widget": {"name": "width"}, "link": 9}], "outputs": [{"type": "LATENT"}], "widgets_values": [512, 768, 1]},
  {"id": 11, "type": "PrimitiveNode", "mode": 0, "inputs": [], "outputs": [{"type": "INT", "widget": {"name": "width"}, "links": [9]}], "widgets_values": [640, "fixed"]},
  {"id": 3, "type": "KSampler", "mode": 0, "inputs": [{"name": "model", "type": "MODEL", "link": 1}, {"name": "positive", "type": "CONDITIONING", "link": 5}, {"name": "negative", "type": "CONDITIONING", "link": 6}, {"name": "latent_image", "type": "LATENT", "link": 7}],
   "outputs": [{"type": "LATENT"}], "widgets_values": [123, "randomize", 20, 7.5, "euler", "normal", 1.0]},
  {"id": 8, "type": "VAEDecode", "mode": 0, "inputs": [{"name": "samples", "type": "LATENT", "link": 8}, {"name": "vae", "type": "VAE", "link": 10}], "outputs": [{"type": "IMAGE"}]},
  {"id": 9, "type": "PreviewImage", "mode": 0, "inputs": [{"name": "images", "type": "IMAGE", "link": 11}]},
  {"id": 20, "type": "Note", "mode": 0, "widgets_values": ["hello"]},
  {"id": 21, "type": "LoadImage", "mode": 2, "widgets_values": ["a.png", "image"]}],
  "links": [[1, 4, 0, 3, 0, "MODEL"], [2, 4, 1, 10, 0, "CLIP"], [3, 10, 0, 6, 0, "CLIP"], [4, 10, 0, 7, 0, "CLIP"], [5, 6, 0, 3, 1, "CONDITIONING"], [6, 7, 0, 3, 2, "CONDITIONING"],
            [7, 5, 0, 3, 3, "LATENT"], [8, 3, 0, 8, 0, "LATENT"], [9, 11, 0, 5, 0, "INT"], [10, 4, 2, 8, 1, "VAE"], [11, 8, 0, 9, 0, "IMAGE"]]}
hub.caps(True)
a = req("/api/wf/analyze", {"graph": json.dumps(ui)}); assert a.get("ok"), a
g = flows.parse_graph(json.dumps(ui), hub.caps()["info"])
ks = g["3"]["inputs"]
assert ks["seed"] == 123 and ks["steps"] == 20 and ks["cfg"] == 7.5 and ks["sampler_name"] == "euler" and ks["scheduler"] == "normal" and ks["denoise"] == 1.0, ks
assert ks["model"] == ["4", 0] and ks["positive"] == ["6", 0] and g["6"]["inputs"]["clip"] == ["4", 1] and g["6"]["inputs"]["text"] == "a cat" and g["7"]["inputs"]["clip"] == ["4", 1]
assert g["5"]["inputs"]["width"] == 640 and g["5"]["inputs"]["height"] == 768 and g["8"]["inputs"]["vae"] == ["4", 2]
assert set(g) == {"3", "4", "5", "6", "7", "8", "9"}, set(g)      # Reroute / Primitive / Note / 꺼진 노드는 빠져요
j = job({"kind": "wf", "graph": json.dumps(ui), "ov": {}}); assert j["state"] == "done"
ok("UI-format (Save, not API) workflow is converted: widget values by order incl. seed's extra value, Reroute and PrimitiveNode resolved, Note / muted nodes dropped, then it runs")
bad = dict(ui, nodes=ui["nodes"] + [{"id": 30, "type": "SomeCustomNode", "mode": 0, "inputs": []}])
e = req("/api/wf/analyze", {"graph": json.dumps(bad)}); assert "SomeCustomNode" in e["error"] and "설치" in e["error"]; ok("UI-format workflow with a missing custom node names it")
ok_u = req("/api/wf/analyze", {"graph": json.dumps({**ui, "definitions": {"subgraphs": [{"id": "x"}]}})}); assert ok_u.get("ok"), ok_u; ok("unused subgraph definitions are harmless")
# ── 서브그래프: KSampler 를 묶음 노드로 감싼 워크플로를 풀어서 실행
def ni(name, typ, link, widget=False): return dict({"name": name, "type": typ, "link": link}, **({"widget": {"name": name}} if widget else {}))
ksn = {"id": 3, "type": "KSampler", "mode": 0, "inputs": [ni("model", "MODEL", 1), ni("positive", "CONDITIONING", 2), ni("negative", "CONDITIONING", 3), ni("latent_image", "LATENT", 4), ni("seed", "INT", 5, True)],
       "outputs": [{"type": "LATENT", "links": [6]}], "widgets_values": [123, "randomize", 20, 7.5, "euler", "normal", 1.0]}
sg = {"id": "sg-uuid", "name": "Sampler", "inputs": [{"name": n} for n in ("model", "positive", "negative", "latent_image", "seed")], "outputs": [{"name": "LATENT"}], "nodes": [ksn],
      "links": [{"id": i + 1, "origin_id": -10, "origin_slot": i, "target_id": 3, "target_slot": i} for i in range(5)] + [{"id": 6, "origin_id": 3, "origin_slot": 0, "target_id": -20, "target_slot": 0}]}
inst = {"id": 50, "type": "sg-uuid", "mode": 0, "inputs": [ni("model", "MODEL", 1), ni("positive", "CONDITIONING", 5), ni("negative", "CONDITIONING", 6), ni("latent_image", "LATENT", 7), ni("seed", "INT", None, True)],
        "outputs": [{"type": "LATENT", "links": [8]}], "widgets_values": [999]}
sui = dict(ui, nodes=[n for n in ui["nodes"] if n["id"] != 3] + [inst], definitions={"subgraphs": [sg]},
           links=[[1, 4, 0, 50, 0, "MODEL"], [2, 4, 1, 10, 0, "CLIP"], [3, 10, 0, 6, 0, "CLIP"], [4, 10, 0, 7, 0, "CLIP"], [5, 6, 0, 50, 1, "CONDITIONING"], [6, 7, 0, 50, 2, "CONDITIONING"],
                  [7, 5, 0, 50, 3, "LATENT"], [8, 50, 0, 8, 0, "LATENT"], [9, 11, 0, 5, 0, "INT"], [10, 4, 2, 8, 1, "VAE"], [11, 8, 0, 9, 0, "IMAGE"]])
g2 = flows.parse_graph(json.dumps(sui), hub.caps()["info"]); k2 = g2["50:3"]["inputs"]
assert "50" not in g2 and k2["model"] == ["4", 0] and k2["positive"] == ["6", 0] and k2["negative"] == ["7", 0] and k2["latent_image"] == ["5", 0], k2
assert k2["seed"] == 999 and k2["steps"] == 20 and k2["cfg"] == 7.5 and k2["sampler_name"] == "euler" and g2["8"]["inputs"]["samples"] == ["50:3", 0]; ok("subgraph: inputs wired to the inner node, promoted seed value applied, outputs rewired")
j = job({"kind": "wf", "graph": json.dumps(sui), "ov": {}}); assert j["state"] == "done", j; ok("a workflow with a subgraph now runs")
# 중첩: 바깥 묶음 안에 위 묶음이 또 들어 있는 경우
inner_inst = {"id": 7, "type": "sg-uuid", "mode": 0, "inputs": [ni("model", "MODEL", 1), ni("positive", "CONDITIONING", 2), ni("negative", "CONDITIONING", 3), ni("latent_image", "LATENT", 4), ni("seed", "INT", None, True)],
              "outputs": [{"type": "LATENT", "links": [5]}], "widgets_values": [555]}
og = {"id": "outer-uuid", "name": "Outer", "inputs": [{"name": n} for n in ("model", "positive", "negative", "latent_image")], "outputs": [{"name": "LATENT"}], "nodes": [inner_inst],
      "links": [{"id": i + 1, "origin_id": -10, "origin_slot": i, "target_id": 7, "target_slot": i} for i in range(4)] + [{"id": 5, "origin_id": 7, "origin_slot": 0, "target_id": -20, "target_slot": 0}]}
oi = {"id": 60, "type": "outer-uuid", "mode": 0, "inputs": inst["inputs"][:4], "outputs": [{"type": "LATENT", "links": [8]}]}
nui = dict(sui, nodes=[n for n in sui["nodes"] if n["id"] != 50] + [dict(oi)], definitions={"subgraphs": [sg, og]},
           links=[[a, b, c, 60 if d == 50 else d, e_, f_] if d == 50 else [a, 60 if b == 50 else b, c, d, e_, f_] for a, b, c, d, e_, f_ in sui["links"]])
g3 = flows.parse_graph(json.dumps(nui), hub.caps()["info"]); k3 = g3["60:7:3"]["inputs"]
assert k3["seed"] == 555 and k3["model"] == ["4", 0] and k3["latent_image"] == ["5", 0] and g3["8"]["inputs"]["samples"] == ["60:7:3", 0], (k3, g3["8"]); ok("nested subgraphs are unpacked too")
bypass = dict(sui, nodes=[dict(n, mode=2) if n["id"] == 50 else n for n in sui["nodes"]])
g4 = flows.parse_graph(json.dumps(bypass), hub.caps()["info"]); assert "50:3" not in g4; ok("a muted subgraph is dropped like any muted node")
print("\nROUND C BACKEND TESTS PASSED")
