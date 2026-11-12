"""4.9.4: 3D 얼굴 품질 — 둥근 머리(타원체)에 실제 얼굴 사진(NASA 우주비행사, 퍼블릭 도메인)을 입혀서 확인해요.
'정답' = 선명한 사진을 그대로 입힌 머리, '엔진 결과' = 같은 머리에 흐리고 바래고 옆으로 갈수록 어두운 색.
사진 붙이기 뒤 30°·50° 옆에서 봤을 때 ① 볼 옆까지 사진처럼 선명한지 ② 사진과 엔진 색의 경계가 톱니처럼 깨지지 않는지
③ 사진이 닿지 않는 옆머리 색이 사진 색감을 이어받는지. 실제 3D 엔진 결과로는 확인하지 못했어요(미검증)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import io, os, sys
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import numpy as np
from PIL import Image, ImageFilter
from skimage import data
import glbscene, photoproj
ok = lambda m: print("PASS", m)
OUT = os.environ.get("FACE49_OUT")

# 실제 얼굴 사진: 얼굴 둘레를 잘라 1024 로(시험용 확대)
src = Image.fromarray(data.astronaut()).crop((105, 25, 385, 305)).resize((1024, 1024), Image.LANCZOS)
S = 1024
# 둥근 머리: 타원체(가로 0.085 · 세로 0.115 · 앞뒤 0.095 m), 매끈한 정점 방향
NU, NV = 160, 120
th, ph = np.meshgrid(np.linspace(-np.pi, np.pi, NU + 1), np.linspace(0.02, np.pi - 0.02, NV + 1))
A = np.array([0.085, 0.115, 0.095])
D = np.stack([np.sin(ph) * np.sin(th), np.cos(ph), np.sin(ph) * np.cos(th)], -1).reshape(-1, 3)
B = np.array([0.13, 0.07, 0.07])                         # 머리 아래 어깨(몸) — 머리만 있으면 '머리 고르기'가 안 돼요
P = np.concatenate([D * A + [0, 1.6, 0], D * B + [0, 1.44, 0]])
N = np.concatenate([D / A, D / B]); N /= np.linalg.norm(N, axis=1, keepdims=True)
uv0 = np.stack([(th / (2 * np.pi) + 0.5).ravel() * 0.96 + 0.02, (ph / np.pi).ravel() * 0.96 + 0.02], 1)
UV = np.concatenate([uv0 * [1, 0.5], uv0 * [1, 0.5] + [0, 0.5]])
i = np.arange(NU * NV).reshape(NV, NU); r, c = np.divmod(i, NU); a = r * (NU + 1) + c
F = np.concatenate([np.stack([a, a + NU + 1, a + 1], -1).reshape(-1, 3), np.stack([a + 1, a + NU + 1, a + NU + 2], -1).reshape(-1, 3)])
F = np.concatenate([F, F + len(D)])
FRAME, CY = 0.38, 1.555                                  # 사진에 담기는 높이(m)와 가운데
K = S / FRAME
px_of = lambda X: (S / 2 + K * X[:, 0], S / 2 - K * (X[:, 1] - CY))
sharp = np.asarray(src).astype(np.float32)
soft_src = np.asarray(src.filter(ImageFilter.GaussianBlur(9))).astype(np.float32)
TS = 2048
tp, tf, b0, b1 = photoproj.raster(UV * TS, F, TS, TS)
bc = np.stack([b0, b1, 1 - b0 - b1], 1)
X = (P[F[tf]] * bc[..., None]).sum(1); Nt = (N[F[tf]] * bc[..., None]).sum(1)
sx, sy = px_of(X)
true_c = photoproj._sample(sharp, sx, sy)
eng_c = photoproj._sample(soft_src, sx, sy)
eng_c = (0.7 * eng_c + 0.3 * eng_c.mean(1, keepdims=True)) * (0.55 + 0.4 * np.clip(Nt[:, 2:3], 0, 1))      # 바래고, 옆으로 갈수록 어둡게(그늘 굽기)
def tex_of(c):
    T = np.full((TS * TS, 3), 110.0, np.float32); T[tp] = c
    T, _ = photoproj._spread(T.reshape(TS, TS, 3), np.bincount(tp, minlength=TS * TS).reshape(TS, TS) > 0, 3)
    return Image.fromarray(np.clip(T, 0, 255).astype(np.uint8))


def glb_of(tex):
    bb = io.BytesIO(); tex.save(bb, "PNG")
    parts = [P.astype(np.float32).tobytes(), UV.astype(np.float32).tobytes(), F.astype(np.uint32).tobytes(), N.astype(np.float32).tobytes(), bb.getvalue()]
    bvs, blob = [], b""
    for x in parts:
        blob += b"\0" * (-len(blob) % 4); bvs.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(x)}); blob += x
    g = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(blob)}], "bufferViews": bvs,
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(P), "type": "VEC3", "min": P.min(0).tolist(), "max": P.max(0).tolist()},
                       {"bufferView": 1, "componentType": 5126, "count": len(UV), "type": "VEC2"},
                       {"bufferView": 2, "componentType": 5125, "count": F.size, "type": "SCALAR"},
                       {"bufferView": 3, "componentType": 5126, "count": len(N), "type": "VEC3"}],
         "images": [{"bufferView": 4, "mimeType": "image/png"}], "textures": [{"source": 0}],
         "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1, "NORMAL": 3}, "indices": 2, "material": 0}]}],
         "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
    return glbscene.write(g, blob)


def render(gl, deg, R=768):
    """→ (그림, 화소마다 '사진 쪽을 보는 정도'(cos, 안 보이면 -1))"""
    g, bb = glbscene.read(gl); an = np.radians(deg); Rm = np.array([[np.cos(an), 0, np.sin(an)], [0, 1, 0], [-np.sin(an), 0, np.cos(an)]])
    out = np.zeros((R * R, 3), np.float32); zb = np.full(R * R, -np.inf); cz = np.full(R * R, -1.0, np.float32); k = R / 0.26
    for pr in g["meshes"][0]["primitives"]:
        at = pr["attributes"]; P0 = photoproj._acc(g, bb, at["POSITION"]); Pp = (P0 - [0, 1.6, 0]) @ Rm.T; Fp = photoproj._acc(g, bb, pr["indices"]).astype(int).reshape(-1, 3)
        Tt = np.asarray(photoproj._img_of(g, bb, g["materials"][pr["material"]]["pbrMetallicRoughness"]["baseColorTexture"]["index"]).convert("RGB")).astype(np.float32)
        UVp = photoproj._acc(g, bb, at["TEXCOORD_0"])
        pix, fid, c0, c1 = photoproj.raster(np.stack([R / 2 + k * Pp[:, 0], R / 2 - k * Pp[:, 1]], 1), Fp, R, R, -Pp[:, 2])
        cc = np.stack([c0, c1, 1 - c0 - c1], 1); z = (Pp[Fp[fid], 2] * cc).sum(1); win = z > zb[pix]
        uv = (UVp[Fp[fid]] * cc[..., None]).sum(1)[win]
        out[pix[win]] = photoproj._sample(Tt, (uv[:, 0] % 1.0) * Tt.shape[1], uv[:, 1] * Tt.shape[0]); zb[pix[win]] = z[win]
        X0 = (P0[Fp[fid]] * cc[..., None]).sum(1)[win]; n0 = (X0 - [0, 1.6, 0]) / A ** 2
        on = np.abs(np.linalg.norm((X0 - [0, 1.6, 0]) / A, axis=1) - 1) < 0.02                           # 머리 위의 점만
        cz[pix[win]] = np.where(on, n0[:, 2] / np.linalg.norm(n0, axis=1), -2.0)
    return out.reshape(R, R, 3), cz.reshape(R, R)


def detail(img, m):
    """그 부분의 잔무늬 세기(선명도): 흐린 것과의 차이"""
    g = img.mean(2); lo = photoproj._gblur(g, 3.0)
    return float(np.abs(g - lo)[m].mean())


g_true, g_eng = glb_of(tex_of(true_c)), glb_of(tex_of(eng_c))
mask = np.zeros((S, S), np.uint8)
px, py = px_of(P); pix, _, _, _ = photoproj.raster(np.stack([px, py], 1), F, S, S); mask.reshape(-1)[pix] = 255
photo = src.convert("RGBA"); photo.putalpha(Image.fromarray(mask))      # 앞에서 본 정답 = 원래 사진을 3D 실루엣으로 오린 것
fx, fy = px_of(np.array([[-0.062, 1.675, 0], [0.062, 1.5, 0]]))
box = (fx[0], fy[0], fx[1], fy[1])                       # 얼굴 상자(이마~턱)
res, info = photoproj.project(g_eng, photo, head=box, head_size=2048)
assert info.get("head") and not info.get("head_error") and info["iou"] > 0.95, info
ok(f"photo pasted on a round head with its own head texture (overlap {info['iou']:.0%}, tone carried on {info.get('head_tone', 0):.0%} of head texels)")

rows = []
for deg in (30, 50):
    t, cz = render(g_true, deg); e, _ = render(g_eng, deg); n, _ = render(res, deg)
    rows.append((t, e, n))
    for name, lo, hi, need_err, need_det in (("cheek side (40~60° off the photo)", 0.5, 0.77, 0.45, 0.7), ("grazing band (60~75° off)", 0.26, 0.5, 0.75, 0.3)):
        m = (cz >= lo) & (cz < hi)
        assert m.sum() > 2000, (deg, name, int(m.sum()))
        e_eng, e_new = float(np.abs(e - t)[m].mean()), float(np.abs(n - t)[m].mean())
        d_t, d_n, d_e = detail(t, m), detail(n, m), detail(e, m)
        print(f"   {deg}° {name}: error vs sharp photo — engine {e_eng:.1f} → now {e_new:.1f} | detail — sharp {d_t:.2f}, engine {d_e:.2f}, now {d_n:.2f}")
        assert e_new < e_eng * need_err and d_n > d_t * need_det, (deg, name, e_eng, e_new, d_t, d_n)
ok("seen from 30° and 50°: the side of the face (up to ~60° away from the photo) is as sharp as the photo; the grazing band is closer to the photo than to the engine colours")

# 경계가 톱니처럼 깨지지 않는지: 사진을 쓰는 정도가 바뀌는 띠에서, 옆(가로)으로는 변해도 위아래 이웃끼리는 매끈해야 해요
t, cz = render(g_true, 50); n, _ = render(res, 50); e, _ = render(g_eng, 50)
band = (cz > 0.15) & (cz < 0.55)
mix = np.clip((np.abs(n - e).sum(2)) / np.maximum(np.abs(t - e).sum(2), 20), 0, 1)       # 0 = 엔진 색, 1 = 사진 색
lo = photoproj._gblur(mix, 6.0)
rough = float(np.abs(mix - lo)[band].mean())
assert rough < 0.12, rough
ok(f"photo/engine boundary is smooth, not saw-toothed (roughness {rough:.3f})")

# 사진이 닿지 않는 옆(사진에서 75° 넘게 돌아간 곳): 엔진 색 그대로가 아니라 사진 색감 쪽으로
t, cz = render(g_true, 85); n, _ = render(res, 85); e, _ = render(g_eng, 85)
m = (cz > -0.1) & (cz < 0.15) & (t.sum(2) > 0)
bt, be, bn = t[m].mean(), e[m].mean(), n[m].mean()
print(f"   side of the head beyond the photo: brightness sharp {bt:.0f}, engine {be:.0f}, now {bn:.0f}")
assert be < bt - 12 and bn > be + 0.3 * (bt - be) and bn < bt + 10, (bt, be, bn)
ok("beyond the photo's reach the head keeps the photo's tone instead of the engine's darker, washed-out colour")

# 뒤통수는 건드리지 않아요(사진에서 먼 곳)
t, cz = render(g_true, 180); n, _ = render(res, 180); e, _ = render(g_eng, 180)
m = cz < -0.8
assert m.sum() > 2000 and float(np.abs(n - e)[m].mean()) < 6, float(np.abs(n - e)[m].mean())
ok("the back of the head is left as the engine painted it")
if OUT:
    sh = Image.new("RGB", (768 * 3, 768 * 2))
    for j, row in enumerate(rows):
        for q, im in enumerate(row):
            sh.paste(Image.fromarray(np.clip(im, 0, 255).astype(np.uint8)), (768 * q, 768 * j))
    sh.resize((768 * 3 // 2, 768)).save(OUT)
print("ALL OK")
