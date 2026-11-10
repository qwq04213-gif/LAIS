"""4.6.1(4.7 부터 기본 꺼짐 — 켰을 때만): 3D 얼굴 맞추기 — 3D 엔진이 만든 얼굴과 사진 속 얼굴의 각도·기울기가 다를 때(고개 돌린 사진) 사진 얼굴을 3D 얼굴 자리로 휘어 붙이기.
실제 얼굴 사진(우주비행사, NASA 퍼블릭 도메인)을 머리에 입힌 가짜 3D 로: 사진은 머리를 돌리고 기울여 찍고, 엔진 텍스처는 흐리게.
그리고 노멀맵: 엔진이 준 접선(TANGENT)으로 읽어 머리 텍스처로 옮기고, 머리에도 접선을 적어요(화면에서 검은 얼룩·흰 반점이 생기던 문제)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import io, sys
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import numpy as np
from PIL import Image, ImageFilter
from skimage import data as _sd
import glbscene, photoproj
ok = lambda m: print("PASS", m)
FACE = np.asarray(Image.fromarray(_sd.astronaut()).crop((150, 30, 340, 250)).resize((380, 440), Image.LANCZOS)).astype(np.float64)


def pattern(X):                                   # 실제 얼굴 사진을 머리 앞쪽에(머리 기준 좌표), 몸은 파랑
    x, y, z = X[:, 0], X[:, 1], X[:, 2]
    c = np.tile(np.array([[70.0, 60, 50]]), (len(x), 1))
    head = y > 1.42
    fx = (x + 0.095) / 0.19 * FACE.shape[1]; fy = (1.69 - y) / 0.22 * FACE.shape[0]
    m = head & (z > 0) & (fx >= 0) & (fx < FACE.shape[1]) & (fy >= 0) & (fy < FACE.shape[0])
    c[m] = photoproj._sample(FACE, fx[m], fy[m])
    c[~head] = (60, 90, 170)
    return c


def mesh():
    P, UV, F = [], [], []
    def grid(fn, nu, nv, u0, v0, du, dv):
        base = len(P)
        for j in range(nv + 1):
            for i in range(nu + 1):
                s, t = i / nu, j / nv; P.append(fn(s, t)); UV.append((u0 + du * s, v0 + dv * t))
        for j in range(nv):
            for i in range(nu):
                a = base + j * (nu + 1) + i; F.extend([(a, a + nu + 1, a + 1), (a + 1, a + nu + 1, a + nu + 2)])
    R = 0.12
    grid(lambda s, t: (R * np.sin(t * np.pi) * np.sin(s * 2 * np.pi), 1.55 + R * np.cos(t * np.pi), R * np.sin(t * np.pi) * np.cos(s * 2 * np.pi)), 160, 80, 0.01, 0.01, 0.24, 0.24)
    grid(lambda s, t: (0.2 * np.sin(s * 2 * np.pi), 1.43 - 1.43 * t, 0.2 * np.cos(s * 2 * np.pi)), 120, 60, 0.3, 0.01, 0.69, 0.98)
    P, UV, F = np.array(P, float), np.array(UV, float), np.array(F)
    N = P - np.where(P[:, 1:2] > 1.42, [[0, 1.55, 0]], P * [0, 1, 0]); N /= np.linalg.norm(N, axis=1, keepdims=True)
    return P, UV, F, N


def bake(P, UV, F, S):
    tp, tf, b0, b1 = photoproj.raster(UV * S, F, S, S)
    X = P[F[tf, 0]] * b0[:, None] + P[F[tf, 1]] * b1[:, None] + P[F[tf, 2]] * (1 - b0 - b1)[:, None]
    T = np.zeros((S * S, 3)); T[:] = (128, 128, 128); T[tp] = pattern(X)
    return Image.fromarray(T.reshape(S, S, 3).astype(np.uint8))


def glb_of(P, UV, F, N, ims, TG=None):
    pngs = []
    for im in ims:
        b = io.BytesIO(); im.save(b, "PNG"); pngs.append(b.getvalue())
    parts = [P.astype(np.float32).tobytes(), UV.astype(np.float32).tobytes(), F.astype(np.uint32).tobytes(), N.astype(np.float32).tobytes()] + pngs + ([TG.astype(np.float32).tobytes()] if TG is not None else [])
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
    if TG is not None:
        g["accessors"].append({"bufferView": len(bvs) - 1, "componentType": 5126, "count": len(TG), "type": "VEC4"})
        g["meshes"][0]["primitives"][0]["attributes"]["TANGENT"] = len(g["accessors"]) - 1
    return glbscene.write(g, blob)


S, K = 1200, 1200 * 0.45 / 0.85
def proj(P): return np.stack([S / 2 + K * P[:, 0], S / 2 - K * (P[:, 1] - 0.8)], 1), -P[:, 2]


def shoot(P, F):
    xy, z = proj(P); pix, fid, b0, b1 = photoproj.raster(xy, F, S, S, z)
    X = P[F[fid, 0]] * b0[:, None] + P[F[fid, 1]] * b1[:, None] + P[F[fid, 2]] * (1 - b0 - b1)[:, None]
    out = np.zeros((S * S, 4)); out[pix, :3] = pattern(X); out[pix, 3] = 255
    return Image.fromarray(out.reshape(S, S, 4).astype(np.uint8), "RGBA")


def prims_of(glb):
    g, b = glbscene.read(glb); out = []
    for pr in g["meshes"][0]["primitives"]:
        at = pr["attributes"]; mat = g["materials"][pr["material"]]
        out.append({"P": photoproj._acc(g, b, at["POSITION"]), "UV": photoproj._acc(g, b, at["TEXCOORD_0"]), "N": photoproj._acc(g, b, at["NORMAL"]),
                    "F": photoproj._acc(g, b, pr["indices"]).astype(int).reshape(-1, 3), "mat": mat,
                    "T": np.asarray(photoproj._img_of(g, b, mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]).convert("RGB")).astype(float),
                    "NM": np.asarray(photoproj._img_of(g, b, mat["normalTexture"]["index"]).convert("RGB")).astype(float)})
    return g, out


def render(glb):
    g, ps = prims_of(glb); allP, allF, starts, off, fo = [], [], [0], 0, 0
    for p in ps:
        allP.append(p["P"]); allF.append(p["F"] + off); off += len(p["P"]); fo += len(p["F"]); starts.append(fo)
    P, F = np.concatenate(allP), np.concatenate(allF)
    xy, z = proj(P); pix, fid, b0, b1 = photoproj.raster(xy, F, S, S, z); out = np.zeros((S * S, 3))
    for k, p in enumerate(ps):
        m = (fid >= starts[k]) & (fid < starts[k + 1]); f = fid[m] - starts[k]
        uv = p["UV"][p["F"][f, 0]] * b0[m, None] + p["UV"][p["F"][f, 1]] * b1[m, None] + p["UV"][p["F"][f, 2]] * (1 - b0[m] - b1[m])[:, None]
        out[pix[m]] = photoproj._sample(p["T"], (uv[:, 0] % 1.0) * p["T"].shape[1], uv[:, 1] * p["T"].shape[0])
    return out.reshape(S, S, 3)




def shoot(Pv, F, Pl):                             # 사진: Pv 모양으로 찍되 무늬는 원래 자리(Pl) 기준 — 머리를 돌린 사람
    xy, z = proj(Pv); pix, fid, b0, b1 = photoproj.raster(xy, F, S, S, z)
    X = Pl[F[fid, 0]] * b0[:, None] + Pl[F[fid, 1]] * b1[:, None] + Pl[F[fid, 2]] * (1 - b0 - b1)[:, None]
    out = np.zeros((S * S, 4)); out[pix, :3] = pattern(X); out[pix, 3] = 255
    return Image.fromarray(out.reshape(S, S, 4).astype(np.uint8), "RGBA")


P, UV, F, N = mesh()
hd = P[:, 1] > 1.42; c0 = np.array([0, 1.5, 0])
nm = Image.new("RGB", (512, 512), (128, 128, 255)); orm = Image.new("RGB", (512, 512), (150, 230, 0))
glb = glb_of(P, UV, F, N, [bake(P, UV, F, 512).filter(ImageFilter.GaussianBlur(2)), nm, orm])      # 엔진 색: 흐림
rt = render(glb_of(P, UV, F, N, [bake(P, UV, F, 2048), nm, orm]))                                  # 정답: 3D 얼굴 자리에 선명한 얼굴
fb = (int(S / 2 - 0.1 * K), int(S / 2 - 0.87 * K), int(S / 2 + 0.1 * K), int(S / 2 - 0.65 * K)); x0, y0, x1, y1 = fb
err = lambda gl: float(np.abs(render(gl)[y0:y1, x0:x1] - rt[y0:y1, x0:x1]).mean())
for yaw, roll in ((20, 8), (-30, -10), (0, 0)):
    a1, a2 = np.radians(yaw), np.radians(roll)
    R = np.array([[np.cos(a2), -np.sin(a2), 0], [np.sin(a2), np.cos(a2), 0], [0, 0, 1]]) @ np.array([[np.cos(a1), 0, np.sin(a1)], [0, 1, 0], [-np.sin(a1), 0, np.cos(a1)]])
    Pr = P.copy(); Pr[hd] = (P[hd] - c0) @ R.T + c0
    photo = shoot(Pr, F, P)
    plain, i0 = photoproj.project(glb, photo, head=fb, head_size=1024)                  # 기본: 휘지 않아요(원본 얼굴 그대로)
    assert i0.get("align") is None, i0.get("align")
    al, info = photoproj.project(glb, photo, head=fb, head_size=1024, align=True)       # [얼굴 각도 맞추기]를 켰을 때
    e0, e1 = err(plain), err(al)
    fm = photoproj.engine_match(glb, photo, head=fb)["face"]                          # 4.7: 단계 비교의 '얼굴 자리 일치'
    assert (fm > 0.7) if not (yaw or roll) else (fm < 0.5), (yaw, roll, fm)
    if yaw or roll:
        assert info["align"]["ok"] and e1 < e0 * 0.7, (yaw, roll, info["align"], e0, e1)
    else:
        assert not info["align"]["ok"] and abs(e1 - e0) < 0.5, (info["align"], e0, e1)
    ok(f"head turned {yaw}° / tilted {roll}°: face match {fm:.2f}, face error {e0:.1f} → aligned {e1:.1f} ({'bent' if info['align']['ok'] else 'left as is'})")

# 노멀맵: 엔진이 준 접선(TANGENT)이 우리가 계산하는 방향과 반대(손잡이 w=-1 쪽)인 3D — 엔진 방향으로 읽어야 해요
e1_, e2_ = P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]
TGv = np.zeros((len(P), 3))
Tu, Bu = photoproj._frames(P[F], UV[F], None)
for k in range(3): np.add.at(TGv, F[:, k], Tu)
TGv -= N * (TGv * N).sum(1, keepdims=True); TGv /= np.maximum(np.linalg.norm(TGv, axis=1, keepdims=True), 1e-12)
Bours = np.zeros((len(P), 3))
for k in range(3): np.add.at(Bours, F[:, k], Bu)
w = -np.sign((np.cross(N, TGv) * Bours).sum(1)); w[w == 0] = 1          # 엔진: B = cross(N,T)·w 가 우리 B 와 반대
TG = np.c_[TGv, w]
yy, xx = np.mgrid[0:512, 0:512]
bump = np.stack([0.45 * np.sin(xx / 9.0), 0.45 * np.cos(yy / 7.0)], -1)                              # 굴곡이 곳곳에 있는 노멀맵
nmap = np.concatenate([bump, np.sqrt(np.clip(1 - (bump ** 2).sum(-1, keepdims=True), 0, 1))], -1)
nmi = Image.fromarray(((nmap + 1) * 127.5).clip(0, 255).astype(np.uint8))
g_src = glb_of(P, UV, F, N, [bake(P, UV, F, 512), nmi, orm], TG)
out, info = photoproj.project(g_src, shoot(P, F, P), head=fb, head_size=1024)
g, b = glbscene.read(out); hp = g["meshes"][0]["primitives"][1]; assert "TANGENT" in hp["attributes"], hp
def world(P_, UV_, N_, TG_, F_, nm_, f, c):
    n = (N_[F_[f]] * c[..., None]).sum(1); n /= np.linalg.norm(n, axis=1, keepdims=True)
    uv = (UV_[F_[f]] * c[..., None]).sum(1); ns = photoproj._sample(nm_, (uv[:, 0] % 1) * nm_.shape[1], uv[:, 1] * nm_.shape[0]) / 127.5 - 1
    T = (TG_[F_[f], :3] * c[..., None]).sum(1); T -= n * (T * n).sum(1, keepdims=True); T /= np.linalg.norm(T, axis=1, keepdims=True)
    B = np.cross(n, T) * np.where(TG_[F_[f][:, 0], 3:4] < 0, -1, 1)
    v = ns[:, 0:1] * T + ns[:, 1:2] * B + ns[:, 2:3] * n
    return v / np.linalg.norm(v, axis=1, keepdims=True), (P_[F_[f]] * c[..., None]).sum(1)
A = lambda i: photoproj._acc(g, b, hp["attributes"][i])
hF = photoproj._acc(g, b, hp["indices"]).astype(int).reshape(-1, 3)
hnm = np.asarray(photoproj._img_of(g, b, g["materials"][hp["material"]]["normalTexture"]["index"]).convert("RGB")).astype(float)
rs = np.random.RandomState(2); f = rs.choice(len(hF), 400, replace=False); c = np.full((400, 3), 1 / 3)
wh, X = world(A("POSITION"), A("TEXCOORD_0"), A("NORMAL"), A("TANGENT"), hF, hnm, f, c)
cen = P[F].mean(1); near = np.array([np.argmin(((cen - x) ** 2).sum(1)) for x in X])
wo, _ = world(P, UV, N, TG, F, np.asarray(nmi).astype(float), near, c)
ang = np.degrees(np.arccos(np.clip((wh * wo).sum(1), -1, 1)))
assert np.median(ang) < 6 and np.percentile(ang, 90) < 15, (np.median(ang), np.percentile(ang, 90))
ok(f"normal map read with the engine's own tangents and written with tangents on the head (median {np.median(ang):.1f}° off)")
print("ALL OK")
