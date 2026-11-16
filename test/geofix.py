"""얼굴 3D 형상 보정 시험용 도우미(시험 파일이 아니에요).

· 진짜 얼굴 랜드마크: MediaPipe FaceLandmarker(파이썬 꾸러미 mediapipe + face_landmarker.task) — ComfyUI 의 MediaPipe 노드가 그리는 것과 같은 부위 선을 그려요.
· 정답이 있는 가짜 3D: 실제 얼굴 사진으로
    진짜 머리  = 타원체 + 코·눈·입·턱 굴곡이 '사진 속 자리'에 있음(사진을 그대로 입힌 것이 정답)
    엔진 머리 = 같은 타원체인데 굴곡과 엔진이 칠한(흐린) 얼굴이 조금 다른 자리에 있음(눈이 가깝고 코가 아래·옆, 입이 위)
  → 사진을 엔진 머리에 붙이면 정면은 사진 같지만 굴곡과 그림이 어긋나요. 형상 보정 뒤 굴곡이 진짜 자리로 돌아오는지 잴 수 있어요.
필요: pip install mediapipe scipy scikit-image (+ libEGL), 인터넷(모델·남성 사진을 처음 한 번 받아요 — TMPDIR/lais_geofit 에 보관)."""
import io, os, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BASE = os.environ.get("LAS_BASE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import glbscene, photoproj

CACHE = Path(tempfile.gettempdir()) / "lais_geofit"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MALE_URL = "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/obama.jpg"     # 미국 정부 공식 초상(퍼블릭 도메인)
_DET = {}


def fetch(url, name):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / name
    if not f.is_file() or f.stat().st_size < 1000:
        r = subprocess.run(["curl", "-sS", "-L", "-m", "120", "-o", str(f), url], capture_output=True)
        if r.returncode or not f.is_file() or f.stat().st_size < 1000:
            f.unlink(missing_ok=True)
            return None
    return f


def detector():
    if "d" not in _DET:
        import mediapipe as mp
        m = fetch(MODEL_URL, "face_landmarker.task")
        if not m:
            raise RuntimeError("face_landmarker.task 를 받지 못했어요")
        opt = mp.tasks.vision.FaceLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(m)), num_faces=1, min_face_detection_confidence=0.3)
        _DET["d"], _DET["mp"] = mp.tasks.vision.FaceLandmarker.create_from_options(opt), mp
        C = mp.tasks.vision.FaceLandmarksConnections
        pair = lambda cs: [(c.start, c.end) for c in cs]
        _DET["conn"] = {"face_oval": pair(C.FACE_LANDMARKS_FACE_OVAL), "lips": pair(C.FACE_LANDMARKS_LIPS), "left_eye": pair(C.FACE_LANDMARKS_LEFT_EYE), "right_eye": pair(C.FACE_LANDMARKS_RIGHT_EYE),
                        "left_eyebrow": pair(C.FACE_LANDMARKS_LEFT_EYEBROW), "right_eyebrow": pair(C.FACE_LANDMARKS_RIGHT_EYEBROW),
                        "irises": pair(C.FACE_LANDMARKS_LEFT_IRIS) + pair(C.FACE_LANDMARKS_RIGHT_IRIS), "nose": pair(C.FACE_LANDMARKS_NOSE)}
    return _DET["d"]


def points(img):
    """그림 → 랜드마크 478개 (n, 2) 화소 좌표, 없으면 None"""
    d = detector(); mp = _DET["mp"]
    im = img.convert("RGB")
    r = d.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(np.asarray(im))))
    if not r.face_landmarks:
        return None
    return np.array([(p.x * im.width, p.y * im.height) for p in r.face_landmarks[0]])


def draw_lines(img, feats, thickness=2, xy="detect"):
    """ComfyUI 의 MediaPipeFaceMeshVisualize 를 이어 붙인 것과 같은 그림: 검은 바탕에 부위마다 주어진 색 선. feats = [(부위 이름, (r, g, b))]
    xy: 이미 찾은 랜드마크(없으면 여기서 찾아요)"""
    out = Image.new("RGB", img.size, (0, 0, 0))
    if isinstance(xy, str):
        xy = points(img)
    if xy is None:
        return out
    dr = ImageDraw.Draw(out)
    for name, rgb in feats:
        for a, b in _DET["conn"].get(name, []):
            dr.line([tuple(xy[a]), tuple(xy[b])], fill=tuple(rgb), width=thickness)
    return out


