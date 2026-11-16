"""얼굴 3D 형상 보정(실험) — 사진 속 얼굴 특징(눈·코·입·턱선)에 맞게 3D 얼굴의 정점을 실제로 옮겨요.

왜 필요한가: 사진을 3D 에 붙이면 정면에서는 언제나 사진처럼 보여요. 하지만 3D 엔진이 만든 얼굴 모양(코가 솟은 자리, 눈이 들어간 자리)이
사진 속 눈·코·입 자리와 다르면, 사진의 코가 3D 의 볼에 칠해져서 옆으로 돌렸을 때 얼굴이 일그러져 보여요.
텍스처를 더 휘는 대신, 3D 모양 쪽을 사진에 맞춰 옮겨요.

방법(모두 CPU · numpy):
 1. 랜드마크 두 벌: '3D 모양 쪽' = 엔진이 칠한 원래 얼굴을 사진 카메라로 그린 그림에서, '목표' = 사진을 붙인 결과를 같은 카메라로 그린 그림에서.
    (랜드마크 그림은 ComfyUI 의 MediaPipe 노드가 부위마다 다른 색 선으로 그려 줘요 — landmarks() 가 그 그림을 읽어요.)
 2. 두 벌의 차이(사진 화소 단위)를 얇은 판 스플라인(TPS)으로 얼굴 전체에 매끈하게 퍼뜨려요.
 3. 얼굴 윤곽 안쪽·얼굴 겉면 가까이에만 적용해요(윤곽으로 갈수록, 깊이 들어갈수록 0 — 머리카락·귀·목·뒤통수는 그대로).
 4. 그물망 이웃끼리 한 번 더 고르고(라플라시안 평활), 면이 뒤집히면 세기를 줄여요.
 5. 정점을 카메라 화면과 나란한 방향으로 옮기되, 머리의 큰 둥근 모양(원래 3D 의 매끈한 깊이)은 제자리에 두고 굴곡(코·눈·입의 잔 깊이)만 함께 옮겨요.
    새 깊이를 지어내지 않아요 — 사진 한 장으로는 깊이를 알 수 없으니, 깊이는 모두 원래 3D 에서 가져와요.
 6. 삼각형 구조·UV 는 그대로, 법선·접선만 따라 돌려요. 옮긴 뒤 검사(뒤집힘·퇴화·바깥 정점·이음새)를 통과해야 써요.
"""
import hashlib
import io
import math

import numpy as np
from PIL import Image, ImageDraw

import glbscene
import photoproj

# 부위마다 다른 색 선(ComfyUI MediaPipeFaceMeshVisualize 의 부위 이름 그대로)
FEATURES = (("face_oval", (255, 0, 0)), ("lips", (0, 255, 0)), ("left_eye", (0, 0, 255)), ("right_eye", (255, 255, 0)),
            ("left_eyebrow", (255, 0, 255)), ("right_eyebrow", (0, 255, 255)), ("irises", (255, 128, 0)), ("nose", (128, 0, 255)))
ALL_FEATURES = tuple(n for n, _ in FEATURES) + ("tesselation",)
DET = 640                # 랜드마크를 찾는 얼굴 그림 크기(px)
REGION = 1.7             # 얼굴 상자의 이 배수만큼 잘라서 봐요
MIN_IOD = 0.07           # 눈 사이 거리가 그림 크기의 이 비율보다 작으면 얼굴이 너무 작아요
OVAL_N = 16              # 얼굴 윤곽에서 뽑는 점 개수(방향별)
MIN_NEED = 0.02          # 3D 모양과 목표의 차이(눈 사이 거리 대비)가 이보다 작으면 보정하지 않아요
MAX_MEDIAN = 0.30        # 차이의 가운데값이 이보다 크면 보정하지 않아요(고개 방향이 다른 것 — 옮겨서 맞출 수 없어요)
CAP = 0.35               # 랜드마크 하나가 옮길 수 있는 최대(눈 사이 거리 대비)
LAM = 0.05               # TPS 고르기 세기(클수록 매끈, 랜드마크를 덜 정확히 따라가요)
FALL = 0.35              # 윤곽에서 이만큼(눈 사이 거리 대비) 안쪽까지 0 → 1 로 올라가요
GROW = (0.05, 0.08)      # 윤곽을 바깥으로 넓히는 정도: 옆 · 턱(눈 사이 거리 대비) — 위(이마·머리카락)는 넓히지 않아요.
                         # 턱 아래로 넓히면 목이 같이 움직여서 조금만(턱선은 윤곽 안쪽까지만 보정돼요)
DEPTH = (0.15, 0.5)      # 얼굴 겉면에서 이만큼 뒤까지는 온전히, 그 뒤로 줄어들어 0(눈 사이 거리 대비)
SMOOTH = (5, 0.5)        # 그물망 이웃 고르기: 횟수 · 섞는 정도
BASE_DEG = 3             # '머리의 큰 모양' = 얼굴 겉면 깊이에 맞춘 매끈한 곡면(이 차수의 다항식) — 코·눈 같은 굴곡은 여기서 빠져요
MIN_GAIN = 0.85          # 보정 뒤 랜드마크 오차가 보정 전의 이 비율 이하여야 채택해요
MAX_PASS = 3             # 재기 → 옮기기를 되풀이하는 최대 횟수
MAX_ROT = 40.0           # 면 방향이 이보다 많이 도는 면이 1% 를 넘으면 표면이 구겨진 것으로 봐요(도)


class FitError(Exception):
    """보정하지 않고 기존 결과로 돌아가야 하는 경우(이유가 메시지)."""


# ───────────────────────── 랜드마크 ─────────────────────────
def region_of(box):
    """얼굴 상자(x0, y0, x1, y1) → 정사각형 영역 (x0, y0, 한 변) — 사진 좌표."""
    x0, y0, x1, y1 = box
    side = REGION * max(x1 - x0, y1 - y0)
    return ((x0 + x1) / 2 - side / 2, (y0 + y1) / 2 - side / 2, side)


def crop_photo(photo, region, face=None):
    """사진의 얼굴 영역을 DET×DET 로(배경은 회색). face = (x0, y0, x1, y1, 키운 그림) 이 있으면 그 부분은 키운 그림으로(더 선명)."""
    x0, y0, side = region
    bg = Image.new("RGB", photo.size, (128, 128, 128))
    bg.paste(photo.convert("RGB"), mask=photo.getchannel("A") if photo.mode == "RGBA" else None)
    out = bg.transform((DET, DET), Image.EXTENT, (x0, y0, x0 + side, y0 + side), Image.BICUBIC, fillcolor=(128, 128, 128))
    if face is not None:
        fx0, fy0, fx1, fy1, big = face
        k = DET / side
        if big.width / max(1.0, fx1 - fx0) > k:           # 키운 그림이 더 촘촘할 때만
            w, h = max(1, round((fx1 - fx0) * k)), max(1, round((fy1 - fy0) * k))
            fb = Image.new("RGB", big.size, (128, 128, 128))
            fb.paste(big.convert("RGB"), mask=big.getchannel("A") if big.mode == "RGBA" else None)
            out.paste(fb.resize((w, h), Image.LANCZOS), (round((fx0 - x0) * k), round((fy0 - y0) * k)))
    return out


