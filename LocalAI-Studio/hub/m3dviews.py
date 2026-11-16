"""3D 뒷면 진단 — 뒷모습이 이상할 때 '모양 / 텍스처·UV / 법선·그물망 구조 / 보이는 방식' 가운데 무엇이 문제인지 가려내는 그림과 숫자.

· 여섯 방향(정면·뒤·좌우 45°·좌우 옆) × 다섯 방식:
    원본 재질  — 텍스처 그대로(약한 음영)
    단색(Clay) — 색을 빼고 모양만. 법선이 뒤집힌 곳은 어둡게 나와요
    그물망     — 삼각형 선. 빨강 = 구멍(이웃 없는 모서리), 주황 = 자리는 붙어 있지만 정점이 이어지지 않은 모서리, 보라 = 면이 셋 넘게 만나는 모서리
    법선       — 표면이 보는 방향을 색으로. 자홍 = 면이 뒤집혀(안쪽을 봄) 있는 곳
    UV 체커    — 텍스처 좌표에 바둑판을 입힌 것. 칸이 크면 그 부분 텍스처 해상도가 낮고, 찌그러지면 늘어난 거예요(색조는 재질별)
· 단계 비교: 엔진 원본 → 사진 붙이기 뒤 → Blender 마무리 뒤. 뒷면이 어느 단계에서 얼마나 바뀌었는지 재요.
· 그물망 구조 검사: 구멍·이어지지 않은 정점·겹친 면·뒤집힌 면·법선 불일치, 앞/뒤 텍스처 해상도.
모두 CPU(numpy)로 그려요 — GPU·ComfyUI·Blender 를 쓰지 않아요."""
import math

import numpy as np
from PIL import Image, ImageDraw

import photoproj

VIEWS6 = (("정면", "front", 0.0), ("뒤", "back", 180.0), ("왼쪽 45°", "left 45", -45.0), ("오른쪽 45°", "right 45", 45.0), ("왼쪽 옆", "left side", -90.0), ("오른쪽 옆", "right side", 90.0))
MODES = (("원본 재질", "material", "material"), ("단색(Clay)", "clay", "clay"), ("그물망", "wireframe", "wire"), ("법선", "normal", "normal"), ("UV 체커", "uv checker", "uv"))
EDGE_COL = {1: (235, 140, 30), 2: (230, 40, 40), 3: (170, 60, 220)}      # 1 정점이 안 이어짐, 2 구멍, 3 면이 셋 넘게
LIGHT = np.array([0.30, 0.40, 0.86])
TINT = ((0.72, 0.86, 1.0), (1.0, 0.80, 0.55), (0.75, 1.0, 0.75), (1.0, 0.75, 0.95))
CHECK = 48                # UV 체커 칸 수(텍스처 한 변)


def _weld_ids(P, ext):
    q = np.round(P / (1e-6 * ext)).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    return inv.reshape(-1)


def prepare(glb, tex_max=2048):
    """GLB → 그리기·검사에 쓸 묶음(덩어리들을 한 그물망으로, 모서리 분류 포함)."""
    sc = photoproj._scene(glb, tex_max)
    Ps, Fs, pid, off = [], [], [], 0
    for i, (P, F, *_) in enumerate(sc):
        Ps.append(P)
        Fs.append(F + off)
        pid.append(np.full(len(F), i))
        off += len(P)
    P, F, pid = np.concatenate(Ps), np.concatenate(Fs), np.concatenate(pid)
    lo, hi = P.min(0), P.max(0)
    ext = float(np.linalg.norm(hi - lo)) or 1.0
    wid = _weld_ids(P, ext)
    nv = len(P)

    def edge_count(ids):
        """면마다 세 모서리(0-1, 1-2, 2-0)를 함께 쓰는 면의 수"""
        e = np.stack([ids[F[:, [0, 1]]], ids[F[:, [1, 2]]], ids[F[:, [2, 0]]]], 1).reshape(-1, 2)
        e.sort(1)
        key = e[:, 0].astype(np.int64) * (int(ids.max()) + 1) + e[:, 1]
        _, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
        return cnt[inv.reshape(-1)].reshape(-1, 3), key.reshape(-1, 3)

    ci, _ = edge_count(np.arange(nv))                   # 정점 번호 기준(이어져 있는지)
    cw, kw = edge_count(wid)                            # 자리 기준(진짜 구멍인지)
    kind = np.zeros(ci.shape, np.uint8)
    kind[(ci == 1) & (cw == 2)] = 1
    kind[cw == 1] = 2
    kind[cw > 2] = 3
    degen = (wid[F[:, 0]] == wid[F[:, 1]]) | (wid[F[:, 1]] == wid[F[:, 2]]) | (wid[F[:, 0]] == wid[F[:, 2]])
    kind[degen] = 0
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    return {"sc": sc, "P": P, "F": F, "pid": pid, "lo": lo, "hi": hi, "ext": ext, "wid": wid, "kind": kind, "edge_w": cw, "edge_key": kw, "degen": degen, "fn": fn}


