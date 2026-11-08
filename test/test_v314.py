"""3.14: LoRA 만들기 — 세트·사진·캡션(WD14/대화 모델), 학습(가짜 sd-scripts)·진행률·미리보기·loras 등록, 검사."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, io, urllib.request, urllib.parse
from pathlib import Path
os.environ["TEST_HUB_PORT"] = "17977"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def up(sid, name, data):
    r = urllib.request.Request(B + f"/api/lora/set/upload?id={sid}&name={urllib.parse.quote(name)}", data=data, method="POST"); return json.load(urllib.request.urlopen(r))
def job2(o):
    jid = post("/api/job", o)["id"]; last = None
    for _ in range(600):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j, last
        if j.get("step"): last = j
        time.sleep(0.1)
def pngb(c, s=(640, 640)):
    b = io.BytesIO(); Image.new("RGB", s, c).save(b, "PNG"); return b.getvalue()
# 가짜 학습 엔진(진짜 sd-scripts 대신 같은 인자를 받아 진행 줄을 찍고 결과 파일을 써요)
eng = TMP / "engine/lora"; (eng / "sd-scripts").mkdir(parents=True, exist_ok=True); (eng / ".ready").write_text("ok")
(eng / "sd-scripts/sdxl_train_network.py").write_text(r'''
import sys, time, json, os, pathlib
a = sys.argv[1:]; g = lambda k: a[a.index(k) + 1] if k in a else None
out = pathlib.Path(g("--output_dir")); out.mkdir(parents=True, exist_ok=True); n = int(g("--max_train_steps"))
toml = pathlib.Path(g("--dataset_config")).read_text(encoding="utf-8"); img = pathlib.Path(toml.split('image_dir = "')[1].split('"')[0])
caps = sorted(p.read_text(encoding="utf-8") for p in img.glob("*.txt")); json.dump({"args": a, "caps": caps, "toml": toml}, open(out / "seen.json", "w", encoding="utf-8"))
print("loading model"); print("caching latents", flush=True)
for i in range(1, n + 1):
    print(f"steps: {i*100//n}%|###| {i}/{n} [00:01<00:01, 9it/s, avr_loss=0.{100-i:03d}]", flush=True); time.sleep(0.01)
    if g("--sample_every_n_steps") and i % int(g("--sample_every_n_steps")) == 0:
        (out / "sample").mkdir(exist_ok=True); open(out / "sample" / f"s_{i:06d}.png", "wb").write(open(os.environ["FAKE_PNG"], "rb").read())
open(out / (g("--output_name") + ".safetensors"), "wb").write(b"lora")
''', encoding="utf-8")
Image.new("RGB", (64, 64), (0, 200, 0)).save(TMP / "fake.png"); os.environ["FAKE_PNG"] = str(TMP / "fake.png")
hub.lora_train.py_of = lambda root: Path(sys.executable)
hub.model_family = lambda folder, name: ("sdxl", True, "test")
hub.bgremove.have_ort = lambda: True
hub.wd14.ready = lambda m: True
hub.wd14.tags = lambda m, img, general=0.35, **k: ["1girl", "smile", "red hair"]
assert get("/api/lora/engine")["installed"]
# 1) 세트 · 사진
assert post("/api/lora/set/new", {"name": ""})["error"]
assert "미성년" in post("/api/lora/set/new", {"name": "x", "trigger": "nude schoolgirl"})["error"]
S = post("/api/lora/set/new", {"name": "나비 고양이", "file": "nabi cat!", "trigger": "nabicat", "kind": "character"}); sid = S["id"]
assert S["file"] == "nabi_cat" and S["trigger"] == "nabicat"
for i in range(6): assert up(sid, f"사진{i}.jpg", pngb((i * 30, 100, 200)))["ok"]
assert "작아요" in up(sid, "tiny.png", pngb((1, 1, 1), (100, 100)))["error"]
assert up(sid, "x.png", b"not an image")["error"]
gd = hub.OUT / "생성"; gd.mkdir(parents=True, exist_ok=True); Image.new("RGB", (512, 512), (9, 9, 9)).save(gd / "g1.png")
r = post("/api/lora/set/from_gallery", {"id": sid, "urls": ["/out/%EC%83%9D%EC%84%B1/g1.png", "/out/../../x.png"]}); assert r["added"] == 1 and len(r["bad"]) == 1
V = get("/api/lora/set/" + sid); assert len(V["images"]) == 7
th = urllib.request.urlopen(B + V["images"][0]["url"]); assert th.headers["Content-Type"] == "image/png"
try: urllib.request.urlopen(B + f"/lora_data/{sid}/meta.json"); raise AssertionError("must 404")
except urllib.error.HTTPError: pass
V = post("/api/lora/set/remove", {"id": sid, "file": V["images"][-1]["file"]}); assert len(V["images"]) == 6
ok("set with photos (upload, gallery import, too-small/broken rejected, safe file serving)")
# 2) 캡션: WD14 · 직접 고치기
j, _ = job2({"kind": "lora", "op": "caption", "id": sid, "method": "wd14"}); assert j["state"] == "done", j
V = get("/api/lora/set/" + sid); assert all(x["caption"] == "1girl, smile, red hair" for x in V["images"])
V = post("/api/lora/set/update", {"id": sid, "captions": {V["images"][0]["file"]: "1girl, sitting on a sofa"}}); assert V["images"][0]["caption"] == "1girl, sitting on a sofa"
j, _ = job2({"kind": "lora", "op": "caption", "id": sid, "method": "wd14"}); assert get("/api/lora/set/" + sid)["images"][0]["caption"] == "1girl, sitting on a sofa"
ok("captions: WD14 tags, edited caption kept unless 'overwrite'")
# 3) 학습
j, live = job2({"kind": "lora", "op": "train", "id": sid, "ckpt": "noobai_xl_v11.safetensors", "preset": "fast", "steps": 50, "sample_prompt": "smile"})
assert j["state"] == "done" and j["lora_file"] == "nabi_cat.safetensors", j
assert live and live["step"] > 0 and live["loss"] is not None, live
assert (M / "loras/nabi_cat.safetensors").read_bytes() == b"lora"
seen = json.loads((TMP / "lora_data" / sid / "train/out/seen.json").read_text(encoding="utf-8"))
a = seen["args"]; assert a[a.index("--max_train_steps") + 1] == "50" and "--network_train_unet_only" in a and "--no_half_vae" in a and "--sample_every_n_steps" in a
assert all(c.startswith("nabicat, ") for c in seen["caps"]) and "resolution = 1024" in seen["toml"]
V = get("/api/lora/set/" + sid); assert V["lora_file"] == "nabi_cat.safetensors" and V["samples"]
u = hub.lora_user().get("nabi_cat.safetensors"); assert u["alias"] == "나비 고양이" and u["trigger"] == ["nabicat"] and "사진 6장" in u["memo"], u
j, _ = job2({"kind": "lora", "op": "train", "id": sid, "ckpt": "noobai_xl_v11.safetensors", "steps": 20}); assert j["lora_file"] == "nabi_cat_v2.safetensors"
ok("training: progress/loss/samples, LoRA copied to loras (no overwrite) with alias, trigger, memo")
# 4) 검사
S2 = post("/api/lora/set/new", {"name": "few"}); up(S2["id"], "a.png", pngb((1, 2, 3)))
j, _ = job2({"kind": "lora", "op": "train", "id": S2["id"], "ckpt": "noobai_xl_v11.safetensors"}); assert j["state"] == "error" and "최소 5장" in j["error"]
hub.model_family = lambda f, n: ("flux", False, "test")
j, _ = job2({"kind": "lora", "op": "train", "id": sid, "ckpt": "noobai_xl_v11.safetensors"}); assert j["state"] == "error" and "SDXL" in j["error"]
hub.model_family = lambda f, n: ("sdxl", True, "test")
assert post("/api/lora/set/delete", {"id": sid})["ok"] and not (TMP / "lora_data" / sid).exists() and (M / "loras/nabi_cat.safetensors").exists()
assert get("/api/lora/sets")["items"][0]["name"] == "few"
ok("needs 5+ photos, SD1.5/SDXL only, deleting a set keeps the made LoRA")
print("ALL OK")