def render(glb, cam, region, size=DET, bg=128, want_depth=False):
    """GLB 를 사진 카메라(cam)로 본 얼굴 영역 그림(텍스처 색 그대로, 음영 없음) → PIL (want_depth 면 (PIL, 깊이 배열))."""
    x0, y0, side = region
    k = size / side
    sc = photoproj._scene(glb, 4096)
    Ps, Fs, starts, off, n0 = [], [], [0], 0, 0
    for P, F, *_ in sc:
        Ps.append(P)
        Fs.append(F + off)
        off += len(P)
        n0 += len(F)
        starts.append(n0)
    P, F = np.concatenate(Ps), np.concatenate(Fs)
    x, y, d = cam.px(P)
    gx, gy = (x - x0) * k, (y - y0) * k
    near = ((gx[F] > -2) & (gx[F] < size + 2) & (gy[F] > -2) & (gy[F] < size + 2)).any(1)
    sel = np.nonzero(near)[0]
    out = np.full((size * size, 3), float(bg), np.float32)
    dep = np.full(size * size, np.inf)
    if len(sel):
        pix, fid, b0, b1 = photoproj.raster(np.stack([gx, gy], 1), F[sel], size, size, d)
        f = sel[fid]
        b2 = 1 - b0 - b1
        dep[pix] = d[F[f, 0]] * b0 + d[F[f, 1]] * b1 + d[F[f, 2]] * b2
        for i, (Pi, Fi, UV, _, T, fac) in enumerate(sc):
            m = (f >= starts[i]) & (f < starts[i + 1])
            if not m.any():
                continue
            if T is None or UV is None:
                out[pix[m]] = fac
                continue
            fl = Fi[f[m] - starts[i]]
            uv = UV[fl[:, 0]] * b0[m, None] + UV[fl[:, 1]] * b1[m, None] + UV[fl[:, 2]] * b2[m, None]
            out[pix[m]] = photoproj._sample(T, (uv[:, 0] % 1.0) * T.shape[1], np.clip(uv[:, 1], 0, 1) * T.shape[0]) * fac / 255
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8).reshape(size, size, 3))
    return (im, dep.reshape(size, size)) if want_depth else im


LINE_SETS = (tuple(n for n, _ in FEATURES if n != "irises"), ("irises",))      # 홍채 선은 눈 선과 겹쳐서 따로 그려요(겹치면 눈 가운데가 치우쳐요)
LM_WEIGHT = {"left_eye": 1.0, "right_eye": 1.0, "iris": 1.0, "nose": 1.0, "lips": 1.0, "left_eyebrow": 0.5, "right_eyebrow": 0.5, "oval": 0.3}   # 믿는 정도


def landmarks(imgs):
    """부위마다 다른 색 선으로 그린 그림(FEATURES 색, 한 장 또는 여러 장) → 랜드마크.
    → {"ok": bool, "why": 이유, "pts": {이름: [x, y]}, "iod": 눈 사이 거리, "ex"/"ey": 얼굴의 가로·세로 방향, "counts": 부위별 화소 수}
    같은 방법으로 두 그림에서 뽑으니 이름이 같은 점끼리 짝이에요(눈 가운데·눈꼬리·눈썹 끝·콧방울·코끝·입꼬리·입술 위아래·윤곽 방향별 점)."""
    if isinstance(imgs, Image.Image):
        imgs = [imgs]
    arrs = [np.asarray(im.convert("RGB")).astype(np.int16) for im in imgs]
    W = arrs[0].shape[1]
    S = {}
    for name, col in FEATURES:
        got = [np.nonzero(np.abs(a - np.array(col, np.int16)).max(2) <= 40) for a in arrs]
        ys, xs = max(got, key=lambda v: len(v[0]))      # 그 색이 가장 많이 그려진 그림에서
        S[name] = np.stack([xs + 0.5, ys + 0.5], 1).astype(np.float64)
    out = {"ok": False, "pts": {}, "counts": {n: int(len(p)) for n, p in S.items()}}
    miss = [n for n in ("face_oval", "lips", "left_eye", "right_eye", "nose") if len(S[n]) < 12]
    if miss:
        out["why"] = "얼굴을 찾지 못했어요" if len(miss) == 5 else "얼굴 부위를 찾지 못했어요(" + ", ".join(miss) + ")"
        return out
    ca, cb = S["left_eye"].mean(0), S["right_eye"].mean(0)
    if ca[0] > cb[0]:
        ca, cb = cb, ca                                   # ca = 그림에서 왼쪽 눈
    iod = float(np.linalg.norm(cb - ca))
    out["iod"] = iod
    if iod < MIN_IOD * W:
        out["why"] = "얼굴이 너무 작아요"
        return out
    ex = (cb - ca) / iod
    ey = np.array([-ex[1], ex[0]])                        # 그림 아래쪽
    mid = (ca + cb) / 2
    pts = {}

    def ext(p, axis, sign, k=3):
        v = p @ axis * sign
        return p[np.argsort(v)[-min(k, len(p)):]].mean(0)

    def vext(p, sign, k=3):
        """위(−1)·아래(+1) 끝: 세로 자리는 끝의 것, 가로 자리는 부위 가운데(끝이 평평하면 가로로 튀어서)"""
        e = ext(p, ey, sign, k)
        c = p.mean(0)
        return c + ey * float((e - c) @ ey)

    for nm in ("left_eye", "right_eye"):
        p = S[nm]
        pts[nm + ".c"], pts[nm + ".x0"], pts[nm + ".x1"] = p.mean(0), ext(p, ex, -1), ext(p, ex, 1)
        pts[nm + ".y0"], pts[nm + ".y1"] = vext(p, -1), vext(p, 1)
    p = S["irises"]
    if len(p) >= 12:
        side = (p - mid) @ ex
        if (side < 0).sum() >= 5 and (side > 0).sum() >= 5:
            pts["iris.a"], pts["iris.b"] = p[side < 0].mean(0), p[side > 0].mean(0)
    for nm in ("left_eyebrow", "right_eyebrow"):
        p = S[nm]
        if len(p) >= 8:
            pts[nm + ".c"], pts[nm + ".x0"], pts[nm + ".x1"] = p.mean(0), ext(p, ex, -1), ext(p, ex, 1)
    p = S["nose"]
    v = p @ ey
    pts["nose.x0"], pts["nose.x1"], pts["nose.y0"], pts["nose.y1"] = ext(p, ex, -1), ext(p, ex, 1), vext(p, -1), vext(p, 1)
    pts["nose.tip"] = p[v >= v.min() + 0.7 * (v.max() - v.min())].mean(0)
    p = S["lips"]
    pts["lips.c"], pts["lips.x0"], pts["lips.x1"], pts["lips.y0"], pts["lips.y1"] = p.mean(0), ext(p, ex, -1), ext(p, ex, 1), vext(p, -1), vext(p, 1)
    p = S["face_oval"]
    c = p.mean(0)
    q = p - c
    ang, rad = np.arctan2(q @ ey, q @ ex), np.linalg.norm(q, axis=1)       # 0 = 그림 오른쪽, 90° = 아래(턱)
    for k in range(OVAL_N):
        t = 2 * math.pi * k / OVAL_N
        df = np.abs((ang - t + math.pi) % (2 * math.pi) - math.pi)
        m = df < math.pi / OVAL_N
        if m.sum() >= 2:                                   # 그 방향으로 윤곽까지의 거리만 쓰고, 점은 방향선 위에 놓아요(윤곽을 따라 미끄러지지 않게)
            r = float(np.sort(rad[m])[-min(3, int(m.sum())):].mean())
            pts[f"oval.{k:02d}"] = c + r * (math.cos(t) * ex + math.sin(t) * ey)
    if sum(1 for n in pts if n.startswith("oval.")) < OVAL_N - 4:
        out["why"] = "얼굴 윤곽을 다 찾지 못했어요"
        return out
    out.update(ok=True, pts={n: [float(v[0]), float(v[1])] for n, v in pts.items()}, ex=[float(ex[0]), float(ex[1])], ey=[float(ey[0]), float(ey[1])],
               center=[float(c[0]), float(c[1])])
    return out


