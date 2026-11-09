# -*- coding: utf-8 -*-
"""사진 붙이기: 3D 결과(GLB)의 색 텍스처에 원본 사진을 그대로 붙여요(파이썬 + numpy 만).

3D 엔진은 사진을 그대로 쓰지 않고 색을 다시 칠해요. 촘촘함에 한계가 있어서 얼굴처럼 작은 곳이 뭉개지고 생김새가 바뀌어요.
그래서 앞 사진에서 보이는 면에는 사진 화소를 그대로 붙이고, 옆으로 돌아갈수록 원래 색과 자연스럽게 섞어요.

1) 카메라 맞추기: 3D 를 여러 방향(위쪽 축 4 × 앞쪽 4)·원근(8)으로 비춰 보고, 사진의 실루엣과 가장 잘 겹치는 것을 골라요.
   앞·뒤처럼 실루엣이 비슷하면 지금 텍스처 색이 사진과 더 닮은 쪽을 골라요. 겹침이 낮으면 붙이지 않아요(어긋나 번지는 것보다 나아요).
2) 사진 쪽 깊이 지도로 가려진 면을 빼고, 텍스처의 화소마다 3D 위치 → 사진 위치를 구해 색을 가져와요.
3) 얼굴 확대본(face)이 있으면 그 부분은 확대본에서 가져와요(사진보다 촘촘해요).
"""
import io
import json
import math

import numpy as np
from PIL import Image, ImageFilter

import glbscene

MIN_IOU = 0.85          # 사진·3D 실루엣이 이만큼 겹쳐야 붙여요
MIN_IOU_PAT = (0.75, 0.4)   # 또는: 겹침이 이만큼이고 무늬(밝기)가 이만큼 맞으면 — 머리카락이 많아 실루엣이 덜 겹치는 캐릭터
AO_KEEP = 0.15          # 사진을 붙인 곳의 그늘 굽기는 이만큼만 남겨요(사진에 이미 진짜 그늘이 있어서 겹치면 두 배로 어두워져요)
SKIN_ROUGH = 0.5        # 사진을 붙인 피부의 거칠기(업계 시작값 0.4~0.6) — 3D 엔진은 피부를 매우 거칠게 칠해 찰흙처럼 보여요
FACING = (0.3, 0.65)    # 면이 사진 쪽을 보는 정도(cos) — 아래쪽은 원래 색, 위쪽은 사진 색, 사이는 섞어요
_CT = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8, 5122: np.int16, 5120: np.int8}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _acc(g, b, i):
    a = g["accessors"][i]
    bv = g["bufferViews"][a["bufferView"]]
    dt, n = np.dtype(_CT[a["componentType"]]), _NC[a["type"]]
    st = bv.get("byteStride") or dt.itemsize * n
    arr = np.ndarray((a["count"], n), dt, buffer=b, offset=bv.get("byteOffset", 0) + a.get("byteOffset", 0), strides=(st, dt.itemsize))
    arr = arr.astype(np.float64)
    if a.get("normalized") and dt.kind in "ui":
        arr /= np.iinfo(dt).max
    return arr


