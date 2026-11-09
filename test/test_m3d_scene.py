"""4.2: 3D 장면 전체 — 원본 사진에서 고른 물체 넣기·빼기, 물체 자리 어림(깊이 + 사진 속 위치), GLB 합치기(파이썬만),
물체마다 TRELLIS.2 → 한 장면 GLB + 물체별 GLB + layout.json 묶음, 가려진 부분 채우기(Qwen 편집), Blender 로 FBX·.blend."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, zipfile, urllib.request
os.environ["TEST_HUB_PORT"] = "17949"
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import numpy as np
import glbscene
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid):
    for _ in range(600):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def url(im, fmt="PNG"): b = io.BytesIO(); im.save(b, fmt); return f"data:image/{fmt.lower()};base64," + base64.b64encode(b.getvalue()).decode()
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")

# 1) 합치기(파이썬만)
a, b = tiny_glb(0.6, 1.0, 0.4), tiny_glb(2.0, 0.5, 1.0)
g, info = glbscene.merge([{"glb": a, "name": "chair", "pos": [1.0, 3.0, 0.0], "height": 0.9}, {"glb": b, "name": "table", "pos": [-1.0, 5.0, 0.2], "height": 0.75}])
G, BIN = glbscene.read(g)
assert [G["nodes"][i]["name"] for i in G["scenes"][0]["nodes"]] == ["chair", "table"] and len(G["meshes"]) == 2 and len(G["images"]) == 2
assert G["buffers"][0]["byteLength"] == len(BIN) and all(bv["byteOffset"] + bv["byteLength"] <= len(BIN) for bv in G["bufferViews"])
assert G["meshes"][1]["primitives"][0]["material"] == 1 and G["materials"][1]["pbrMetallicRoughness"]["baseColorTexture"]["index"] == 1 and G["textures"][1]["source"] == 1
img1 = G["images"][1]; bv = G["bufferViews"][img1["bufferView"]]; png = BIN[bv["byteOffset"]:bv["byteOffset"] + bv["byteLength"]]; assert png[:4] == b"\x89PNG"
for k, (name, pos, h) in enumerate((("chair", [1.0, 3.0, 0.0], 0.9), ("table", [-1.0, 5.0, 0.2], 0.75))):
    sub = {**G, "scenes": [{"nodes": [G["scenes"][0]["nodes"][k]]}], "scene": 0}
    lo, hi = glbscene.bounds(sub)
    assert abs((hi[1] - lo[1]) - h) < 1e-4, (name, lo, hi)                                  # 키
    assert abs(lo[1] - pos[2]) < 1e-4 and abs((lo[0] + hi[0]) / 2 - pos[0]) < 1e-4 and abs((lo[2] + hi[2]) / 2 + pos[1]) < 1e-4, (name, lo, hi)   # 바닥 가운데(Blender y → glTF -z)
assert info[0]["tris"] == 12 and abs(info[1]["size_m"][2] - 0.75) < 1e-3 and abs(info[1]["size_m"][0] - 3.0) < 1e-3
try: glbscene.read(b"nope"); assert False
except ValueError: pass
ok("merge: GLBs combined into one scene (buffers, textures, materials re-indexed), each object scaled to its height with its floor centre at its spot")

# 2) 자리 어림
W, H = 400, 300
D = np.zeros((H, W), np.float32); D[:, :200] = 0.9; D[:, 200:] = 0.2                        # 왼쪽 가까움, 오른쪽 멀리
m1 = np.zeros((H, W), bool); m1[100:250, 50:150] = True; m2 = np.zeros((H, W), bool); m2[150:200, 260:300] = True
L = glbscene.layout((W, H), D, [(1, (50, 100, 149, 249), m1), (2, (260, 150, 299, 199), m2)])
assert L[0]["dist"] < L[1]["dist"] and L[0]["pos"][0] < 0 < L[1]["pos"][0] and min(x["pos"][2] for x in L) == 0.0, L
assert L[0]["pos"][1] == L[0]["dist"] and L[0]["height"] > 0 and L[1]["near"] == 0.2
ok("layout: nearer (brighter depth) objects come closer, left/right follows the photo, the lowest object stands on z=0")

# 3) 작업 흐름
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True
class Cut:
    def cut(self, img, _):
        a = Image.new("L", img.size, 0); w, h = img.size; a.paste(255, (w // 4, h // 6, w * 3 // 4, h * 5 // 6)); o = img.convert("RGBA"); o.putalpha(a); return o
hub.rmbg_engine = lambda k: Cut()
photo = Image.new("RGB", (400, 300), (90, 120, 150)); photo.paste((200, 40, 40), (40, 80, 160, 280)); photo.paste((40, 200, 40), (250, 140, 320, 220))
j = job({"kind": "m3d", "op": "prep", "image": url(photo), "kind3": "object", "name": "room"}); assert j["state"] == "done", j
sid = j["m3d"]["id"]; d = hub.M3D_DIR / sid; assert j["m3d"]["scene"] == []
def mask(box, size=(400, 300)):
    m = Image.new("L", size, 0); m.paste(255, box); return url(m)
r = post("/api/m3d/scene", {"id": sid, "mask": mask((40, 80, 160, 280))}); assert len(r["scene"]) == 1 and r["scene"][0]["n"] == 1 and not r["scene"][0]["edge"], r
im = Image.open(io.BytesIO(urllib.request.urlopen(B + r["scene"][0]["url"]).read())); assert im.mode == "RGBA" and im.getpixel((im.width // 2, im.height // 2))[3] == 255 and im.getpixel((0, 0))[3] == 0
r = post("/api/m3d/scene", {"id": sid, "mask": mask((100, 50, 150, 75), (200, 150))}); assert len(r.get("scene") or []) == 2, r        # 작게 보낸 마스크도 원본 크기로 맞춰요
r = post("/api/m3d/scene", {"id": sid, "mask": mask((250, 140, 320, 220))}); assert [x["n"] for x in r["scene"]] == [1, 2, 3]
r = post("/api/m3d/scene", {"id": sid, "remove": 2}); assert [x["n"] for x in r["scene"]] == [1, 3] and not (d / "scene_obj_2.png").exists() and not (d / "scene_mask_2.png").exists()
assert "error" in post("/api/m3d/scene", {"id": sid, "mask": mask((0, 0, 3, 3))}) and "error" in post("/api/m3d/scene", {"id": sid, "mask": "data:image/png;base64,xx"})
r = post("/api/m3d/scene", {"id": sid, "mask": mask((0, 100, 60, 200))}); assert r["scene"][-1]["edge"]; post("/api/m3d/scene", {"id": sid, "remove": r["scene"][-1]["n"]})
for bad in (f"/m3d/{sid}/scene_mask_1.png",):
    try: urllib.request.urlopen(B + bad); assert False
    except urllib.error.HTTPError as e: assert e.code == 404
ok("scene objects: pick (cut-out with transparent background), remove, tiny/broken masks refused, cut at the photo edge flagged, masks not served")

j = job({"kind": "m3d", "op": "scene", "id": sid, "blender": ""}); assert j["state"] == "error" and "TRELLIS.2" in j["error"], j
touch("diffusion_models/trellis_2_int8_convrot.safetensors", "clip_vision/dino_v3_vit_l.safetensors", "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors")
n0 = len(SUBMITTED)
j = job({"kind": "m3d", "op": "scene", "id": sid, "blender": "", "seed": 5}); assert j["state"] == "done", j
graphs = SUBMITTED[n0:]; tg = [g for g in graphs if any(v["class_type"] == "Trellis2Conditioning" for v in g.values())]
assert len(tg) == 2 and [min(v["inputs"]["seed"] for v in g.values() if v["class_type"] == "KSampler") for g in tg] == [5, 15]
assert any(any(v["class_type"] == "DepthAnythingV2Preprocessor" or "Depth" in v["class_type"] for v in g.values()) for g in graphs) or (hub.DEPTH_DIR).is_dir()
glb, z = j["images"]; assert glb.endswith(".glb") and z.endswith(".zip") and "3D" in glb
G2, _ = glbscene.read(urllib.request.urlopen(B + glb).read()); assert [G2["nodes"][i]["name"] for i in G2["scenes"][0]["nodes"]] == ["object_1", "object_3"]
names = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(B + z).read())).namelist(); assert {"object_1.glb", "object_3.glb", "layout.json", "room_장면.glb"} <= set(names), names
lay = json.loads(zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(B + z).read())).read("layout.json")); assert "AI 추정값" in lay["note"] and len(lay["objects"]) == 2
st = j["m3d_stats"]["scene"]; assert len(st) == 2 and all(x["height"] > 0 and x["dist"] >= 2 for x in st) and "AI 어림값" in j["msg"]
assert any("Blender" not in w for w in j.get("warn") or [""]) and not list(d.glob("scene_*/")) and not list(d.glob("*.zip"))
side = json.loads((hub.OUT / "3D" / (glb.rsplit("/", 1)[1] + ".json")).read_text(encoding="utf-8")); assert side["engine"] == "TRELLIS.2 장면" and side["objects"] == 2
ok("scene build: one TRELLIS.2 run per object, merged scene GLB shown, zip has scene + per-object GLBs + layout.json, AI-estimate note")
n0 = len(SUBMITTED)
j = job({"kind": "m3d", "op": "scene", "id": sid, "blender": "", "fill": True, "fast": "on"}); assert j["state"] == "done", j
txt = " ".join(str(v["inputs"].get("prompt", "")) + str(v["inputs"].get("text", "")) for g in SUBMITTED[n0:] for v in g.values())
assert txt.count("hidden or missing part") == 2, txt[:300]
ok("fill hidden parts: one Qwen edit per object before 3D")
fb = BASE + "/test/fake_blender.py"; os.chmod(fb, 0o755); os.environ["BLENDER_EXE"] = fb
j = job({"kind": "m3d", "op": "scene", "id": sid, "blender": "on", "fmt_fbx": True, "fmt_obj": True}); assert j["state"] == "done" and not j.get("warn"), j
names = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(B + j["images"][1]).read())).namelist()
assert {"room_장면.blend", "room_장면.fbx", "room_장면.obj", "room_장면.glb", "object_1.glb", "layout.json"} <= set(names) and "result.json" not in names, names
assert j["m3d_stats"]["blender"]
ok("with Blender: .blend + FBX + OBJ of the whole scene in the zip")
r = post("/api/m3d/scene", {"id": sid, "clear": 1}); assert r["scene"] == [] and not list(d.glob("scene_obj_*.png"))
j = job({"kind": "m3d", "op": "scene", "id": sid}); assert j["state"] == "error" and "물체를 먼저" in j["error"], j
ok("clear all objects; building with none explains what to do")
print("ALL OK")