def frame_of(S):
    """그림 틀: (가운데, 크기) — 캐릭터 전체가 들어가게."""
    lo, hi = S["lo"], S["hi"]
    return (lo + hi) / 2, max(hi[1] - lo[1], np.hypot(hi[0] - lo[0], hi[2] - lo[2]), 1e-9)


def render(S, yaw=0.0, size=384, mode="material", frame=None, bg=(34, 34, 40)):
    """한 방향·한 방식 그림 → (H×W×3 uint8 배열, 물체가 있는 화소 마스크).
    yaw: 0 앞, 180 뒤, -90 캐릭터의 왼쪽, 90 오른쪽(photoproj.capture 와 같아요). frame = (가운데, 크기)."""
    P, F = S["P"], S["F"]
    ctr, ext = frame if frame is not None else frame_of(S)
    a = math.radians(yaw)
    R = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    Q = (P - np.asarray(ctr)) @ R.T
    k = size * 0.92 / ext
    xy = np.stack([size / 2 + k * Q[:, 0], size / 2 - k * Q[:, 1]], 1)
    pix, fid, b0, b1 = photoproj.raster(xy, F, size, size, -Q[:, 2])
    out = np.zeros((size * size, 3), np.float32)
    out[:] = bg
    mask = np.zeros(size * size, bool)
    if not len(pix):
        return out.reshape(size, size, 3).astype(np.uint8), mask.reshape(size, size)
    mask[pix] = True
    b2 = 1 - b0 - b1
    ng = S["fn"][fid] @ R.T                               # 면 감는 방향으로 본 면 방향(화면 좌표: z 가 카메라 쪽)
    ng /= np.maximum(np.linalg.norm(ng, axis=1, keepdims=True), 1e-18)
    ns = ng.copy()                                        # 음영에 쓰는 방향(정점 법선이 있으면 그것)
    col = np.zeros((len(pix), 3), np.float32)
    uvc = np.zeros((len(pix), 2))
    has_uv = np.zeros(len(pix), bool)
    starts = np.cumsum([0] + [len(x[1]) for x in S["sc"]])
    for i, (Pi, Fi, UV, N, T, fac) in enumerate(S["sc"]):
        m = S["pid"][fid] == i
        if not m.any():
            continue
        fl = Fi[fid[m] - starts[i]]
        c = np.stack([b0[m], b1[m], b2[m]], 1)
        if N is not None:
            v = (N[fl] * c[..., None]).sum(1) @ R.T
            ln = np.linalg.norm(v, axis=1, keepdims=True)
            ns[m] = np.where(ln > 1e-9, v / np.maximum(ln, 1e-12), ng[m])
        if UV is not None:
            uv = (UV[fl] * c[..., None]).sum(1)
            uvc[m], has_uv[m] = uv, True
            if T is not None:
                col[m] = photoproj._sample(T, (uv[:, 0] % 1.0) * T.shape[1], np.clip(uv[:, 1], 0, 1) * T.shape[0]) * fac / 255
            else:
                col[m] = np.array([200.0, 200, 205]) * fac / 255
        else:
            col[m] = np.array([200.0, 200, 205]) * fac / 255
    L = LIGHT / np.linalg.norm(LIGHT)
    if mode == "material":
        res = col * (0.45 + 0.55 * np.abs(ns @ L))[:, None]
    elif mode == "clay":                                  # 뒤집힌 법선은 빛을 못 받아 어두워요(일부러 절댓값을 쓰지 않아요)
        res = np.array([196.0, 194, 190]) * (0.22 + 0.78 * np.clip(ns @ L, 0, 1))[:, None]
    elif mode == "normal":
        res = (ns * 0.5 + 0.5) * 255
        res[ng[:, 2] < 0] = (255, 0, 255)                 # 보이는 면인데 면 방향이 카메라 반대쪽 = 뒤집힌 면
    elif mode == "uv":
        chk = ((np.floor(uvc[:, 0] * CHECK) + np.floor(uvc[:, 1] * CHECK)) % 2)
        fine = ((np.floor(uvc[:, 0] * CHECK * 4) + np.floor(uvc[:, 1] * CHECK * 4)) % 2)
        tint = np.array(TINT)[S["pid"][fid] % len(TINT)]
        res = (150 + 80 * chk + 18 * (fine - 0.5))[:, None] * tint * (0.6 + 0.4 * np.abs(ns @ L))[:, None]
        res[~has_uv] = (90, 90, 90)
    elif mode == "wire":
        res = np.array([214.0, 214, 218]) * (0.5 + 0.5 * np.abs(ns @ L))[:, None]
        T3 = xy[F[fid]]                                    # 화소에서 세 모서리까지의 거리(화소)
        e01, e12, e20 = T3[:, 1] - T3[:, 0], T3[:, 2] - T3[:, 1], T3[:, 0] - T3[:, 2]
        ar = np.abs(e01[:, 0] * e20[:, 1] - e01[:, 1] * e20[:, 0])
        d = np.stack([b2 * ar / np.maximum(np.linalg.norm(e01, axis=1), 1e-9),      # 모서리 0-1 까지 = 맞은편(2)의 무게 × 높이
                      b0 * ar / np.maximum(np.linalg.norm(e12, axis=1), 1e-9),
                      b1 * ar / np.maximum(np.linalg.norm(e20, axis=1), 1e-9)], 1)
        near = d.argmin(1)
        dm = d[np.arange(len(d)), near]
        kd = S["kind"][fid]
        res[dm < 0.7] = (70, 82, 120)
        for kk, c_ in EDGE_COL.items():                   # 문제 모서리는 굵게, 위에
            hit = ((d < 1.8) & (kd == kk)).any(1)
            res[hit] = c_
    else:
        raise ValueError(mode)
    out[pix] = res
    return np.clip(out, 0, 255).astype(np.uint8).reshape(size, size, 3), mask.reshape(size, size)


