"""사진 준비: 원본 보존 → 사람 마스크 → 배경 지운 사진 → 정사각형 가운데 정렬(전신이 잘리지 않게 여백 자동 계산),
그리고 자세 검출 결과(COCO-WholeBody 133점: DWPose·RTMPose 가 내는 형식)를 SiTH 가 읽는 OpenPose JSON 으로 바꾸기."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from . import contracts as K

SIZE = 1024          # SiTH 입력 크기
RATIO = 0.85         # 사람 키가 그림 높이에서 차지하는 비율(SiTH 기본)
SIDE_MAX = 0.90      # 팔을 벌린 사진처럼 옆으로 넓으면 폭이 이 비율을 넘지 않게 줄여요


def person_box(alpha, thr=24):
    a = np.asarray(alpha) > thr
    ys, xs = np.where(a)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def body_checks(rgba):
    """사진 상태 점검(전신이 잘렸는지·너무 작은지). [{id, level(ok/warn/bad), text}]"""
    a = np.asarray(rgba.getchannel("A")) > 24
    h, w = a.shape
    out = []
    box = person_box(rgba.getchannel("A"))
    if box is None or a.mean() < 0.01:
        return [{"id": "person", "level": "bad", "text": "사람이 보이지 않아요. 배경 지우기가 사람을 지웠을 수 있어요."}]
    x0, y0, x1, y1 = box
    edge = {"위": a[0].mean(), "아래": a[-1].mean(), "왼쪽": a[:, 0].mean(), "오른쪽": a[:, -1].mean()}
    cut = [k for k, v in edge.items() if v > 0.02]
    if cut:
        out.append({"id": "cut", "level": "warn", "text": f"사람이 사진 {'·'.join(cut)} 가장자리에 닿아 있어요. 잘린 부분은 3D 에서도 없거나 AI 가 추정해요. 몸 전체가 들어온 사진이 가장 좋아요."})
    ph = y1 - y0
    if ph < 512:
        out.append({"id": "small", "level": "warn", "text": f"사람 크기가 {ph}px 로 작아요(권장 1024px 이상). 얼굴·옷 무늬가 흐리게 나올 수 있어요."})
    asp = (x1 - x0) / max(1, ph)
    if asp > 1.2:
        out.append({"id": "wide", "level": "warn", "text": "서 있는 전신 사진이 아닌 것 같아요(가로로 넓어요). 앉거나 누운 자세는 결과가 나쁠 수 있어요."})
    if not out:
        out.append({"id": "ok", "level": "ok", "text": "사진 상태가 좋아요."})
    return out


def square_input(rgba, size=SIZE, ratio=RATIO, erode=2):
    """배경 지운 사진 → 정사각형 가운데 정렬 RGBA. 사람 범위만 잘라 키를 size×ratio 에 맞추고(폭이 넘치면 폭 기준),
    가장자리 잡티를 줄이려고 마스크를 조금 깎아요(SiTH 의 centralize_rgba 와 같은 처리).
    돌려주는 값: (그림, frame) — frame 은 원본 화소 (x, y) → 정사각형 (x*s+ox, y*s+oy) 변환 값."""
    box = person_box(rgba.getchannel("A"))
    if box is None:
        raise ValueError(K.ERRORS["no_person"])
    x0, y0, x1, y1 = box
    crop = rgba.crop(box)
    s = min(size * ratio / crop.height, size * SIDE_MAX / crop.width)
    tw, th = max(1, round(crop.width * s)), max(1, round(crop.height * s))
    small = crop.resize((tw, th), Image.LANCZOS)
    if erode > 0:
        r, g, b, a = small.split()
        a = a.filter(ImageFilter.MinFilter(2 * erode + 1))
        small = Image.merge("RGBA", (r, g, b, a))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ox, oy = (size - tw) // 2, (size - th) // 2
    canvas.paste(small, (ox, oy))
    frame = {"size": size, "scale": tw / crop.width, "scale_y": th / crop.height, "ox": ox - x0 * tw / crop.width, "oy": oy - y0 * th / crop.height,
             "box": [x0, y0, x1, y1], "src": [rgba.width, rgba.height], "ratio": round(th / size, 4)}
    return canvas, frame


def save_inputs(job_dir, original_bytes, original_img, rgba):
    """작업 폴더에 원본·마스크·배경 지운 사진·정사각형 입력을 각각 남겨요. 원본은 받은 파일 그대로도 함께 둬요."""
    d = Path(job_dir)
    for k in ("original", "mask", "rgba", "square", "frame"):
        (d / K.FILES[k]).parent.mkdir(parents=True, exist_ok=True)
    if original_bytes:
        (d / "input" / "original.bin").write_bytes(original_bytes)        # 올린 파일 그대로(형식 불문)
    original_img.save(d / K.FILES["original"])
    rgba.getchannel("A").save(d / K.FILES["mask"])
    rgba.save(d / K.FILES["rgba"])
    sq, frame = square_input(rgba)
    sq.save(d / K.FILES["square"])
    (d / K.FILES["frame"]).write_text(json.dumps(frame), encoding="utf-8")
    return sq, frame


# ── 자세: COCO-WholeBody 133점 → OpenPose(BODY_25 + 손 21×2 + 얼굴 70) ──────────────────────────
# COCO-WholeBody: 몸 0~16, 발 17~22(왼 엄지·왼 새끼·왼 뒤꿈치·오 엄지·오 새끼·오 뒤꿈치), 얼굴 23~90(68점), 왼손 91~111, 오른손 112~132
_B25 = {0: 0, 2: 6, 3: 8, 4: 10, 5: 5, 6: 7, 7: 9, 9: 12, 10: 14, 11: 16, 12: 11, 13: 13, 14: 15, 15: 2, 16: 1, 17: 4, 18: 3,
        19: 17, 20: 18, 21: 19, 22: 20, 23: 21, 24: 22}        # BODY_25 번호 → COCO-WholeBody 번호(목 1 · 골반 가운데 8 은 계산)


def wholebody_to_openpose(kps, scores=None):
    """kps: (133, 2 또는 3) 화소 좌표[, 점수], scores: (133,) — OpenPose JSON(dict) 으로.
    목 = 두 어깨 가운데, 골반 가운데 = 두 엉덩이 가운데, 눈동자(얼굴 68·69) = 눈 둘레 점의 가운데."""
    k = np.asarray(kps, np.float64)
    if k.shape[0] != 133:
        raise ValueError(f"관절점이 133개여야 해요(받은 수 {k.shape[0]})")
    if k.shape[1] == 2:
        sc = np.ones(133) if scores is None else np.asarray(scores, np.float64).reshape(133)
        k = np.concatenate([k, sc[:, None]], 1)

    def mid(a, b):
        return np.array([(k[a, 0] + k[b, 0]) / 2, (k[a, 1] + k[b, 1]) / 2, min(k[a, 2], k[b, 2])])

    body = np.zeros((25, 3))
    for o, c in _B25.items():
        body[o] = k[c]
    body[1], body[8] = mid(5, 6), mid(11, 12)
    face68 = k[23:91]
    pupil = lambda idx: np.array([face68[idx, 0].mean(), face68[idx, 1].mean(), face68[idx, 2].min()])
    face = np.concatenate([face68, pupil(slice(36, 42))[None], pupil(slice(42, 48))[None]], 0)       # 68: 오른쪽 눈동자, 69: 왼쪽
    flat = lambda a: [round(float(v), 4) for v in a.reshape(-1)]
    return {"version": 1.3, "people": [{"person_id": [-1], "pose_keypoints_2d": flat(body), "face_keypoints_2d": flat(face),
                                        "hand_left_keypoints_2d": flat(k[91:112]), "hand_right_keypoints_2d": flat(k[112:133]),
                                        "pose_keypoints_3d": [], "face_keypoints_3d": [], "hand_left_keypoints_3d": [], "hand_right_keypoints_3d": []}]}


def load_openpose(path):
    """OpenPose JSON → {body (25,3), face (70,3), lhand (21,3), rhand (21,3)} (사람이 없으면 None)."""
    try:
        p = json.loads(Path(path).read_text(encoding="utf-8"))["people"][0]
    except (OSError, ValueError, KeyError, IndexError):
        return None
    g = lambda key, n: np.array(p.get(key) or [0.0] * (n * 3), np.float64).reshape(-1, 3)[:n]
    return {"body": g("pose_keypoints_2d", 25), "face": g("face_keypoints_2d", 70), "lhand": g("hand_left_keypoints_2d", 21), "rhand": g("hand_right_keypoints_2d", 21)}
