"""MobileSAM 대신 쓰는 가짜 ONNX 세션: 임베딩 = 정규화된 이미지, 디코더 = 클릭한 곳과 비슷한 색 영역(레벨별로 허용치가 커짐)."""
import numpy as np

class _In:
    def __init__(s, name, shape): s.name, s.shape = name, shape

class FakeEnc:
    def get_inputs(s): return [_In("input_image", [1, 3, 1024, 1024])]
    def run(s, _, feed): return [feed["input_image"]]

class FakeDec:
    calls = []
    def get_inputs(s): return [_In(n, None) for n in ("image_embeddings", "point_coords", "point_labels", "mask_input", "has_mask_input", "orig_im_size")]
    def run(s, _, f):
        FakeDec.calls.append({k: np.array(v) for k, v in f.items() if k != "image_embeddings"})
        emb = f["image_embeddings"][0]; h, w = [int(v) for v in f["orig_im_size"]]
        sc = 1024 / max(h, w); nh, nw = round(h * sc), round(w * sc)
        img = emb[:, :nh, :nw]
        sel = np.zeros((nh, nw), bool)
        for (x, y), l in zip(f["point_coords"][0], f["point_labels"][0]):
            if l < 0: continue
            x, y = min(nw - 1, int(x)), min(nh - 1, int(y)); c = img[:, y, x][:, None, None]
            sel |= np.abs(img - c).sum(0) < 0.3
        ys = (np.arange(h) * sc).astype(int).clip(0, nh - 1); xs = (np.arange(w) * sc).astype(int).clip(0, nw - 1)
        m = sel[np.ix_(ys, xs)].astype(np.float32) * 2 - 1
        return [np.stack([m] * 4)[None], np.array([[.9, .8, .7, .6]], np.float32)]

def factory(path): return FakeEnc() if "encoder" in str(path) else FakeDec()