def to_photo(L, region):
    """DET 그림 좌표의 랜드마크 → 사진 좌표."""
    if not L.get("ok"):
        return L
    x0, y0, side = region
    k = side / DET
    return {**L, "pts": {n: [x0 + v[0] * k, y0 + v[1] * k] for n, v in L["pts"].items()}, "iod": L["iod"] * k,
            "center": [x0 + L["center"][0] * k, y0 + L["center"][1] * k]}


GROUPS = (("eyes", ("left_eye", "right_eye", "iris")), ("brows", ("left_eyebrow", "right_eyebrow")), ("nose", ("nose",)), ("lips", ("lips",)), ("outline", ("oval",)))


def lm_error(La, Lb):
    """두 랜드마크의 차이(눈 사이 거리 대비) → {"mean", "max", "n", 부위별} 또는 None(잴 수 없음)."""
    if not (La and Lb and La.get("ok") and Lb.get("ok")):
        return None
    keys = sorted(set(La["pts"]) & set(Lb["pts"]))
    if len(keys) < 12:
        return None
    d = np.linalg.norm(np.array([La["pts"][k] for k in keys]) - np.array([Lb["pts"][k] for k in keys]), axis=1) / Lb["iod"]
    out = {"mean": round(float(d.mean()), 4), "max": round(float(d.max()), 4), "n": len(keys)}
    for g, pre in GROUPS:
        m = np.array([k.split(".")[0] in pre for k in keys])
        if m.any():
            out[g] = round(float(d[m].mean()), 4)
    return out


# ───────────────────────── 부위별 무늬 맞추기(랜드마크 보조) ─────────────────────────
# 얼굴 랜드마크 모델은 '보통 얼굴 모양'을 깔고 맞추기 때문에, 엔진이 칠한 흐린 얼굴에서는 코·입이 위아래로 어긋난 것을 잘 못 잡아요.
# 그래서 눈·코·입 부위마다 목표 그림의 그 부분이 엔진 그림의 어디에 있는지 무늬(밝기 모양)로 직접 찾아요(옮기기만, ±RANGE).
REFINE_RANGE = 0.22      # 찾는 범위(눈 사이 거리 대비)
REFINE_PAD = 0.12        # 부위 상자 둘레 여유(눈 사이 거리 대비)
REFINE_MIN = (0.45, 0.04)   # 믿을 만한 일치도(NCC) · 다음으로 잘 맞는 곳과의 차이
REFINE_BLURS = (1.5, 3.0, 5.0)


def _gray(img):
    a = np.asarray(img.convert("RGB")).astype(np.float64)
    return 0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2]


def _match(E, T, box, rng):
    """T 의 상자 부분이 E 에서 어디로 옮겨져 있나 → (dx, dy, 일치도, 둘째와의 차이). E[y + dy, x + dx] ≈ T[y, x]"""
    from numpy.lib.stride_tricks import sliding_window_view
    x0, y0, x1, y1 = box
    H, W = T.shape
    rng = int(min(rng, x0, y0, W - x1, H - y1))
    if rng < 2 or x1 - x0 < 6 or y1 - y0 < 6:
        return None
    t = T[y0:y1, x0:x1]
    hh, ww = t.shape                                        # 상자 가운데에 무게를 더 줘요(둘레의 볼·윗입술은 다르게 움직일 수 있어서)
    gy, gx = np.mgrid[0:hh, 0:ww]
    wgt = np.exp(-0.5 * (((gx - (ww - 1) / 2) / (0.35 * ww)) ** 2 + ((gy - (hh - 1) / 2) / (0.35 * hh)) ** 2))
    sw = float(wgt.sum())
    t = t - float((t * wgt).sum()) / sw
    tn = math.sqrt(float((t * t * wgt).sum())) + 1e-9
    win = sliding_window_view(E[y0 - rng:y1 + rng, x0 - rng:x1 + rng], t.shape)      # (2r+1, 2r+1, h, w)
    mu = np.einsum("abhw,hw->ab", win, wgt) / sw
    num = np.einsum("abhw,hw->ab", win, wgt * t)
    den = np.sqrt(np.maximum(np.einsum("abhw,abhw,hw->ab", win, win, wgt) - mu * mu * sw, 1e-12))
    ncc = num / (den * tn)
    iy, ix = np.unravel_index(int(np.argmax(ncc)), ncc.shape)
    best = float(ncc[iy, ix])
    yy, xx = np.mgrid[0:ncc.shape[0], 0:ncc.shape[1]]
    far = (np.abs(yy - iy) > 3) | (np.abs(xx - ix) > 3)
    second = float(ncc[far].max()) if far.any() else -1.0
    # 화소보다 잘게: 꼭대기 둘레를 포물선으로
    sub = [0.0, 0.0]
    for k, (i, n, sl) in enumerate(((ix, ncc.shape[1], ncc[iy]), (iy, ncc.shape[0], ncc[:, ix]))):
        if 0 < i < n - 1:
            a, b, c = sl[i - 1], sl[i], sl[i + 1]
            d = a - 2 * b + c
            if d < -1e-9:
                sub[k] = float(np.clip(0.5 * (a - c) / d, -0.5, 0.5))
    return ix - rng + sub[0], iy - rng + sub[1], best, best - second


