"""깊이 맵으로 하는 일(이미지 엔진 없이 numpy 로): 배경 흐림·전경/배경 효과, 패럴랙스(2.5D) 장면, 3D 메시(.glb),
영상 깊이의 프레임 간 일관성(깜빡임 줄이기), 영상의 카메라 움직임(2D) 추정.

깊이 맵은 '가까울수록 밝게'(0~255) 흑백 이미지로 받아요. 모든 값은 AI 추정이라 실제 거리·실제 3D 와 같지 않아요.
"""
import io
import json
import math
import struct

import numpy as np
from PIL import Image, ImageFilter


def as_depth(d, size=None):
    """흑백 깊이 → 0~1 float 배열(가까울수록 1)."""
    g = d.convert("L")
    if size and g.size != size:
        g = g.resize(size, Image.BICUBIC)
    a = np.asarray(g, dtype=np.float32) / 255.0
    lo, hi = np.percentile(a, 1), np.percentile(a, 99)
    return np.clip((a - lo) / max(1e-6, hi - lo), 0, 1)


# ─────────────────────────── 배경 흐림 · 전경/배경 효과 ───────────────────────────
def lens_blur(img, depth, focus=None, strength=12, levels=6):
    """초점(0~1, None 이면 가장 가까운 쪽)에서 멀어질수록 더 흐리게. 여러 단계로 흐린 그림을 깊이에 따라 섞어요."""
    img = img.convert("RGB")
    d = as_depth(depth, img.size)
    f = float(np.percentile(d, 95)) if focus is None else float(focus)
    dist = np.clip(np.abs(d - f) / max(f, 1 - f, 1e-3), 0, 1)
    dist = np.asarray(Image.fromarray((dist * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)), dtype=np.float32) / 255.0
    stack = [np.asarray(img, dtype=np.float32)]
    for i in range(1, levels):
        stack.append(np.asarray(img.filter(ImageFilter.GaussianBlur(strength * i / (levels - 1))), dtype=np.float32))
    pos = dist * (levels - 1)
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, levels - 1)
    t = (pos - lo)[..., None]
    S = np.stack(stack)                          # (L,H,W,3)
    yy, xx = np.indices(lo.shape)
    out = S[lo, yy, xx] * (1 - t) + S[hi, yy, xx] * t
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def fg_bg(img, depth, effect="gray", amount=0.8, near=50, feather=8):
    """깊이로 앞(전경)·뒤(배경)를 나눠 배경에만 효과: gray(흑백) · dark(어둡게) · fog(먼 곳일수록 안개) · desat(채도 낮추기) · blur."""
    img = img.convert("RGB")
    d = as_depth(depth, img.size)
    a = np.asarray(img, dtype=np.float32)
    if effect == "fog":
        w = (1 - d)[..., None] * float(amount)
        fogc = np.array([215, 220, 228], dtype=np.float32)
        return Image.fromarray(np.clip(a * (1 - w) + fogc * w, 0, 255).astype(np.uint8))
    cut = near / 100.0
    m = (d >= cut).astype(np.float32)
    if feather:
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(feather)), dtype=np.float32) / 255.0
    bgw = (1 - m)[..., None] * float(amount)
    if effect == "dark":
        b = a * 0.35
    elif effect == "blur":
        b = np.asarray(img.filter(ImageFilter.GaussianBlur(14)), dtype=np.float32)
    else:
        g = (a @ np.array([0.299, 0.587, 0.114], dtype=np.float32))[..., None]
        b = np.repeat(g, 3, axis=2) if effect == "gray" else a * 0.35 + np.repeat(g, 3, axis=2) * 0.65
    return Image.fromarray(np.clip(a * (1 - bgw) + b * bgw, 0, 255).astype(np.uint8))


def colorize(gray):
    """흑백 깊이 → 색(먼 곳 파랑 → 가까운 곳 빨강)."""
    stops = np.array([0, 85, 150, 205, 255], dtype=np.float32)
    cols = np.array([(40, 40, 160), (30, 170, 200), (90, 200, 80), (250, 210, 50), (220, 40, 30)], dtype=np.float32)
    v = np.asarray(gray.convert("L"), dtype=np.float32)
    out = np.stack([np.interp(v, stops, cols[:, c]) for c in range(3)], axis=-1)
    return Image.fromarray(out.astype(np.uint8))