def load(glb):
    """GLB → 메시 하나(위치·면·UV)와 색 텍스처. 붙일 수 없는 모양(여러 덩어리, 텍스처 없음)이면 ValueError."""
    g, b = glbscene.read(glb)
    prims = [(ni, p) for ni, nd in enumerate(g.get("nodes") or []) if "mesh" in nd for p in g["meshes"][nd["mesh"]].get("primitives") or []]
    if len(prims) != 1:
        raise ValueError("덩어리가 여러 개인 3D 예요")
    ni, pr = prims[0]
    at = pr.get("attributes") or {}
    if "TEXCOORD_0" not in at or "indices" not in pr or pr.get("mode", 4) != 4:
        raise ValueError("텍스처 좌표가 없어요")
    mat = (g.get("materials") or [{}])[pr.get("material", 0)] if g.get("materials") else {}
    bt = (mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
    if not bt or bt.get("texCoord", 0) != 0:
        raise ValueError("색 텍스처가 없어요")
    ii = g["textures"][bt["index"]]["source"]
    im = g["images"][ii]
    if "bufferView" not in im:
        raise ValueError("텍스처가 파일 안에 없어요")
    v = g["bufferViews"][im["bufferView"]]
    tex = Image.open(io.BytesIO(b[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]))
    P = _acc(g, b, at["POSITION"])[:, :3]
    m = _world(g, ni)
    P = P @ m[:3, :3].T + m[:3, 3]
    F = _acc(g, b, pr["indices"]).astype(np.int64).reshape(-1, 3)
    UV = _acc(g, b, at["TEXCOORD_0"])[:, :2]
    N = None
    if "NORMAL" in at:
        N = _acc(g, b, at["NORMAL"])[:, :3] @ m[:3, :3].T
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return {"g": g, "b": b, "P": P, "F": F, "UV": UV, "N": N, "image": ii, "tex": tex, "mat": mat, "node": ni, "prim": pr}


def _world(g, ni):
    nodes = g.get("nodes") or []
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children") or []}
    m, i, k = np.eye(4), ni, 0
    while i is not None and k < 64:
        m = glbscene._mat(nodes[i]) @ m
        i, k = parent.get(i), k + 1
    return m


def rebuild(g, b, repl=None, add=()):
    """버퍼 다시 묶기: repl {bufferView 번호: 새 바이트} 는 바꾸고, add 의 바이트는 새 bufferView 로 뒤에 붙여요.
    → (g, 새 bin, 새로 붙인 bufferView 번호들). g 는 복사본이에요."""
    repl = repl or {}
    g = {**g, "bufferViews": [dict(v) for v in g["bufferViews"]], "buffers": [dict(x) for x in g["buffers"]]}
    out, pos = [], 0
    for k in sorted(range(len(g["bufferViews"])), key=lambda k: g["bufferViews"][k].get("byteOffset", 0)):
        v = g["bufferViews"][k]
        if v.get("buffer", 0) != 0:
            raise ValueError("버퍼가 여러 개예요")
        chunk = repl[k] if k in repl else b[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]
        pad = -pos % 4
        out.append(b"\0" * pad)
        pos += pad
        v["byteOffset"], v["byteLength"] = pos, len(chunk)
        out.append(chunk)
        pos += len(chunk)
    new = []
    for chunk in add:
        pad = -pos % 4
        out.append(b"\0" * pad)
        pos += pad
        g["bufferViews"].append({"buffer": 0, "byteOffset": pos, "byteLength": len(chunk)})
        new.append(len(g["bufferViews"]) - 1)
        out.append(chunk)
        pos += len(chunk)
    nb = b"".join(out)
    g["buffers"][0]["byteLength"] = len(nb)
    return g, nb, new


def replace_image(g, b, ii, data, mime="image/png"):
    """GLB 안의 그림 하나를 바꿔 넣고 → 새 GLB 바이트(버퍼를 다시 이어 붙여요)."""
    g = {**g, "bufferViews": [dict(v) for v in g["bufferViews"]], "images": [dict(x) for x in g["images"]], "buffers": [dict(x) for x in g["buffers"]]}
    tgt = g["images"][ii]["bufferView"]
    g["images"][ii]["mimeType"] = mime
    out, pos = [], 0
    for k in sorted(range(len(g["bufferViews"])), key=lambda k: g["bufferViews"][k].get("byteOffset", 0)):
        v = g["bufferViews"][k]
        if v.get("buffer", 0) != 0:
            raise ValueError("버퍼가 여러 개예요")
        chunk = data if k == tgt else b[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]
        pad = -pos % 4
        out.append(b"\0" * pad)
        pos += pad
        v["byteOffset"], v["byteLength"] = pos, len(chunk)
        out.append(chunk)
        pos += len(chunk)
    nb = b"".join(out)
    g["buffers"][0]["byteLength"] = len(nb)
    return glbscene.write(g, nb)


def fix_samplers(glb):
    """텍스처 '밉맵'을 켜요(게임 엔진 기본값). ComfyUI 는 줄일 때 밉맵 없이(minFilter LINEAR) 저장해서,
    텍스처가 화면에서 작게 보이면 자글자글 깨져 보여요(얼굴이 픽셀처럼). 텍스처가 없으면 그대로 돌려줘요."""
    try:
        g, b = glbscene.read(glb)
    except Exception:  # noqa: BLE001 — GLB 가 아니거나 깨졌으면 손대지 않아요
        return glb
    if not g.get("textures"):
        return glb
    ss = g.setdefault("samplers", [])
    if not ss:
        ss.append({})
    for s in ss:
        s["magFilter"], s["minFilter"] = 9729, 9987       # LINEAR / LINEAR_MIPMAP_LINEAR
        s.setdefault("wrapS", 33071)
        s.setdefault("wrapT", 33071)
    for t in g["textures"]:
        t.setdefault("sampler", 0)
    return glbscene.write(g, b)


# ───────────────────────── 삼각형 → 화소 ─────────────────────────
def raster(xy, F, W, H, z=None, limit=3_000_000):
    """삼각형을 W×H 격자에 그려요(화소 중심이 안에 든 것). → (화소 번호, 면 번호, 무게중심 b0, b1).
    z 가 있으면 화소마다 가장 가까운(z 가 작은) 면만 남겨요."""
    T = xy[F]
    lo = np.ceil(T.min(1) - 0.5).astype(np.int64)
    hi = np.floor(T.max(1) - 0.5).astype(np.int64)
    lo = np.maximum(lo, 0)
    hi[:, 0] = np.minimum(hi[:, 0], W - 1)
    hi[:, 1] = np.minimum(hi[:, 1], H - 1)
    n = hi - lo + 1
    x0, y0, x1, y1, x2, y2 = T[:, 0, 0], T[:, 0, 1], T[:, 1, 0], T[:, 1, 1], T[:, 2, 0], T[:, 2, 1]
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    ok = (n[:, 0] > 0) & (n[:, 1] > 0) & (np.abs(den) > 1e-12)
    span = np.maximum(n[:, 0], n[:, 1])
    outs = []
    s_prev = 0
    s = 1
    while ok.any() and s_prev < max(W, H):
        sel = np.nonzero(ok & (span > s_prev) & (span <= s))[0]
        if len(sel):
            oy, ox = np.divmod(np.arange(s * s), s)
            step = max(1, limit // (s * s))
            for c in range(0, len(sel), step):
                t = sel[c:c + step]
                px = lo[t, 0:1] + ox[None]
                py = lo[t, 1:2] + oy[None]
                valid = (ox[None] < n[t, 0:1]) & (oy[None] < n[t, 1:2])
                cx, cy = px + 0.5, py + 0.5
                d = den[t][:, None]
                b0 = ((y1[t][:, None] - y2[t][:, None]) * (cx - x2[t][:, None]) + (x2[t][:, None] - x1[t][:, None]) * (cy - y2[t][:, None])) / d
                b1 = ((y2[t][:, None] - y0[t][:, None]) * (cx - x2[t][:, None]) + (x0[t][:, None] - x2[t][:, None]) * (cy - y2[t][:, None])) / d
                inside = valid & (b0 >= -1e-9) & (b1 >= -1e-9) & (1 - b0 - b1 >= -1e-9)
                r, cc = np.nonzero(inside)
                if len(r):
                    outs.append(((py[r, cc] * W + px[r, cc]), t[r], b0[r, cc], b1[r, cc]))
        s_prev, s = s, s * 2
    if not outs:
        e = np.zeros(0)
        return e.astype(np.int64), e.astype(np.int64), e, e
    pix, fid, b0, b1 = (np.concatenate(x) for x in zip(*outs))
    if z is not None:
        zz = z[F[fid, 0]] * b0 + z[F[fid, 1]] * b1 + z[F[fid, 2]] * (1 - b0 - b1)
        o = np.lexsort((zz, pix))
        pix, fid, b0, b1 = pix[o], fid[o], b0[o], b1[o]
        keep = np.r_[True, pix[1:] != pix[:-1]]
        pix, fid, b0, b1 = pix[keep], fid[keep], b0[keep], b1[keep]
    return pix, fid, b0, b1


def _sample(img, x, y):
    """img(H,W,C float) 를 화소 좌표(중심 +0.5)에서 겹선형으로 읽어요."""
    H, W = img.shape[:2]
    fx, fy = np.clip(x - 0.5, 0, W - 1), np.clip(y - 0.5, 0, H - 1)
    ix, iy = np.minimum(fx.astype(np.int64), W - 2 if W > 1 else 0), np.minimum(fy.astype(np.int64), H - 2 if H > 1 else 0)
    ax, ay = (fx - ix)[:, None], (fy - iy)[:, None]
    jx, jy = np.minimum(ix + 1, W - 1), np.minimum(iy + 1, H - 1)
    return (img[iy, ix] * (1 - ax) * (1 - ay) + img[iy, jx] * ax * (1 - ay) + img[jy, ix] * (1 - ax) * ay + img[jy, jx] * ax * ay)


# ───────────────────────── 카메라 맞추기 ─────────────────────────
AXES = {"+y": (0, 1, 0), "+z": (0, 0, 1), "-y": (0, -1, 0), "-z": (0, 0, -1)}     # glTF 는 보통 y 위 — 엔진마다 달라서 모두 비춰 봐요
DIST = (None, 3.0, 2.0, 1.5, 1.2, 1.0, 0.8, 0.65)     # 카메라 거리 ÷ 물체 대각선(None = 멀리서, 원근 없음)


def _cams():
    out = []
    for un, u in AXES.items():
        u = np.array(u, float)
        hz = [np.array(a, float) for a in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)) if abs(np.dot(a, u)) < 0.5]
        for bk in hz:
            out.append({"name": f"up{un} back{tuple(int(x) for x in bk)}", "u": u, "b": bk, "r": np.cross(u, bk)})
    return out


