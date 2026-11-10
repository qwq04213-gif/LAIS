# -*- coding: utf-8 -*-
"""배경 지우기 (U²-Net 계열 ONNX 모델, CPU 로 충분해요).

모델은 rembg 프로젝트가 배포하는 공개 ONNX 파일을 그대로 써요(받기는 '일괄 처리' 화면의 [설치] 버튼).
  fast    u2netp              약 5MB   빠르고 가벼움
  normal  silueta             약 44MB  보통 사진에 무난함(기본)
  precise isnet-general-use   약 179MB 머리카락·가장자리가 더 정교하지만 느림
"""
from pathlib import Path

import numpy as np
from PIL import Image

REPO = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
MODELS = {
    "fast": {"file": "u2netp.onnx", "size": 320, "mean": (0.485, 0.456, 0.406), "std": (0.229, 0.224, 0.225), "mb": 5, "label": "빠름"},
    "normal": {"file": "silueta.onnx", "size": 320, "mean": (0.485, 0.456, 0.406), "std": (0.229, 0.224, 0.225), "mb": 44, "label": "보통"},
    "precise": {"file": "isnet-general-use.onnx", "size": 1024, "mean": (0.5, 0.5, 0.5), "std": (1.0, 1.0, 1.0), "mb": 179, "label": "정밀"},
}


def have_ort():
    try:
        import onnxruntime  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def installed(folder, key):
    f = Path(folder) / MODELS[key]["file"]
    return f.is_file() and f.stat().st_size > MODELS[key]["mb"] * 1e6 * 0.5


class Remover:
    """session_factory(path) -> onnxruntime 처럼 run()/get_inputs() 를 가진 객체(테스트에서 가짜를 넣을 수 있어요)."""

    def __init__(self, folder, key, session_factory=None):
        if key not in MODELS:
            raise ValueError("알 수 없는 모델이에요.")
        if session_factory is None:
            import onnxruntime as ort

            def session_factory(p):
                so = ort.SessionOptions()
                so.log_severity_level = 3
                return ort.InferenceSession(str(p), so, providers=["CPUExecutionProvider"])
        self.cfg = MODELS[key]
        self.sess = session_factory(Path(folder) / self.cfg["file"])

    def mask(self, img):
        """PIL 이미지 -> 같은 크기의 'L' 마스크(흰색=남길 부분)."""
        c = self.cfg
        s = c["size"]
        a = np.asarray(img.convert("RGB").resize((s, s), Image.Resampling.LANCZOS), dtype=np.float32)
        a = a / max(float(a.max()), 1e-6)
        a = (a - np.array(c["mean"], dtype=np.float32)) / np.array(c["std"], dtype=np.float32)
        x = a.transpose(2, 0, 1)[None].astype(np.float32)
        out = self.sess.run(None, {self.sess.get_inputs()[0].name: x})[0]
        pred = np.asarray(out)[0, 0] if np.ndim(out) == 4 else np.asarray(out).reshape(s, s)
        lo, hi = float(pred.min()), float(pred.max())
        pred = (pred - lo) / (hi - lo) if hi > lo else np.zeros_like(pred)
        return Image.fromarray((pred * 255).clip(0, 255).astype("uint8"), "L").resize(img.size, Image.Resampling.LANCZOS)

    def cut(self, img, bg=None, refine_edges=True, **_):
        """배경을 지운 RGBA 이미지. bg 가 (r,g,b) 면 그 색으로 채운 RGB 이미지. 경계는 원본 사진에 맞춰 다듬어요(refine)."""
        m = self.mask(img)
        return compose(img, m, bg, refine_edges, coarse=self.cfg["size"] < 1024, model_size=self.cfg["size"])


def _box(a, r):
    """가로·세로 (2r+1) 평균 흐림(누적합, 가장자리는 늘려 채움)."""
    for ax in (0, 1):
        n = a.shape[ax]
        pad = [(0, 0)] * a.ndim
        pad[ax] = (r + 1, r)
        c = np.cumsum(np.pad(a, pad, mode="edge"), axis=ax, dtype=np.float64)
        a = (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax) - np.take(c, np.arange(0, n), axis=ax)) / (2 * r + 1)
    return a.astype(np.float32)


