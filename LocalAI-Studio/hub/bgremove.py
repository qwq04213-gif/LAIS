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

    def cut(self, img, bg=None):
        """배경을 지운 RGBA 이미지. bg 가 (r,g,b) 면 그 색으로 채운 RGB 이미지."""
        m = self.mask(img)
        rgba = img.convert("RGBA")
        rgba.putalpha(m)
        if bg is None:
            return rgba
        base = Image.new("RGBA", img.size, tuple(bg) + (255,))
        base.alpha_composite(rgba)
        return base.convert("RGB")
