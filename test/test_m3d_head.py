"""4.5: 3D 머리 전용 텍스처 — 머리를 따로 떼어 자기 텍스처(앞쪽에 넓게 펼침)를 주고, 원래 텍스처·사진으로 채우고,
굴곡(노멀맵)을 새 텍스처 방향으로 옮겨요. 얼굴 해상도가 여러 배."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17983"
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import numpy as np
import glbscene, photoproj
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid):
    for _ in range(1500):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])


# ── 가짜 캐릭터: 몸통(원기둥) + 머리(구). 무늬는 3D 위치로 정해요(얼굴에 1cm 줄무늬·눈) ──
def pattern(X):
    x, y, z = X[:, 0], X[:, 1], X[:, 2]
    c = np.stack([np.full_like(x, 200), np.full_like(x, 160), np.full_like(x, 140)], 1)
    head = y > 1.42
    c[(np.floor(x / 0.01) % 2 == 0) & head & (z > 0)] = (120, 60, 50)
    c[head & (z > 0) & (np.abs(np.abs(x) - 0.04) < 0.015) & (np.abs(y - 1.57) < 0.01)] = (10, 10, 40)
    c[~head & (np.floor(y / 0.1) % 2 == 0)] = (60, 90, 170)
    c[~head & (np.floor(y / 0.1) % 2 == 1)] = (80, 110, 190)
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


def glb_of(P, UV, F, N, ims):
    pngs = []
    for im in ims:
        b = io.BytesIO(); im.save(b, "PNG"); pngs.append(b.getvalue())
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


P, UV, F, N = mesh()
TS_TS = (0.5, 0.0, np.sqrt(0.75))                                                  # 노멀맵: 모든 곳이 텍스처 오른쪽으로 30° 기운 굴곡
nmap = Image.new("RGB", (512, 512), tuple(int(round((c + 1) * 127.5)) for c in TS_TS))
orm = Image.new("RGB", (512, 512), (150, 230, 0))
glb = glb_of(P, UV, F, N, [bake(P, UV, F, 512), nmap, orm])                          # 몸 전체 512 → 머리 몫 약 120px(엔진 색처럼 흐림)
photo = shoot(P, F); truth = np.asarray(photo.convert("RGB")).astype(float)
fb = (int(S / 2 - 0.1 * K), int(S / 2 - 0.87 * K), int(S / 2 + 0.1 * K), int(S / 2 - 0.65 * K))
x0, y0, x1, y1 = fb
err = lambda gl: float(np.abs(render(gl)[y0:y1, x0:x1] - truth[y0:y1, x0:x1]).mean())

one, i1 = photoproj.project(glb, photo)
two, i2 = photoproj.project(glb, photo, head=fb, head_size=2048)
e0, e1, e2 = err(glb), err(one), err(two)
assert i2.get("head") and i2["head_tex"] == 2048 and not i2.get("head_error"), i2
assert e2 < e1 * 0.75 and e2 < e0 * 0.6, (e0, e1, e2)
ok(f"face error: engine colours {e0:.1f} → photo on one texture {e1:.1f} → head texture {e2:.1f}")

g2, ps = prims_of(two)
assert len(ps) == 2 and len(g2["materials"]) == 2 and ps[1]["T"].shape[:2] == (2048, 2048)
assert len(ps[0]["F"]) + len(ps[1]["F"]) == len(F) and 0.3 < len(ps[1]["F"]) / len(F) < 0.85
hm = ps[1]["mat"]; smp = g2["samplers"][g2["textures"][hm["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["sampler"]]
assert smp["wrapS"] == 10497 and smp["minFilter"] == 9987 and hm["occlusionTexture"]["index"] == hm["pbrMetallicRoughness"]["metallicRoughnessTexture"]["index"]
ok("head split into its own primitive + material (base/normal/ORM, 2048px, wraps around the back)")

# 노멀맵: 같은 3D 지점에서 원래 덩어리로 본 굴곡 방향 = 머리 덩어리로 본 굴곡 방향
def world_n(p, f, c, T, nm_override=None):
    P3, UV3 = p["P"][p["F"][f]], p["UV"][p["F"][f]]
    Nn = (p["N"][p["F"][f]] * c[..., None]).sum(1); Nn /= np.linalg.norm(Nn, axis=1, keepdims=True)
    uv = (UV3 * c[..., None]).sum(1)
    ns = photoproj._sample(T, (uv[:, 0] % 1.0) * T.shape[1], uv[:, 1] * T.shape[0]) / 127.5 - 1
    Tu, Bu = photoproj._frames(P3, UV3, None); Tt, Bt = photoproj._tbn(Tu, Bu, Nn)
    w = ns[:, 0:1] * Tt + ns[:, 1:2] * Bt + ns[:, 2:3] * Nn
    return w / np.linalg.norm(w, axis=1, keepdims=True), (P3 * c[..., None]).sum(1)
h = ps[1]; rs = np.random.RandomState(1); fsel = rs.choice(len(h["F"]), 400, replace=False); c = np.full((400, 3), 1 / 3)
wn_head, X = world_n(h, fsel, c, h["NM"])
orig = {"P": P, "UV": UV, "N": N, "F": F}
cen = P[F].mean(1); near = np.array([np.argmin(((cen - x) ** 2).sum(1)) for x in X])
wn_old, _ = world_n(orig, near, c, np.asarray(nmap).astype(float))
ang = np.degrees(np.arccos(np.clip((wn_head * wn_old).sum(1), -1, 1)))
assert np.median(ang) < 4 and np.percentile(ang, 90) < 10, (np.median(ang), np.percentile(ang, 90))
ok(f"normal map moved to the new texture direction (median {np.median(ang):.1f}° off)")

# ── 3D 만들기 화면 흐름 ──
class Keep:
    def cut(self, img, _):
        o = img.convert("RGBA"); a = np.asarray(img.convert("RGB")).sum(2) > 0; o.putalpha(Image.fromarray((a * 255).astype(np.uint8))); return o
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True; hub.rmbg_engine = lambda k: Keep()
for f in (M / "upscale_models").glob("*") if (M / "upscale_models").is_dir() else []: f.unlink()
for f in ("diffusion_models/trellis_2_int8_convrot.safetensors", "clip_vision/dino_v3_vit_l.safetensors", "vae/trellis_2_shape_vae_bf16.safetensors",
          "vae/trellis_2_texture_vae_bf16.safetensors", "detection/mediapipe_face_fp32.safetensors"):
    (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
STATE["glb"], STATE["face_box"] = glb, ((S, S), fb)
bi = io.BytesIO(); photo.convert("RGB").save(bi, "PNG")
j = job({"kind": "m3d", "op": "prep", "image": "data:image/png;base64," + base64.b64encode(bi.getvalue()).decode(), "kind3": "character", "name": "head"}); sid = j["m3d"]["id"]
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "tex": "2048"}); assert j["state"] == "done", j
ph = j["m3d_stats"]["photo"]; assert ph["done"] and ph["head"] and "머리는 전용 텍스처 2048px" in ph["text"], ph
assert len(glbscene.read(urllib.request.urlopen(B + j["images"][0]).read())[0]["meshes"][0]["primitives"]) == 2
assert any("얼굴 부분이" in w and "업스케일" in w for w in j.get("warn", [])), j.get("warn")      # 얼굴이 작은데 업스케일 모델이 없으면 알려 줘요
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "tex": "2048", "head": False}); assert j["state"] == "done", j
assert len(glbscene.read(urllib.request.urlopen(B + j["images"][0]).read())[0]["meshes"][0]["primitives"]) == 1 and not j["m3d_stats"]["photo"].get("head")
ok("3D build: face found → head texture on by default (shown on the result), off with the option")

# Pixal3D 화각 → 사진 붙이기 원근을 계산으로(카메라 거리 = 0.55/tan(화각/2) × 긴 변)
CAT = {m["id"]: m for m in json.loads((Path(BASE) / "LocalAI-Studio/hub/models.json").read_text(encoding="utf-8"))["image"]}
for f in CAT["pixal3d"]["files"]:
    (M / f["dir"] / f["url"].rsplit("/", 1)[1]).parent.mkdir(parents=True, exist_ok=True); (M / f["dir"] / f["url"].rsplit("/", 1)[1]).write_bytes(b"x")
STATE["fov_text"] = "38.5"
jid = post("/api/job", {"kind": "m3d", "op": "build", "id": sid, "blender": "", "tex": "2048", "head": False})["id"]; j = wait(jid); assert j["state"] == "done", j
assert hub.JOBS[jid]["m3d_photo"][-1]["dist"] == f"e{0.55 / np.tan(np.radians(38.5) / 2):.2f}", hub.JOBS[jid]["m3d_photo"]
(M / CAT["pixal3d"]["files"][-1]["dir"] / CAT["pixal3d"]["files"][-1]["url"].rsplit("/", 1)[1]).unlink()           # MoGe 없음 → 기본 화각 49.13
jid = post("/api/job", {"kind": "m3d", "op": "build", "id": sid, "blender": "", "tex": "2048", "head": False})["id"]; j = wait(jid)
assert hub.JOBS[jid]["m3d_photo"][-1]["dist"] == f"e{0.55 / np.tan(np.radians(49.13) / 2):.2f}", hub.JOBS[jid]["m3d_photo"]
ok("Pixal3D: field of view read back from MoGe (or the 49.13 default) sets the projection perspective exactly")
print("ALL OK")