def _bbox(mask, keep=0.001):
    ys, xs = np.nonzero(mask)
    if len(xs) < 16:
        return None
    return (np.quantile(xs, keep), np.quantile(ys, keep), np.quantile(xs, 1 - keep) + 1, np.quantile(ys, 1 - keep) + 1)


class Cam:
    """3D → 사진 화소 좌표. 사진 실루엣 상자에 3D 상자를 맞춰요."""

    def __init__(self, c, P, abox, dist=None):
        self.r, self.u, self.b = c["r"], c["u"], c["b"]
        self.name, self.dist = c["name"], dist
        self.ctr = (P.min(0) + P.max(0)) / 2
        ext = float(np.linalg.norm(P.max(0) - P.min(0))) or 1.0
        self.ext = ext
        self.D = None if dist is None else dist * ext
        X, Y, _ = self._proj(P)
        mx, my, Mx, My = X.min(), -Y.max(), X.max(), -Y.min()
        ax0, ay0, ax1, ay1 = abox
        s = math.sqrt(max(1e-9, (ax1 - ax0) / max(1e-9, Mx - mx)) * max(1e-9, (ay1 - ay0) / max(1e-9, My - my)))
        self.s = s
        self.t = np.array([(ax0 + ax1) / 2 - s * (mx + Mx) / 2, (ay0 + ay1) / 2 - s * (my + My) / 2])

    def _proj(self, P):
        q = P - self.ctr
        x, y, w = q @ self.r, q @ self.u, q @ self.b
        if self.D is None:
            return x, y, -w
        dep = np.maximum(self.D - w, 1e-6)
        return x * self.D / dep, y * self.D / dep, dep

    def px(self, P):
        """→ (사진 x, 사진 y, 깊이: 작을수록 카메라에 가까움)"""
        X, Y, z = self._proj(P)
        return self.s * X + self.t[0], -self.s * Y + self.t[1], z

    def view(self, P):
        """점에서 카메라 쪽 방향(단위 벡터)"""
        if self.D is None:
            return np.broadcast_to(self.b, P.shape)
        v = self.ctr + self.b * self.D - P
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def _sil(cam, P, F, scale, W, H, z=False):
    x, y, d = cam.px(P)
    xy = np.stack([x * scale, y * scale], 1)
    return raster(xy, F, W, H, d if z else None)


def fit(P, F, UV, tex, alpha, rgb, log=None):
    """사진 실루엣(alpha, 0~1)과 가장 잘 맞는 카메라 → (Cam, 겹침, 무늬 겹침)"""
    L = 192
    H0, W0 = alpha.shape
    sc = L / max(H0, W0)
    W, H = max(1, round(W0 * sc)), max(1, round(H0 * sc))
    am_im = Image.fromarray((alpha * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR).point(lambda q: 255 if q > 127 else 0)
    am = np.asarray(am_im.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))) > 127      # 가는 머리카락 가닥은 빼고 비교해요
    abox = _bbox(alpha > 0.5)
    if abox is None:
        raise ValueError("사진에 물체가 없어요")

    def iou(cam):
        pix = np.unique(_sil(cam, P, F, sc, W, H)[0])
        m = np.zeros(W * H, bool)
        m[pix] = True
        m = m.reshape(H, W)
        return (m & am).sum() / max(1, (m | am).sum())

    small = np.asarray(Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)).astype(np.float64) / 255
    T = np.asarray(tex.convert("RGB")).astype(np.float64) / 255
    vc = _sample(T, UV[:, 0] * T.shape[1], UV[:, 1] * T.shape[0])

    def render(cam):
        pix, fid, b0, b1 = _sil(cam, P, F, sc, W, H, z=True)
        col = vc[F[fid, 0]] * b0[:, None] + vc[F[fid, 1]] * b1[:, None] + vc[F[fid, 2]] * (1 - b0 - b1)[:, None]
        ok = am.reshape(-1)[pix]
        return col[ok], small.reshape(-1, 3)[pix[ok]]

    def diff(cam):
        a, b = render(cam)
        return float(np.abs(a - b).mean()) if len(a) >= 16 else 9.0

    def ncc(cam):
        """지금 텍스처를 비춘 그림과 사진의 밝기 무늬가 얼마나 겹치나(원근·위치가 맞을수록 커요)"""
        a, b = render(cam)
        if len(a) < 16:
            return -1.0
        a, b = a.mean(1) - a.mean(), b.mean(1) - b.mean()
        return float((a * b).sum() / max(1e-9, math.sqrt((a * a).sum() * (b * b).sum())))

    tried = sorted(((iou(Cam(c, P, abox)), c) for c in _cams()), key=lambda x: -x[0])
    top = [x for x in tried if x[0] >= tried[0][0] - 0.03]
    if len(top) > 1:                                  # 실루엣만으로 앞·뒤를 못 가리면 색으로
        top.sort(key=lambda x: diff(Cam(x[1], P, abox)) - x[0])
    v, c = top[0]
    cands = [(ncc(cam), cam) for cam in (Cam(c, P, abox, k) for k in DIST)]      # 원근은 무늬로 골라요
    pat, cam = max(cands, key=lambda x: x[0])
    if log:
        log(f"[사진 붙이기] 카메라 {cam.name} 거리 {cam.dist} 겹침 {v:.3f} 무늬 {pat:.3f}")
    return cam, float(v), float(pat)