def sheet(S, size=256, title=None, yaw_off=0.0):
    """한 3D 의 다섯 방식 × 여섯 방향 그림(PIL). yaw_off: 앞 방향을 돌려 저장한 3D(Blender '앞 방향 돌리기')를 같은 방향으로 보려고."""
    head, lab = 34 + (26 if title else 0), 150
    im = Image.new("RGB", (lab + size * len(VIEWS6), head + size * len(MODES)), (22, 22, 26))
    dr = ImageDraw.Draw(im)
    fnt, ko = photoproj._font(18)
    if title:
        dr.text((8, 4), title, fill=(255, 255, 255), font=fnt)
    for j, (k_, e_, _) in enumerate(VIEWS6):
        dr.text((lab + j * size + 8, head - 28), k_ if ko else e_, fill=(230, 230, 235), font=fnt)
    fr = frame_of(S)
    for i, (k_, e_, mode) in enumerate(MODES):
        dr.text((8, head + i * size + 8), k_ if ko else e_, fill=(240, 240, 245), font=fnt)
        for j, (_, _, yaw) in enumerate(VIEWS6):
            im.paste(Image.fromarray(render(S, yaw + yaw_off, size, mode, fr)[0]), (lab + j * size, head + i * size))
    return im


def back_sheet(stages, size=320):
    """단계 비교(뒤에서 본 것만): stages = [(한국어 이름, 영어 이름, 준비한 묶음, yaw_off)] — 줄 = 단계, 칸 = 다섯 방식."""
    head, lab = 34, 210
    im = Image.new("RGB", (lab + size * len(MODES), head + size * len(stages)), (22, 22, 26))
    dr = ImageDraw.Draw(im)
    fnt, ko = photoproj._font(18)
    for j, (k_, e_, _) in enumerate(MODES):
        dr.text((lab + j * size + 8, 6), ("뒤 · " + k_) if ko else ("back · " + e_), fill=(230, 230, 235), font=fnt)
    for i, (k_, e_, S, yo) in enumerate(stages):
        dr.text((8, head + i * size + 8), k_ if ko else e_, fill=(240, 240, 245), font=fnt)
        fr = frame_of(S)
        for j, (_, _, mode) in enumerate(MODES):
            im.paste(Image.fromarray(render(S, 180.0 + yo, size, mode, fr)[0]), (lab + j * size, head + i * size))
    return im