# ─────────────────────────── 패럴랙스(2.5D) 영상 ───────────────────────────
MOTIONS = ("orbit", "sway", "dolly", "rise", "camera")


def motion_path(kind, n, camera=None):
    """프레임마다 (가로 이동, 세로 이동, 확대) — -1~1 범위의 상대값."""
    t = np.linspace(0, 1, n, endpoint=False)
    if kind == "camera" and camera:
        c = np.asarray(camera, dtype=np.float32)                 # [[dx, dy, scale], ...] 누적값
        src = np.linspace(0, 1, len(c))
        dx, dy, sc = (np.interp(t, src, c[:, k]) for k in range(3))
        span = max(1e-6, float(np.max(np.abs(np.concatenate([dx, dy])))))
        return np.stack([dx / span, dy / span, (sc - 1) * 4], axis=1)
    if kind == "sway":
        return np.stack([np.sin(t * 2 * math.pi), np.zeros(n), np.zeros(n)], axis=1)
    if kind == "dolly":
        e = (1 - np.cos(t * math.pi)) / 2
        return np.stack([np.zeros(n), np.zeros(n), e], axis=1)
    if kind == "rise":
        e = (1 - np.cos(t * math.pi)) / 2
        return np.stack([np.zeros(n), e * 2 - 1, e * 0.4], axis=1)
    return np.stack([np.sin(t * 2 * math.pi), np.cos(t * 2 * math.pi) * 0.5, np.zeros(n)], axis=1)       # orbit