# ───────────────────────── 붙이기 ─────────────────────────
def _skin(col):
    """사진 색(0~255) → 피부일 정도 0~1 (YCbCr 피부색 범위, 밝은 피부·만화 피부 포함)"""
    r, g, b = col[:, 0], col[:, 1], col[:, 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.1687 * r - 0.3313 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.4187 * g - 0.0813 * b
    ok = (cr > 133) & (cr < 175) & (cb > 75) & (cb < 130) & (y > 50)
    return ok.astype(np.float32)


def _color_match(T, tp, w, col):
    """3D 엔진이 칠한 색 전체를 사진 색감에 맞춰요(같은 곳을 비교해 채널별 밝기·대비) → 맞춘 T.
    사진 색과 엔진 색이 만나는 경계에 띠가 생기지 않게 하고, 옆·뒤 색도 사진과 어울리게 해요."""
    sel = w[:, 0] > 0.7
    if sel.sum() < 500:
        return T
    ty, tx = np.divmod(tp[sel], T.shape[1])
    o, p = T[ty, tx].astype(np.float64), col[sel].astype(np.float64)
    mo, mp = o.mean(0), p.mean(0)
    so, sp = o.std(0) + 1e-6, p.std(0) + 1e-6
    k = np.clip(sp / so, 0.75, 1.33)
    out = (T - mo) * k + mo + np.clip(mp - mo, -40, 40)
    return np.clip(0.2 * T + 0.8 * out, 0, 255).astype(np.float32)


def _spread(vals, mask, steps=2):
    """바뀐 값을 둘레로 번지게(섬 가장자리 이음새가 안 보이게) — vals(H,W,C), mask(H,W)"""
    for _ in range(steps):
        grow = np.zeros_like(mask)
        acc = np.zeros_like(vals)
        cnt = np.zeros(mask.shape + (1,), np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sh = np.roll(mask, (dy, dx), (0, 1))
            acc += np.roll(vals, (dy, dx), (0, 1)) * sh[..., None]
            cnt += sh[..., None]
            grow |= sh
        add = grow & ~mask
        vals[add] = acc[add] / np.maximum(cnt[add], 1)
        mask |= add
    return vals, mask


def _adjust_orm(M, wmap, skin):
    """사진을 붙인 곳: 그늘 굽기(AO) 줄이기, 피부는 거칠기 맞추기(금속 0). → [(그림 번호, PNG)]"""
    g, b, mat = M["g"], M["b"], M["mat"] or {}
    occ = (mat.get("occlusionTexture") or {}).get("index")
    mr = ((mat.get("pbrMetallicRoughness") or {}).get("metallicRoughnessTexture") or {}).get("index")
    jobs = {}
    if occ is not None:
        jobs.setdefault(g["textures"][occ]["source"], set()).add("ao")
    if mr is not None:
        jobs.setdefault(g["textures"][mr]["source"], set()).add("mr")
    out = []
    for ii, what in jobs.items():
        im = g["images"][ii]
        if "bufferView" not in im:
            continue
        v = g["bufferViews"][im["bufferView"]]
        pic = Image.open(io.BytesIO(b[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]])).convert("RGB")
        A = np.asarray(pic).astype(np.float32)
        size = (A.shape[1], A.shape[0])
        wm = np.asarray(Image.fromarray((wmap * 255).astype(np.uint8)).resize(size, Image.BILINEAR)).astype(np.float32) / 255
        if "ao" in what:
            A[..., 0] += (255 - A[..., 0]) * wm * (1 - AO_KEEP)
        if "mr" in what:
            sk = np.asarray(Image.fromarray((skin * 255).astype(np.uint8)).resize(size, Image.BILINEAR)).astype(np.float32) / 255 * wm
            A[..., 1] += (SKIN_ROUGH * 255 - A[..., 1]) * sk
            A[..., 2] *= 1 - sk
        buf = io.BytesIO()
        Image.fromarray(np.clip(A, 0, 255).astype(np.uint8)).save(buf, "PNG", compress_level=4)
        out.append((ii, buf.getvalue()))
    return out


def project(glb, photo, face=None, log=None, progress=None, head=None, head_size=4096):
    """photo: 배경 지운 앞 사진(RGBA PIL). face: (x0, y0, x1, y1, 확대한 RGBA PIL) — 사진 좌표의 얼굴 상자와 그 확대본.
    head: (x0, y0, x1, y1) 사진 속 얼굴 상자 — 주면 머리를 따로 떼어 자기 텍스처(head_size)를 줘요(얼굴 해상도 여러 배).
    → (새 GLB 바이트, 정보 dict). 맞지 않으면 (원래 GLB, {"skip": 이유})"""
    M = load(glb)
    P, F, UV, tex = M["P"], M["F"], M["UV"], M["tex"]
    ph = np.asarray(photo.convert("RGBA")).astype(np.float64) / 255
    alpha, rgb = ph[..., 3], ph[..., :3]
    cam, v, pat = fit(P, F, UV, tex, alpha, rgb, log)
    if not (v >= MIN_IOU or (v >= MIN_IOU_PAT[0] and pat >= MIN_IOU_PAT[1])):
        return glb, {"skip": "shape", "iou": round(v, 3), "pat": round(pat, 3)}
    if progress:
        progress(0.2)
    H0, W0 = alpha.shape
    # 가려진 면 빼기: 사진 쪽 깊이 지도(긴 변 1024)
    zs = min(1.0, 1024 / max(H0, W0))
    ZW, ZH = max(1, round(W0 * zs)), max(1, round(H0 * zs))
    x, y, d = cam.px(P)
    pix, fid, b0, b1 = raster(np.stack([x * zs, y * zs], 1), F, ZW, ZH, d)
    zb = np.full(ZW * ZH, np.inf)
    zb[pix] = d[F[fid, 0]] * b0 + d[F[fid, 1]] * b1 + d[F[fid, 2]] * (1 - b0 - b1)
    zb = zb.reshape(ZH, ZW)
    tol = cam.ext * 0.01                    # 깊이 비교 여유(물체 크기의 1%)

    def visible(xx, yy, dd):
        ix = np.clip((xx * zs).astype(np.int64), 0, ZW - 1)
        iy = np.clip((yy * zs).astype(np.int64), 0, ZH - 1)
        return dd <= zb[iy, ix] + tol

    # 사진 쪽을 보는 면만 고르기
    e1, e2 = P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]
    n = np.cross(e1, e2)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    cen = P[F].mean(1)
    cosf = np.abs((n * cam.view(cen)).sum(1))
    vv = visible(x, y, d)
    cx, cy, cd = cam.px(cen)
    pick = (cosf >= FACING[0]) & (vv[F].any(1) | visible(cx, cy, cd))
    if not pick.any():
        return glb, {"skip": "none", "iou": round(v, 3)}
    if progress:
        progress(0.35)
    # 텍스처 화소마다 3D 위치 → 사진 위치 (먼저 모두 모으고, 색 맞추기 뒤에 섞어요)
    T = np.asarray(tex.convert("RGB")).astype(np.float32)
    TH, TW = T.shape[:2]
    sel = np.nonzero(pick)[0]
    soft = Image.fromarray((alpha * 255).astype(np.uint8))
    er = max(1, round(max(H0, W0) * 0.004))
    soft = soft.filter(ImageFilter.MinFilter(er * 2 + 1)).filter(ImageFilter.GaussianBlur(er))
    soft = np.asarray(soft).astype(np.float32)[..., None] / 255
    photo_rgb = (rgb * 255).astype(np.float32)
    fbox = None
    if face is not None:
        fx0, fy0, fx1, fy1, fim = face
        fa = np.asarray(fim.convert("RGB")).astype(np.float32)
        fbox = (fx0, fy0, fx1, fy1, fa)
    uvp = np.stack([UV[:, 0] * TW, UV[:, 1] * TH], 1)
    CH = 60000
    TPs, Ws, COLs = [], [], []
    for k in range(0, len(sel), CH):
        fs = sel[k:k + CH]
        tp, tf, c0, c1 = raster(uvp, F[fs], TW, TH)
        if not len(tp):
            continue
        f = fs[tf]
        c2 = 1 - c0 - c1
        X = P[F[f, 0]] * c0[:, None] + P[F[f, 1]] * c1[:, None] + P[F[f, 2]] * c2[:, None]
        sx, sy, sd = cam.px(X)
        ok = visible(sx, sy, sd) & (sx >= 0) & (sy >= 0) & (sx < W0) & (sy < H0)
        if not ok.any():
            continue
        tp, f, X, sx, sy = tp[ok], f[ok], X[ok], sx[ok], sy[ok]
        cs = np.abs((n[f] * cam.view(X)).sum(1))
        w = np.clip((cs - FACING[0]) / (FACING[1] - FACING[0]), 0, 1)
        w = (w * w * (3 - 2 * w))[:, None].astype(np.float32) * _sample(soft, sx, sy)
        col = _sample(photo_rgb, sx, sy)
        if fbox:
            fx0, fy0, fx1, fy1, fa = fbox
            inb = (sx > fx0) & (sx < fx1) & (sy > fy0) & (sy < fy1)
            if inb.any():
                kx, ky = fa.shape[1] / (fx1 - fx0), fa.shape[0] / (fy1 - fy0)
                fc = _sample(fa, (sx[inb] - fx0) * kx, (sy[inb] - fy0) * ky)
                ex = np.minimum.reduce([sx[inb] - fx0, fx1 - sx[inb], sy[inb] - fy0, fy1 - sy[inb]]) / max(1.0, 0.08 * (fx1 - fx0))
                fw = np.clip(ex, 0, 1)[:, None].astype(np.float32)
                col[inb] = col[inb] * (1 - fw) + fc * fw
        keep = w[:, 0] > 0.002
        TPs.append(tp[keep]); Ws.append(w[keep]); COLs.append(col[keep].astype(np.float32))
        if progress:
            progress(0.35 + 0.45 * min(1.0, (k + CH) / len(sel)))
    if not TPs:
        return glb, {"skip": "none", "iou": round(v, 3)}
    tp, w, col = np.concatenate(TPs), np.concatenate(Ws), np.concatenate(COLs)
    T = _color_match(T, tp, w, col)
    ty, tx = np.divmod(tp, TW)
    delta = np.zeros((TH, TW, 3), np.float32)
    changed = np.zeros((TH, TW), bool)
    delta[ty, tx] = (col - T[ty, tx]) * w
    changed[ty, tx] = True
    delta, changed = _spread(delta, changed)
    out = np.clip(T + delta, 0, 255).astype(np.uint8)
    # 그늘 굽기·피부 거칠기: 사진을 붙인 정도(w)와 피부일 정도를 텍스처 크기 지도로
    wm = np.zeros((TH, TW, 1), np.float32)
    wm[ty, tx] = w
    sk = np.zeros((TH, TW, 1), np.float32)
    sk[ty, tx] = _skin(col)[:, None]
    mk = changed.copy()
    wm, _ = _spread(wm, np.zeros((TH, TW), bool) | (wm[..., 0] > 0))
    sk, _ = _spread(sk, mk.copy())
    if progress:
        progress(0.9)
    buf = io.BytesIO()
    Image.fromarray(out).save(buf, "PNG", compress_level=4)
    pics = [(M["image"], buf.getvalue())] + [x for x in _adjust_orm(M, wm[..., 0], sk[..., 0]) if x[0] != M["image"]]
    g, b = M["g"], M["b"]
    for ii, data in pics:
        new = replace_image(g, b, ii, data)
        g, b = glbscene.read(new)
    info = {"iou": round(v, 3), "pat": round(pat, 3), "cam": cam.name, "texels": int((w[:, 0] > 0.5).sum()), "face": bool(fbox),
            "skin": round(float(sk.mean()), 3)}
    if head is not None:
        try:
            new, hi = head_split(new, cam, head, head_size, n, visible, soft, photo_rgb, fbox, (W0, H0), x, y, d, log)
            info.update(hi)
        except Exception as e:  # noqa: BLE001 — 머리 텍스처는 덤: 실패하면 한 장 텍스처 그대로
            info["head_error"] = str(e)[:120]
            if log:
                log("[머리 텍스처 실패]", repr(e))
    if progress:
        progress(1.0)
    return new, info