def structure(S):
    """그물망 구조·법선·UV 검사 → dict(숫자). 뒷면이 이상한 까닭이 구조·법선·UV 인지 가릴 때 봐요."""
    P, F, fn, kind = S["P"], S["F"], S["fn"], S["kind"]
    ext = S["ext"]
    area = np.linalg.norm(fn, axis=1) / 2
    tot = float(area.sum()) or 1.0
    nw = int(S["wid"].max()) + 1
    used = np.zeros(len(P), bool)
    used[F.ravel()] = True
    # 겹친 면(같은 세 자리를 쓰는 면이 둘 이상)
    tw = np.sort(S["wid"][F], 1)
    key = (tw[:, 0].astype(np.int64) * nw + tw[:, 1]) * nw + tw[:, 2]
    _, cnt = np.unique(key[~S["degen"]], return_counts=True)
    dup = int((cnt - 1).sum())
    # 정점 법선과 면 방향이 반대인 넓이 비율(법선만 잘못된 것 — 모양은 멀쩡한데 어둡게 보임)
    flip_n, has_n = 0.0, False
    off = 0
    starts = np.cumsum([0] + [len(x[1]) for x in S["sc"]])
    for i, (Pi, Fi, UV, N, T, fac) in enumerate(S["sc"]):
        if N is not None:
            has_n = True
            g = fn[starts[i]:starts[i + 1]]
            vn = N[Fi].mean(1)
            flip_n += float(area[starts[i]:starts[i + 1]][(g * vn).sum(1) < 0].sum())
        off += len(Pi)
    # 면이 바깥을 보는지: 이웃 면과 감는 방향이 맞지 않는 모서리(같은 방향으로 지나가면 한쪽이 뒤집힌 것)
    w = S["wid"][F]
    e = np.stack([w[:, [0, 1]], w[:, [1, 2]], w[:, [2, 0]]], 1).reshape(-1, 2)
    dirn = e[:, 0] < e[:, 1]
    kk = S["edge_key"].reshape(-1)
    two = S["edge_w"].reshape(-1) == 2
    o = np.argsort(kk[two], kind="stable")
    d2 = dirn[two][o].reshape(-1, 2) if two.sum() % 2 == 0 else dirn[two][o][: (two.sum() // 2) * 2].reshape(-1, 2)
    bad_wind = int((d2[:, 0] == d2[:, 1]).sum())
    # 앞/뒤 텍스처 해상도: 면마다 (텍스처 화소 넓이 ÷ 3D 넓이)의 제곱근 = 길이 1 에 텍스처 화소 몇 개
    ctr = (S["lo"] + S["hi"]) / 2
    dens = {}
    for i, (Pi, Fi, UV, N, T, fac) in enumerate(S["sc"]):
        if UV is None or T is None:
            continue
        a3 = area[starts[i]:starts[i + 1]]
        uv = UV[Fi]
        auv = np.abs((uv[:, 1, 0] - uv[:, 0, 0]) * (uv[:, 2, 1] - uv[:, 0, 1]) - (uv[:, 2, 0] - uv[:, 0, 0]) * (uv[:, 1, 1] - uv[:, 0, 1])) / 2 * T.shape[0] * T.shape[1]
        g = fn[starts[i]:starts[i + 1]]
        cen = Pi[Fi].mean(1)
        outw = np.where((g * (cen - ctr)).sum(1, keepdims=True) < 0, -g, g)      # 바깥쪽으로 맞춘 면 방향
        ok = a3 > 1e-14 * ext * ext
        d = np.sqrt(auv[ok] / a3[ok]) * ext                # 물체 크기(대각선)만큼의 길이에 텍스처 화소 몇 개
        fz = outw[ok, 2] / np.maximum(np.linalg.norm(outw[ok], axis=1), 1e-18)
        wa = a3[ok]

        def wmed(m):
            if m.sum() < 10:
                return None
            idx = np.argsort(d[m])
            cs = np.cumsum(wa[m][idx])
            return round(float(d[m][idx][np.searchsorted(cs, cs[-1] / 2)]), 1)
        dens[str(i)] = {"triangles": int(len(Fi)), "texture": [int(T.shape[1]), int(T.shape[0])], "front": wmed(fz > 0.3), "back": wmed(fz < -0.3), "side": wmed(np.abs(fz) <= 0.3)}
    hole_e = int((kind == 2).sum())
    return {"triangles": int(len(F)), "vertices": int(len(P)), "positions": nw, "primitives": len(S["sc"]),
            "unwelded_ratio": round(len(P) / max(nw, 1), 2),                    # 1 이면 정점이 다 이어져 있고, 3 에 가까우면 삼각형마다 따로
            "split_edges": int((kind == 1).sum() // 2), "hole_edges": hole_e, "nonmanifold_edges": int((kind == 3).sum() // 3),
            "duplicate_faces": dup, "degenerate_faces": int(S["degen"].sum()), "unused_vertices": int((~used).sum()),
            "winding_conflicts": bad_wind, "normals": has_n, "normal_flip_area": round(flip_n / tot, 4) if has_n else None,
            "texel_density": dens}


def compare(Sa, Sb, size=384, yaw_off=0.0):
    """두 단계의 차이(같은 틀·같은 방향으로 그려서) → {방향: {material, clay, silhouette}} — 0 이면 그 방향에서 안 바뀐 것.
    material = 색 차이 평균(0~255), changed = 눈에 띄게(24 넘게) 바뀐 화소 비율, clay = 모양·법선 차이, silhouette = 윤곽 겹침(1 이 같음)."""
    out = {}
    fa, fb = frame_of(Sa), frame_of(Sb)
    for k_, e_, yaw in VIEWS6:
        r = {}
        ma = mb = None
        for mode in ("material", "clay"):
            a, ma = render(Sa, yaw, size, mode, fa)
            b, mb = render(Sb, yaw + yaw_off, size, mode, fb)
            m = ma | mb
            d = np.abs(a.astype(np.float32) - b.astype(np.float32)).max(2)
            r[mode] = round(float(d[m].mean()), 2) if m.any() else 0.0
            if mode == "material":
                r["changed"] = round(float((d[m] > 24).mean()), 4) if m.any() else 0.0
        r["silhouette"] = round(float((ma & mb).sum() / max(1, (ma | mb).sum())), 4)
        out[e_.replace(" ", "_")] = r
    return out


def mirror_score(S, size=256):
    """뒷면 텍스처가 앞면을 좌우로 뒤집은 것과 얼마나 비슷한지(-1~1). 사진 한 장으로 만드는 엔진은 뒷면에 앞 사진을 비쳐 칠하는 일이 있어요
    (뒤통수에 얼굴이 비침). → {"whole": 전체, "head": 위쪽 18%} — 0.5 를 넘으면 의심해요."""
    fr = frame_of(S)
    a, ma = render(S, 0.0, size, "material", fr)
    b, mb = render(S, 180.0, size, "material", fr)
    b, mb = b[:, ::-1], mb[:, ::-1]                       # 뒤에서 본 그림을 좌우로 뒤집으면 앞 그림과 같은 자리
    g = lambda x: photoproj._lcn(photoproj._gblur(x.astype(np.float64).mean(2), 1.0), 5.0)
    ga, gb, m = g(a), g(b), ma & mb
    out = {}
    ys = np.nonzero(m.any(1))[0]
    if len(ys) < 8:
        return {"whole": None, "head": None}
    top = np.zeros_like(m)
    top[ys[0]:ys[0] + max(4, int(0.18 * (ys[-1] - ys[0])))] = True
    for k, mm in (("whole", m), ("head", m & top)):
        out[k] = round(photoproj._ncc(ga, gb, mm), 3) if mm.sum() > 200 else None
    return out


def verdict(rep):
    """진단 숫자 → 사람이 읽는 판정 목록 [{stage, kind, level, text}] (kind: shape 모양 / texture 텍스처·UV / mesh 그물망·법선 / none)."""
    out = []

    def add(stage, kind, level, text):
        out.append({"stage": stage, "kind": kind, "level": level, "text": text})
    names = {"engine": "엔진 원본", "photo": "사진 붙이기 뒤", "final": "마무리(Blender) 뒤"}
    for st in ("engine", "photo", "final"):
        s = (rep.get("stages") or {}).get(st)
        if not s:
            continue
        x, nm = s["structure"], names[st]
        if x["hole_edges"]:
            add(st, "mesh", "warn", f"{nm}: 그물망에 구멍이 있어요(이웃 없는 모서리 {x['hole_edges']:,}개) — 그물망 그림의 빨간 선")
        if x["normal_flip_area"] and x["normal_flip_area"] > 0.02:
            add(st, "mesh", "warn", f"{nm}: 법선이 면 방향과 반대인 곳이 넓이의 {x['normal_flip_area']:.0%} — 모양은 멀쩡한데 어둡게 보여요(단색 그림에서 어두운 곳)")
        if x["winding_conflicts"] > 0.01 * x["triangles"]:
            add(st, "mesh", "warn", f"{nm}: 이웃과 감는 방향이 다른 면이 {x['winding_conflicts']:,}곳 — 면이 뒤집혀 있어요(법선 그림의 자홍색)")
        if x["duplicate_faces"] > 0.001 * x["triangles"]:
            add(st, "mesh", "warn", f"{nm}: 같은 자리에 겹친 면이 {x['duplicate_faces']:,}개 — 겹쳐서 깜빡여 보일 수 있어요")
        if x["nonmanifold_edges"] > 0.005 * x["triangles"]:
            add(st, "mesh", "info", f"{nm}: 면이 셋 넘게 만나는 모서리 {x['nonmanifold_edges']:,}개(겉껍질이 겹친 구조)")
        if x["unwelded_ratio"] > 1.5:
            add(st, "mesh", "warn", f"{nm}: 정점이 이어지지 않은 삼각형이 많아요(정점 ÷ 자리 = {x['unwelded_ratio']}) — 면 줄이기·법선 계산에서 깨져요")
        mr = s.get("mirror") or {}
        if st == "engine" and ((mr.get("head") or 0) > 0.5 or (mr.get("whole") or 0) > 0.5):
            add(st, "texture", "warn", f"{nm}: 뒷면 텍스처가 앞면을 뒤집은 것과 비슷해요(머리 {mr.get('head')}, 전체 {mr.get('whole')}) — 3D 엔진이 뒷면에 앞 사진을 비쳐 칠한 거예요. "
                                       "'만드는 방식'을 AI 멀티뷰 보조로 바꿔 뒤 그림을 함께 넣으면 나아져요")
        for pid, d in (x.get("texel_density") or {}).items():
            if d.get("front") and d.get("back") and d["back"] < 0.4 * d["front"]:
                add(st, "texture", "info", f"{nm}: 재질 {pid} 의 뒷면 텍스처 해상도가 앞면의 {d['back'] / d['front']:.0%} 예요")
    for key, a_, b_ in (("engine_to_photo", "엔진 원본", "사진 붙이기"), ("photo_to_final", "사진 붙이기", "마무리(Blender)")):
        c = (rep.get("changes") or {}).get(key)
        if not c:
            continue
        bk = c["back"]
        if bk["silhouette"] < 0.97 or bk["clay"] > 6:
            add(key, "shape", "warn", f"{b_} 단계에서 뒷면의 모양·음영이 바뀌었어요(윤곽 겹침 {bk['silhouette']}, 단색 그림 차이 {bk['clay']})")
        if bk["changed"] > 0.03:
            add(key, "texture", "warn", f"{b_} 단계에서 뒷면 색이 바뀌었어요(눈에 띄게 달라진 화소 {bk['changed']:.1%}, 평균 차이 {bk['material']})")
        if bk["silhouette"] >= 0.97 and bk["clay"] <= 6 and bk["changed"] <= 0.03:
            add(key, "none", "ok", f"{b_} 단계는 뒷면을 바꾸지 않았어요({a_}과 같아요 — 달라진 화소 {bk['changed']:.1%})")
    if not any(v["level"] == "warn" for v in out):
        add("all", "none", "info", "숫자로 잡히는 문제는 없어요. 엔진 원본 그림에서부터 뒷모습이 어색하다면 사진 한 장으로는 알 수 없는 뒷면을 3D 엔진이 추정한 결과예요 — AI 멀티뷰 보조(뒤 그림)로 만들어 비교해 보세요")
    return out


def diagnose(stages, rotate=0.0, size=256):
    """stages = {"engine": GLB, "photo": GLB 또는 None, "final": GLB 또는 None} → (기록 dict, {파일 이름: PNG 바이트}).
    rotate: Blender 마무리의 '앞 방향 돌리기'(도) — 마무리 뒤 3D 를 같은 방향으로 보려고."""
    names = {"engine": ("엔진 원본", "engine original"), "photo": ("사진 붙이기 뒤", "after photo"), "final": ("마무리(Blender) 뒤", "after Blender")}
    S, rep, files = {}, {"stages": {}, "changes": {}, "views": [e for _, e, _ in VIEWS6], "modes": [m for _, _, m in MODES]}, {}
    rep["errors"] = []
    for k in ("engine", "photo", "final"):
        if stages.get(k):
            try:
                S[k] = prepare(stages[k])
            except Exception as e:  # noqa: BLE001 — 한 단계를 못 읽어도 나머지는 진단해요
                rep["errors"].append(f"{names[k][0]} 3D 를 읽지 못해 이 단계는 건너뛰었어요({str(e)[:80]})")
    if not S:
        raise ValueError("진단할 3D 를 읽지 못했어요")
    yo = {"engine": 0.0, "photo": 0.0, "final": 0.0}
    if "final" in S and rotate:                           # 돌린 방향을 찾아요(부호는 프로그램마다 달라서 앞 그림이 가장 잘 겹치는 쪽)
        ref = S.get("photo") or S.get("engine")
        if ref is not None:
            best = None
            for cand in (0.0, float(rotate), -float(rotate)):
                a, ma = render(ref, 0.0, 128, "clay")
                b, mb = render(S["final"], cand, 128, "clay")
                iou = (ma & mb).sum() / max(1, (ma | mb).sum())
                if best is None or iou > best[0]:
                    best = (iou, cand)
            yo["final"] = best[1]
    for k, s in S.items():
        rep["stages"][k] = {"structure": structure(s), "mirror": mirror_score(s), "yaw_offset": yo[k]}
        files[f"back_views_{k}.png"] = png(sheet(s, size, None, yo[k]))
    if "engine" in S and "photo" in S:
        rep["changes"]["engine_to_photo"] = compare(S["engine"], S["photo"])
    if "final" in S and ("photo" in S or "engine" in S):
        rep["changes"]["photo_to_final"] = compare(S.get("photo") or S["engine"], S["final"], yaw_off=yo["final"])
    files["back_compare.png"] = png(back_sheet([(names[k][0], names[k][1], S[k], yo[k]) for k in ("engine", "photo", "final") if k in S]))
    rep["verdict"] = verdict(rep)
    for e_ in rep["errors"]:
        rep["verdict"].append({"stage": "all", "kind": "none", "level": "info", "text": e_})
    return rep, files


def png(im):
    import io
    bio = io.BytesIO()
    im.save(bio, "PNG")
    return bio.getvalue()