def parallax_frames(img, depth, kind="orbit", seconds=4.0, fps=24, strength=0.05, camera=None, max_side=1280):
    """사진 + 깊이 → 카메라가 움직이는 듯한 프레임들(가까운 것이 더 많이 움직여요). 생성기(PIL 이미지)를 돌려줘요."""
    img = img.convert("RGB")
    if max(img.size) > max_side:
        k = max_side / max(img.size)
        img = img.resize((round(img.width * k) // 2 * 2, round(img.height * k) // 2 * 2), Image.LANCZOS)
    W, H = img.width // 2 * 2, img.height // 2 * 2
    img = img.crop((0, 0, W, H))
    a = np.asarray(img, dtype=np.float32)
    d = as_depth(depth, (W, H))
    d = np.asarray(Image.fromarray((d * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3)), dtype=np.float32) / 255.0
    n = max(2, int(round(seconds * fps)))
    path = motion_path(kind, n, camera)
    yy, xx = np.indices((H, W), dtype=np.float32)
    cx, cy = W / 2, H / 2
    amp = strength * max(W, H)
    pad = 1 + strength * 2.2                       # 가장자리 빈 곳이 안 보이게 살짝 확대해요
    for mx, my, mz in path:
        z = 1 + mz * strength * 3
        sx = (xx - cx) / (pad * z) + cx - mx * amp * d
        sy = (yy - cy) / (pad * z) + cy - my * amp * d
        x0 = np.clip(np.floor(sx).astype(int), 0, W - 2)
        y0 = np.clip(np.floor(sy).astype(int), 0, H - 2)
        fx = np.clip(sx - x0, 0, 1)[..., None]
        fy = np.clip(sy - y0, 0, 1)[..., None]
        p = (a[y0, x0] * (1 - fx) + a[y0, x0 + 1] * fx) * (1 - fy) + (a[y0 + 1, x0] * (1 - fx) + a[y0 + 1, x0 + 1] * fx) * fy
        yield Image.fromarray(np.clip(p, 0, 255).astype(np.uint8))


# ─────────────────────────── 3D 메시(.glb) ───────────────────────────
def mesh_glb(img, depth, grid=192, depth_scale=0.35):
    """사진을 깊이만큼 앞뒤로 밀어낸 격자 메시(정면에서 본 모양) → glTF 바이너리(.glb). 사진이 그대로 표면 무늬가 돼요."""
    img = img.convert("RGB")
    W, H = img.size
    gx = max(8, min(512, int(grid)))
    gy = max(8, int(round(gx * H / W)))
    d = as_depth(depth, (gx, gy))
    aspect = W / H
    xs, ys = np.linspace(-aspect / 2, aspect / 2, gx, dtype=np.float32), np.linspace(0.5, -0.5, gy, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)
    Z = (d - 0.5) * depth_scale
    pos = np.stack([X, Y, Z], axis=-1).reshape(-1, 3).astype(np.float32)
    u, v = np.meshgrid(np.linspace(0, 1, gx, dtype=np.float32), np.linspace(0, 1, gy, dtype=np.float32))
    uv = np.stack([u, v], axis=-1).reshape(-1, 2).astype(np.float32)
    i = np.arange(gx * gy, dtype=np.uint32).reshape(gy, gx)
    a, b, c, e = i[:-1, :-1], i[:-1, 1:], i[1:, :-1], i[1:, 1:]
    jump = np.abs(d[:-1, :-1] - d[1:, 1:]) > 0.25          # 깊이가 크게 끊기는 곳(물체 경계)은 늘어난 면을 만들지 않아요
    tri = np.concatenate([np.stack([a, c, b], -1)[~jump], np.stack([b, c, e], -1)[~jump]]).reshape(-1).astype(np.uint32)
    tex = io.BytesIO()
    t_img = img if max(img.size) <= 2048 else img.resize((round(W * 2048 / max(W, H)), round(H * 2048 / max(W, H))), Image.LANCZOS)
    t_img.save(tex, "JPEG", quality=90)
    blobs = [pos.tobytes(), uv.tobytes(), tri.tobytes(), tex.getvalue()]
    views, off, binbuf = [], 0, b""
    for k, bl in enumerate(blobs):
        while len(binbuf) % 4:
            binbuf += b"\0"
        off = len(binbuf)
        binbuf += bl
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(bl), **({"target": 34962} if k < 2 else {"target": 34963} if k == 2 else {})})
    while len(binbuf) % 4:
        binbuf += b"\0"
    gltf = {"asset": {"version": "2.0", "generator": "LocalAI-Studio depthfx"},
            "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
            "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0, "roughnessFactor": 1}, "doubleSided": True}],
            "textures": [{"source": 0, "sampler": 0}], "samplers": [{"magFilter": 9729, "minFilter": 9987}],
            "images": [{"bufferView": 3, "mimeType": "image/jpeg"}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3", "min": pos.min(0).tolist(), "max": pos.max(0).tolist()},
                          {"bufferView": 1, "componentType": 5126, "count": len(uv), "type": "VEC2"},
                          {"bufferView": 2, "componentType": 5125, "count": int(tri.size), "type": "SCALAR"}],
            "bufferViews": views, "buffers": [{"byteLength": len(binbuf)}]}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    total = 12 + 8 + len(js) + 8 + len(binbuf)
    return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(binbuf), 0x004E4942) + binbuf), int(tri.size // 3)


# ─────────────────────────── 영상 깊이 일관성 ───────────────────────────
def stabilize_depth(frames, smooth=0.6):
    """프레임마다 따로 추정한 깊이를 이어지게: 전체 영상 기준 밝기 범위로 맞추고(프레임마다 밝기 기준이 달라 깜빡이는 것),
    앞뒤 프레임과 섞어(지수 평균, 양방향) 작은 떨림을 줄여요. frames: 흑백 PIL 목록 → 같은 크기 흑백 PIL 목록."""
    A = np.stack([np.asarray(f.convert("L"), dtype=np.float32) for f in frames])
    # 프레임마다 1~99% 값을 영상 전체의 중앙값 범위로 맞춰요
    lo, hi = np.percentile(A, 1, axis=(1, 2)), np.percentile(A, 99, axis=(1, 2))
    Lo, Hi = float(np.median(lo)), float(np.median(hi))
    A = (A - lo[:, None, None]) / np.maximum(1e-3, (hi - lo)[:, None, None]) * (Hi - Lo) + Lo
    s = float(min(max(smooth, 0.0), 0.95))
    if s > 0 and len(A) > 1:
        fw, bw = A.copy(), A.copy()
        for k in range(1, len(A)):
            fw[k] = s * fw[k - 1] + (1 - s) * A[k]
        for k in range(len(A) - 2, -1, -1):
            bw[k] = s * bw[k + 1] + (1 - s) * A[k]
        A = (fw + bw) / 2
    return [Image.fromarray(np.clip(x, 0, 255).astype(np.uint8)) for x in A]


def flicker(frames):
    """깊이 영상이 얼마나 깜빡이는지(이웃 프레임 평균 밝기 차이의 평균). 낮을수록 안정적."""
    m = np.array([np.asarray(f.convert("L"), dtype=np.float32).mean() for f in frames])
    return float(np.mean(np.abs(np.diff(m)))) if len(m) > 1 else 0.0


# ─────────────────────────── 카메라 움직임(2D) 추정 ───────────────────────────
def _shift(a, b):
    """두 흑백 배열 사이 평행 이동(위상 상관)."""
    F = np.fft.fft2(a) * np.conj(np.fft.fft2(b))
    r = np.fft.ifft2(F / np.maximum(np.abs(F), 1e-6)).real
    y, x = np.unravel_index(int(np.argmax(r)), r.shape)
    h, w = a.shape
    return (x - w if x > w // 2 else x), (y - h if y > h // 2 else y), float(r.max())


def camera_track(frames, size=256):
    """이웃 프레임 사이의 화면 이동(가로·세로, 픽셀 비율)과 확대(줌)를 어림해 누적한 경로.
    돌려주는 값: [{"dx","dy","scale"}...] 누적값 — 진짜 3D 카메라가 아니라 화면 위 움직임(2D) 추정이에요."""
    prev, out, cx, cy, cs = None, [{"dx": 0.0, "dy": 0.0, "scale": 1.0}], 0.0, 0.0, 1.0
    win = None
    for f in frames:
        g = f.convert("L")
        k = size / max(g.size)
        g = g.resize((max(16, round(g.width * k)), max(16, round(g.height * k))), Image.BILINEAR)
        a = np.asarray(g, dtype=np.float32)
        a = a - a.mean()
        if win is None or win.shape != a.shape:
            win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1])).astype(np.float32)
        a = a * win
        if prev is not None:
            best = (0.0, 0.0, 1.0, -1.0)
            for s in (0.97, 0.985, 1.0, 1.015, 1.03):
                if s == 1.0:
                    b = prev
                else:
                    h, w = prev.shape
                    im = Image.fromarray(prev).resize((max(8, round(w * s)), max(8, round(h * s))), Image.BILINEAR)
                    bb = np.asarray(im, dtype=np.float32)
                    b = np.zeros_like(prev)
                    oy, ox = (bb.shape[0] - h) // 2, (bb.shape[1] - w) // 2
                    if s > 1:
                        b = bb[oy:oy + h, ox:ox + w]
                    else:
                        b[-oy:-oy + bb.shape[0], -ox:-ox + bb.shape[1]] = bb
                dx, dy, q = _shift(a, b)
                if q > best[3]:
                    best = (dx, dy, s, q)
            cx += best[0] / a.shape[1]
            cy += best[1] / a.shape[0]
            cs *= best[2]
            out.append({"dx": round(cx, 5), "dy": round(cy, 5), "scale": round(cs, 5)})
        prev = a
    return out


