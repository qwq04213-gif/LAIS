"""원본 사진 화소 붙이기 + 간단한 그리기(직교 투영). numpy 만 써요.

SiTH 는 몸을 [-1, 1] 정육면체 안에 두고 사진을 '직교 카메라'(멀리서 평행하게 보는 카메라)로 맞춰요:
  사진 화소 x = (X + 1) / 2 × 크기,  y = (1 − Y) / 2 × 크기,  Z 가 클수록 카메라(앞)에 가까워요.
그래서 원근 계산 없이, 앞에서 실제로 보이는 표면(깊이 검사 통과 + 카메라를 향한 면 + 사람 마스크 안)에만
사진 화소를 덮어쓰고, 나머지(옆·뒤·가려진 곳)는 엔진이 만든 색을 그대로 둬요."""
import numpy as np
from PIL import Image, ImageFilter

MAX_SAMPLES = 24_000_000


def rot_y(deg):
    a = np.deg2rad(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], np.float32)


def surface_samples(V, F, size):
    """표면을 화소보다 촘촘하게 덮는 점들. 돌려주는 값: (면 번호, 무게중심 좌표 (K,3)).
    촘촘한 메시(면이 1화소 안팎)는 면마다 한 점, 큰 면은 변 길이만큼 나눠요."""
    if not len(F):
        return np.zeros(0, np.int64), np.zeros((0, 3), np.float32)
    P = V[:, :2] * (size / 2.0)
    e = np.stack([np.linalg.norm(P[F[:, a]] - P[F[:, b]], axis=1) for a, b in ((0, 1), (1, 2), (2, 0))], 1).max(1)
    n = np.clip(np.ceil(e * 1.5), 1, 4096).astype(np.int64)
    n = 2 ** np.ceil(np.log2(n)).astype(np.int64)                       # 1, 2, 4, …
    tot = ((n + 1) * (n + 2) // 2).sum()
    while tot > MAX_SAMPLES:                                             # 너무 많으면 큰 면부터 덜 나눠요
        n = np.maximum(1, np.where(n == n.max(), n // 2, n))
        tot = ((n + 1) * (n + 2) // 2).sum()
    fi, bc = [], []
    for k in np.unique(n):
        idx = np.where(n == k)[0]
        if k == 1:
            w = np.array([[1 / 3, 1 / 3, 1 / 3], [1, 0, 0], [0, 1, 0], [0, 0, 1]], np.float32)
        else:
            i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
            ok = i + j <= k
            w = np.stack([i[ok], j[ok], k - i[ok] - j[ok]], 1).astype(np.float32) / k
        fi.append(np.repeat(idx, len(w)))
        bc.append(np.tile(w, (len(idx), 1)))
    return np.concatenate(fi), np.concatenate(bc)


def zbuffer(V, F, size, yaw=0.0):
    """직교 투영 깊이 그림. 돌려주는 값: dict(depth (S,S) — 빈 곳은 -inf, face (S,S) 면 번호(-1 = 빈 곳), bary (S,S,3), VR 돌린 꼭짓점)."""
    VR = V @ rot_y(yaw).T if yaw else V
    fi, bc = surface_samples(VR, F, size)
    tri = VR[F[fi]]                                                       # (K,3,3)
    p = (tri * bc[:, :, None]).sum(1)
    x = np.floor((p[:, 0] + 1) * 0.5 * size).astype(np.int64)
    y = np.floor((1 - p[:, 1]) * 0.5 * size).astype(np.int64)
    ok = (x >= 0) & (x < size) & (y >= 0) & (y < size)
    lin, z, fi, bc = (y * size + x)[ok], p[ok, 2], fi[ok], bc[ok]
    order = np.argsort(z, kind="stable")                                  # 가까운 점이 나중에 덮어써요
    depth = np.full(size * size, -np.inf, np.float32)
    face = np.full(size * size, -1, np.int64)
    bary = np.zeros((size * size, 3), np.float32)
    depth[lin[order]] = z[order]
    face[lin[order]] = fi[order]
    bary[lin[order]] = bc[order]
    return {"depth": depth.reshape(size, size), "face": face.reshape(size, size), "bary": bary.reshape(size, size, 3), "VR": VR}


def silhouette(V, F, size, yaw=0.0):
    return zbuffer(V, F, size, yaw)["face"] >= 0


def render(V, F, C=None, size=768, yaw=0.0, bg=(30, 30, 36), N=None, tint=None):
    """한 방향에서 본 그림(PIL). 꼭짓점 색 + 약한 음영. tint: (N,) 0~1 — 낮은 곳(AI 추정)을 푸르게 표시."""
    from .export import vertex_normals
    zb = zbuffer(V, F, size, yaw)
    hit = zb["face"] >= 0
    img = np.empty((size, size, 3), np.float32)
    img[:] = bg
    if hit.any():
        f = F[zb["face"][hit]]
        w = zb["bary"][hit][:, :, None]
        NR = (vertex_normals(V, F) if N is None else N) @ rot_y(yaw).T
        n = (NR[f] * w).sum(1)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        L = np.array([0.3, 0.4, 0.86], np.float32)
        sh = 0.45 + 0.55 * np.abs(n @ L)                                   # 뒤집힌 면도 어둡게 묻히지 않게 절댓값
        col = np.full((len(f), 3), 190.0, np.float32) if C is None else (C[f].astype(np.float32) * w).sum(1)
        if tint is not None:
            t = (tint[f] * w[:, :, 0]).sum(1)[:, None]
            col = col * (0.55 + 0.45 * t) + np.array([40, 70, 150], np.float32) * (1 - t) * 0.45
        img[hit] = col * sh[:, None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def _bilinear(img, x, y):
    h, w = img.shape[:2]
    x, y = np.clip(x, 0, w - 1.001), np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


def project_front(mesh, square_rgba, original_rgba=None, frame=None, size=1024, nz_lo=0.15, nz_hi=0.5, depth_px=3.0, edge_px=3):
    """앞에서 실제로 보이는 꼭짓점에 원본 사진 화소를 덮어써요.
    mesh: export.Mesh(꼭짓점 색 = 엔진 색). square_rgba: 엔진에 넣은 정사각형 그림.
    original_rgba·frame 이 있으면 줄이기 전 원본 화소(더 선명)를 써요.
    돌려주는 값: (새 색 (N,3) uint8, obs (N,) 0~1 — 사진에서 가져온 정도, 통계 dict)."""
    from .export import vertex_normals
    V, F = mesh.V, mesh.F
    base = mesh.C if mesh.C is not None else np.full((len(V), 3), 160, np.uint8)
    zb = zbuffer(V, F, size)
    N = vertex_normals(V, F)
    # 면 방향이 뒤집힌 메시(바깥이 안쪽)면 노멀 부호를 맞춰요 — 앞 표면의 노멀 z 평균으로 판단
    px = (V[:, 0] + 1) * 0.5 * size
    py = (1 - V[:, 1]) * 0.5 * size
    xi, yi = np.clip(np.floor(px).astype(np.int64), 0, size - 1), np.clip(np.floor(py).astype(np.int64), 0, size - 1)
    inside = (px >= 0) & (px < size) & (py >= 0) & (py < size)
    eps = depth_px * 2.0 / size
    near = inside & (V[:, 2] >= zb["depth"][yi, xi] - eps)                 # 깊이 검사: 그 화소에서 가장 앞에 있는 표면만
    flipped = bool(near.any() and np.median(N[near, 2]) < 0)
    nz = -N[:, 2] if flipped else N[:, 2]
    facing = np.clip((nz - nz_lo) / max(1e-6, nz_hi - nz_lo), 0, 1)
    facing = facing * facing * (3 - 2 * facing)
    # 사람 마스크 가장자리는 배경색이 섞여 있어서 안쪽으로 조금 들어간 곳부터 써요
    a = square_rgba.getchannel("A").resize((size, size), Image.BILINEAR)
    soft = np.asarray(a.filter(ImageFilter.MinFilter(2 * edge_px + 1)).filter(ImageFilter.GaussianBlur(edge_px / 2)), np.float32) / 255.0
    w = np.where(near, facing, 0.0) * _bilinear(soft[:, :, None], px - 0.5, py - 0.5)[:, 0]
    if original_rgba is not None and frame:
        src = np.asarray(original_rgba.convert("RGB"), np.float32)
        k = frame["size"] / size
        sx = (px * k - frame["ox"]) / frame["scale"] - 0.5
        sy = (py * k - frame["oy"]) / frame.get("scale_y", frame["scale"]) - 0.5
        used = "original"
    else:
        src = np.asarray(square_rgba.convert("RGB").resize((size, size), Image.BILINEAR), np.float32)
        sx, sy = px - 0.5, py - 0.5
        used = "square"
    photo = _bilinear(src, sx, sy)
    out = base.astype(np.float32) * (1 - w[:, None]) + photo * w[:, None]
    stats = {"observed_ratio": round(float((w > 0.5).mean()), 4), "front_visible_ratio": round(float(near.mean()), 4), "source": used,
             "flipped_normals": flipped, "size": size, "src_px": [int(src.shape[1]), int(src.shape[0])]}
    return np.clip(np.rint(out), 0, 255).astype(np.uint8), w.astype(np.float32), stats