# ───────────────────────── 머리 전용 텍스처 ─────────────────────────
# 게임 회사들은 머리를 따로 떼어 자기 텍스처를 줘요(카메라에 가까이 잡히는 얼굴에 해상도를 몰아줘요).
# 몸 전체가 텍스처 한 장을 나눠 쓰면 얼굴 몫은 5% 남짓이라, 사진을 아무리 키워 붙여도 그 크기로 줄어들어요.
# 머리 둘레를 원통처럼 펼치되 앞쪽 반(±90°)에 가로 70% 를 줘요 → 얼굴이 텍스처의 절반 가까이를 써요.
HEAD_BOX = (1.05, 0.95, 0.3)     # 얼굴 크기 기준 머리 상자: 좌우 반폭, 위로(머리카락), 아래로(턱·목)
HEAD_DEPTH = (0.6, 1.7)          # 얼굴 앞면 깊이 기준 앞쪽·뒤쪽 범위(얼굴 크기 배수)


def _head_uv(Q, cam, hmin, hmax):
    """머리 가운데 기준 좌표 → (u, v). 앞(카메라 쪽)이 u=0.5, 뒤가 u=0/1(이음새)."""
    a, bb, h = Q @ cam.r, Q @ cam.b, Q @ cam.u
    th = np.arctan2(a, bb)
    hp = np.pi / 2
    u = np.where(np.abs(th) <= hp, 0.5 + 0.35 * th / hp, np.where(th > 0, 0.85 + 0.15 * (th - hp) / hp, 0.15 + 0.15 * (th + hp) / hp))
    v = (hmax - h) / max(1e-9, hmax - hmin)
    return u, np.clip(v, 0.002, 0.998)