def track_chart(track, w=640, h=360):
    """카메라 경로 그림(위: 가로·세로 이동 경로, 아래: 확대 변화)."""
    from PIL import ImageDraw
    im = Image.new("RGB", (w, h), (24, 24, 28))
    dr = ImageDraw.Draw(im)
    xs = np.array([t["dx"] for t in track]); ys = np.array([t["dy"] for t in track]); ss = np.array([t["scale"] for t in track])
    span = max(1e-6, float(np.max(np.abs(np.concatenate([xs, ys])))))
    top = h * 0.68
    pts = [(w / 2 + x / span * (w * 0.4), top / 2 + y / span * (top * 0.4)) for x, y in zip(xs, ys)]
    dr.rectangle((0, 0, w - 1, top), outline=(70, 70, 80))
    if len(pts) > 1:
        dr.line(pts, fill=(120, 170, 255), width=3)
    dr.ellipse((pts[0][0] - 5, pts[0][1] - 5, pts[0][0] + 5, pts[0][1] + 5), fill=(90, 220, 120))
    dr.ellipse((pts[-1][0] - 5, pts[-1][1] - 5, pts[-1][0] + 5, pts[-1][1] + 5), fill=(240, 90, 80))
    dr.text((8, 6), "camera path (screen 2D)  green=start  red=end", fill=(200, 200, 210))
    smin, smax = float(ss.min()), float(ss.max())
    rng = max(1e-6, smax - smin)
    zp = [(8 + i / max(1, len(ss) - 1) * (w - 16), h - 10 - (s - smin) / rng * (h - top - 30)) for i, s in enumerate(ss)]
    if len(zp) > 1:
        dr.line(zp, fill=(250, 200, 80), width=2)
    dr.text((8, top + 6), f"zoom {smin:.3f} ~ {smax:.3f}", fill=(200, 200, 210))
    return im