def guided(img, p, r, eps=1e-4, lo=1024):
    """컬러 가이드 필터(빠른 판): 마스크 p(0~1, H×W)의 경계를 사진의 실제 색 경계에 맞춰요.
    계산은 긴 변 lo 이하로 줄여서 하고, 계수만 원래 크기로 늘려 적용해요(4000px 사진도 몇 초)."""
    W, H = img.size
    s = max(1.0, max(W, H) / lo)
    w2, h2 = max(1, round(W / s)), max(1, round(H / s))
    I = np.asarray(img.convert("RGB").resize((w2, h2), Image.Resampling.BILINEAR), dtype=np.float32) / 255
    pl = np.asarray(Image.fromarray(p.astype(np.float32), "F").resize((w2, h2), Image.Resampling.BILINEAR), dtype=np.float32)
    rr = max(1, round(r / s))
    mI = np.stack([_box(I[..., c], rr) for c in range(3)], -1)
    mp = _box(pl, rr)
    cov = np.stack([_box(I[..., c] * pl, rr) for c in range(3)], -1) - mI * mp[..., None]
    S = np.empty((h2, w2, 3, 3), np.float32)
    for i in range(3):
        for j in range(i, 3):
            S[..., i, j] = S[..., j, i] = _box(I[..., i] * I[..., j], rr) - mI[..., i] * mI[..., j]
    S += eps * np.eye(3, dtype=np.float32)
    A = np.linalg.solve(S, cov[..., None])[..., 0]
    b = mp - (A * mI).sum(-1)

    def up(x):
        return np.asarray(Image.fromarray(_box(x, rr).astype(np.float32), "F").resize((W, H), Image.Resampling.BILINEAR), dtype=np.float32)
    full = np.asarray(img.convert("RGB"), dtype=np.float32) / 255
    return sum(up(A[..., c]) * full[..., c] for c in range(3)) + up(b)


def refine(img, mask, coarse=True, model_size=320):
    """경계 다듬기 → (알파 'L', 경계 색을 바로잡은 RGB).
    1) 작은 해상도로 찾은 흐릿한 경계를 원본 사진의 실제 색 경계에 맞춰 또렷하게(컬러 가이드 필터, 경계 근처만)
    2) 반투명 띠를 조금 좁혀 흐릿함을 줄이고(머리카락 같은 가는 부분은 남겨요)
    3) 경계 픽셀에 남은 배경색을 걷어내고 안쪽 물체 색으로 채워요(색 번짐 제거)"""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32) / 255
    p = np.asarray(mask.convert("L").resize(img.size), dtype=np.float32) / 255
    H, W = p.shape
    if coarse:
        r = max(3, int(np.ceil(3 * max(W, H) / model_size)))           # 늘린 배율의 3배 창이어야 흐린 띠를 잡아요
        q = np.clip(guided(img, p, r), 0, 1)
        band = _box(((p > 0.02) & (p < 0.98)).astype(np.float32), r) > 0
        p = np.where(band, q, p)
    a = np.clip((p - 0.04) / 0.92, 0, 1)
    a = a * a * (3 - 2 * a) * 0.5 + a * 0.5                               # 가운데를 조금 더 가파르게
    semi = (a > 0.01) & (a < 0.97)
    if semi.any():
        rr = max(3, round(max(W, H) / 120))
        w = (a >= 0.97).astype(np.float32)
        sw = _box(w, rr)
        F = np.stack([_box(rgb[..., c] * w, rr) for c in range(3)], -1) / np.maximum(sw, 1e-6)[..., None]
        ok = semi & (sw > 1e-3)
        rgb = rgb.copy()
        rgb[ok] = F[ok]
    return Image.fromarray((a * 255 + 0.5).astype("uint8"), "L"), Image.fromarray((rgb * 255 + 0.5).clip(0, 255).astype("uint8"), "RGB")


def compose(img, mask, bg=None, refine_edges=True, coarse=True, model_size=320):
    """마스크로 배경 지우기 → RGBA(또는 bg 색으로 채운 RGB)."""
    if refine_edges:
        alpha, col = refine(img, mask, coarse, model_size)
    else:
        alpha, col = mask.convert("L").resize(img.size), img.convert("RGB")
    rgba = col.convert("RGBA")
    rgba.putalpha(alpha)
    if bg is None:
        return rgba
    base = Image.new("RGBA", img.size, tuple(bg) + (255,))
    base.alpha_composite(rgba)
    return base.convert("RGB")