def refine(Lg, Lt, eng_img, tgt_img):
    """부위별 무늬 맞추기로 3D 모양 쪽 랜드마크(Lg, DET 좌표)를 다듬어요. Lt = 목표 랜드마크, eng_img/tgt_img = 엔진·목표 그림(DET×DET).
    → (다듬은 Lg, 기록 {부위: {shift, score, margin, used, landmark_shift}})"""
    if not (Lg.get("ok") and Lt.get("ok")):
        return Lg, {}
    S = 2                                                   # 절반 크기에서 찾아요(빠르고, 엔진 그림이 흐려서 충분)
    small = lambda im: _gray(im.resize((im.width // S, im.height // S), Image.BILINEAR))
    E0, T0 = small(eng_img), small(tgt_img)
    iod = Lt["iod"] / S
    ca = np.array(Lt["pts"]["left_eye.c"])
    groups = {"left_eye": ["left_eye", "left_eyebrow"], "right_eye": ["right_eye", "right_eyebrow"], "nose": ["nose"], "lips": ["lips"]}
    for ir in ("iris.a", "iris.b"):                         # 홍채는 가까운 눈 묶음으로
        if ir in Lt["pts"]:
            near = "left_eye" if np.linalg.norm(np.array(Lt["pts"][ir]) - ca) < np.linalg.norm(np.array(Lt["pts"][ir]) - np.array(Lt["pts"]["right_eye.c"])) else "right_eye"
            groups[near] = groups[near] + [ir]
    pts, rec = dict(Lg["pts"]), {}
    El = photoproj._lcn(photoproj._gblur(E0, 1.0), 5.0)
    Ts = [photoproj._lcn(photoproj._gblur(T0, sb), 5.0) for sb in REFINE_BLURS]      # 엔진 그림은 더 흐려요 — 목표를 여러 정도로 흐려 보고 가장 잘 맞는 것
    for g, pre in groups.items():
        names = [k for k in Lt["pts"] if k.split(".")[0] in pre or k in pre]
        core = [k for k in names if k.split(".")[0] == pre[0]]
        if len(core) < 3:
            continue
        q = np.array([Lt["pts"][k] for k in core]) / S
        pad = REFINE_PAD * iod
        box = (int(max(0, q[:, 0].min() - pad)), int(max(0, q[:, 1].min() - pad)), int(min(T0.shape[1], q[:, 0].max() + pad)), int(min(T0.shape[0], q[:, 1].max() + pad)))
        cands = [m for m in (_match(El, Tb, box, int(round(REFINE_RANGE * iod))) for Tb in Ts) if m]
        if not cands:
            continue
        dx, dy, sc, mg = max(cands, key=lambda m: m[2])
        both = [k for k in names if k in Lg["pts"]]
        lm = np.mean([np.array(Lg["pts"][k]) - np.array(Lt["pts"][k]) for k in both], 0) if both else np.zeros(2)
        used = sc >= REFINE_MIN[0] and mg >= REFINE_MIN[1]
        rec[g] = {"shift": [round(float(dx) * S / Lt["iod"], 4), round(float(dy) * S / Lt["iod"], 4)], "score": round(float(sc), 3), "margin": round(float(mg), 3), "used": bool(used),
                  "landmark_shift": [round(float(lm[0]) / Lt["iod"], 4), round(float(lm[1]) / Lt["iod"], 4)]}
        if used:                                            # 그 부위는 '목표 모양 그대로, 이만큼 옮겨진 자리'에 있다고 봐요
            for k in names:
                pts[k] = [Lt["pts"][k][0] + dx * S, Lt["pts"][k][1] + dy * S]
    return {**Lg, "pts": pts}, rec


# ───────────────────────── 얇은 판 스플라인 ─────────────────────────
def _tps_u(r2):
    return np.where(r2 > 1e-18, 0.5 * r2 * np.log(np.maximum(r2, 1e-18)), 0.0)


def tps_fit(src, val, lam, wt=None):
    """src(n,2) 에서의 값 val(n,k) 를 매끈하게 잇는 얇은 판 스플라인. lam > 0 이면 점을 정확히 지나지 않고 고르게.
    wt(n): 점마다 믿는 정도(작을수록 덜 따라가요)."""
    n = len(src)
    K = _tps_u(((src[:, None] - src[None]) ** 2).sum(-1)) + np.diag(lam / np.maximum(np.ones(n) if wt is None else np.asarray(wt, float), 1e-3))
    Pm = np.concatenate([np.ones((n, 1)), src], 1)
    A = np.zeros((n + 3, n + 3))
    A[:n, :n], A[:n, n:], A[n:, :n] = K, Pm, Pm.T
    rhs = np.zeros((n + 3, val.shape[1]))
    rhs[:n] = val
    return src.copy(), np.linalg.solve(A, rhs)


def tps_eval(model, pts, chunk=20000):
    src, w = model
    out = np.zeros((len(pts), w.shape[1]))
    for i in range(0, len(pts), chunk):
        p = pts[i:i + chunk]
        U = _tps_u(((p[:, None] - src[None]) ** 2).sum(-1))
        out[i:i + chunk] = U @ w[:len(src)] + np.concatenate([np.ones((len(p), 1)), p], 1) @ w[len(src):]
    return out


# ───────────────────────── 그물망 도우미 ─────────────────────────
def _seg_dist(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-18), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def _inside(p, poly):
    x, y = p[:, 0], p[:, 1]
    ins = np.zeros(len(p), bool)
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if y1 == y2:
            continue
        c = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1)
        ins ^= c
    return ins


def _smoothstep(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def _weld(P, tol):
    q = np.round(P / tol).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    return inv.reshape(-1)


def _sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()[:16]


def _unproject(cam, px, py, dep):
    """사진 화소·깊이 → 3D 자리(Cam.px 의 거꾸로)."""
    xn, yn = (px - cam.t[0]) / cam.s, -(py - cam.t[1]) / cam.s
    if cam.D is None:
        return cam.ctr + xn[:, None] * cam.r + yn[:, None] * cam.u - dep[:, None] * cam.b
    return cam.ctr + (xn * dep / cam.D)[:, None] * cam.r + (yn * dep / cam.D)[:, None] * cam.u + (cam.D - dep)[:, None] * cam.b


def _poly_terms(q):
    """(n,2) → 다항식 항들(차수 BASE_DEG 까지)"""
    x, y = q[:, 0], q[:, 1]
    return np.stack([x ** i * y ** j for i in range(BASE_DEG + 1) for j in range(BASE_DEG + 1 - i)], 1)


def _wpp(cam, dep):
    """화소 하나가 그 깊이에서 3D 로 얼마인지."""
    return dep / (cam.s * cam.D) if cam.D is not None else np.full_like(dep, 1.0 / cam.s)


def _raw(g, b, ai, n, comp):
    """accessor 의 원래 float32 배열(복사본)과 덮어쓸 수 있는지."""
    a = g["accessors"][ai]
    bv = g["bufferViews"][a["bufferView"]]
    if a.get("componentType") != 5126 or a.get("sparse") or a.get("count") != n:
        raise FitError("정점 자료 형식이 달라서 고칠 수 없어요")
    st = bv.get("byteStride") or 4 * comp
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    arr = np.ndarray((n, comp), np.float32, buffer=b, offset=off, strides=(st, 4)).copy()
    alone = st == 4 * comp and a.get("byteOffset", 0) == 0 and bv["byteLength"] == n * 4 * comp and sum(1 for x in g["accessors"] if x.get("bufferView") == a["bufferView"]) == 1
    return arr, alone


# ───────────────────────── 형상 보정 ─────────────────────────
def fit(glb, cam, Lg, Lt, log=None):
    """엔진 원본 GLB 의 얼굴 정점을 옮겨요. Lg = 3D 모양 쪽 랜드마크, Lt = 목표 랜드마크(둘 다 사진 좌표, to_photo 를 거친 것).
    → (새 GLB, 기록). 옮기면 안 되는 경우는 FitError(이유)."""
    M = photoproj.load(glb)
    g, b, P, F, N, TG = M["g"], M["b"], M["P"], M["F"], M["N"], M["TG"]
    ext = float(np.linalg.norm(P.max(0) - P.min(0))) or 1.0
    iod = float(Lg["iod"])
    ex, ey = np.array(Lg["ex"]), np.array(Lg["ey"])
    cen = np.array(Lg["center"])
    keys = []
    for k in sorted(set(Lg["pts"]) & set(Lt["pts"])):
        if k.startswith("oval."):                         # 윤곽은 눈 높이 아래쪽(볼·턱)만 — 위쪽은 머리카락이라 믿을 수 없어요
            if (np.array(Lg["pts"][k]) - cen) @ ey < -0.15 * iod:
                continue
        keys.append(k)
    if len(keys) < 12:
        raise FitError("짝이 맞는 랜드마크가 모자라요")
    src = np.array([Lg["pts"][k] for k in keys])
    d = np.array([Lt["pts"][k] for k in keys]) - src
    mag = np.linalg.norm(d, axis=1) / iod
    st = {"landmarks_used": len(keys), "landmark_shift_median": round(float(np.median(mag)), 4), "landmark_shift_max": round(float(mag.max()), 4)}
    if np.median(mag) > MAX_MEDIAN:
        raise FitError(f"3D 얼굴과 사진 얼굴의 자리가 너무 많이 달라요(가운데값 {np.median(mag):.2f} × 눈 사이 거리) — 고개 방향이 다른 것으로 보여 옮기지 않았어요")
    # 혼자 튀는 랜드마크는 빼요(매끈한 흐름에서 크게 벗어난 것)
    sn = (src - cen) / iod
    wt = np.array([LM_WEIGHT.get(k.split(".")[0], 1.0) for k in keys])
    res = np.linalg.norm(d / iod - tps_eval(tps_fit(sn, d / iod, 1.0, wt), sn), axis=1)
    keep = res <= max(0.08, 3.0 * float(np.median(res)))
    if keep.sum() >= 12 and not keep.all():
        st["landmarks_dropped"] = [keys[i] for i in np.nonzero(~keep)[0]]
        sn, d, mag, wt = sn[keep], d[keep], mag[keep], wt[keep]
    d = d * np.minimum(1.0, CAP / np.maximum(mag, 1e-9))[:, None]
    model = tps_fit(sn, d / iod, LAM, wt)

    x, y, dep = cam.px(P)
    XY = np.stack([x, y], 1)
    # 보정 영역: 3D 모양 쪽 얼굴 윤곽을 턱·볼 쪽으로 조금 넓힌 다각형 안
    ov = sorted((k, np.array(v)) for k, v in Lg["pts"].items() if k.startswith("oval."))
    poly = []
    for _, p in ov:
        q = p - cen
        r = float(np.linalg.norm(q)) or 1.0
        dn = max(0.0, float(q @ ey) / r)                  # 아래(턱)일수록 1
        up = max(0.0, -float(q @ ey) / r)
        poly.append(cen + q * (1 + iod * (GROW[0] * (1 - up) + (GROW[1] - GROW[0]) * dn) / r))
    poly = np.array(poly)
    lo, hi = poly.min(0), poly.max(0)
    cand = np.nonzero((x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1]))[0]
    if len(cand) < 30:
        raise FitError("얼굴 부분의 3D 정점을 찾지 못했어요")
    cand = cand[_inside(XY[cand], poly)]
    if len(cand) < 30:
        raise FitError("얼굴 부분의 3D 정점을 찾지 못했어요")
    dist = np.full(len(cand), np.inf)
    for i in range(len(poly)):
        dist = np.minimum(dist, _seg_dist(XY[cand], poly[i], poly[(i + 1) % len(poly)]))
    w_xy = _smoothstep(dist / (FALL * iod))
    # 얼굴 겉면에서 얼마나 뒤인지(겉면 = 카메라에서 가장 가까운 면)
    ZR = 256
    kz = ZR / max(hi[0] - lo[0], hi[1] - lo[1], 1e-9)
    gxy = (XY - lo) * kz
    fsel = np.nonzero(((gxy[F][..., 0] > -1) & (gxy[F][..., 0] < ZR + 1) & (gxy[F][..., 1] > -1) & (gxy[F][..., 1] < ZR + 1)).any(1))[0]
    pix, fid, b0, b1 = photoproj.raster(gxy, F[fsel], ZR, ZR, dep)
    zb = np.full(ZR * ZR, np.inf)
    f = fsel[fid]
    zb[pix] = dep[F[f, 0]] * b0 + dep[F[f, 1]] * b1 + dep[F[f, 2]] * (1 - b0 - b1)
    zb = zb.reshape(ZR, ZR)
    # 머리의 큰 모양: 얼굴 겉면 깊이를 넓게 흐린 것(얼굴 다각형 안쪽만 써서 목·배경이 섞이지 않게)
    gy_, gx_ = np.mgrid[0:ZR, 0:ZR]
    gpos = np.stack([gx_.ravel() + 0.5, gy_.ravel() + 0.5], 1) / kz + lo
    inpoly = _inside(gpos, poly) & np.isfinite(zb.ravel())
    if inpoly.sum() < 200:
        raise FitError("얼굴 겉면을 찾지 못했어요")
    bq, bz = (gpos[inpoly] - cen) / iod, zb.ravel()[inpoly]
    bw = np.ones(len(bz))
    for _ in range(3):                                    # 튀어나온 코 같은 굴곡에 끌려가지 않게 몇 번 다시 맞춰요
        Am = _poly_terms(bq) * bw[:, None]
        coef = np.linalg.lstsq(Am, bz * bw, rcond=None)[0]
        rr = np.abs(bz - _poly_terms(bq) @ coef)
        sc_ = 1.5 * float(np.median(rr)) + 1e-12
        bw = np.sqrt(np.minimum(1.0, sc_ / np.maximum(rr, 1e-12)))
    zmin = zb.copy()                                       # 둘레 3×3 에서 가장 가까운 값(가장자리에서 흔들리지 않게)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            zmin = np.minimum(zmin, np.roll(zb, (dy, dx), (0, 1)))
    ix = np.clip(gxy[cand, 0].astype(np.int64), 0, ZR - 1)
    iy = np.clip(gxy[cand, 1].astype(np.int64), 0, ZR - 1)
    zf = zmin[iy, ix]
    front = np.isfinite(zf)
    wpp = _wpp(cam, dep[cand])
    s_iod = iod * float(np.median(wpp))                   # 눈 사이 거리(3D 단위)
    behind = np.where(front, dep[cand] - zf, np.inf)
    w_z = 1 - _smoothstep((behind - DEPTH[0] * s_iod) / max((DEPTH[1] - DEPTH[0]) * s_iod, 1e-12))
    w = w_xy * w_z
    use = w > 1e-4
    cand, w, wpp = cand[use], w[use], wpp[use]
    if len(cand) < 30:
        raise FitError("얼굴 겉면의 3D 정점을 찾지 못했어요")
    disp = tps_eval(model, (XY[cand] - cen) / iod) * iod * w[:, None]          # 사진 화소 단위
    n_cap = np.linalg.norm(disp, axis=1)
    disp *= np.minimum(1.0, CAP * iod / np.maximum(n_cap, 1e-9))[:, None]

    # 그물망 이웃끼리 고르기(같은 자리의 정점 — UV 이음새에서 나뉜 것 — 은 하나로 묶어서)
    wid = _weld(P, 1e-7 * ext)
    inreg = np.zeros(len(P), bool)
    inreg[cand] = True
    ftouch = np.nonzero(inreg[F].any(1))[0]
    Ft = F[ftouch]
    nodes, comp = np.unique(wid[Ft], return_inverse=True)
    comp = comp.reshape(-1, 3)
    slot = np.full(int(wid.max()) + 1, -1, np.int64)
    slot[nodes] = np.arange(len(nodes))
    D = np.zeros((len(nodes), 2))
    cnt = np.zeros(len(nodes))
    np.add.at(D, slot[wid[cand]], disp)
    np.add.at(cnt, slot[wid[cand]], 1)
    free = cnt > 0
    D[free] /= cnt[free, None]
    e = np.concatenate([comp[:, [0, 1]], comp[:, [1, 2]], comp[:, [2, 0]]])
    e = np.unique(np.sort(e, 1), axis=0)
    e = e[e[:, 0] != e[:, 1]]
    deg = np.bincount(e.ravel(), minlength=len(nodes)).astype(np.float64)
    for _ in range(SMOOTH[0]):
        acc = np.zeros_like(D)
        np.add.at(acc, e[:, 0], D[e[:, 1]])
        np.add.at(acc, e[:, 1], D[e[:, 0]])
        D = np.where(free[:, None], (1 - SMOOTH[1]) * D + SMOOTH[1] * acc / np.maximum(deg, 1)[:, None], 0.0)
    # 면이 뒤집히거나 심하게 눌리면 세기를 줄여요
    nxy = np.zeros((len(nodes), 2))
    cn = np.zeros(len(nodes))
    np.add.at(nxy, slot[wid[Ft].ravel()], XY[Ft].reshape(-1, 2))
    np.add.at(cn, slot[wid[Ft].ravel()], 1)
    nxy /= cn[:, None]

    def area2(q):
        a_, b_, c_ = q[comp[:, 0]], q[comp[:, 1]], q[comp[:, 2]]
        return (b_[:, 0] - a_[:, 0]) * (c_[:, 1] - a_[:, 1]) - (b_[:, 1] - a_[:, 1]) * (c_[:, 0] - a_[:, 0])

    a0 = area2(nxy)
    big = np.abs(a0) > 1e-9
    strength = 1.0
    for _ in range(8):
        a1 = area2(nxy + D * strength)
        flip = int((big & (a0 * a1 < 0)).sum())
        squash = int((big & (np.abs(a1) < 0.2 * np.abs(a0))).sum())
        if flip == 0 and squash <= 0.002 * len(a0):
            break
        strength *= 0.75
    else:
        raise FitError("옮기면 얼굴 면이 뒤집혀서 보정하지 않았어요")
    D *= strength
    st["strength"] = round(strength, 3)

    # 정점 옮기기: 화면과 나란하게 옮기고, 깊이는 '큰 모양'이 옮긴 자리와 원래 자리에서 다른 만큼만 따라가요(굴곡은 그대로 들고 감)
    dv = D[slot[wid[cand]]]
    ddep = (_poly_terms((XY[cand] + dv - cen) / iod) - _poly_terms((XY[cand] - cen) / iod)) @ coef
    P2 = P.copy()
    P2[cand] = _unproject(cam, x[cand] + dv[:, 0], y[cand] + dv[:, 1], dep[cand] + ddep)
    still = (np.abs(dv).max(1) == 0) & (ddep == 0)          # 옮기지 않는 정점은 원래 값 그대로(비트까지)
    P2[cand[still]] = P[cand[still]]
    m = photoproj._world(g, M["node"])
    A, t = m[:3, :3], m[:3, 3]
    Ai = np.linalg.inv(A)
    pr = M["prim"]["attributes"]
    raw_p, alone_p = _raw(g, b, pr["POSITION"], len(P), 3)
    old_p = raw_p.copy()
    go = cand[~still]
    raw_p[go] = ((P2[go] - t) @ Ai.T).astype(np.float32)
    moved = np.nonzero((raw_p != old_p).any(1))[0]
    if not len(moved):
        raise FitError("옮길 것이 없어요")
    P2 = raw_p.astype(np.float64) @ A.T + t                 # 실제로 저장되는 값(float32)으로 다시
    repl, add, acc_fix = {}, [], {}

    def put(ai, arr, alone, mm=False):
        a = g["accessors"][ai]
        if alone:
            repl[a["bufferView"]] = arr.tobytes()
            acc_fix[ai] = {}
        else:                                              # 다른 자료와 한 덩어리로 묶여 있으면 새 덩어리로 따로 붙여요
            add.append(arr.tobytes())
            acc_fix[ai] = {"_new": len(add) - 1}
        if mm:
            acc_fix[ai].update(min=arr.min(0).astype(float).tolist(), max=arr.max(0).astype(float).tolist())

    put(pr["POSITION"], raw_p, alone_p, True)
    # 법선·접선: 옮긴 정점만, 표면이 돈 만큼 따라 돌려요(엔진이 준 방향의 결을 유지)
    rot_deg = np.zeros(0)
    fa = np.cross(P[Ft[:, 1]] - P[Ft[:, 0]], P[Ft[:, 2]] - P[Ft[:, 0]])
    fb = np.cross(P2[Ft[:, 1]] - P2[Ft[:, 0]], P2[Ft[:, 2]] - P2[Ft[:, 0]])
    la, lb = np.linalg.norm(fa, axis=1), np.linalg.norm(fb, axis=1)
    okf = (la > 1e-14 * ext * ext) & (lb > 1e-14 * ext * ext)
    cosr = np.clip((fa[okf] * fb[okf]).sum(1) / (la[okf] * lb[okf]), -1, 1)
    rot_deg = np.degrees(np.arccos(cosr))
    if N is not None:
        na, nb = np.zeros((len(nodes), 3)), np.zeros((len(nodes), 3))
        for k in range(3):
            np.add.at(na, comp[:, k], fa)
            np.add.at(nb, comp[:, k], fb)
        na /= np.maximum(np.linalg.norm(na, axis=1, keepdims=True), 1e-18)
        nb /= np.maximum(np.linalg.norm(nb, axis=1, keepdims=True), 1e-18)
        dn = (nb - na)[slot[wid[moved]]]
        sign = np.where((na[slot[wid[moved]]] * N[moved]).sum(1) < 0, -1.0, 1.0)[:, None]      # 면 감는 방향이 거꾸로인 3D
        Nn = N[moved] + sign * dn
        Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-12)
        raw_n, alone_n = _raw(g, b, pr["NORMAL"], len(P), 3)
        nl = Nn @ Ai.T
        nl /= np.maximum(np.linalg.norm(nl, axis=1, keepdims=True), 1e-12)
        raw_n[moved] = nl.astype(np.float32)
        put(pr["NORMAL"], raw_n, alone_n)
        if TG is not None:
            T3 = TG[moved, :3] - Nn * (TG[moved, :3] * Nn).sum(1, keepdims=True)
            ln = np.linalg.norm(T3, axis=1, keepdims=True)
            good = ln[:, 0] > 1e-9
            raw_t, alone_t = _raw(g, b, pr["TANGENT"], len(P), 4)
            tl = (T3 / np.maximum(ln, 1e-12)) @ Ai.T
            tl /= np.maximum(np.linalg.norm(tl, axis=1, keepdims=True), 1e-12)
            raw_t[moved[good], :3] = tl[good].astype(np.float32)
            put(pr["TANGENT"], raw_t, alone_t)
    g2, b2, nv = photoproj.rebuild(g, b, repl, add)
    acc = [dict(a_) for a_ in g2["accessors"]]
    for ai, fx in acc_fix.items():
        if "_new" in fx:
            acc[ai]["bufferView"] = nv[fx.pop("_new")]
            acc[ai]["byteOffset"] = 0
        acc[ai].update(fx)
    g2["accessors"] = acc
    new = glbscene.write(g2, b2)

    # 검사
    mv = np.linalg.norm(P2[moved] - P[moved], axis=1)
    out_reg = int((~inreg[moved]).sum())
    x2, y2, dep2 = cam.px(P2)
    grp = slot[wid[moved]]
    gm = np.zeros((len(nodes), 3))
    gc = np.zeros(len(nodes))
    np.add.at(gm, grp, P2[moved])
    np.add.at(gc, grp, 1)
    split = float(np.linalg.norm(P2[moved] - gm[grp] / gc[grp, None], axis=1).max())
    # 같은 자리였던 정점 가운데 일부만 옮겨졌는지(이음새가 벌어짐)
    members = np.bincount(slot[wid[Ft].ravel()], minlength=len(nodes))             # 참고용(면 꼭짓점 수)
    all_moved = np.zeros(len(P), bool)
    all_moved[moved] = True
    wm = np.zeros(int(wid.max()) + 1)
    wt = np.zeros(int(wid.max()) + 1)
    np.add.at(wm, wid, all_moved)
    np.add.at(wt, wid, 1)
    torn = int(((wm > 0) & (wm < wt)).sum())
    flips = int((okf.sum() and (cosr < 0).sum()) or 0)
    degen0, degen1 = int((la <= 1e-14 * ext * ext).sum()), int((lb <= 1e-14 * ext * ext).sum())
    ratio = lb[okf] / la[okf]
    st.update(vertices=int(len(P)), triangles=int(len(F)), face_vertices=int(len(cand)), moved_vertices=int(len(moved)),
              move_mean=round(float(mv.mean()), 6), move_max=round(float(mv.max()), 6),
              move_mean_rel=round(float(mv.mean() / s_iod), 4), move_max_rel=round(float(mv.max() / s_iod), 4), eye_distance_3d=round(s_iod, 6),
              outside_moved=out_reg, depth_follow_max_rel=round(float(np.abs(dep2 - dep).max() / s_iod), 4), seam_split=split, seam_torn=torn,
              flipped_triangles=flips, degenerate_before=degen0, degenerate_after=degen1,
              area_ratio_p01=round(float(np.percentile(ratio, 1)), 3) if len(ratio) else None, area_ratio_p99=round(float(np.percentile(ratio, 99)), 3) if len(ratio) else None,
              normal_turn_p99=round(float(np.percentile(rot_deg, 99)), 2) if len(rot_deg) else 0.0, normal_turn_max=round(float(rot_deg.max()), 2) if len(rot_deg) else 0.0,
              hash={"position_before": _sha(old_p), "position_after": _sha(raw_p), "indices": _sha(F), "uv": _sha(M["UV"])})
    del members
    bad = []
    if out_reg:
        bad.append(f"얼굴 바깥 정점 {out_reg}개가 움직였어요")
    if flips:
        bad.append(f"뒤집힌 삼각형 {flips}개")
    if degen1 > degen0:
        bad.append(f"퇴화된 삼각형이 {degen1 - degen0}개 늘었어요")
    if torn or split > 1e-6 * ext:
        bad.append("이음새가 벌어졌어요")
    if st["depth_follow_max_rel"] > 0.5 * max(st["move_max_rel"], 1e-9) + 0.02:      # 깊이는 옆으로 옮긴 거리의 절반 안쪽으로만 따라가야 해요
        bad.append("깊이가 너무 많이 바뀌었어요")
    if len(rot_deg) and float((rot_deg > MAX_ROT).mean()) > 0.01:
        bad.append("얼굴 표면이 구겨졌어요")
    st["valid"] = not bad
    if bad:
        st["problems"] = bad
        raise FitError("메시 검사 실패: " + ", ".join(bad))
    if log:
        log(f"[얼굴 형상 보정] 정점 {len(moved):,}개 · 평균 {st['move_mean_rel']:.3f} · 최대 {st['move_max_rel']:.3f} × 눈 사이 거리 · 세기 {strength:.2f}")
    return new, st


def run(engine_glb, cam, region, target_img, Lt, detect, log=None):
    """형상 보정 전체: 재기 → 옮기기 → 다시 재기를 나아지는 동안 되풀이(최대 MAX_PASS 번).
    target_img / Lt: 사진을 붙인 결과를 사진 카메라로 그린 그림(DET×DET)과 그 랜드마크(DET 좌표) — 3D 모양이 맞춰 갈 목표.
    detect(그림) → landmarks() 결과(랜드마크 찾기는 부르는 쪽이: 허브는 ComfyUI, 시험은 직접).
    → (보정한 엔진 GLB, 기록). 보정하지 않을 때는 FitError(이유) — 기록은 예외의 rec 에 담아요."""
    rec = {"passes": []}

    def fail(msg):
        e = FitError(msg)
        e.rec = rec
        return e

    def measure(glb):
        img = render(glb, cam, region)
        L = detect(img)
        if not L.get("ok"):
            return img, L, None, {}
        L2, rf = refine(L, Lt, img, target_img)
        return img, L2, lm_error(L2, Lt), rf

    img, Lg, err, rf = measure(engine_glb)
    rec["engine_landmarks"] = {"ok": bool(Lg.get("ok")), "why": Lg.get("why"), "score": Lg.get("score"), "counts": Lg.get("counts")}
    if err is None:
        raise fail("3D 엔진이 칠한 얼굴에서 랜드마크를 찾지 못했어요" + (f"({Lg.get('why')})" if Lg.get("why") else ""))
    rec.update(before=err, refine_before=rf, engine_img=img, engine_lm=Lg)
    if err["mean"] < MIN_NEED:
        rec["status"] = "not_needed"
        raise fail(f"3D 얼굴 모양이 이미 사진과 맞아요(차이 {err['mean']:.3f} × 눈 사이 거리) — 옮기지 않았어요")
    cur, first = engine_glb, err
    for i in range(MAX_PASS):
        try:
            new, st = fit(cur, cam, to_photo(Lg, region), to_photo(Lt, region), log)
        except FitError as e:
            rec["passes"].append({"pass": i + 1, "error": str(e)})
            if i == 0:
                raise fail(str(e)) from None
            break
        img2, Lg2, err2, rf2 = measure(new)
        ps = {"pass": i + 1, "mesh": st, "landmark_error_after": err2 if err2 else "not_evaluable", "refine_after": rf2}
        rec["passes"].append(ps)
        if err2 is None:
            if i == 0:
                raise fail("옮긴 뒤 3D 얼굴에서 랜드마크를 다시 찾지 못해 나아졌는지 확인할 수 없어요")
            ps["kept"] = False
            break
        if err2["mean"] >= err["mean"] * 0.97:              # 더 나아지지 않으면 이번 것은 버리고 멈춰요
            ps["kept"] = False
            break
        ps["kept"] = True
        cur, Lg, err, img = new, Lg2, err2, img2
        if err["mean"] < 0.5 * MIN_NEED:
            break
    if cur is engine_glb:
        raise fail("정점을 옮겨도 3D 얼굴 모양과 사진의 차이가 줄지 않았어요")
    rec.update(after=err, fitted_img=img, fitted_lm=Lg, passes_kept=sum(1 for p in rec["passes"] if p.get("kept")))
    if err["mean"] > MIN_GAIN * first["mean"]:
        raise fail(f"보정 효과가 작아요(랜드마크 차이 {first['mean']:.3f} → {err['mean']:.3f}) — 기존 결과를 썼어요")
    return cur, rec


def same_triangles(result, fitted):
    """사진을 붙인 결과(몸 + 머리 전용 메시)의 삼각형이 보정한 원본의 삼각형과 하나도 빠짐·겹침 없이 같은지.
    → {"ok", "triangles", "missing", "max_gap"} — 머리 메시와 몸 메시의 표면이 어긋나거나 겹치면(Z-fighting) 여기서 걸려요."""
    def cents(glb):
        out = []
        for P, F, *_ in photoproj._scene(glb, 8):
            out.append(P[F].mean(1))
        return np.concatenate(out)
    a, b = cents(result), cents(fitted)
    if len(a) != len(b):
        return {"ok": False, "triangles": [int(len(a)), int(len(b))], "missing": abs(len(a) - len(b)), "max_gap": None}
    ext = float(np.linalg.norm(b.max(0) - b.min(0))) or 1.0
    ka, kb = np.lexsort(a.T[::-1]), np.lexsort(b.T[::-1])
    gap = float(np.abs(a[ka] - b[kb]).max())
    return {"ok": gap <= 1e-6 * ext, "triangles": [int(len(a)), int(len(b))], "missing": 0, "max_gap": gap}


def moved_report(before, after):
    """두 GLB(같은 구조)의 정점 자리가 실제로 다른지 — 첫 덩어리 기준. → {"vertices", "changed", "max"}"""
    a, b = photoproj._scene(before, 8), photoproj._scene(after, 8)
    out = []
    for (Pa, Fa, *_), (Pb, Fb, *_) in zip(a, b):
        same_n = Pa.shape == Pb.shape
        d = np.linalg.norm(Pa - Pb, axis=1) if same_n else np.zeros(0)
        out.append({"vertices": int(len(Pa)), "triangles": int(len(Fa)), "same_layout": bool(same_n and np.array_equal(Fa, Fb)),
                    "changed": int((d > 0).sum()), "max": float(d.max()) if len(d) else None, "mean": float(d[d > 0].mean()) if (d > 0).any() else 0.0})
    return out


# ───────────────────────── 확인용 그림 ─────────────────────────
def overlay(img, sets, size=None):
    """그림 위에 랜드마크를 찍어요. sets = [(랜드마크(DET 좌표), 색)] — 두 벌이면 짝끼리 선으로 이어요."""
    im = img.convert("RGB").copy()
    dr = ImageDraw.Draw(im)
    ok = [(L, c) for L, c in sets if L and L.get("ok")]
    if len(ok) == 2:
        for k in set(ok[0][0]["pts"]) & set(ok[1][0]["pts"]):
            dr.line([tuple(ok[0][0]["pts"][k]), tuple(ok[1][0]["pts"][k])], fill=(255, 255, 255), width=1)
    for L, c in ok:
        for x, y in L["pts"].values():
            dr.ellipse((x - 3, y - 3, x + 3, y + 3), fill=c, outline=(0, 0, 0))
    return im.resize((size, size), Image.LANCZOS) if size else im


def panel_sheet(panels, size=420):
    """[(한국어 제목, 영어 제목, 그림)] 을 옆으로 나란히 → PIL."""
    fnt, ko = photoproj._font(18)
    im = Image.new("RGB", (size * len(panels), size + 30), (22, 22, 26))
    dr = ImageDraw.Draw(im)
    for i, (k_, e_, p) in enumerate(panels):
        dr.text((i * size + 6, 5), k_ if ko else e_, fill=(235, 235, 240), font=fnt)
        if p is not None:
            im.paste(p.convert("RGB").resize((size, size), Image.LANCZOS), (i * size, 30))
    return im


def png(im):
    bio = io.BytesIO()
    im.save(bio, "PNG")
    return bio.getvalue()
