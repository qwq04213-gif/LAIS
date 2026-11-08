"""기능 모음: 얼굴·손 보정(FaceDetailer), 참고 이미지(IPAdapter), 카탈로그 파일 이름 바꿔 저장."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import io, sys, base64
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
ok = lambda m: print("PASS", m)
def pu(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def classes(wf): return [n["class_type"] for n in wf.values()]
def nodes(wf, c): return [n["inputs"] for n in wf.values() if n["class_type"] == c]

src = Image.new("RGB", (640, 480), (120, 80, 60))
base = {"kind": "feat", "feature": "detailer", "image": pu(src), "ckpt": "noobai_xl_v11.safetensors", "target": "both", "denoise": "0.35", "prompt": "blue eyes"}
j = job(dict(base)); wf = SUBMITTED[-1]
fd = nodes(wf, "FaceDetailer"); assert len(fd) == 2, classes(wf)
det = [n["model_name"] for n in nodes(wf, "UltralyticsDetectorProvider")]; assert det == ["bbox/face_yolov8m.pt", "bbox/hand_yolov8s.pt"], det
assert all(abs(n["denoise"] - 0.35) < 1e-6 for n in fd) and fd[0]["guide_size"] == 768 and fd[0]["sam_detection_hint"] == "center-1" and fd[0]["sam_mask_hint_use_negative"] == "False" and fd[0]["cycle"] == 1, fd[0]
assert fd[1]["image"][0] != fd[0]["image"][0] and fd[1]["image"] == [[k for k, v in wf.items() if v["inputs"] is fd[0] or v["inputs"] == fd[0]][0], 0], "passes must be chained"
texts = [n["text"] for n in nodes(wf, "CLIPTextEncode")]; assert any("detailed face" in t and "blue eyes" in t for t in texts) and any("detailed hands" in t for t in texts), texts
assert j["state"] == "done" and j["images"], j
ok("detailer: face then hand passes chained, detector picked from object_info, missing inputs filled from defaults")

j = job({**base, "target": "hand"}); wf = SUBMITTED[-1]; assert len(nodes(wf, "FaceDetailer")) == 1 and nodes(wf, "UltralyticsDetectorProvider")[0]["model_name"].startswith("bbox/hand")
STATE["dets"] = ["segm/person_yolov8m-seg.pt"]; hub.caps(force=True)
r = job({**base, "target": "face"}, expect_ok=False); assert r["state"] == "error" and "감지 모델" in r["error"], r
del STATE["dets"]; hub.caps(force=True)
STATE["missing"].add("FaceDetailer"); hub.caps(force=True)
r = job(dict(base), expect_ok=False); assert r["state"] == "error" and "FaceDetailer" in r["error"], r
F = req("/api/features"); d = [f for f in F if f["id"] == "detailer"][0]; assert d["missing_nodes"] == ["FaceDetailer"], d
STATE["missing"].clear(); hub.caps(force=True)
ok("detailer: single part, missing detector model and missing node give clear Korean messages")

ib = {"kind": "feat", "feature": "ipadapter", "image": pu(src), "prompt": "1girl, city", "ckpt": "noobai_xl_v11.safetensors", "mode": "face", "weight": "0.8", "w": "832", "h": "1216"}
j = job(dict(ib)); wf = SUBMITTED[-1]
ld = nodes(wf, "IPAdapterUnifiedLoader")[0]; ip = nodes(wf, "IPAdapter")[0]
assert ld["preset"] == "PLUS FACE (portraits)" and ip["weight_type"] == "linear" and abs(ip["weight"] - 0.8) < 1e-6 and ip["start_at"] == 0.0 and ip["end_at"] == 1.0, (ld, ip)
assert nodes(wf, "KSampler")[0]["model"][0] == [k for k, v in wf.items() if v["class_type"] == "IPAdapter"][0]
e = nodes(wf, "EmptyLatentImage")[0]; assert (e["width"], e["height"]) == (832, 1216)
j = job({**ib, "mode": "style"}); wf = SUBMITTED[-1]
assert nodes(wf, "IPAdapterUnifiedLoader")[0]["preset"] == "PLUS (high strength)" and nodes(wf, "IPAdapter")[0]["weight_type"] == "style transfer"
r = job({**ib, "prompt": ""}, expect_ok=False); assert r["state"] == "error" and "프롬프트" in r["error"], r
ok("ipadapter: face/style presets and weight types chosen, model chained into KSampler, size honoured")

cat = req("/api/catalog")["image"]; ids = {m["id"]: m for m in cat}
assert "adetailer" in ids and "ipadapter-sdxl" in ids and not ids["ipadapter-sdxl"]["installed"]
(hub.MODELS / "ultralytics" / "bbox").mkdir(parents=True, exist_ok=True)
for n in ("face_yolov8m.pt", "hand_yolov8s.pt"): (hub.MODELS / "ultralytics" / "bbox" / n).write_bytes(b"x")
assert {m["id"]: m for m in req("/api/catalog")["image"]}["adetailer"]["installed"]
x = [f for f in ids["ipadapter-sdxl"]["files"] if f.get("name")][0]; assert hub.cat_name(x) == "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
(hub.MODELS / "clip_vision").mkdir(parents=True, exist_ok=True)
for f in ids["ipadapter-sdxl"]["files"]: 
    (hub.MODELS / f["dir"]).mkdir(parents=True, exist_ok=True); (hub.MODELS / f["dir"] / hub.cat_name(f)).write_bytes(b"x")
assert {m["id"]: m for m in req("/api/catalog")["image"]}["ipadapter-sdxl"]["installed"]
ok("catalog: new entries listed; installed check honours renamed files and ultralytics/bbox folder")
print("ALL OK")
