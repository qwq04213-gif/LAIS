# -*- coding: utf-8 -*-
"""자동 마스크: 얼굴 찾기(LBP 캐스케이드, numpy 로 직접 계산 - OpenCV 설치 불필요). 모델 파일은 처음 쓸 때 한 번만 받아요.

- 실사 얼굴: OpenCV 의 lbpcascade_frontalface_improved
- 애니메 얼굴: nagadomi 의 lbpcascade_animeface (MIT)
정면에 가까운 얼굴에 잘 맞고, 옆모습·가려진 얼굴·아주 작은 얼굴은 놓칠 수 있어요(그럴 땐 마법봉이나 브러시로 보정).
"""
import urllib.request
from pathlib import Path

CASCADES = {
    "anime": ("lbpcascade_animeface.xml", "https://raw.githubusercontent.com/nagadomi/lbpcascade_animeface/master/lbpcascade_animeface.xml"),
    "real": ("lbpcascade_frontalface_improved.xml", "https://raw.githubusercontent.com/opencv/opencv/4.x/data/lbpcascades/lbpcascade_frontalface_improved.xml"),
}


def fetch(kind, folder, opener=None):
    """캐스케이드 파일 경로(없으면 받아 옴). 받지 못하면 None."""
    name, url = CASCADES[kind]
    f = Path(folder) / name
    if f.is_file() and f.stat().st_size > 1000:
        return f
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "LocalAI-Studio/1.0"})
        with (opener or urllib.request.build_opener()).open(req, timeout=30) as r:
            data = r.read()
        if len(data) < 1000 or b"<opencv_storage" not in data[:400]:
            return None
        f.write_bytes(data)
        return f
    except Exception:  # noqa: BLE001
        return None


def _iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix, iy = max(0, min(ax + aw, bx + bw) - max(ax, bx)), max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / float(aw * ah + bw * bh - inter or 1)


_CACHE = {}


def load_lbp(path):
    """OpenCV LBP 캐스케이드 XML 을 읽어요(numpy 만 쓰고 OpenCV 는 필요 없어요)."""
    import xml.etree.ElementTree as ET
    import numpy as np
    key = str(path)
    if key in _CACHE:
        return _CACHE[key]
    c = ET.parse(str(path)).getroot().find("cascade")
    if c is None or (c.findtext("featureType") or "").strip().upper() != "LBP":
        raise ValueError("지원하지 않는 캐스케이드 형식이에요(LBP 만 지원).")
    win = (int(c.findtext("width")), int(c.findtext("height")))
    feats = [tuple(int(v) for v in f.findtext("rect").split()) for f in c.find("features")]
    stages = []
    for st in c.find("stages"):
        weak = []
        for wc in st.find("weakClassifiers"):
            n = wc.findtext("internalNodes").split()
            fi, sub = int(n[2]), np.array([int(v) & 0xFFFFFFFF for v in n[3:11]], dtype=np.uint32)
            lv = [float(v) for v in wc.findtext("leafValues").split()]
            weak.append((fi, sub, lv[0], lv[1]))
        stages.append((float(st.findtext("stageThreshold")), weak))
    _CACHE[key] = (win, feats, stages)
    return _CACHE[key]


def detect(gray, cascade, min_size=24, scale=1.1, step=2, min_hits=2):
    """gray: uint8 2차원 배열. 얼굴 상자 [(x,y,w,h)...]."""
    import numpy as np
    from PIL import Image
    (ww, wh), feats, stages = cascade
    H, W = gray.shape
    hits = []
    s = max(1.0, min_size / ww)
    while ww * s <= W and wh * s <= H:
        sw, sh = int(W / s), int(H / s)
        if sw < ww + 2 or sh < wh + 2:
            break
        g = np.asarray(Image.fromarray(gray).resize((sw, sh), Image.BILINEAR), dtype=np.int64)
        I = np.zeros((sh + 1, sw + 1), dtype=np.int64)
        I[1:, 1:] = g.cumsum(0).cumsum(1)
        ys, xs = np.mgrid[0:sh - wh + 1:step, 0:sw - ww + 1:step]
        ys, xs = ys.ravel(), xs.ravel()
        for thr, weak in stages:
            if len(ys) == 0:
                break
            tot = np.zeros(len(ys))
            for fi, sub, l0, l1 in weak:
                fx, fy, fw, fh = feats[fi]
                X, Y = xs + fx, ys + fy

                def cell(r, c):
                    x0, y0 = X + c * fw, Y + r * fh
                    return I[y0 + fh, x0 + fw] - I[y0, x0 + fw] - I[y0 + fh, x0] + I[y0, x0]
                cv = cell(1, 1)
                code = ((cell(0, 0) >= cv) * 128 | (cell(0, 1) >= cv) * 64 | (cell(0, 2) >= cv) * 32 | (cell(1, 2) >= cv) * 16 |
                        (cell(2, 2) >= cv) * 8 | (cell(2, 1) >= cv) * 4 | (cell(2, 0) >= cv) * 2 | (cell(1, 0) >= cv) * 1)
                bit = (sub[code >> 5] >> (code & 31).astype(np.uint32)) & 1
                tot += np.where(bit == 1, l0, l1)
            keep = tot >= thr - 1e-5
            ys, xs = ys[keep], xs[keep]
        hits += [(int(x * s), int(y * s), int(ww * s), int(wh * s)) for x, y in zip(xs, ys)]
        s *= scale
    # 겹치는 후보를 묶고, 후보가 충분히 모인 곳만 얼굴로 인정해요
    groups = []
    for h in sorted(hits, key=lambda b: -b[2]):
        for g in groups:
            if _iou(g[0], h) > 0.3:
                g.append(h)
                break
        else:
            groups.append([h])
    top = max([len(g) for g in groups] or [0])
    out = []
    for g in groups:
        if len(g) >= max(min_hits, 0.3 * top):   # 후보가 많이 모인 곳만 (오탐 줄이기)
            out.append(tuple(int(sum(b[i] for b in g) / len(g)) for i in range(4)))
    return out


def find_faces(img, files):
    """PIL 이미지에서 얼굴 상자 (원본 좌표). files: [(종류, xml 경로)...]"""
    import numpy as np
    W, H = img.size
    k = min(1.0, 800 / max(W, H))
    g = img.convert("L").resize((max(1, round(W * k)), max(1, round(H * k))))
    from PIL import ImageOps
    arr = np.asarray(ImageOps.equalize(g), dtype=np.uint8)
    boxes = []
    for kind, f in files:
        for b in detect(arr, load_lbp(f), min_size=max(24, int(min(arr.shape) * 0.06))):
            b = tuple(int(v / k) for v in b)
            if not any(_iou(b, o) > 0.4 for o in boxes):
                boxes.append(b)
    return boxes


def face_mask(img, boxes, pad=0.15):
    """얼굴 상자마다 타원을 그린 마스크(L). pad 는 상자 크기에 대한 바깥 여유 비율(머리카락까지 넣으려면 0.5~0.7)."""
    from PIL import Image, ImageDraw
    m = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(m)
    for x, y, w, h in boxes:
        px, py = w * pad, h * pad
        d.ellipse((x - px, y - py, x + w + px, y + h + py), fill=255)
    return m