def line_images(img, sets, colors):
    """허브가 부르는 방식 그대로: 부위 묶음(sets)마다 그림 한 장 → [PIL]. colors = {부위: (r, g, b)}"""
    xy = points(img)
    return [draw_lines(img, [(n, colors[n]) for n in grp], xy=xy) for grp in sets]


def face_photo(kind):
    """실제 얼굴 사진을 얼굴 둘레로 잘라 1024×1024 로 → (PIL RGB, 랜드마크 478개) 또는 None(사진·얼굴 없음)"""
    if kind == "female":
        from skimage import data
        src = Image.fromarray(data.astronaut())           # NASA 우주비행사(퍼블릭 도메인)
    else:
        f = fetch(MALE_URL, "male.jpg")
        if not f:
            return None
        src = Image.open(f).convert("RGB")
    xy = points(src)
    if xy is None:
        return None
    fw = float(np.linalg.norm(xy[454] - xy[234]))          # 얼굴 너비(귀 앞 ~ 귀 앞)
    c = (xy[10] + xy[152]) / 2                             # 이마 위 ~ 턱 끝의 가운데
    side = 2.3 * fw
    im = src.transform((1024, 1024), Image.EXTENT, (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2), Image.BICUBIC)
    xy2 = points(im)
    return (im, xy2) if xy2 is not None else None


S = 1024
FRAME, CY = 0.40, 1.555                                    # 사진에 담기는 높이(m)와 가운데
K = S / FRAME


def px_of(X):
    return S / 2 + K * X[:, 0], S / 2 - K * (X[:, 1] - CY)


