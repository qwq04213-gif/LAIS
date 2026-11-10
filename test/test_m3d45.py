"""4.5: 3D 얼굴·질감 — 텍스처 밉맵 켜기, 사진 점검에 얼굴 크기, 가장자리 검은 테두리 막기(색 채우기·경계 또렷하게),
사진 붙이기: 색감 맞추기·사진 붙인 곳 그늘 줄이기·피부 거칠기, 결과 화면에 붙이기 결과."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17982"
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import numpy as np
import glbscene, photoproj
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


def with_orm(glb, ao=100, rough=255, metal=128, size=256):
    """GLB 에 그늘(AO)·거칠기·금속 그림(한 장에 R·G·B) 붙이기 — ComfyUI 결과처럼"""
    g, b = glbscene.read(glb)
    bi = io.BytesIO(); Image.new("RGB", (size, size), (ao, rough, metal)).save(bi, "PNG"); png = bi.getvalue()
    b = bytes(b) + b"\0" * (-len(b) % 4); off = len(b); b += png
    g["bufferViews"].append({"buffer": 0, "byteOffset": off, "byteLength": len(png)}); g["buffers"][0]["byteLength"] = len(b)
    g["images"].append({"bufferView": len(g["bufferViews"]) - 1, "mimeType": "image/png"}); g["textures"].append({"source": len(g["images"]) - 1})
    mt = g["materials"][0]; ti = len(g["textures"]) - 1
    mt["pbrMetallicRoughness"]["metallicRoughnessTexture"] = {"index": ti}; mt["occlusionTexture"] = {"index": ti}
    return glbscene.write(g, b)


def pic(g, b, tex_index):
    im = g["images"][g["textures"][tex_index]["source"]]; v = g["bufferViews"][im["bufferView"]]
    return np.asarray(Image.open(io.BytesIO(b[v["byteOffset"]:v["byteOffset"] + v["byteLength"]])).convert("RGB")).astype(int)


# 1) 밉맵: 텍스처가 작게 보일 때 깨지지 않게(게임 엔진 기본값)
g0 = uv_glb(); g, _ = glbscene.read(photoproj.fix_samplers(g0))
assert g["samplers"] == [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}] and all(t["sampler"] == 0 for t in g["textures"])
assert photoproj.fix_samplers(b"not a glb") == b"not a glb" and photoproj.fix_samplers(tiny_glb()) != b""
ok("texture mipmaps on (LINEAR_MIPMAP_LINEAR); non-GLB data untouched")

# 2) 가장자리 손질: 반투명 가장자리의 배경색(초록)을 물체색(빨강)으로, 경계는 또렷하게
im = Image.new("RGBA", (200, 200), (0, 255, 0, 0)); a = np.zeros((200, 200), np.uint8); a[50:150, 50:150] = 255
a[48:50, 50:150] = 120; a[150:152, 50:150] = 60                                        # 반투명 가장자리
rgb = np.zeros((200, 200, 3), np.uint8); rgb[...] = (0, 255, 0); rgb[50:150, 50:150] = (220, 30, 30); rgb[48:50, 50:150] = (110, 140, 15)
im = Image.fromarray(np.dstack([rgb, a]), "RGBA")
o = np.asarray(hub.m3d_defringe(im)).astype(int)
assert np.abs(o[49, 100, :3] - (220, 30, 30)).max() <= 3 and o[100, 100, 3] == 255 and o[0, 0, 3] == 0, o[49, 100]
assert o[150, 100, 3] == 0 and 0 < o[49, 100, 3] < 255                                    # 아주 옅은 가장자리는 투명, 반쯤은 그대로 반쯤
ok("defringe: half-transparent edge takes the object colour (no background/black halo), faint edge dropped")

# 3) 색감 맞추기: 엔진 색이 어둡고 푸르면 사진 쪽으로
T = np.full((64, 64, 3), (90, 80, 120), np.float32); tp = np.arange(64 * 64); w = np.ones((len(tp), 1), np.float32)
col = np.tile(np.array([[200, 150, 130]], np.float32), (len(tp), 1)) + np.random.RandomState(0).rand(len(tp), 3).astype(np.float32) * 10
T2 = photoproj._color_match(T, tp, w, col)
assert np.abs(T2.reshape(-1, 3).mean(0) - (90 + 0.8 * 40, 80 + 0.8 * 40, 120 + 0.8 * 15)).max() < 2      # 차이는 한 번에 ±40 까지만
assert photoproj._skin(np.array([[250, 225, 215], [230, 180, 150], [40, 90, 200], [20, 20, 20]], np.float32)).tolist() == [1, 1, 0, 0]
ok("colour match pulls the engine texture toward the photo (limited), skin tone detection")

# 4) 3D 만들기: 사진 붙인 곳 그늘(AO) 줄이고, 피부는 거칠기 0.5·금속 0, 뒤는 그대로 + 결과 화면용 정보
S = 1200
photo = Image.new("RGB", (S, S), (128, 128, 128)); photo.paste((235, 190, 165), (0, 0, S // 2, S)); photo.paste((40, 90, 200), (S // 2, 0, S, S))
photo.paste((235, 190, 165), (690, 290, 830, 430))                                        # 얼굴 자리(피부색)   # 왼쪽 피부색, 오른쪽 파랑 옷
TX = Image.new("RGB", (512, 512), (40, 40, 160)); TX.paste((200, 160, 140), (0, 0, 85, 256)); TX.paste((50, 80, 170), (85, 0, 171, 256))
STATE["glb"] = with_orm(uv_glb(0.75, 1.0, 0.5, TX, n=16))
j = job({"kind": "m3d", "op": "prep", "image": url(photo), "kind3": "character", "name": "hero"}); sid = j["m3d"]["id"]
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done", j
ph = j["m3d_stats"]["photo"]; assert ph["done"] is True and "그대로 붙였어요" in ph["text"], ph
G, BIN = glbscene.read(urllib.request.urlopen(B + j["images"][0]).read())
assert all(s["minFilter"] == 9987 for s in G["samplers"])
orm = pic(G, BIN, G["materials"][0]["occlusionTexture"]["index"])
fx, fy = lambda x: int((0.05 + 0.9 * (x - 300) / 600) / 3 * 256), lambda y: int((0.05 + 0.9 * (y - 200) / 800) / 2 * 256)
skin, cloth, back = orm[fy(600), fx(450)], orm[fy(600), fx(750)], orm[192, 128]
assert skin[0] > 230 and abs(skin[1] - 128) <= 6 and skin[2] <= 6, skin                   # 그늘 거의 없음 · 거칠기 0.5 · 금속 0
assert cloth[0] > 230 and cloth[1] > 245 and abs(cloth[2] - 128) <= 3, cloth              # 옷: 그늘만 줄이고 재질은 그대로
assert back.tolist() == [100, 255, 128], back                                             # 사진이 안 닿는 뒤는 그대로
th = urllib.request.urlopen(B + j["images"][0].replace("/out/", "/thumb/")).read(); assert th[:3] == b"\xff\xd8\xff" and Image.open(io.BytesIO(th)).size == (320, 320)
assert "/3D/" in j["images"][0] and hub.JOB_RX.match(j["images"][0].split("/")[3]) and j["images"][0].split("/")[3].endswith("-hero")   # 작업 한 번 = 폴더 하나(3D 이름 붙임)
ok("output saved in its own job folder; gallery thumbnail of the 3D model is drawn automatically")
ok("photo-covered area: baked AO mostly removed (photo has real shading), skin gets roughness 0.5/metal 0, cloth material kept, back untouched")

# 4-2) 엔진이 옷을 반들반들(거칠기 0.24)하게 칠했으면 사진 붙인 옷은 0.75 이상으로(검은 바지 번들거림·신발 비침), 피부는 0.5
STATE["glb"] = with_orm(uv_glb(0.75, 1.0, 0.5, TX, n=16), rough=60)
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done", j
G, BIN = glbscene.read(urllib.request.urlopen(B + j["images"][0]).read()); orm = pic(G, BIN, G["materials"][0]["occlusionTexture"]["index"])
skin, cloth, back = orm[fy(600), fx(450)], orm[fy(600), fx(750)], orm[192, 128]
assert cloth[1] >= 188 and abs(skin[1] - 128) <= 6 and back[1] == 60, (skin, cloth, back)
ok("glossy engine roughness on photo-covered cloth raised to fabric level; skin 0.5; back untouched")

# 5) 건너뛰면 결과 화면에 이유
STATE["glb"] = uv_glb(2.0, 0.3, 0.5, TX, n=8)
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); ph = j["m3d_stats"]["photo"]
assert ph["done"] is False and "겹치지 않아" in ph["text"] and "%" in ph["text"], ph
ok("skipped photo projection shows the reason on the result")

# 6) 사진 점검에 얼굴 크기(얼굴 찾기 모델이 있고 이미지 엔진이 켜져 있을 때)
touch("detection/mediapipe_face_fp32.safetensors")
STATE["face_box"] = ((S, S), (700, 300, 820, 420))
j = job({"kind": "m3d", "op": "prep", "image": url(photo), "kind3": "character", "name": "hero2"}); st = j["m3d"]["stats"]
assert st["face"] == 120 and st["face_rec"] == 512 and any("얼굴이 120px" in c["text"] for c in j["m3d"]["checks"]), (st, j["m3d"]["checks"])
touch("upscale_models/RealESRGAN_x4plus.pth"); sid2 = j["m3d"]["id"]
j = job({"kind": "m3d", "op": "enlarge", "id": sid2}); st = j["m3d"]["stats"]
assert j["state"] == "done" and st["face"] > 120 and st["face_box"][0] > 700, st
STATE["face_box"] = ((S, S), (300, 200, 1000, 1000))
j = job({"kind": "m3d", "op": "prep", "image": url(photo), "kind3": "character"}); assert not any("얼굴이" in c["text"] for c in j["m3d"]["checks"])
ok("photo check shows face size (warns under 512px), enlarged with the photo")
print("ALL OK")
