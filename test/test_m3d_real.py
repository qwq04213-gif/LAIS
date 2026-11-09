"""3D 사진 붙이기 — 실제 사진으로(사용자 요청: 단순한 무늬가 아니라 실제 사람 사진으로, 얼굴만이 아니라 전체를).
우주비행사 사진(NASA, 퍼블릭 도메인 — scikit-image 에 들어 있음) → 실제 배경 지우기(u2netp) → 프로그램의 가장자리 손질
→ 실루엣을 부풀린 사람 모양 3D(두께 약 28cm) + 3D 엔진처럼 흐리고 바랜 텍스처 → 사진 붙이기·머리 전용 텍스처 → 앞·45°·뒤 확인."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import io, sys
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
from skimage import data
import glbscene, photoproj, bgremove
ok = lambda m: print("PASS", m)

src = Image.fromarray(data.astronaut())
cut = bgremove.Remover(BASE + "/rmbg-test", "fast").cut(src).convert("RGBA")
code = open(BASE + "/LocalAI-Studio/hub/server/27_m3d.py", encoding="utf-8").read()
ns = {"np": np, "Image": Image, "ImageFilter": ImageFilter}; exec(code[code.index("def m3d_defringe"):code.index("def m3d_glb")], ns)
cut = ns["m3d_defringe"](cut)
W, H = cut.size
alpha = np.asarray(cut.getchannel("A")).astype(np.float32) / 255
ok("real photo cut out with u2netp and defringed")

# 사람 모양 3D: 실루엣 격자, 두께 = √(가장자리까지 거리), 앞(왼쪽 반)·뒤(오른쪽 반) 텍스처
step = 2
gx, gy = np.meshgrid(np.arange(0, W, step), np.arange(0, H, step))
inside = alpha[gy, gx] > 0.5
dist = ndimage.distance_transform_edt(alpha > 0.5)[gy, gx]
sc = 1.7 / H
depth = 0.14 * np.sqrt(dist / max(dist.max(), 1))
idx = -np.ones(inside.shape, int); idx[inside] = np.arange(inside.sum())
q = inside[:-1, :-1] & inside[1:, :-1] & inside[:-1, 1:] & inside[1:, 1:]
a, b, c, d = idx[:-1, :-1][q], idx[:-1, 1:][q], idx[1:, :-1][q], idx[1:, 1:][q]
Ff = np.concatenate([np.stack([a, c, b], 1), np.stack([b, c, d], 1)])
base_xy = np.stack([(gx - W / 2) * sc, -(gy - H / 2) * sc], -1)[inside]
n = len(base_xy)
P = np.concatenate([np.c_[base_xy, depth[inside]], np.c_[base_xy, -depth[inside]]])
F = np.concatenate([Ff, Ff[:, ::-1] + n])
u, v = gx[inside] / W, gy[inside] / H
UV = np.concatenate([np.stack([0.02 + 0.46 * u, 0.02 + 0.96 * v], 1), np.stack([0.98 - 0.46 * u, 0.02 + 0.96 * v], 1)])
fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
N = np.zeros_like(P)
for k in range(3): np.add.at(N, F[:, k], fn)
N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
TS = 2048
low = cut.convert("RGB").resize((W // 10, H // 10), Image.BILINEAR).resize((W, H), Image.BILINEAR)
low = np.asarray(low).astype(np.float32); low = (0.75 * low + 0.25 * low.mean(2, keepdims=True)) * 0.85
tp, tf, b0, b1 = photoproj.raster(UV * TS, F, TS, TS)
X = P[F[tf, 0]] * b0[:, None] + P[F[tf, 1]] * b1[:, None] + P[F[tf, 2]] * (1 - b0 - b1)[:, None]
col = photoproj._sample(low, X[:, 0] / sc + W / 2, -X[:, 1] / sc + H / 2); col[X[:, 2] < 0] *= 0.7
T = np.full((TS * TS, 3), 90.0); T[tp] = col


def glb_of(ims):
    pngs = []
    for im in ims:
        bb = io.BytesIO(); im.save(bb, "PNG"); pngs.append(bb.getvalue())
    parts = [P.astype(np.float32).tobytes(), UV.astype(np.float32).tobytes(), F.astype(np.uint32).tobytes(), N.astype(np.float32).tobytes()] + pngs
    bvs, blob = [], b""
    for x in parts:
        blob += b"\0" * (-len(blob) % 4); bvs.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(x)}); blob += x
    mat = {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicRoughnessTexture": {"index": 2}}, "normalTexture": {"index": 1}, "occlusionTexture": {"index": 2}}
    g = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(blob)}], "bufferViews": bvs,
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(P), "type": "VEC3", "min": P.min(0).tolist(), "max": P.max(0).tolist()},
                       {"bufferView": 1, "componentType": 5126, "count": len(UV), "type": "VEC2"},
                       {"bufferView": 2, "componentType": 5125, "count": F.size, "type": "SCALAR"},
                       {"bufferView": 3, "componentType": 5126, "count": len(N), "type": "VEC3"}],
         "images": [{"bufferView": 4 + i, "mimeType": "image/png"} for i in range(len(pngs))], "textures": [{"source": i} for i in range(len(pngs))],
         "materials": [mat], "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1, "NORMAL": 3}, "indices": 2, "material": 0}]}],
         "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
    return glbscene.write(g, blob)


glb = glb_of([Image.fromarray(T.reshape(TS, TS, 3).astype(np.uint8)), Image.new("RGB", (256, 256), (128, 128, 255)), Image.new("RGB", (512, 512), (170, 240, 0))])


def render(gl, deg, S=1000):
    g, bb = glbscene.read(gl); an = np.radians(deg); R = np.array([[np.cos(an), 0, np.sin(an)], [0, 1, 0], [-np.sin(an), 0, np.cos(an)]])
    allP, allF, prims, off = [], [], [], 0
    for pr in g["meshes"][0]["primitives"]:
        at = pr["attributes"]; Pp = photoproj._acc(g, bb, at["POSITION"]) @ R.T; Fp = photoproj._acc(g, bb, pr["indices"]).astype(int).reshape(-1, 3)
        mt = g["materials"][pr["material"]]; Tt = np.asarray(photoproj._img_of(g, bb, mt["pbrMetallicRoughness"]["baseColorTexture"]["index"]).convert("RGB")).astype(np.float32)
        prims.append((photoproj._acc(g, bb, at["TEXCOORD_0"]), Fp, Tt)); allP.append(Pp); allF.append(Fp + off); off += len(Pp)
    PP, FF = np.concatenate(allP), np.concatenate(allF)
    k = S / (H * sc); pix, fid, c0, c1 = photoproj.raster(np.stack([S / 2 + k * PP[:, 0], S / 2 - k * PP[:, 1]], 1), FF, S, S, -PP[:, 2])
    out = np.zeros((S * S, 3), np.float32); st = np.cumsum([0] + [len(p[1]) for p in prims]); pid = np.full(S * S, -1)
    for i, (UVp, Fp, Tt) in enumerate(prims):
        m = (fid >= st[i]) & (fid < st[i + 1]); f = fid[m] - st[i]; cc = np.stack([c0[m], c1[m], 1 - c0[m] - c1[m]], 1)
        uv = (UVp[Fp[f]] * cc[..., None]).sum(1)
        out[pix[m]] = photoproj._sample(Tt, (uv[:, 0] % 1.0) * Tt.shape[1], uv[:, 1] * Tt.shape[0]); pid[pix[m]] = i
    return out.reshape(S, S, 3), pid.reshape(S, S)


face = (185, 75, 300, 200)                                                        # 얼굴 상자(이마~턱, MediaPipe 얼굴 윤곽과 같은 범위)
one, i1 = photoproj.project(glb, cut)
two, i2 = photoproj.project(glb, cut, head=face, head_size=4096)
assert i1["iou"] > 0.95 and i2.get("head") and not i2.get("head_error"), (i1, i2)
S = 1000; k = S / H
ph = np.asarray(cut.convert("RGB").resize((S, S), Image.LANCZOS)).astype(np.float32)
fy0, fy1, fx0, fx1 = int(face[1] * k), int(face[3] * k), int(face[0] * k), int(face[2] * k)
r0, _ = render(glb, 0); r1, _ = render(one, 0); r2, pid = render(two, 0)
am = np.asarray(cut.getchannel("A").resize((S, S), Image.BILINEAR)) > 200            # 물체 안쪽만 비교해요
err = lambda r, sl=(slice(fy0, fy1), slice(fx0, fx1)): float(np.abs(r[sl] - ph[sl])[am[sl]].mean())
e0, e1, e2 = err(r0), err(r1), err(r2)
assert e1 < e0 * 0.5 and e2 < e0 * 0.5 and abs(e2 - e1) < 3, (e0, e1, e2)
ok(f"face vs photo: engine-like {e0:.1f} → photo {e1:.1f} / with head texture {e2:.1f}")
body = (slice(int(300 * k), int(480 * k)), slice(int(60 * k), int(330 * k)))
assert err(r2, body) < err(r0, body) * 0.6, (err(r0, body), err(r2, body))
ok("body (suit, patches) also follows the photo")

# 점박이·얼룩: 머리 텍스처를 쓴 결과가 한 장 결과와 크게 다른 화소(앞·45°·뒤)
for deg in (0, 45, 180):
    a_, _ = render(one, deg); b_, _ = render(two, deg)
    bad = int((np.abs(a_ - b_).sum(2) > 120).sum())
    assert bad < 60, (deg, bad)
ok("no speckles/stains from the head texture seen from the front, 45° and the back")

# 머리 전용 텍스처: 얼굴(눈 높이 앞쪽)이 텍스처의 가운데 넓은 자리를 써요
g, bb = glbscene.read(two); hm = g["materials"][1]
ht = np.asarray(photoproj._img_of(g, bb, hm["pbrMetallicRoughness"]["baseColorTexture"]["index"]).convert("RGB")).astype(np.float32)
mid = ht[ht.shape[0] // 4: ht.shape[0] * 3 // 4, ht.shape[1] // 4: ht.shape[1] * 3 // 4]
skin = photoproj._skin(mid.reshape(-1, 3)).mean()
assert skin > 0.4, skin
fm = am[fy0:fy1, fx0:fx1]
assert (pid[fy0:fy1, fx0:fx1][fm] == 1).mean() > 0.8 and (pid[int(400 * k):, :] == 1).mean() < 0.01, ((pid[fy0:fy1, fx0:fx1][fm] == 1).mean(), (pid[int(400 * k):, :] == 1).mean())
ok("head texture gives the middle of the texture to the face; shoulders/body stay on the body texture")
print("ALL OK")