def _frames(P3, UV3, N):
    """삼각형마다 텍스처 방향(접선 T, 종접선 B) — glTF 규칙(B 는 텍스처 위쪽 = -v). N 은 점마다 법선(정규화)."""
    e1, e2 = P3[:, 1] - P3[:, 0], P3[:, 2] - P3[:, 0]
    d1, d2 = UV3[:, 1] - UV3[:, 0], UV3[:, 2] - UV3[:, 0]
    r = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(r) < 1e-12, 1e-12, r)
    Tu = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / r[:, None]
    Bv = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / r[:, None]
    return Tu, -Bv


def _tbn(Tu, Bu, N):
    """점마다: 법선 N 에 맞춰 T 를 곧게 세우고 B 는 방향(손잡이)만 따라요."""
    T = Tu - N * (Tu * N).sum(1, keepdims=True)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    B = np.cross(N, T)
    sgn = np.sign((B * Bu).sum(1, keepdims=True))
    return T, B * np.where(sgn == 0, 1, sgn)


def _img_of(g, b, tex_index):
    im = g["images"][g["textures"][tex_index]["source"]]
    v = g["bufferViews"][im["bufferView"]]
    return Image.open(io.BytesIO(b[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]))


def _png(arr):
    buf = io.BytesIO()
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(buf, "PNG", compress_level=4)
    return buf.getvalue()