def build(kind, shift=1.0, res=(220, 160), ts=2048):
    """→ dict(photo RGBA, true GLB, engine GLB, box 얼굴 상자, …) 또는 None. shift: 엔진 머리의 어긋남 배율. res: 그물망 촘촘함, ts: 텍스처 크기."""
    from scipy.interpolate import RBFInterpolator
    got = face_photo(kind)
    if not got:
        return None
    img, lm = got
    fw_px = float(np.linalg.norm(lm[454] - lm[234]))
    m_per_px = 0.150 / fw_px                               # 얼굴 너비를 15cm 로
    cpx = (lm[10] + lm[152]) / 2
    hc = np.array([0.0, 1.60, 0.0])                        # 머리 가운데

    def head_xy(p):                                        # 사진(1024) 화소 → 머리 좌표(m)
        return np.stack([(p[..., 0] - cpx[0]) * m_per_px, hc[1] - (p[..., 1] - cpx[1]) * m_per_px], -1)

    A = np.array([0.62 * 0.150, 0.82 * 0.150, 0.095])      # 타원체 반지름
    feats = [(head_xy((lm[1] + lm[6]) / 2 * 0.4 + lm[1] * 0.6), (0.012, 0.022), 0.024),      # 코
             (head_xy(lm[468]), (0.016, 0.009), -0.006), (head_xy(lm[473]), (0.016, 0.009), -0.006),      # 눈
             (head_xy((lm[13] + lm[14]) / 2), (0.022, 0.008), 0.004),                                  # 입
             (head_xy(lm[152] * 0.8 + lm[14] * 0.2), (0.016, 0.013), 0.006)]                           # 턱

    def relief(xy):
        z = np.zeros(len(xy))
        for c, (sx, sy), h in feats:
            z += h * np.exp(-0.5 * (((xy[:, 0] - c[0]) / sx) ** 2 + ((xy[:, 1] - c[1]) / sy) ** 2))
        return z

    # 엔진 머리의 어긋남(머리 좌표, m): 눈은 안쪽·위로, 코는 아래·옆으로, 입은 위로·좁게, 턱은 위로 — 윤곽에서는 0
    e1, e2, nose, mo, chin = head_xy(lm[468]), head_xy(lm[473]), head_xy(lm[1]), head_xy((lm[13] + lm[14]) / 2), head_xy(lm[152])
    mid = (e1 + e2) / 2
    ctrl = [(e1, 0.005 * np.sign(mid[0] - e1[0]), 0.002), (e2, 0.005 * np.sign(mid[0] - e2[0]), 0.002), (nose, 0.003, -0.006), (head_xy(lm[6]), 0.001, -0.002),
            (mo, 0.0, 0.004), (head_xy(lm[61]), 0.003 * np.sign(mo[0] - head_xy(lm[61])[0]), 0.004), (head_xy(lm[291]), 0.003 * np.sign(mo[0] - head_xy(lm[291])[0]), 0.004), (chin, 0.0, 0.003)]
    ring = [np.array([hc[0] + 1.02 * A[0] * np.cos(t), hc[1] + 1.02 * A[1] * np.sin(t)]) for t in np.linspace(0, 2 * np.pi, 24, endpoint=False)]
    cp = np.array([c for c, _, _ in ctrl] + ring)
    cd = np.array([[dx, dy] for _, dx, dy in ctrl] + [[0, 0]] * len(ring)) * shift
    rbf = RBFInterpolator(cp, cd, kernel="thin_plate_spline", smoothing=1e-9)

    def delta(xy):
        d = rbf(xy)
        inside = ((xy[:, 0] - hc[0]) / A[0]) ** 2 + ((xy[:, 1] - hc[1]) / A[1]) ** 2 < 1.0
        return d * inside[:, None]

    NU, NV = res
    th, ph = np.meshgrid(np.linspace(-np.pi, np.pi, NU + 1), np.linspace(0.02, np.pi - 0.02, NV + 1))
    D = np.stack([np.sin(ph) * np.sin(th), np.cos(ph), np.sin(ph) * np.cos(th)], -1).reshape(-1, 3)
    Bd = np.array([0.15, 0.075, 0.075])
    i = np.arange(NU * NV).reshape(NV, NU); r, c = np.divmod(i, NU); a = r * (NU + 1) + c
    F1 = np.concatenate([np.stack([a, a + NU + 1, a + 1], -1).reshape(-1, 3), np.stack([a + 1, a + NU + 1, a + NU + 2], -1).reshape(-1, 3)])
    F = np.concatenate([F1, F1 + len(D)])
    uv0 = np.stack([(th / (2 * np.pi) + 0.5).ravel() * 0.96 + 0.02, (ph / np.pi).ravel() * 0.96 + 0.02], 1)
    UV = np.concatenate([uv0 * [1, 0.5], uv0 * [1, 0.5] + [0, 0.5]])
    sharp = np.asarray(img).astype(np.float32)
    soft = np.asarray(img.filter(ImageFilter.GaussianBlur(5))).astype(np.float32)

    def img_px(xy):                                        # 머리 좌표(m) → 원본 얼굴 그림(1024) 화소
        return cpx[0] + (xy[:, 0] - hc[0]) / m_per_px, cpx[1] - (xy[:, 1] - hc[1]) / m_per_px

    def make(engine):
        H = D * A + hc
        front = np.clip(D[:, 2] / 0.35, 0, 1); front = front * front * (3 - 2 * front)      # 앞쪽에만(옆으로 갈수록 0)
        xy = H[:, :2]
        src_xy = xy - delta(xy) if engine else xy          # 엔진: 굴곡·그림이 어긋난 자리에
        H = H.copy(); H[:, 2] += relief(src_xy) * front
        P = np.concatenate([H, D * Bd + [0, 1.43, 0]])
        fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
        N = np.zeros_like(P)
        for k in range(3):
            np.add.at(N, F[:, k], fn)
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
        if (N[:len(H)] * (H - hc)).sum() < 0:
            N = -N
        TS = ts
        tp, tf, b0, b1 = photoproj.raster(UV * TS, F, TS, TS)
        bc = np.stack([b0, b1, 1 - b0 - b1], 1)
        X = (P[F[tf]] * bc[..., None]).sum(1)
        Xn = (N[F[tf]] * bc[..., None]).sum(1)
        ishead = F[tf, 0] < len(H)
        sxy = X[:, :2].copy()
        if engine:
            sxy[ishead] -= delta(sxy[ishead])
        ix, iy = img_px(sxy)
        col = photoproj._sample(soft if engine else sharp, ix, iy)
        if engine:                                         # 엔진처럼: 바래고, 옆으로 갈수록 어둡게
            col = (0.75 * col + 0.25 * col.mean(1, keepdims=True)) * (0.6 + 0.4 * np.clip(Xn[:, 2:3], 0, 1))
        col[~ishead] = (70, 90, 150) if not engine else (60, 78, 128)
        T = np.full((TS * TS, 3), 110.0, np.float32); T[tp] = col
        T, _ = photoproj._spread(T.reshape(TS, TS, 3), np.bincount(tp, minlength=TS * TS).reshape(TS, TS) > 0, 3)
        return P, N, Image.fromarray(np.clip(T, 0, 255).astype(np.uint8))

    def glb_of(P, N, tex):
        bb = io.BytesIO(); tex.save(bb, "PNG")
        parts = [P.astype(np.float32).tobytes(), UV.astype(np.float32).tobytes(), F.astype(np.uint32).tobytes(), N.astype(np.float32).tobytes(), bb.getvalue()]
        bvs, blob = [], b""
        for x in parts:
            blob += b"\0" * (-len(blob) % 4); bvs.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(x)}); blob += x
        g = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(blob)}], "bufferViews": bvs,
             "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(P), "type": "VEC3", "min": P.astype(np.float32).min(0).tolist(), "max": P.astype(np.float32).max(0).tolist()},
                           {"bufferView": 1, "componentType": 5126, "count": len(UV), "type": "VEC2"},
                           {"bufferView": 2, "componentType": 5125, "count": F.size, "type": "SCALAR"},
                           {"bufferView": 3, "componentType": 5126, "count": len(N), "type": "VEC3"}],
             "images": [{"bufferView": 4, "mimeType": "image/png"}], "textures": [{"source": 0}],
             "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
             "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1, "NORMAL": 3}, "indices": 2, "material": 0}]}],
             "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
        return glbscene.write(g, blob)

    Pt, Nt, Tt = make(False)
    Pe, Ne, Te = make(True)
    true_glb, eng_glb = glb_of(Pt, Nt, Tt), glb_of(Pe, Ne, Te)
    # 사진 = 진짜 머리를 앞에서 본 것(= 원본 얼굴 사진을 3D 실루엣으로 오린 것)
    px, py = px_of(Pt)
    pix, fid, b0, b1 = photoproj.raster(np.stack([px, py], 1), F, S, S, -Pt[:, 2])
    X = Pt[F[fid, 0]] * b0[:, None] + Pt[F[fid, 1]] * b1[:, None] + Pt[F[fid, 2]] * (1 - b0 - b1)[:, None]
    ishead = F[fid, 0] < len(D)
    ix, iy = img_px(X[:, :2])
    col = photoproj._sample(sharp, ix, iy); col[~ishead] = (70, 90, 150)
    ph_ = np.zeros((S * S, 4), np.uint8); ph_[pix, :3] = np.clip(col, 0, 255); ph_[pix, 3] = 255
    photo = Image.fromarray(ph_.reshape(S, S, 4), "RGBA")
    # 얼굴 상자(이마 ~ 턱, MediaPipe 얼굴 윤곽 범위) — 사진 좌표
    ov = np.array([head_xy(lm[i_]) for i_ in sorted({a_ for a_, _ in _DET["conn"]["face_oval"]})])
    ox, oy = px_of(np.c_[ov, np.zeros(len(ov))])
    box = (float(ox.min()), float(oy.min()), float(ox.max()), float(oy.max()))
    return {"kind": kind, "photo": photo, "true": true_glb, "engine": eng_glb, "box": box, "hc": hc, "A": A, "F": F, "nhead": len(D),
            "feats_true": [c for c, _, _ in feats], "delta": delta, "relief": relief, "m_per_px": m_per_px}


