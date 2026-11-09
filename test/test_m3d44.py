"""4.4: 3D 사진 붙이기 — 3D 엔진이 다시 칠한 색 대신 앞 사진 화소를 텍스처에 그대로(카메라 자동 맞춤), 끄기,
모양이 안 맞으면 건너뛰기, 얼굴 찾기(MediaPipe) → 얼굴 부분 키워 붙이기, 면 수 기본값."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17999"
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import numpy as np
import photoproj
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid):
    for _ in range(900):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
def url(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True
class Cut:
    def cut(self, img, _):
        a = Image.new("L", img.size, 0); w, h = img.size; a.paste(255, (w // 4, h // 6, w * 3 // 4, h * 5 // 6)); o = img.convert("RGBA"); o.putalpha(a); return o
hub.rmbg_engine = lambda k: Cut()
for f in (M / "upscale_models").glob("*") if (M / "upscale_models").is_dir() else []: f.unlink()
touch("diffusion_models/trellis_2_int8_convrot.safetensors", "clip_vision/dino_v3_vit_l.safetensors", "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors")

S = 1200                                                       # 물체 부분 600×800 — 키우지 않아도 되는 크기
photo = Image.new("RGB", (S, S), (128, 128, 128)); photo.paste((200, 40, 40), (0, 0, S // 2, S)); photo.paste((40, 200, 40), (S // 2, 0, S, S))
T = Image.new("RGB", (512, 512), (40, 40, 160))                # 3D 엔진이 칠한 색(흐릿): 앞 칸 왼쪽 탁한 빨강, 오른쪽 탁한 초록, 나머지 파랑
T.paste((120, 70, 70), (0, 0, 85, 256)); T.paste((70, 120, 70), (85, 0, 171, 256))
STATE["glb"] = uv_glb(0.75, 1.0, 0.5, T, n=16)
j = job({"kind": "m3d", "op": "prep", "image": url(photo), "kind3": "character", "name": "hero"}); assert j["state"] == "done", j
sid = j["m3d"]["id"]
def tex_of(j):
    return np.asarray(photoproj.load(urllib.request.urlopen(B + j["images"][0]).read())["tex"].convert("RGB")).astype(int)
def at(t, x, y):
    """사진 좌표 → 앞 칸 텍스처 색 (물체 부분 x 300~900, y 200~1000)"""
    u = (0.05 + 0.9 * (x - 300) / 600) / 3; v = (0.05 + 0.9 * (y - 200) / 800) / 2
    return t[int(v * t.shape[0]), int(u * t.shape[1])]

# 1) 사진 붙이기(기본): 앞에서 보이는 면은 사진 색 그대로, 뒤는 그대로
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done", j
assert not [w for w in j.get("warn", []) if "사진" in w and "얼굴" not in w], j.get("warn")
t = tex_of(j)
assert np.abs(at(t, 450, 600) - (200, 40, 40)).max() <= 12 and np.abs(at(t, 750, 600) - (40, 200, 40)).max() <= 12, (at(t, 450, 600), at(t, 750, 600))
bk = t[384, 256]; assert bk[2] > bk[0] + 60 and bk[2] > bk[1] + 60, bk                       # 뒤 칸은 사진 색이 아니라 원래 파랑(색감만 사진에 맞춰요)
side = json.loads((hub.OUT / "3D" / (j["images"][0].rsplit("/", 1)[1] + ".json")).read_text(encoding="utf-8")); assert side["photo"] is True and side["face"] is False
ok("photo projection: front-visible texels take the photo colours exactly (camera found automatically), back keeps its own colour")

# 2) 끄기
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "photo": False}); assert j["state"] == "done", j
t = tex_of(j); assert np.abs(at(t, 450, 600) - (120, 70, 70)).max() <= 2, at(t, 450, 600)
ok("photo projection can be turned off (engine colours kept)")

# 3) 모양이 안 맞으면 건너뛰어요
STATE["glb"] = uv_glb(2.0, 0.3, 0.5, T, n=8)
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done" and any("겹치지 않아" in w for w in j["warn"]), j.get("warn")
STATE["glb"] = None
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done" and not [w for w in j.get("warn", []) if "사진 붙이기" in w], j   # 텍스처 좌표 없는 3D: 조용히 그대로
ok("shape mismatch → skipped with a note; a GLB without texture coordinates is left as is quietly")

# 4) 얼굴 찾기 → 얼굴 부분 키워 붙이기
STATE["glb"] = uv_glb(0.75, 1.0, 0.5, T, n=16)
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert any("얼굴 찾기 모델이 없어" in w for w in j["warn"]), j.get("warn")
touch("detection/mediapipe_face_fp32.safetensors")
STATE["face_box"] = ((S, S), (700, 300, 780, 380))
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done" and any("얼굴 부분이 120px" in w for w in j.get("warn", [])), j.get("warn")
touch("upscale_models/RealESRGAN_x4plus.pth")
n0 = len(SUBMITTED)
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done", j
gs = SUBMITTED[n0:]; kinds = [{v["class_type"] for v in g.values()} for g in gs]
fi = next(i for i, k in enumerate(kinds) if "MediaPipeFaceMask" in k); assert any("UpscaleModelLoader" in k for k in kinds[fi + 1:]), kinds
fm = next(v["inputs"] for v in gs[fi].values() if v["class_type"] == "MediaPipeFaceLandmarker"); assert fm["detector_variant"] == "both" and fm["num_faces"] == 1
t = tex_of(j)
assert np.abs(at(t, 740, 340) - (255, 0, 0)).max() <= 30 and np.abs(at(t, 750, 800) - (40, 200, 40)).max() <= 12, (at(t, 740, 340), at(t, 750, 800))
ok("face: MediaPipe finds the face, that part is upscaled and pasted from the enlarged crop (rest from the photo); missing face model noted")
STATE["face_box"] = ((S, S), (300, 200, 1000, 1000))          # 이미 큰 얼굴은 키우지 않아요
n0 = len(SUBMITTED); j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""})
assert j["state"] == "done" and not any("UpscaleModelLoader" in {v["class_type"] for v in g.values()} for g in SUBMITTED[n0:])
ok("a face that is already large is not upscaled")

# 5) 면 수 기본값·다시 짜기
assert hub.M3D_KIND["character"]["faces"] == 200000 and 700000 in hub.M3D_FACES
n0 = len(SUBMITTED); j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "res": "1536", "photo": False})
g = next(g for g in SUBMITTED[n0:] if any(v["class_type"] == "DecimateMesh" for v in g.values()))
dm = [v["inputs"] for v in g.values() if v["class_type"] == "DecimateMesh"][0]; rm = [v["inputs"] for v in g.values() if v["class_type"] == "RemeshMesh"][0]
assert dm["target_face_count"] == 200000 and rm["resolution"] == 1024, (dm, rm)
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "res": "1024", "faces": "700000", "photo": False})
g = SUBMITTED[-1]; assert [v["inputs"]["target_face_count"] for v in g.values() if v["class_type"] == "DecimateMesh"] == [700000]
assert [v["inputs"]["resolution"] for v in g.values() if v["class_type"] == "RemeshMesh"] == [768]
ok("character default 200k faces, 700k option; remesh 1024 at detail 1536 (768 otherwise)")
print("ALL OK")
