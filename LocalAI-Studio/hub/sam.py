# -*- coding: utf-8 -*-
"""클릭으로 물체·옷·부위를 골라 주는 선택 도구 (MobileSAM, ONNX).

- 이미지를 한 번 분석(embed)해 두면, 클릭할 때마다 아주 빠르게 마스크를 만들어요(CPU 로 충분).
- 모델 파일은 둘: 이미지 인코더(약 28MB) + 마스크 디코더(약 17MB). 설치 버튼이 받아 와요.
"""
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

REPO = "https://huggingface.co/Acly/MobileSAM/resolve/main/"
ENCODER = "mobile_sam_image_encoder.onnx"
DECODER = "sam_mask_decoder_multi.onnx"
SIZE = 1024
MEAN = np.array([123.675, 116.28, 103.53], dtype=np.float32)
STD = np.array([58.395, 57.12, 57.375], dtype=np.float32)


def have_ort():
    try:
        import onnxruntime  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def model_files(folder):
    f = Path(folder)
    return f / ENCODER, f / DECODER


def installed(folder):
    e, d = model_files(folder)
    return e.is_file() and d.is_file() and e.stat().st_size > 1e6 and d.stat().st_size > 1e6


class Sam:
    """session_factory(path) -> onnxruntime 처럼 run()/get_inputs() 를 가진 객체 (테스트에서 가짜를 넣을 수 있어요)."""

    def __init__(self, folder, session_factory=None):
        if session_factory is None:
            import onnxruntime as ort

            def session_factory(p):
                so = ort.SessionOptions()
                so.log_severity_level = 3
                return ort.InferenceSession(str(p), so, providers=["CPUExecutionProvider"])
        e, d = model_files(folder)
        self.enc, self.dec = session_factory(e), session_factory(d)
        self.cache = {}        # 이미지 해시 -> (임베딩, 원본 크기, 배율)

    def embed(self, img):
        """PIL 이미지 -> 이미지 id. 같은 이미지는 다시 분석하지 않아요."""
        key = hashlib.sha1(img.tobytes()[:2_000_000] + str(img.size).encode()).hexdigest()[:16]
        if key in self.cache:
            return key
        w, h = img.size
        s = SIZE / max(w, h)
        nw, nh = max(1, round(w * s)), max(1, round(h * s))
        arr = np.asarray(img.convert("RGB").resize((nw, nh), Image.BILINEAR), dtype=np.float32)
        inp = self.enc.get_inputs()[0]
        if len(inp.shape) == 3:      # 전처리가 모델 안에 들어 있는 형태: 원본 픽셀(HWC)
            x = arr
        else:                        # 밖에서 정규화하고 1024x1024 로 채우는 형태
            x = np.zeros((1, 3, SIZE, SIZE), dtype=np.float32)
            x[0, :, :nh, :nw] = ((arr - MEAN) / STD).transpose(2, 0, 1)
        emb = self.enc.run(None, {inp.name: x})[0]
        if len(self.cache) >= 4:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = (emb, (w, h), s)
        return key

    def segment(self, key, points, level=1):
        """points: [(x, y, label)] x,y 는 0~1 비율, label 1=포함 0=제외. level: 0 작게 / 1 보통 / 2 크게 (점이 하나일 때).
        반환: 원본 크기의 bool 배열(H, W)."""
        emb, (w, h), s = self.cache[key]
        pts = np.array([[x * w * s, y * h * s] for x, y, _ in points] + [[0.0, 0.0]], dtype=np.float32)[None]
        lab = np.array([l for _, _, l in points] + [-1], dtype=np.float32)[None]
        names = {i.name for i in self.dec.get_inputs()}
        feed = {"image_embeddings": emb, "point_coords": pts, "point_labels": lab,
                "mask_input": np.zeros((1, 1, 256, 256), dtype=np.float32), "has_mask_input": np.zeros(1, dtype=np.float32),
                "orig_im_size": np.array([h, w], dtype=np.float32)}
        out = self.dec.run(None, {k: v for k, v in feed.items() if k in names})
        masks, iou = out[0][0], out[1][0]           # (K, H, W) 로짓, (K,)
        idx = 0
        if len(points) == 1 and masks.shape[0] >= 4:
            cand = sorted(range(1, masks.shape[0]), key=lambda i: float((masks[i] > 0).sum()))   # 작은 → 큰 후보
            idx = cand[min(max(int(level), 0), len(cand) - 1)]
        return masks[idx] > 0
