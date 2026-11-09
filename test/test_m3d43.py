"""4.3: 3D 품질 — Pixal3D(사진 한 장, MoGe 화각) 기본 엔진·없으면 TRELLIS.2 로 안내, 작은 사진 자동 키우기·[업스케일로 키우기],
권장 크기 표시, 방향 하나만 그리기, 방향·T자 그림이 결과 폴더(3D)에 남기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17946"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid):
    for _ in range(600):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def cls(c): return [v["inputs"] for v in SUBMITTED[-1].values() if v["class_type"] == c]
def node(ref): return SUBMITTED[-1][ref[0]]["class_type"]
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
CAT = {m["id"]: m for k in ("llm", "image") for m in json.loads((Path(BASE) / "LocalAI-Studio/hub/models.json").read_text(encoding="utf-8"))[k]}
files_of = lambda i: [f["dir"] + "/" + (f.get("name") or f["url"].rsplit("/", 1)[1]) for f in CAT[i]["files"]]
def url(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True
class Cut:
    def cut(self, img, _):
        a = Image.new("L", img.size, 0); w, h = img.size; a.paste(255, (w // 4, h // 6, w * 3 // 4, h * 5 // 6)); o = img.convert("RGBA"); o.putalpha(a); return o
hub.rmbg_engine = lambda k: Cut()
for f in (M / "upscale_models").glob("*") if (M / "upscale_models").is_dir() else []: f.unlink()

# 권장 크기·키우기
j = job({"kind": "m3d", "op": "prep", "image": url(Image.new("RGB", (600, 600), (90, 30, 30))), "kind3": "character", "name": "hero"}); assert j["state"] == "done", j
S = j["m3d"]; sid = S["id"]; d = hub.M3D_DIR / sid
assert S["stats"]["long"] == 400 and S["stats"]["good"] == 1024 and any("권장" in c["text"] and "400px" in c["text"] for c in S["checks"]), S["checks"]
j = job({"kind": "m3d", "op": "enlarge", "id": sid}); assert j["state"] == "error" and "업스케일 모델이 없어요" in j["error"], j
touch("upscale_models/RealESRGAN_x4plus.pth")
j = job({"kind": "m3d", "op": "enlarge", "id": sid}); assert j["state"] == "done" and "키웠어요" in j["msg"], j
assert j["m3d"]["stats"]["long"] >= 1000 and cls("UpscaleModelLoader") and Image.open(d / "view_front.png").mode == "RGBA"
j = job({"kind": "m3d", "op": "enlarge", "id": sid}); assert j["state"] == "done" and "충분" in j["msg"], j
ok("object size vs recommended 1024px shown; [enlarge] upscales the cut-out (alpha kept), says when it's already big enough or no upscaler")

# 방향 하나만 그리기 + 결과 폴더 저장
j = job({"kind": "m3d", "op": "views", "id": sid, "sides": ["back"]}); assert j["state"] == "done", j
assert j["m3d"]["slots"]["back"] and not j["m3d"]["slots"]["left"] and len(j["images"]) == 1 and "/3D/" in j["images"][0]
meta = json.loads((hub.OUT / "3D" / (j["images"][0].rsplit("/", 1)[1] + ".json")).read_text(encoding="utf-8")) if (hub.OUT / "3D" / (j["images"][0].rsplit("/", 1)[1] + ".json")).is_file() else None
assert Image.open(io.BytesIO(urllib.request.urlopen(B + j["images"][0]).read())).mode == "RGBA"
j = job({"kind": "m3d", "op": "tpose", "id": sid}); assert j["state"] == "done" and len(j["images"]) == 1 and "/3D/" in j["images"][0], j
ok("drawing a single side only; side and T-pose drawings are also saved in outputs/3D")

# Pixal3D(사진 한 장)
touch(*files_of("trellis2"))
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "engine3": "pixal"}); assert j["state"] == "done" and any("Pixal3D 가 아직 없어" in w for w in j["warn"]), j
assert cls("Trellis2Conditioning") and not cls("Pixal3DConditioning")
touch(*files_of("pixal3d"))
assert get("/api/m3d/" + sid)["ready"]["pixal"]
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "res": "1536", "tex": "4096"}); assert j["state"] == "done", j      # 자동 → Pixal3D
pc = cls("Pixal3DConditioning")[0]; assert node(pc["camera_angle_x"]) == "MoGeGeometryToFOV" and node(pc["image"]) == "ImageCropToMask"
assert cls("ImageCropToMask")[0]["pad_factor"] == 1.1 and cls("MoGeGeometryToFOV")[0]["axis"] == "horizontal" and cls("LoadMoGeModel")[0]["model_name"].startswith("moge")
assert cls("UNETLoader")[0]["unet_name"] == "pixal3d_int8_convrot.safetensors" and cls("CLIPVisionLoader")[0]["clip_name"] == "dino_v3_L_naf_fp32.safetensors"
assert cls("Trellis2UpsampleStage")[0]["target_resolution"] == 1536 and cls("BakeTextureFromVoxel")[0]["texture_size"] == 4096 and not cls("Trellis2Conditioning")
side = json.loads((hub.OUT / "3D" / (j["images"][0].rsplit("/", 1)[1] + ".json")).read_text(encoding="utf-8")); assert side["engine"] == "Pixal3D"
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "engine3": "trellis"}); assert j["state"] == "done" and cls("Trellis2Conditioning") and not cls("Pixal3DConditioning"), j
(M / files_of("pixal3d")[-1]).unlink()                                                       # MoGe 없음 → 기본 화각
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done" and any("MoGe" in w for w in j["warn"]), j
assert cls("Pixal3DConditioning")[0]["camera_angle_x"] == 49.13 and not cls("MoGeInference")
STATE["missing"].add("Pixal3DConditioning"); hub._CAPS["t"] = 0
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done" and any("Pixal3D 노드가 없어" in w for w in j["warn"]) and cls("Trellis2Conditioning"), j
STATE["missing"].discard("Pixal3DConditioning"); hub._CAPS["t"] = 0
ok("Pixal3D single image: default when installed (MoGe fov → Pixal3DConditioning, pad 1.1, 1536/4096), TRELLIS.2 on request, falls back with notes")

# 작은 사진은 만들기 전에 자동으로 키워요
j = job({"kind": "m3d", "op": "prep", "image": url(Image.new("RGB", (400, 400), (20, 90, 30))), "kind3": "object"}); sid2 = j["m3d"]["id"]
n0 = len(SUBMITTED)
j = job({"kind": "m3d", "op": "build", "id": sid2, "blender": ""}); assert j["state"] == "done" and any("업스케일로 키워" in w for w in j["warn"]), j
assert any(any(v["class_type"] == "UpscaleModelLoader" for v in g.values()) for g in SUBMITTED[n0:])
ok("small subjects are upscaled automatically before 3D (with a note)")
print("ALL OK")