def view(glb, deg, R=640, span=0.30, cy=1.60, depth=False):
    """머리 가까이에서 yaw 도 돌려 본 그림(텍스처 색 그대로) → (그림 배열 R×R×3, 깊이 배열(가까울수록 큼, 없으면 -inf))"""
    an = np.radians(deg); Rm = np.array([[np.cos(an), 0, np.sin(an)], [0, 1, 0], [-np.sin(an), 0, np.cos(an)]])
    out = np.zeros((R * R, 3), np.float32); zb = np.full(R * R, -np.inf); k = R / span
    for P, Fp, UVp, _, T, fac in photoproj._scene(glb, 4096):
        Pp = (P - [0, cy, 0]) @ Rm.T
        pix, fid, c0, c1 = photoproj.raster(np.stack([R / 2 + k * Pp[:, 0], R / 2 - k * Pp[:, 1]], 1), Fp, R, R, -Pp[:, 2])
        cc = np.stack([c0, c1, 1 - c0 - c1], 1); z = (Pp[Fp[fid], 2] * cc).sum(1); win = z > zb[pix]
        uv = (UVp[Fp[fid]] * cc[..., None]).sum(1)[win]
        out[pix[win]] = photoproj._sample(T, (uv[:, 0] % 1.0) * T.shape[1], np.clip(uv[:, 1], 0, 1) * T.shape[0]); zb[pix[win]] = z[win]
    return out.reshape(R, R, 3), zb.reshape(R, R)


def close():
    """랜드마크 엔진을 닫아요(안 닫으면 프로그램이 끝날 때 오류 글이 찍혀요)."""
    d = _DET.pop("d", None)
    if d is not None:
        try:
            d.close()
        except Exception:  # noqa: BLE001
            pass