def head_split(glb, cam, fbox_px, TS, n_face, visible, soft, photo_rgb, fbox, size, px, py, pd, log=None):
    """사진을 붙인 GLB → 머리를 따로 떼어 자기 텍스처(TS×TS: 색·노멀·그늘/거칠기)를 준 GLB. → (GLB, 정보)"""
    M = load(glb)
    g, b, P, F, UV, N = M["g"], M["b"], M["P"], M["F"], M["UV"], M["N"]
    W0, H0 = size
    x0, y0, x1, y1 = fbox_px
    fs = max(x1 - x0, y1 - y0)
    cxp, cyp = (x0 + x1) / 2, (y0 + y1) / 2
    hx0, hx1 = cxp - HEAD_BOX[0] * fs, cxp + HEAD_BOX[0] * fs
    hy0, hy1 = y0 - HEAD_BOX[1] * fs, y1 + HEAD_BOX[2] * fs
    # 얼굴 앞면 깊이와 얼굴 크기(3D 단위): 얼굴 상자 안에서 보이는 정점들
    inf = (px > x0) & (px < x1) & (py > y0) & (py < y1) & visible(px, py, pd)
    if inf.sum() < 20:
        raise ValueError("얼굴 부분의 3D 를 찾지 못했어요")
    Qf = P[inf] - P[inf].mean(0)
    fw = max(np.ptp(Qf @ cam.r), np.ptp(Qf @ cam.u))
    zf = float(np.percentile(pd[inf], 10))
    zr = fw
    cen = P[F].mean(1)
    cx, cy, cd = cam.px(cen)
    sel = (cx > hx0) & (cx < hx1) & (cy > hy0) & (cy < hy1) & (cd > zf - HEAD_DEPTH[0] * zr) & (cd < zf + HEAD_DEPTH[1] * zr)
    if sel.sum() < 50 or sel.mean() > 0.85:
        raise ValueError("머리 부분을 고르지 못했어요")
    hf = np.nonzero(sel)[0]
    FH = F[hf]
    P3 = P[FH]                                         # (Mh, 3, 3) 머리 삼각형 모서리
    ctr = P3.reshape(-1, 3).mean(0)
    hh = (P3.reshape(-1, 3) - ctr) @ cam.u
    hmin, hmax = hh.min(), hh.max()
    u, v = _head_uv(P3.reshape(-1, 3) - ctr, cam, hmin, hmax)
    U3, V3 = u.reshape(-1, 3), v.reshape(-1, 3)
    seam = U3.max(1) - U3.min(1) > 0.5                 # 뒤쪽 이음새를 넘는 삼각형: 작은 쪽을 +1(텍스처는 가로로 되풀이)
    U3 = np.where(seam[:, None] & (U3 < 0.5), U3 + 1, U3)
    NUV3 = np.stack([U3, V3], -1)                      # (Mh, 3, 2)
    OUV3 = UV[FH]
    N3 = N[FH] if N is not None else np.repeat(n_face[hf][:, None], 3, 1)
    # 새 텍스처 화소마다 → 머리 삼각형·무게중심 (이음새 삼각형은 한 칸 왼쪽에도 한 번 더)
    tri_xy = NUV3 * TS
    ids = np.arange(len(hf))
    extra = np.nonzero(seam)[0]
    xy = np.concatenate([tri_xy.reshape(-1, 2), (tri_xy[extra] - [TS, 0]).reshape(-1, 2)])
    owner = np.concatenate([ids, extra])
    FF = np.arange(len(xy)).reshape(-1, 3)
    mat = dict(M["mat"] or {})
    pbr = dict(mat.get("pbrMetallicRoughness") or {})
    base = np.asarray(M["tex"].convert("RGB")).astype(np.float32)
    BH, BW = base.shape[:2]
    has_nm = mat.get("normalTexture") is not None
    if has_nm:
        nm = np.asarray(_img_of(g, b, mat["normalTexture"]["index"]).convert("RGB")).astype(np.float32)
        To, Bo = _frames(P3, OUV3, None)
        Tn, Bn = _frames(P3, NUV3, None)
        nt = np.zeros((TS, TS, 3), np.float32)
        nt[...] = (127.5, 127.5, 255)
    tex = np.zeros((TS, TS, 3), np.float32)
    done = np.zeros((TS, TS), bool)
    CH = 20000                                         # 삼각형을 나눠 처리해요(4096 텍스처도 메모리를 적게)
    for k0 in range(0, len(FF), CH):
        tp, tf, c0, c1 = raster(xy, FF[k0:k0 + CH], TS, TS)
        if not len(tp):
            continue
        t = owner[tf + k0]
        c = np.stack([c0, c1, 1 - c0 - c1], 1)
        X = (P3[t] * c[..., None]).sum(1)
        ouv = (OUV3[t] * c[..., None]).sum(1)
        Nn = (N3[t] * c[..., None]).sum(1)
        Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-12)
        ty, tx = np.divmod(tp, TS)
        # 색: 원래 텍스처(사진을 이미 붙인 것)에서 옮기고, 사진에서 보이는 곳은 사진·얼굴 확대본에서 다시(이번엔 머리 텍스처 해상도로)
        col = _sample(base, ouv[:, 0] * BW, ouv[:, 1] * BH)
        sx, sy, sd = cam.px(X)
        ok = visible(sx, sy, sd) & (sx >= 0) & (sy >= 0) & (sx < W0) & (sy < H0)
        if ok.any():
            cs = np.abs((n_face[hf][t[ok]] * cam.view(X[ok])).sum(1))
            w = np.clip((cs - FACING[0]) / (FACING[1] - FACING[0]), 0, 1)
            w = (w * w * (3 - 2 * w))[:, None].astype(np.float32) * _sample(soft, sx[ok], sy[ok])
            pc = _sample(photo_rgb, sx[ok], sy[ok])
            if fbox:
                fx0, fy0, fx1, fy1, fa = fbox
                q = (sx[ok] > fx0) & (sx[ok] < fx1) & (sy[ok] > fy0) & (sy[ok] < fy1)
                if q.any():
                    kx, ky = fa.shape[1] / (fx1 - fx0), fa.shape[0] / (fy1 - fy0)
                    fc = _sample(fa, (sx[ok][q] - fx0) * kx, (sy[ok][q] - fy0) * ky)
                    ex = np.minimum.reduce([sx[ok][q] - fx0, fx1 - sx[ok][q], sy[ok][q] - fy0, fy1 - sy[ok][q]]) / max(1.0, 0.08 * (fx1 - fx0))
                    fwq = np.clip(ex, 0, 1)[:, None].astype(np.float32)
                    pc[q] = pc[q] * (1 - fwq) + fc * fwq
            col[ok] = col[ok] + (pc - col[ok]) * w
        tex[ty, tx], done[ty, tx] = col, True
        if has_nm:                                     # 노멀맵: 원래 텍스처 방향 → 세상 방향 → 새 텍스처 방향으로 옮겨요
            ns = _sample(nm, ouv[:, 0] * nm.shape[1], ouv[:, 1] * nm.shape[0]) / 127.5 - 1
            T1, B1 = _tbn(To[t], Bo[t], Nn)
            T2, B2 = _tbn(Tn[t], Bn[t], Nn)
            wv = ns[:, 0:1] * T1 + ns[:, 1:2] * B1 + ns[:, 2:3] * Nn
            nn = np.stack([(wv * T2).sum(1), (wv * B2).sum(1), (wv * Nn).sum(1)], 1)
            nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
            nt[ty, tx] = (nn + 1) * 127.5
    del base
    tex, dn = _spread(tex, done.copy(), 3)
    imgs = [("base", tex)]
    if has_nm:
        nt, _ = _spread(nt, done, 3)
        imgs.append(("normal", nt))
    # 그늘·거칠기·금속(ORM) 은 같은 자리 값을 옮겨요
    mrt = (pbr.get("metallicRoughnessTexture") or {}).get("index")
    occ = (mat.get("occlusionTexture") or {}).get("index")
    orm_src = {}
    for key, ti in (("mr", mrt), ("ao", occ)):
        if ti is not None:
            orm_src.setdefault(g["textures"][ti]["source"], []).append(key)
    orm_new = {}
    for ii, keys in orm_src.items():
        pic = np.asarray(_img_of(g, b, next(ti for ti in (mrt, occ) if ti is not None and g["textures"][ti]["source"] == ii)).convert("RGB")).astype(np.float32)
        hs = max(1024, TS // 2)
        k = hs / TS
        arr = np.zeros((hs, hs, 3), np.float32)
        dd = np.zeros((hs, hs), bool)
        for k0 in range(0, len(FF), CH):
            tp2, tf2, d0, d1 = raster(xy * k, FF[k0:k0 + CH], hs, hs)
            if not len(tp2):
                continue
            t2 = owner[tf2 + k0]
            cc = np.stack([d0, d1, 1 - d0 - d1], 1)
            o2 = (OUV3[t2] * cc[..., None]).sum(1)
            y2, x2 = np.divmod(tp2, hs)
            arr[y2, x2], dd[y2, x2] = _sample(pic, o2[:, 0] * pic.shape[1], o2[:, 1] * pic.shape[0]), True
        arr, _ = _spread(arr, dd, 3)
        orm_new[ii] = ("orm" + str(ii), arr, keys)
        imgs.append(("orm" + str(ii), arr))
    # 새 머리 그물망(삼각형마다 정점 3개 — 이음새·새 텍스처 좌표 때문에 따로)
    if not np.allclose(_world(g, M["node"]), np.eye(4)):    # ComfyUI 결과는 노드 변환이 없어요 — 있으면 손대지 않아요
        raise ValueError("노드 변환이 있는 3D 예요")
    Ph = P3.reshape(-1, 3).astype(np.float32)
    Nh = N3.reshape(-1, 3).astype(np.float32)
    UVh = NUV3.reshape(-1, 2).astype(np.float32)
    keep = np.ones(len(F), bool)
    keep[hf] = False
    body_idx = F[keep].astype(np.uint32).tobytes()
    head_idx = np.arange(len(Ph), dtype=np.uint32).tobytes()
    adds = [Ph.tobytes(), UVh.tobytes(), head_idx] + ([Nh.tobytes()] if M["N"] is not None else []) + [_png(a) for _, a in imgs]
    pr = M["prim"]
    g2, b2, nv = rebuild(g, b, {g["accessors"][pr["indices"]]["bufferView"]: body_idx}, adds)
    acc = [dict(x) for x in g2["accessors"]]
    ia = dict(acc[pr["indices"]])
    ia.update(componentType=5125, count=int(keep.sum()) * 3, byteOffset=0)
    ia.pop("min", None), ia.pop("max", None)
    acc[pr["indices"]] = ia
    base_acc = len(acc)
    acc += [{"bufferView": nv[0], "componentType": 5126, "count": len(Ph), "type": "VEC3", "min": Ph.min(0).tolist(), "max": Ph.max(0).tolist()},
            {"bufferView": nv[1], "componentType": 5126, "count": len(UVh), "type": "VEC2"},
            {"bufferView": nv[2], "componentType": 5125, "count": len(Ph), "type": "SCALAR"}]
    attrs = {"POSITION": base_acc, "TEXCOORD_0": base_acc + 1}
    vi = 3
    if M["N"] is not None:
        acc.append({"bufferView": nv[3], "componentType": 5126, "count": len(Nh), "type": "VEC3"})
        attrs["NORMAL"] = base_acc + 3
        vi = 4
    g2["accessors"] = acc
    g2["images"] = [dict(x) for x in g2["images"]] + [{"bufferView": nv[vi + i], "mimeType": "image/png"} for i in range(len(imgs))]
    g2["samplers"] = [dict(x) for x in g2.get("samplers") or []] + [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 33071}]
    smp = len(g2["samplers"]) - 1
    tex0 = len(g2["textures"])
    g2["textures"] = [dict(x) for x in g2["textures"]] + [{"source": len(g2["images"]) - len(imgs) + i, "sampler": smp} for i in range(len(imgs))]
    tid = {name: tex0 + i for i, (name, _) in enumerate(imgs)}
    hm = json.loads(json.dumps(mat))
    hm["name"] = (mat.get("name") or "material") + "_head"
    hp = hm.setdefault("pbrMetallicRoughness", {})
    hp["baseColorTexture"] = {"index": tid["base"]}
    if "normal" in tid:
        hm["normalTexture"] = {**(mat.get("normalTexture") or {}), "index": tid["normal"], "texCoord": 0}
    for ii, (name, _, keys) in orm_new.items():
        if "mr" in keys:
            hp["metallicRoughnessTexture"] = {"index": tid[name]}
        if "ao" in keys:
            hm["occlusionTexture"] = {**(mat.get("occlusionTexture") or {}), "index": tid[name], "texCoord": 0}
    g2["materials"] = [dict(x) for x in g2["materials"]] + [hm]
    meshes = [dict(x) for x in g2["meshes"]]
    mi = g2["nodes"][M["node"]]["mesh"]
    meshes[mi] = {**meshes[mi], "primitives": [dict(x) for x in meshes[mi]["primitives"]] + [{"attributes": attrs, "indices": base_acc + 2, "material": len(g2["materials"]) - 1}]}
    g2["meshes"] = meshes
    if log:
        log(f"[머리 텍스처] 삼각형 {len(hf):,}개 · {TS}px · 이음새 {int(seam.sum())}")
    return glbscene.write(g2, b2), {"head": True, "head_tris": int(len(hf)), "head_tex": TS}
