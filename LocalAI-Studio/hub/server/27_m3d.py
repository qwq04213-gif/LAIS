# 로컬 AI 스튜디오 허브 — 3D 만들기 (사진 분석 → 여러 방향 그림 → TRELLIS.2/Pixal3D 로 텍스처 입힌 3D → 게임용 다듬기(ComfyUI) → Blender 마무리)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

import blender3d
import glbscene
import photoproj

M3D_DIR = ROOT / "m3d_work"
M3D_SUB = "3D"
M3D_SIDES = ("left", "back", "right")
M3D_SIDE_KO = {"front": "앞", "left": "왼쪽", "back": "뒤", "right": "오른쪽"}
# Pixal3D 멀티뷰의 방향 약속: 카메라가 물체 둘레를 돌아요(앞 0° · 왼쪽 90° · 뒤 180° · 오른쪽 270°).
# '왼쪽' = 물체 자신의 왼쪽 옆모습 → 물체의 앞(얼굴)이 그림의 왼쪽 끝을 향해요. '오른쪽' 은 그 반대.
# (4.0 의 문장은 '오른쪽으로 돌아 왼쪽을 보여 줘' 처럼 서로 어긋나서 왼쪽·오른쪽이 뒤섞여 앞뒤가 섞인 3D 가 나왔어요)
M3D_SIDE_EN = {"left": "the exact left side profile of the subject (the camera orbits 90 degrees around it). Seen strictly from its own left side: "
                       "the subject's front and face point toward the LEFT edge of the image, its back toward the right edge, only its left arm and left side are visible",
               "back": "the exact back of the subject (the camera orbits 180 degrees around it). Seen strictly from behind: the face and front are NOT visible, "
                       "the back of the head and the back of the body face the camera, the subject's left side is on the left of the image",
               "right": "the exact right side profile of the subject (the camera orbits 270 degrees around it). Seen strictly from its own right side: "
                        "the subject's front and face point toward the RIGHT edge of the image, its back toward the left edge, only its right arm and right side are visible"}
M3D_RES = (512, 1024, 1536)
M3D_REMESH = 768                                     # 다시 짜기 해상도(공식 예시와 같게) — 세밀함 1536 이면 1024 로 올려 얼굴 굴곡을 살려요
M3D_VFIT = 0.6                                       # 실루엣 맞춤 기준(아래면 '의심' — 기본으로 체크를 풀어요)
M3D_FACES = (5000, 20000, 50000, 200000, 700000)        # 70만 = 공식 예시 값
M3D_TEX = (1024, 2048, 4096)
M3D_KIND = {"character": {"faces": 200000, "height": 1.7}, "object": {"faces": 50000, "height": 0}, "big": {"faces": 200000, "height": 0}}


def trellis_files(multiview=False):
    """설치된 TRELLIS.2(또는 Pixal3D 멀티뷰) 파일. 빠진 게 있으면 값이 None."""
    dm, cv, va = files("diffusion_models"), files("clip_vision"), files("vae")
    low = str.lower
    if multiview:
        model = min((n for n in dm if "pixal3d_multiview" in low(n)), key=lambda n: ("int8" not in low(n), n), default=None)
        dino = next((n for n in cv if "dino_v3_l_naf" in low(n)), None)
    else:
        model = min((n for n in dm if re.search(r"trellis_?2", low(n))), key=lambda n: ("int8" not in low(n), n), default=None)
        dino = min((n for n in cv if "dino_v3_vit_l" in low(n) or "dino_v3_l_naf" in low(n)), key=lambda n: ("vit_l" not in low(n), n), default=None)
    return {"model": model, "dino": dino, "svae": next((n for n in va if "trellis_2_shape_vae" in low(n)), None),
            "tvae": next((n for n in va if "trellis_2_texture_vae" in low(n)), None)}


def pixal_files():
    """Pixal3D(사진 한 장) 파일 — moge(화각 어림)는 없으면 기본 화각으로 만들어요."""
    dm, cv, va, ge = files("diffusion_models"), files("clip_vision"), files("vae"), files("geometry_estimation")
    low = str.lower
    return {"model": min((n for n in dm if "pixal3d" in low(n) and "multiview" not in low(n)), key=lambda n: ("int8" not in low(n), n), default=None),
            "dino": next((n for n in cv if "dino_v3_l_naf" in low(n)), None),
            "svae": next((n for n in va if "trellis_2_shape_vae" in low(n)), None), "tvae": next((n for n in va if "trellis_2_texture_vae" in low(n)), None),
            "moge": next((n for n in ge if "moge" in low(n)), None)}


def pixal_ready():
    f = pixal_files()
    return all(v for k, v in f.items() if k != "moge")


def m3d_ready():
    return {"trellis": all(trellis_files().values()), "multiview": all(trellis_files(True).values()), "pixal": pixal_ready()}


def wf_fit(g, notes=None):
    """엔진(ComfyUI)이 알려 준 노드 설명에 맞춰 그래프를 다듬어요: 모르는 칸은 빼고, 빠진 필수 칸은 기본값으로 채워요.
    ComfyUI 판마다 칸 이름이 조금씩 달라도 그래프가 깨지지 않게 하려는 안전장치예요.
    선택 칸(DynamicCombo)에 그 판에 없는 값을 넣으면 ComfyUI 가 칸을 통째로 빼 버려서(→ 'missing ... sign_mode')
    노드의 '_alt'(대신 쓸 값과 하위 칸) → 그 판의 기본값 순서로 바꿔요. 바꾼 내용은 notes 에 적어요."""
    info = caps().get("info") or {}
    for n in g.values():
        alt = n.pop("_alt", None) or {}
        spec = (info.get(n["class_type"]) or {}).get("input")
        if not spec:
            continue
        req, opt = spec.get("required") or {}, spec.get("optional") or {}
        if not (req or opt):                          # 설명이 비어 있으면 손대지 않아요
            continue
        for k in list(n["inputs"]):
            if k not in req and k not in opt and "." not in k:
                del n["inputs"][k]
        for k, v in req.items():
            if k not in n["inputs"] and isinstance(v, (list, tuple)) and len(v) > 1 and isinstance(v[1], dict) and "default" in v[1]:
                n["inputs"][k] = v[1]["default"]
        for k, v in {**opt, **req}.items():                 # 고른 값에 따라 칸이 생기는 선택 칸(DynamicCombo): 하위 칸은 '부모.이름' 으로 채워요
            try:
                if not (isinstance(v, (list, tuple)) and len(v) > 1 and isinstance(v[1], dict) and isinstance(v[1].get("options"), list)):
                    continue
                opts = [o for o in v[1]["options"] if isinstance(o, dict) and "key" in o]
                if not opts:
                    continue
                cur = n["inputs"].get(k, v[1].get("default", opts[0]["key"]))
                if isinstance(cur, list):                   # 다른 노드에서 이어진 값이면 알 수 없어요
                    continue
                keys = [o["key"] for o in opts]
                if cur not in keys:                         # 이 ComfyUI 판에 없는 선택지
                    pick = next(((a, kids) for a, kids in alt.get(k, []) if a in keys), None)
                    new = pick[0] if pick else (v[1].get("default") if v[1].get("default") in keys else keys[0])
                    for x in [x for x in n["inputs"] if x.startswith(k + ".")]:
                        del n["inputs"][x]
                    n["inputs"].update((pick or (None, {}))[1])
                    if notes is not None:
                        notes.append(f"{n['class_type']}.{k}: {cur} → {new}")
                    cur = new
                n["inputs"][k] = cur
                sel = next((o for o in opts if o["key"] == cur), None)
                kids = (sel or {}).get("inputs") or {}
                names = set(kids.get("optional") or {}) | set(kids.get("required") or {})
                for x in [x for x in n["inputs"] if x.startswith(k + ".") and x.split(".", 1)[1] not in names]:
                    del n["inputs"][x]                      # 고른 값에 없는 하위 칸은 빼요
                kids = (sel or {}).get("inputs") or {}
                for c, cs in {**(kids.get("optional") or {}), **(kids.get("required") or {})}.items():
                    if f"{k}.{c}" not in n["inputs"] and isinstance(cs, (list, tuple)) and len(cs) > 1 and isinstance(cs[1], dict) and "default" in cs[1]:
                        n["inputs"][f"{k}.{c}"] = cs[1]["default"]
            except Exception:  # noqa: BLE001
                continue
    return g


def m3d_dir(sid):
    if not re.fullmatch(r"[0-9a-f]{12}", sid or ""):
        raise ValueError("3D 작업을 찾을 수 없어요.")
    d = M3D_DIR / sid
    if not (d / "meta.json").is_file():
        raise ValueError("3D 작업을 찾을 수 없어요.")
    return d


def m3d_meta(sid):
    return json.loads((m3d_dir(sid) / "meta.json").read_text(encoding="utf-8"))


def m3d_save_meta(sid, m):
    (M3D_DIR / sid / "meta.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")


def m3d_load(data_url):
    """사진 읽기 — 이미 배경을 지운 PNG 면 투명한 부분을 그대로 살려요(load_img 는 RGB 로 바꿔 버려요)."""
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(base64.b64decode(str(data_url).split(",", 1)[-1]))))
    alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    return im.convert("RGBA" if alpha else "RGB")


def m3d_cut(img, J=None):
    """배경 지우기(이미 투명 배경이면 그대로). 배경 모델이 없으면 받기 시작하고 안내해요."""
    if img.mode == "RGBA":
        a = np.asarray(img.getchannel("A"))
        if (a < 16).mean() > 0.05:            # 이미 배경이 비어 있어요
            return img
    key = rmbg_default()                              # BiRefNet 이 있으면 그걸로(경계가 또렷해요)
    if not rmbg_ready(key):
        r = rmbg_install({"key": key})
        if r.get("error") and "이미" not in r["error"]:
            raise RuntimeError(r["error"])
        raise RuntimeError(f"3D 로 만들려면 먼저 배경을 지워야 해요. 배경 지우기 모델(약 {bgremove.MODELS[key]['mb']}MB)을 받기 시작했어요. "
                           "설치와 모델의 진행 목록에서 끝난 걸 확인한 뒤 다시 눌러 주세요.")
    if J is not None:
        J["msg"] = "배경 지우는 중"
    return rmbg_cut(key, img.convert("RGB"), None, J)


def m3d_analyze(rgba):
    """배경을 지운 사진 상태 점검 → [{level, text}] (ok·warn·bad)."""
    a = np.asarray(rgba.getchannel("A"), dtype=np.float32) / 255
    H, W = a.shape
    m = a > 0.5
    out = []
    if m.sum() < 64:
        return [{"level": "bad", "text": "물체를 찾지 못했어요. 배경과 물체가 뚜렷한 사진을 써 주세요."}], {}
    ys, xs = np.nonzero(m)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    area = (x1 - x0 + 1) * (y1 - y0 + 1) / (W * H)
    border = np.concatenate([m[0], m[-1], m[:, 0], m[:, -1]]).mean()
    side = min(x1 - x0 + 1, y1 - y0 + 1)
    g = np.asarray(rgba.convert("L"), dtype=np.float32)[y0:y1 + 1, x0:x1 + 1]
    lap = (g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4 * g[1:-1, 1:-1]) if min(g.shape) > 3 else np.zeros((1, 1))
    sharp = float(lap.var()) * (512 / max(side, 1)) ** 2 if side else 0
    if border > 0.02:
        out.append({"level": "bad", "text": "물체가 사진 가장자리에서 잘린 것 같아요. 잘린 부분은 AI 가 지어내요 — 물체 전체가 나온 사진이 좋아요."})
    if area < 0.12:
        out.append({"level": "warn", "text": "물체가 사진에서 작게 나왔어요. 크게 나온 사진일수록 세밀해요."})
    long = max(x1 - x0 + 1, y1 - y0 + 1)
    if long < M3D_SMALL:
        out.append({"level": "warn", "text": f"물체 부분이 {long}px 로 작아요. 권장은 {M3D_GOOD}px 이상이에요 — [업스케일로 키우기]를 누르거나, 만들 때 자동으로 키워요."})
    if sharp < 30:
        out.append({"level": "warn", "text": "사진이 흐려 보여요. 무늬·글자 같은 텍스처가 뭉개질 수 있어요."})
    pieces = 0
    try:                                                  # 큰 덩어리가 여러 개면 여러 물체일 수 있어요(작은 조각은 무시)
        small = np.asarray(rgba.getchannel("A").resize((128, max(1, round(128 * H / W))), RS.NEAREST)) > 127
        seen = np.zeros_like(small)
        for y, x in zip(*np.nonzero(small)):
            if seen[y, x]:
                continue
            stack, n = [(y, x)], 0
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                n += 1
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < small.shape[0] and 0 <= nx < small.shape[1] and small[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if n > small.sum() * 0.15:
                pieces += 1
    except Exception:  # noqa: BLE001
        pieces = 1
    if pieces > 1:
        out.append({"level": "warn", "text": f"물체가 {pieces}개로 떨어져 보여요. 한 번에 한 물체만 만들 때 가장 잘 돼요."})
    if not out:
        out.append({"level": "ok", "text": "좋아요 — 물체가 잘 보이고 크기도 충분해요."})
    return out, {"w": W, "h": H, "box": [int(x0), int(y0), int(x1), int(y1)], "area": round(float(area), 3), "sharp": round(sharp, 1), "pieces": pieces,
                 "long": int(long), "good": M3D_GOOD}


M3D_LEG_GAP = 0.3       # 사람 사진: 다리 높이의 줄 중 두 다리가 떨어져 보이는 줄이 이보다 적으면 '다리가 붙어 보여요'
M3D_DARK = (60, 25)     # 옷·배경 가장자리 밝기가 둘 다 이보다 어둡고(0~255) 차이가 이보다 작으면 '어두운 옷·어두운 배경'


def m3d_legs_gap(mask):
    """사람 실루엣의 다리 높이(키의 72~92%) 줄 중 두 덩어리 이상으로 떨어져 보이는 줄의 비율(0~1). 다리 사이 틈이 보이면 커요."""
    ys, xs = np.nonzero(mask)
    if len(ys) < 50:
        return None
    y0, y1 = ys.min(), ys.max() + 1
    h, w = y1 - y0, xs.max() - xs.min() + 1
    rows = range(y0 + int(0.72 * h), y0 + int(0.92 * h))
    two = 0
    for y in rows:
        r = photoproj._runs(mask[y])
        if sum(1 for a_, b_ in r if b_ - a_ >= max(2, 0.03 * w)) >= 2:
            two += 1
    return round(two / max(1, len(rows)), 3)


def m3d_body_check(orig, cut, kind):
    """사진 점검 덧붙이기: 사람이면 다리 틈(붙어 있으면 엔진이 다리를 하나로 만들 수 있어요), 어두운 옷 + 어두운 배경(배경 지우기가 팔다리를 지울 수 있어요).
    → (점검 목록, 숫자)"""
    out, st = [], {}
    a = np.asarray(cut.getchannel("A")) > 127 if cut.mode == "RGBA" else None
    if a is None or a.sum() < 64:
        return out, st
    if kind == "character":
        g = m3d_legs_gap(a)
        st["legs_gap"] = g
        if g is not None and g < M3D_LEG_GAP:
            out.append({"level": "warn", "text": f"두 다리가 붙어 보여요(다리 사이 틈이 보이는 높이 {g:.0%}). 3D 엔진이 다리를 하나로 만들거나 한쪽을 빠뜨릴 수 있어요 — "
                                                 "다리 사이가 보이는 사진이 좋아요. 만든 뒤 '팔다리 검사' 결과를 확인해 주세요."})
    try:
        o = np.asarray(orig.convert("L").resize(cut.size), dtype=np.float32)
        am = Image.fromarray((a * 255).astype(np.uint8))
        r = max(2, round(max(cut.size) * 0.006))
        inner = (np.asarray(am.filter(ImageFilter.MinFilter(r * 2 + 1))) > 127)
        outer = (np.asarray(am.filter(ImageFilter.MaxFilter(r * 4 + 1))) > 127)
        rin, rout = a & ~inner, outer & ~a
        if rin.sum() > 50 and rout.sum() > 50:
            li, lo = float(o[rin].mean()), float(o[rout].mean())
            st["edge_lum"] = [round(li), round(lo)]
            if li < M3D_DARK[0] and lo < M3D_DARK[0] and abs(li - lo) < M3D_DARK[1]:
                out.append({"level": "warn", "text": "옷과 배경이 둘 다 어두워요. 배경 지우기가 팔·다리 일부를 배경으로 지웠을 수 있어요 — "
                                                     "3D 작업 폴더의 mask_front.png 로 확인하고, 밝거나 단순한 배경 사진이 좋아요."})
    except Exception:  # noqa: BLE001 — 점검은 덤
        pass
    return out, st


def _sil(im, mirror=False, size=(48, 96)):
    """실루엣(알파) → 물체 상자만 잘라 같은 크기로. 비교용."""
    a = im.getchannel("A") if im.mode == "RGBA" else im.convert("L")
    box = a.point(lambda x: 255 if x > 127 else 0).getbbox()
    if not box:
        return None, 0.0
    a = a.crop(box)
    if mirror:
        a = ImageOps.mirror(a)
    return np.asarray(a.resize(size, RS.BILINEAR), dtype=np.float32) / 255 > 0.5, (box[3] - box[1]) / max(1, box[2] - box[0])


def _iou(a, b):
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0


M3D_VCOLOR = 0.45       # 방향 그림과 앞 사진의 물체 색 분포가 이만큼은 겹쳐야 같은 인물·옷으로 봐요


def _vhist(im):
    """물체 부분 색 분포(6단계 × 3색 = 216칸, 합 1)"""
    a = np.asarray(im.getchannel("A")) > 127
    c = np.asarray(im.convert("RGB"))[a]
    if len(c) < 50:
        return None
    q = (c // 43).astype(np.int64)
    h = np.bincount(q[:, 0] * 36 + q[:, 1] * 6 + q[:, 2], minlength=216).astype(np.float64)
    return h / h.sum()


def _legs_n(im):
    """사람 실루엣 다리 높이(키의 80~92%)에서 떨어진 덩어리 수(가운데값)"""
    a = np.asarray(im.getchannel("A")) > 127
    ys, xs = np.nonzero(a)
    if len(ys) < 50:
        return None
    y0, h, w = ys.min(), ys.max() + 1 - ys.min(), xs.max() + 1 - xs.min()
    ns = [sum(1 for a_, b_ in photoproj._runs(a[y]) if b_ - a_ >= max(2, 0.03 * w)) for y in range(y0 + int(0.80 * h), y0 + int(0.92 * h))]
    return int(np.median(ns)) if ns else None


def m3d_vcheck(d):
    """AI 방향 그림이 앞 사진과 맞는지 어림해요 → {방향: {"ok": bool, "score": 0~1, "text"}}.
    앞·뒤 실루엣은 원래 다를 수 있어서 좌우를 뒤집어 비교하지 않아요. 대신
    ① 같은 인물·옷(물체 색 분포가 앞 사진과 겹치는 정도) ② 그림 가장자리에서 잘렸는지 ③ 뒤: 몸 비율(너비÷키)이 앞과 비슷한지,
    사람이면 다리 수가 같은지 ④ 왼쪽·오른쪽: 서로 거울처럼 맞는지(옆모습끼리는 좌우가 뒤집힌 모양이 맞아요)."""
    out = {}
    try:
        ims = {s: Image.open(d / f"view_{s}.png").convert("RGBA") for s in ("front",) + M3D_SIDES if (d / f"view_{s}.png").is_file()}
    except Exception:  # noqa: BLE001
        return out
    if "front" not in ims:
        return out
    try:
        person = (m3d_meta(d.name) or {}).get("kind") == "character"
    except Exception:  # noqa: BLE001
        person = False
    hf = _vhist(ims["front"])
    fb = ims["front"].getchannel("A").point(lambda x: 255 if x > 127 else 0).getbbox()
    fr = (fb[2] - fb[0]) / max(1, fb[3] - fb[1]) if fb else None
    pair = None
    if "left" in ims and "right" in ims:
        lft, _ = _sil(ims["left"], True)
        rgt, _ = _sil(ims["right"])
        pair = _iou(lft, rgt) if lft is not None and rgt is not None else 0.0
    for s_ in M3D_SIDES:
        if s_ not in ims:
            continue
        im, why = ims[s_], []
        h = _vhist(im)
        col = float(np.minimum(h, hf).sum()) if h is not None and hf is not None else 0.0
        if col < M3D_VCOLOR:
            why.append(f"색이 앞 사진과 달라요(같은 인물·옷으로 보기 어려움, {col:.0%})")
        a = np.asarray(im.getchannel("A")) > 127
        if a.any() and np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]).mean() > 0.02:
            why.append("그림 가장자리에서 잘렸어요")
        score = col
        if s_ == "back":
            bb = im.getchannel("A").point(lambda x: 255 if x > 127 else 0).getbbox()
            br = (bb[2] - bb[0]) / max(1, bb[3] - bb[1]) if bb else None
            if fr and br and not (0.7 < br / fr < 1.43):
                why.append("몸 비율(너비÷키)이 앞모습과 많이 달라요")
                score = min(score, 0.4)
            if person:
                nf, nb = _legs_n(ims["front"]), _legs_n(im)
                if nf and nb and nf != nb:
                    why.append(f"다리 수가 앞모습과 달라요(앞 {nf}, 뒤 {nb})")
                    score = min(score, 0.4)
        elif pair is not None and pair < M3D_VFIT:
            why.append("왼쪽·오른쪽 모습이 서로 거울처럼 맞지 않아요(방향이 뒤바뀌었거나 자세가 달라요)")
            score = min(score, pair)
        out[s_] = {"score": round(score, 2), "ok": not why,
                   "text": "앞 사진과 같은 인물·옷이고 비율도 맞아요." if not why else " · ".join(why) + ". 다시 그리거나 체크를 풀어 주세요."}
    return out


def m3d_frame(ims, size=1024, pad=1.1):
    """멀티뷰 사진들을 같은 배율로 맞춰요: 모든 방향에서 키(세로)가 같다는 점을 이용해, 가장 넓은 방향이
    틀의 1/1.1 을 채우게 하고 나머지도 같은 배율로 가운데에 놓아요(검은 배경, 정사각형).
    방향마다 따로 꽉 채우면(앞은 좁고 옆은 긴 자동차처럼) 크기가 서로 달라져 모양이 일그러져요."""
    boxes = {}
    for k, im in ims.items():
        bb = im.getchannel("A").point(lambda x: 255 if x > 127 else 0).getbbox() or (0, 0, im.width, im.height)
        boxes[k] = bb
    ext = max(max(1.0, (b[2] - b[0]) / max(1, b[3] - b[1])) for b in boxes.values())   # 키를 1 로 둔 가장 넓은 폭
    hpx = size / pad / ext                                                             # 모든 방향의 키(px)
    out = {}
    for k, im in ims.items():
        x0, y0, x1, y1 = boxes[k]
        sc = hpx / max(1, y1 - y0)
        crop = im.crop((x0, y0, x1, y1))
        crop = crop.resize((max(1, round(crop.width * sc)), max(1, round(crop.height * sc))), RS.LANCZOS)
        rgb = Image.new("RGB", crop.size, (0, 0, 0))
        rgb.paste(crop.convert("RGB"), mask=crop.getchannel("A"))
        can = Image.new("RGB", (size, size), (0, 0, 0))
        can.paste(rgb, ((size - crop.width) // 2, (size - crop.height) // 2))
        out[k] = can
    return out


M3D_SCENE_MAX = 12
M3D_FILL = ("This picture shows one object cut out of a photo. Parts of it may be hidden behind other things or cut off at the edge. "
            "Redraw the complete, whole object alone with every hidden or missing part filled in naturally. Keep exactly the same design, shape, "
            "proportions, colors, materials, details and viewing angle. Whole object in frame, plain pure white background, soft even lighting, no shadow, nothing else. "
            "Glossy surfaces show only their own true color, without reflections or color tints from the original floor, lights or surroundings.")


def m3d_scene_obj(p):
    """장면 전체: 원본 사진에서 고른 물체(마스크) 넣기 · 빼기 · 모두 비우기."""
    sid = p.get("id")
    d = m3d_dir(sid)
    m = m3d_meta(sid)
    objs = m.get("scene") or []
    if p.get("clear") or p.get("remove") is not None:
        drop = [o for o in objs if p.get("clear") or str(o["n"]) == str(p.get("remove"))]
        for o in drop:
            for nm in (f"scene_obj_{o['n']}.png", f"scene_mask_{o['n']}.png"):
                (d / nm).unlink(missing_ok=True)
        m["scene"] = [o for o in objs if o not in drop]
        m3d_save_meta(sid, m)
        return m3d_view(sid)
    if len(objs) >= M3D_SCENE_MAX:
        return {"error": f"물체는 {M3D_SCENE_MAX}개까지 넣을 수 있어요."}
    if not (d / "orig.png").is_file():
        return {"error": "원본 사진이 없어요. 사진을 다시 골라 주세요."}
    orig = Image.open(d / "orig.png").convert("RGB")
    try:
        mk = load_img(p["mask"]).convert("L").resize(orig.size, RS.BILINEAR)
    except Exception:  # noqa: BLE001
        return {"error": "고른 부분을 읽을 수 없어요."}
    a = np.asarray(mk) > 127
    if a.sum() < 64 or a.mean() > 0.9:
        return {"error": "물체를 찾지 못했어요. 물체 위를 눌러 다시 골라 주세요."}
    ys, xs = np.nonzero(a)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    W, H = orig.size
    pad = round(0.04 * max(x1 - x0, y1 - y0))
    rgba = orig.convert("RGBA")
    alpha = Image.fromarray((a * 255).astype("uint8"), "L")
    rgba.putalpha(alpha)
    n = max([o["n"] for o in objs], default=0) + 1
    rgba.crop((max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad + 1), min(H, y1 + pad + 1))).save(d / f"scene_obj_{n}.png")
    alpha.save(d / f"scene_mask_{n}.png")
    edge = x0 <= 1 or y0 <= 1 or x1 >= W - 2 or y1 >= H - 2
    objs.append({"n": n, "box": [x0, y0, x1, y1], "area": round(float(a.mean()), 4), "edge": bool(edge)})
    m["scene"] = objs
    m3d_save_meta(sid, m)
    return m3d_view(sid)


def m3d_fill(img, p, J, seed):
    """가려지거나 잘린 부분을 Qwen-Image 2.1 편집으로 채워 물체 전체를 다시 그려요 → 배경 지우기."""
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bg.paste(img, mask=img.getchannel("A"))
    side = max(bg.size)
    sq = Image.new("RGB", (round(side * 1.3), round(side * 1.3)), (255, 255, 255))          # 둘레를 넉넉히(잘린 부분을 그릴 자리)
    sq.paste(bg, ((sq.width - bg.width) // 2, (sq.height - bg.height) // 2))
    b = io.BytesIO()
    sq.save(b, "PNG")
    res = do_edit({"kind": "edit", "engine": "qwen", "image": "data:image/png;base64," + base64.b64encode(b.getvalue()).decode(), "prompt": M3D_FILL,
                   "seed": seed, "fast": p.get("fast") or "", "translate": ""}, J)
    return m3d_cut(res[0][0].convert("RGB"), J)


def m3d_scene(p, J):
    """장면 전체: 고른 물체마다 3D → 깊이·사진 속 자리로 배치 → 한 장면 GLB (+ Blender 가 있으면 FBX·.blend)."""
    sid = p.get("id")
    m = m3d_meta(sid)
    J["out_label"] = m.get("name") or ""                 # 결과 폴더 이름에 3D 이름을 붙여요
    d = M3D_DIR / sid
    objs = [o for o in m.get("scene") or [] if (d / f"scene_obj_{o['n']}.png").is_file()]
    if not objs:
        raise ValueError("장면에 넣을 물체를 먼저 골라 주세요(원본 사진에서 물체를 눌러요).")
    o = m3d_opts(p, {**m, "kind": "object"})
    f, _ = m3d_need(False, J, m3d_engine(p))
    orig = Image.open(d / "orig.png").convert("RGB")
    dep, _how, _node = get_depth({}, J, orig)
    D = np.asarray(dep.convert("L").resize(orig.size), dtype=np.float32) / 255
    masks = []
    for ob in objs:
        mf = d / f"scene_mask_{ob['n']}.png"
        masks.append((ob["n"], ob["box"], np.asarray(Image.open(mf).convert("L").resize(orig.size)) > 127 if mf.is_file() else None))
    lay = {x["n"]: x for x in glbscene.layout(orig.size, D, masks)}
    seed = seed_of(p)
    fill = flag(p, "fill", False)
    items, parts = [], []
    for i, ob in enumerate(objs):
        check_cancel(J)
        n, tag = ob["n"], f"물체 {i + 1}/{len(objs)}"
        J["progress"] = i / len(objs)
        img = Image.open(d / f"scene_obj_{n}.png").convert("RGBA")
        if fill:
            J["msg"] = f"{tag} — 가려진 부분 채우는 중"
            img = m3d_fill(img, p, J, seed + i)
        glb = m3d_glb({"front": img}, False, f, o, seed + 10 * i, J, f"{tag} 3D 만드는 중 — 면 {o['faces']:,}개 · 텍스처 {o['tex']}px (물체마다 몇 분)")
        L = lay[n]
        parts.append({"glb": glb, "name": f"object_{n}", "pos": L["pos"], "height": L["height"]})
    J["msg"] = "장면으로 합치는 중"
    scene, info = glbscene.merge(parts)
    name = (m["name"] + "_장면")[:48]
    plan = {"note": "AI 추정값 — 사진 한 장과 깊이 추정으로 어림한 상대 위치·크기예요(실제로 잰 값 아님)", "unit": "m",
            "axes": "x 오른쪽 · y 앞쪽(카메라에서 멀어짐) · z 위 (Blender 기준), 위치는 물체 바닥 가운데",
            "objects": [{"name": pt["name"], "file": pt["name"] + ".glb", "pos": pt["pos"], "height": pt["height"], "size_m": inf["size_m"],
                         "tris": inf["tris"]} for pt, inf in zip(parts, info)]}
    base_info = {"kind": "3d", "photo": bool(J.get("m3d_photo")), "face": any(x.get("face") for x in J.get("m3d_photo") or []), "engine": ("Pixal3D" if f.get("pixal") else "TRELLIS.2") + " 장면", "objects": len(parts), "res": o["res"], "faces": o["faces"], "tex": o["tex"],
                 "seed": seed, "name": m["name"], "_sub": M3D_SUB, "fill": fill}
    work = d / f"scene_{uuid.uuid4().hex[:6]}"
    (work / "pack").mkdir(parents=True, exist_ok=True)
    try:
        (work / "scene.glb").write_bytes(scene)
        for pt in parts:
            (work / "pack" / (pt["name"] + ".glb")).write_bytes(pt["glb"])
        (work / "pack" / "layout.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        shown, bl = scene, None
        if o["blender"] and blender3d.exe(ROOT):
            J["msg"], J["progress"] = "Blender 로 장면 파일 만드는 중 — FBX·.blend", 0.97
            try:
                r = blender3d.finish(ROOT, work / "scene.glb", work / "pack", {"name": name, "scene": True, "formats": o["formats"]},
                                     lambda: J.get("cancel"))
                m3d_fix_pack(work / "pack")
                bl = r.get("blender")
                g = work / "pack" / str(r.get("glb") or "")
                if r.get("glb") and g.is_file():
                    shown = g.read_bytes()
            except InterruptedError:
                raise Cancelled("사용자가 중단했어요.") from None
            except Exception as e:  # noqa: BLE001
                warn(J, f"{e} — Blender 없이 합친 장면(GLB)과 물체별 GLB 만 저장했어요.")
        elif o["blender"]:
            warn(J, "Blender 가 없어 FBX·.blend 는 건너뛰었어요(장면 GLB·물체별 GLB 는 만들었어요). 3D 만들기 화면에서 [Blender 설치]를 누르면 다음부터 해요.")
        if not (work / "pack" / f"{name}.glb").is_file():
            (work / "pack" / f"{name}.glb").write_bytes(scene)
        z = d / f"{m['name']}_scene_{uuid.uuid4().hex[:4]}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for x in sorted((work / "pack").rglob("*")):
                if x.is_file() and x.name not in ("result.json", "error.txt"):
                    zf.write(x, x.relative_to(work / "pack"))
        info2 = {**base_info, **({"blender": bl} if bl else {}), "layout": plan["objects"]}
        items.append((shown, info2, ".glb"))
        items.append((z, {**info2, "pack": True}, ".zip"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    J["m3d_stats"] = {"scene": [{"name": x["name"], "pos": x["pos"], "height": x["height"], "size_m": x["size_m"], "tris": x["tris"],
                                 "dist": lay[int(x["name"].split("_")[-1])]["dist"]} for x in plan["objects"]], "blender": bool(bl)}
    J["msg"] = f"장면을 만들었어요 — 물체 {len(parts)}개 · 위치·크기는 AI 어림값이에요"
    m["scenes"] = m.get("scenes", 0) + 1
    m3d_save_meta(sid, m)
    return items


def m3d_view(sid):
    m = m3d_meta(sid)
    d = M3D_DIR / sid
    url = lambda f: f"/m3d/{sid}/{f}?t={int((d / f).stat().st_mtime)}"   # noqa: E731
    slots = {s: (url(f"view_{s}.png") if (d / f"view_{s}.png").is_file() else None) for s in ("front",) + M3D_SIDES}
    return {**m, "id": sid, "slots": slots, "ready": m3d_ready(), "blender": blender3d.status(ROOT),
            "orig": url("orig.png") if (d / "orig.png").is_file() else None, "front_orig": (d / "view_front_orig.png").is_file(),
            "vcheck": m3d_vcheck(d),
            "scene": [{"n": o["n"], "url": url(f"scene_obj_{o['n']}.png"), "edge": o.get("edge", False)}
                      for o in m.get("scene") or [] if (d / f"scene_obj_{o['n']}.png").is_file()]}


def m3d_list():
    if not M3D_DIR.is_dir():
        return {"items": []}
    out = []
    for d in sorted((x for x in M3D_DIR.iterdir() if (x / "meta.json").is_file()), key=lambda x: -x.stat().st_mtime)[:40]:
        try:
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            out.append({"id": d.name, "name": m.get("name", ""), "time": int(d.stat().st_mtime)})
        except Exception:  # noqa: BLE001
            continue
    return {"items": out}


def m3d_file(sid, name):
    if not re.fullmatch(r"(orig|view_(front|left|back|right|front_orig))\.png|rig_preview\.glb|scene_obj_\d{1,2}\.png", name or ""):
        return None
    try:
        f = m3d_dir(sid) / name
    except ValueError:
        return None
    return f if f.is_file() else None


def m3d_prep(p, J):
    """새 3D 작업: 사진 → 배경 지우기 → 상태 점검. 결과는 J['m3d'] (파일 저장 없음 — 작업 폴더에만 둬요)."""
    img = m3d_load(p["image"])
    full = img
    if max(img.size) > 2048:
        k = 2048 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), RS.LANCZOS)
    cut = m3d_cut(img, J)
    checks, stats = m3d_analyze(cut)
    stats.update(m3d_face_stats(cut, J))
    stats["face_rec"] = M3D_FACE_REC
    checks = m3d_face_check(checks, stats)
    k3 = p.get("kind3") or p.get("kind")
    bc, bs = m3d_body_check(img, cut, k3)
    stats.update(bs)
    checks = [c for c in checks if c["level"] != "ok"] + bc or checks
    sid = uuid.uuid4().hex[:12]
    d = M3D_DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(d / "orig.png")
    if full is not img:                                # 진짜 원본(줄이기 전)도 그대로 남겨요
        full.save(d / "orig_full.png")
    cut.save(d / "view_front.png")
    if cut.mode == "RGBA":                             # 배경 지우기 마스크(흰색 = 물체) — 팔다리가 지워졌는지 눈으로 확인할 수 있게
        cut.getchannel("A").save(d / "mask_front.png")
    name = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", str(p.get("name") or "")).strip("_")[:40] or time.strftime("model_%m%d_%H%M")
    k = p.get("kind3") or p.get("kind")                  # 작업 요청의 kind 는 'm3d' 라서 화면은 kind3 로 보내요
    m3d_save_meta(sid, {"name": name, "checks": checks, "stats": stats, "kind": k if k in M3D_KIND else "object",
                        "time": int(time.time())})
    J["m3d"] = m3d_view(sid)
    J["msg"] = "사진을 살펴봤어요 — " + checks[0]["text"]
    return []


def m3d_views(p, J):
    """앞 사진으로 왼쪽·뒤·오른쪽 그림을 만들어요(Qwen-Image 2.1 편집) → 배경 지우기 → 칸에 넣기."""
    sid = p.get("id")
    m = m3d_meta(sid)
    d = M3D_DIR / sid
    sides = [s for s in (p.get("sides") or M3D_SIDES) if s in M3D_SIDES]
    if not sides:
        raise ValueError("만들 방향을 골라 주세요.")
    front = Image.open(d / "view_front.png").convert("RGBA")
    bg = Image.new("RGB", front.size, (255, 255, 255))
    bg.paste(front, mask=front.getchannel("A"))
    b = io.BytesIO()
    bg.save(b, "PNG")
    src = "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
    what = {"character": "character", "big": "object"}.get(m.get("kind"), "object")
    items = []
    for i, s in enumerate(sides):
        check_cancel(J)
        J["msg"], J["progress"] = f"{M3D_SIDE_KO[s]} 모습 그리는 중 ({i + 1}/{len(sides)})", i / len(sides)
        text = (f"Turnaround view: show {M3D_SIDE_EN[s]}, of the same {what}. Orthographic-like eye-level view, no camera tilt. "
                "Keep exactly the same design, shape, proportions, colors, materials and details, and exactly the same pose as the reference — do not move the arms, legs or head. "
                "Full body / whole object in frame, same height and scale as the reference, plain pure white background, soft even studio lighting, no shadow. "
                "Glossy surfaces (shoes, leather, metal) show only their own true color — no reflections or color tints from the original floor, lights or surroundings.")
        res = do_edit({"kind": "edit", "engine": "qwen", "image": src, "prompt": text, "seed": seed_of(p) + i, "fast": p.get("fast") or "", "translate": ""}, J)
        cut = m3d_cut(res[0][0].convert("RGB"), J)
        cut.save(d / f"view_{s}.png")
        items.append((cut, {"kind": "m3d-view", "prompt": text, "side": s, "name": m["name"], "_sub": M3D_SUB}, None))      # 결과 폴더(3D)에도 남겨요
    m["views_made"] = sorted(set(m.get("views_made", [])) | set(sides))
    m3d_save_meta(sid, m)
    J["m3d"] = m3d_view(sid)
    bad = [M3D_SIDE_KO[k] for k, v in J["m3d"]["vcheck"].items() if not v["ok"]]
    J["msg"] = ("여러 방향 그림을 만들었어요. " + (f"{'·'.join(bad)} 그림은 앞 사진과 잘 맞지 않아 체크를 풀어 뒀어요(다시 그리거나 내 사진으로 바꿀 수 있어요)."
                                                 if bad else "모양이 앞 사진과 다르면 체크를 풀고 3D 를 만들어 주세요."))
    return items


M3D_TPOSE = ("Make the same character stand in a T-pose: both arms stretched straight out horizontally to the sides, palms facing down, "
             "legs straight and slightly apart, body and face toward the camera. Keep exactly the same character design, face, hair, clothing, "
             "colors, materials, proportions and details. Full body in frame, plain pure white background, soft even studio lighting, no shadow.")


def m3d_tpose(p, J):
    """앞 사진의 캐릭터를 T자 자세로 다시 그려요(Qwen-Image 2.1 편집) — 뼈대·가중치가 잘 맞게. 원래 앞 사진은 따로 둬요."""
    sid = p.get("id")
    m = m3d_meta(sid)
    d = M3D_DIR / sid
    front = Image.open(d / "view_front.png").convert("RGBA")
    if not (d / "view_front_orig.png").is_file():
        front.save(d / "view_front_orig.png")
    bg = Image.new("RGB", front.size, (255, 255, 255))
    bg.paste(front, mask=front.getchannel("A"))
    b = io.BytesIO()
    bg.save(b, "PNG")
    J["msg"] = "T자 자세로 다시 그리는 중"
    res = do_edit({"kind": "edit", "engine": "qwen", "image": "data:image/png;base64," + base64.b64encode(b.getvalue()).decode(),
                   "prompt": M3D_TPOSE, "seed": seed_of(p), "fast": p.get("fast") or "", "translate": ""}, J)
    cut = m3d_cut(res[0][0].convert("RGB"), J)
    cut.save(d / "view_front.png")
    m["checks"], m["stats"] = m3d_analyze(cut)
    m3d_save_meta(sid, m)
    J["m3d"] = m3d_view(sid)
    made = [s for s in M3D_SIDES if (d / f"view_{s}.png").is_file()]
    J["msg"] = "T자 자세로 바꿨어요." + (" 방향 그림은 예전 자세라서 다시 그리거나 체크를 풀어 주세요." if made else "")
    return [(cut, {"kind": "m3d-tpose", "prompt": M3D_TPOSE, "name": m["name"], "_sub": M3D_SUB}, None)]


def m3d_enlarge_op(p, J):
    """[업스케일로 키우기]: 방향 칸의 그림을 권장 크기(물체 부분 1024px)로 키워요."""
    sid, s = p.get("id"), p.get("side") or "front"
    if s not in ("front",) + M3D_SIDES:
        raise ValueError("알 수 없는 방향이에요.")
    d = m3d_dir(sid)
    f = d / f"view_{s}.png"
    if not f.is_file():
        raise ValueError("그 방향에 그림이 없어요.")
    if not m3d_upscaler():
        raise RuntimeError("업스케일 모델이 없어요. '설치와 모델'에서 SeedVR2 또는 Real-ESRGAN 을 설치해 주세요.")
    img, k = m3d_enlarge(Image.open(f).convert("RGBA"), J, force=True)
    if not k:
        J["m3d"], J["msg"] = m3d_view(sid), "이미 충분히 커요(물체 부분 1024px 이상)."
        return []
    img.save(f)
    if s == "front":
        m = m3d_meta(sid)
        old = m.get("stats") or {}
        m["checks"], m["stats"] = m3d_analyze(img)
        if old.get("face"):                           # 키운 만큼 얼굴 크기도 커져요
            m["stats"].update(face=int(round(old["face"] * k)), face_box=[round(v * k) for v in old.get("face_box") or []], face_rec=M3D_FACE_REC)
            m["checks"] = m3d_face_check(m["checks"], m["stats"])
        m3d_save_meta(sid, m)
    J["m3d"], J["msg"] = m3d_view(sid), f"{M3D_SIDE_KO[s]} 그림을 {k:g}배 키웠어요."
    return []


def m3d_slot(p):
    """방향 칸에 내 사진 넣기(배경 자동 제거) · 비우기."""
    sid, s = p.get("id"), p.get("side")
    d = m3d_dir(sid)
    if s not in ("front",) + M3D_SIDES:
        return {"error": "알 수 없는 방향이에요."}
    f = d / f"view_{s}.png"
    if p.get("restore"):
        o = d / "view_front_orig.png"
        if s != "front" or not o.is_file():
            return {"error": "되돌릴 원래 사진이 없어요."}
        shutil.copyfile(o, f)
        o.unlink()
        m = m3d_meta(sid)
        m["checks"], m["stats"] = m3d_analyze(Image.open(f).convert("RGBA"))
        m3d_save_meta(sid, m)
        return m3d_view(sid)
    if p.get("clear"):
        if s == "front":
            return {"error": "앞 사진은 비울 수 없어요."}
        f.unlink(missing_ok=True)
        return m3d_view(sid)
    try:
        cut = m3d_cut(m3d_load(p["image"]))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e) or "사진을 읽을 수 없어요."}
    cut.save(f)
    if s == "front":
        m = m3d_meta(sid)
        m["checks"], m["stats"] = m3d_analyze(cut)
        m3d_save_meta(sid, m)
    return m3d_view(sid)


def m3d_delete(p):
    d = m3d_dir(p.get("id"))
    shutil.rmtree(d, ignore_errors=True)
    return m3d_list()


def m3d_opts(p, m):
    kind = M3D_KIND.get(m.get("kind"), M3D_KIND["object"])
    res = int(num(p, "res", 1024, int))
    faces = int(num(p, "faces", kind["faces"], int))
    tex = int(num(p, "tex", 2048, int))
    res = res if res in M3D_RES else 1024
    return {"res": res, "faces": faces if faces in M3D_FACES else kind["faces"], "tex": tex if tex in M3D_TEX else 2048,
            "remesh": (1024 if res >= 1536 else M3D_REMESH) if flag(p, "remesh", True) else 0, "blender": flag(p, "blender", True), "height": clamp(num(p, "height", kind["height"]), 0.0, 500.0),
            "rotate": int(num(p, "rotate", 0, int)) % 360 // 90 * 90, "lods": flag(p, "lods", True),
            "formats": [x for x in ("glb", "fbx", "obj") if flag(p, "fmt_" + x, x != "obj")] or ["glb"],
            "rig": flag(p, "rig", m.get("kind") == "character"), "photo": flag(p, "photo", True), "head": flag(p, "head", True),
            # 만드는 방식: 사진 한 장(기본) / AI 멀티뷰 보조. 예전 호출(방향만 보냄)은 멀티뷰로 알아들어요
            "mode": p.get("mode") if p.get("mode") in ("single", "multi") else ("multi" if p.get("sides") else "single"),
            "align": flag(p, "align", False),        # 사진 얼굴을 3D 얼굴 각도에 맞춰 휘기 — 기본 꺼짐(원본 얼굴 비율·눈코입 자리 보존)
            "compare": flag(p, "compare", False),    # 단계별 결과(A~E)·비교표 저장
            "keep_hi": flag(p, "keep_hi", True),     # 원본 고밀도 메시(면 줄이기 전)를 따로 저장
            "capture": flag(p, "capture", True)}     # 앞·왼쪽·오른쪽·뒤 캡처 그림


def m3d_engine(p):
    """사진 한 장일 때 엔진: auto(Pixal3D 가 있으면 Pixal3D) / pixal / trellis → 'pixal' 또는 'trellis'"""
    e = p.get("engine3") if p.get("engine3") in ("pixal", "trellis") else "auto"
    if e == "pixal" or (e == "auto" and pixal_ready()):
        return "pixal"
    return "trellis"


def m3d_need(mv, J, engine="trellis"):
    """만들 수 있는지 확인: 모델 파일·ComfyUI 노드. 멀티뷰 모델이 없으면 한 장으로 바꿔요 → (파일, 멀티뷰 여부)
    engine='pixal' 이면 사진 한 장을 Pixal3D(픽셀 정렬)로 — 파일에 'pixal': True 가 붙어요(없으면 TRELLIS.2 로)."""
    nodes = caps()["nodes"]
    f = trellis_files(mv)
    if mv and not all(f.values()):
        warn(J, "여러 방향으로 만들려면 'Pixal3D 멀티뷰' 모델이 필요해요. 이번엔 앞 사진 한 장으로 만들었어요.")
        mv = False
        f = trellis_files(False)
    pixal = False
    if not mv and engine == "pixal":
        if pixal_ready() and (not nodes or "Pixal3DConditioning" in nodes):
            f, pixal = {**pixal_files(), "pixal": True}, True
            if not f["moge"] or (nodes and "MoGeInference" not in nodes):
                warn(J, "화각 어림 모델(MoGe)이 없어 기본 화각으로 만들었어요. '설치와 모델'에서 'Pixal3D'를 다시 설치하면 함께 받아요.")
                f["moge"] = None
        elif pixal_ready():
            warn(J, "이 ComfyUI 에는 Pixal3D 노드가 없어 TRELLIS.2 로 만들었어요. ComfyUI 를 업데이트하면 Pixal3D 로 만들어요.")
        elif all(f.values()):
            warn(J, "Pixal3D 가 아직 없어 TRELLIS.2 로 만들었어요. 사진에 더 충실하게 만들려면 '설치와 모델'에서 'Pixal3D'를 받아 주세요.")
        else:
            raise RuntimeError("없는 파일: Pixal3D 모델. '설치와 모델' 탭의 3D 분류에서 'Pixal3D'를 설치해 주세요.")
    if not pixal and not all(f.values()):
        names = {"model": "TRELLIS.2 모델", "dino": "DINOv3 이미지 인코더", "svae": "모양 VAE", "tvae": "텍스처 VAE"}
        raise RuntimeError("없는 파일: " + ", ".join(names[k] for k, v in f.items() if not v) + ". '설치와 모델' 탭의 3D 분류에서 'TRELLIS.2' 를 설치해 주세요.")
    need = ["Trellis2ShapeStage", "VaeDecodeShapeTrellis", "BakeTextureFromVoxel", "SaveGLB"] + \
        (["Pixal3DMultiViewConditioning"] if mv else ["Pixal3DConditioning"] if pixal else ["Trellis2Conditioning"])
    miss = [n for n in need if nodes and n not in nodes]
    if miss:
        raise RuntimeError("이 ComfyUI 에는 3D 노드(" + ", ".join(miss) + ")가 없어요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
    return f, mv


M3D_GOOD = 1024                                     # 3D 모델이 보는 크기(물체 부분 긴 변) — 이만큼이면 충분해요
M3D_SMALL = 768                                     # 이보다 작으면 만들기 전에 키워요


def m3d_upscaler(redraw_ok=True):
    """3D 용 업스케일 모델: 다시 그리지 않는 일반 업스케일(Real-ESRGAN 등)이 먼저예요 — SeedVR2 는 AI 복원이라
    얼굴의 눈·코·입을 조금씩 새로 그릴 수 있어요. redraw_ok=False 면 SeedVR2 는 쓰지 않아요(얼굴 확대). 없으면 None."""
    up = (files("upscale_models") or [None])[0]
    if up or not redraw_ok:
        return up
    sv = seedvr_names()
    return sv[0] if sv else None


def m3d_keep_face(orig, big, J):
    """SeedVR2(다시 그리는 업스케일)로 키운 그림에 원래 얼굴을 되돌려 놓아요(단순 확대 — 눈·코·입이 바뀌지 않게). 얼굴을 못 찾으면 그대로."""
    try:
        box = m3d_face_box(orig, J) if m3d_face_model() else None
    except Exception:  # noqa: BLE001
        box = None
    if not box:
        return big, False
    kx, ky = big.width / orig.width, big.height / orig.height
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    bx = (max(0, round((x0 - 0.15 * w) * kx)), max(0, round((y0 - 0.2 * h) * ky)), min(big.width, round((x1 + 0.15 * w) * kx)), min(big.height, round((y1 + 0.1 * h) * ky)))
    if bx[2] - bx[0] < 8 or bx[3] - bx[1] < 8:
        return big, False
    plain = orig.convert("RGB").resize(big.size, RS.LANCZOS).crop(bx)
    mk = Image.new("L", plain.size, 0)
    pad = max(2, round(min(plain.size) * 0.12))
    mk.paste(255, (pad, pad, plain.width - pad, plain.height - pad))
    mk = mk.filter(ImageFilter.GaussianBlur(pad / 2))
    rgb = big.convert("RGB")
    rgb.paste(plain, bx[:2], mk)
    if big.mode == "RGBA":
        rgb.putalpha(big.getchannel("A"))
    return rgb, True


def m3d_enlarge(img, J, target=M3D_GOOD, force=False):
    """물체 부분이 작으면(긴 변 768px 미만) 업스케일 모델로 키워요(배경 투명도는 그대로 늘려요). → (그림, 키운 배율 또는 0)"""
    box = img.getchannel("A").point(lambda v: 255 if v > 127 else 0).getbbox() if img.mode == "RGBA" else (0, 0, img.width, img.height)
    if not box:
        return img, 0
    side = max(box[2] - box[0], box[3] - box[1])
    if side >= (target if force else M3D_SMALL):
        return img, 0
    model = m3d_upscaler()
    if not model:
        warn(J, f"물체 부분이 {side}px 로 작아요. '설치와 모델'에서 업스케일 모델(SeedVR2 또는 Real-ESRGAN)을 받으면 키워서 더 세밀하게 만들어요.")
        return img, 0
    pad = round(side * 0.08)
    c = img.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(img.width, box[2] + pad), min(img.height, box[3] + pad)))
    k = round(min(4.0, target / side), 2)
    J["msg"] = f"사진이 작아서 키우는 중 ({side}px → 약 {round(side * k)}px)"
    big = upscale(c.convert("RGB"), J, model, k).convert("RGBA")
    big.putalpha(c.getchannel("A").resize(big.size, RS.LANCZOS))
    if seedvr_of(model):                               # 다시 그리는 업스케일이었으면 얼굴은 원래 것으로(단순 확대)
        big, kept = m3d_keep_face(c.convert("RGBA"), big, J)
        if kept:
            warn(J, "SeedVR2 로 키웠어요. 얼굴은 눈·코·입이 바뀌지 않게 원래 얼굴을 그대로 확대해 넣었어요(Real-ESRGAN 이 있으면 그걸 먼저 써요).")
    return big, k


def m3d_defringe(img):
    """배경 지운 사진의 가장자리 손질: 반쯤 투명한 가장자리(머리카락 끝 등)는 원래 배경색이 섞여 있고, 3D 엔진은 이를 검은 배경 위에 얹어 받아서
    3D 색에 검은 테두리로 굳어요. 가장자리 색을 안쪽 물체 색으로 채우고(색 번짐 제거), 투명도 경계를 조금 또렷하게 해요."""
    if img.mode != "RGBA":
        return img
    a = np.asarray(img.getchannel("A")).astype(np.float32) / 255
    if not ((a > 0.02) & (a < 0.98)).any():
        return img
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    solid = (a >= 0.95).astype(np.float32)
    fill = rgb.copy()
    todo = solid < 1
    for r in (2, 4, 8, 16, 32):                       # 가까운 물체 색부터 넓혀 가며 채워요
        if not todo.any():
            break
        sw = np.asarray(Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(r))).astype(np.float32) / 255
        sc = np.stack([np.asarray(Image.fromarray(np.clip(rgb[..., c] * solid, 0, 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(r))).astype(np.float32)
                       for c in range(3)], -1)
        got = todo & (sw > 0.02)
        fill[got] = sc[got] / sw[got][:, None]
        todo &= ~got
    out = np.where(solid[..., None] > 0, rgb, fill)
    a2 = np.clip((a - 0.25) / 0.5, 0, 1)                # 투명도 경계를 또렷하게(0.25 아래는 투명, 0.75 위는 불투명)
    o = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA")
    o.putalpha(Image.fromarray((a2 * 255).astype(np.uint8)))
    return o


def m3d_glb(imgs, mv, f, o, seed, J, label=None, stages=None):
    """사진(배경 지운 RGBA, {방향: 그림}) → ComfyUI TRELLIS.2/Pixal3D → 텍스처 입힌 GLB 바이트.
    stages(dict) 를 주면 단계별 결과를 담아요: A 엔진 원본, B 사진 붙이기(얼굴 텍스처 없이 — 비교할 때만), C 최종, hi 원본 고밀도 메시."""
    for sd in list(imgs):                              # 가장자리 검은 테두리 막기
        imgs[sd] = m3d_defringe(imgs[sd])
    # 3D 엔진 입력: 업스케일하지 않은 사진으로, 비율을 지킨 채 여백을 넣어 정사각형(우리가 직접 — 한 장·멀티뷰 같은 방식).
    # 업스케일(AI 가 세부를 추정해 그림)은 엔진 입력에 쓰지 않고, 아래 사진 붙이기(텍스처)에만 써요.
    pixal_like = mv or bool(f.get("pixal"))
    fr = m3d_frame(imgs, pad=1.1 if pixal_like else 1.0)     # 노드 설명: Pixal3D 는 1.1, TRELLIS.2 는 1.0
    views = {sd: put_input(fr[sd], J) for sd in imgs}
    if J.get("_m3d_dir"):                               # 엔진이 받은 그림 그대로 남겨요(다리 등이 엔진 입력에서부터 빠졌는지 확인용)
        for sd in imgs:
            try:
                fr[sd].save(Path(J["_m3d_dir"]) / f"engine_input_{sd}.png")
            except OSError:
                pass
    tex_front, k_up = m3d_enlarge(imgs["front"], J)     # 사진 붙이기용: 작으면 업스케일(얼굴은 원래 얼굴 유지)
    if k_up:
        warn(J, f"사진이 작아서 사진 붙이기(텍스처)용으로만 업스케일로 키워 썼어요({k_up:g}배). 3D 모양은 원래 사진으로 만들어요.")
    # 단계 수(구조, 모양 512, 재질, 모양 올려 그리기)·cfg — 원본 TRELLIS.2 기본값
    nodes = caps()["nodes"]
    co = not nodes or "CFGOverride" in nodes
    nodes0 = caps()["nodes"]
    q = {"files": f, "views": views, "multiview": mv, "pixal1": bool(f.get("pixal")) and not mv, "moge": f.get("moge"), "framed": True, "seed": seed,
         "fov_out": not nodes0 or "PreviewAny" in nodes0,
         "steps": (12, 20, 12, 12), "cfg": (7.5, 7.5, 1.0),
         "res": o["res"], "remesh": o["remesh"], "faces": o["faces"], "tex": o["tex"], "cfg_override": co,
         "keep_hi": stages is not None and o.get("keep_hi"),
         "stage_saves": stages is not None and o.get("compare")}
    if not co:
        warn(J, "이 ComfyUI 에는 CFGOverride 노드가 없어서 원본 설정 일부(앞쪽 단계에만 가이드 걸기) 없이 만들었어요. "
                "ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 으로 업데이트하면 모양이 더 좋아져요.")
    free_ollama()
    J["msg"] = label or f"3D 만드는 중 — 모양 {o['res']} · 면 {o['faces']:,}개 · 텍스처 {o['tex']}px (몇 분 걸려요)"
    fixed = []
    res = run_wf(wf_fit(flows.wf_trellis(q), fixed), J, raw=True)
    if any(x.startswith("RemeshMesh.") for x in fixed):
        warn(J, "이 ComfyUI 는 '닫힌 몸체로 다시 짜기(solid)'를 몰라서 예전 방식(udf)으로 그물망을 다시 짰어요. 이 방식은 팔·다리가 떨어져 나가거나 "
                "구멍이 생길 수 있어서 안쪽 껍질만 지우게 바꿨어요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 으로 업데이트하면 "
                "닫힌 몸체로 고르게 나와요(권장).")
    glbs = [(n, dat) for n, dat in res if n.lower().endswith(".glb")]
    extra = ("hub3d_hi", "hub3d_remesh", "hub3d_dec")
    glb = next((dat for n, dat in glbs if not any(x in n for x in extra)), None)
    if not glb:
        raise RuntimeError("3D 결과(GLB)를 받지 못했어요.")
    if stages is not None:                             # 모양 단계별 그물망: 고밀도(원본) → 다시 짠 뒤 → 면 줄인 뒤
        for key, nm in (("hi", "hub3d_hi"), ("remesh", "hub3d_remesh"), ("dec", "hub3d_dec")):
            dat = next((d_ for n, d_ in glbs if nm in n), None)
            if dat:
                stages[key] = dat
    _clean_tmp(J)
    glb = photoproj.fix_samplers(glb)
    # 사진 붙이기 원근: Pixal3D 는 정해진 화각으로 만들어서 계산할 수 있어요(카메라 거리 = 0.5/tan(화각/2), 물체는 화면의 1/1.1 → 긴 변 기준 0.55/tan)
    dist_e = None
    texts = J.pop("wf_text", None) or []
    fov = 20.0 if mv else 49.13 if q["pixal1"] else None
    if q["pixal1"] and q.get("moge"):
        fov = next((float(t) for t in texts if re.fullmatch(r"\s*\d+(\.\d+)?\s*", str(t)) and 5 < float(t) < 170), None)
    bb = fr["front"].convert("L").point(lambda x: 255 if x > 8 else 0).getbbox()
    if fov and bb:                                       # 엔진 입력 그림에서 물체가 차지한 크기로 정확히(한 장·멀티뷰 같은 식)
        dist_e = 0.5 / math.tan(math.radians(fov) / 2) * fr["front"].width / max(bb[2] - bb[0], bb[3] - bb[1])
    if J.get("_m3d_dir"):                  # 3D 엔진이 만든 원래 3D(사진 붙이기 전) — 마지막 것 하나만 작업 폴더에 남겨요(문제 살필 때 보내 주세요)
        try:
            (Path(J["_m3d_dir"]) / "engine_last.glb").write_bytes(glb)
        except OSError:
            pass
    o = {**o, "_pixal": bool(f.get("pixal")) or mv}
    if stages is not None:
        stages["A"] = glb
        stages["_dist"], stages["_pixal"], stages["_front"], stages["_fov"] = dist_e, o["_pixal"], tex_front, fov
    if o.get("photo", True):
        if stages is not None and o.get("compare") and o.get("head", True):   # 비교용 B: 얼굴 전용 텍스처 없이
            stages["B"] = m3d_photo(glb, tex_front, J, {**o, "head": False}, dist_e)
        glb = m3d_photo(glb, tex_front, J, o, dist_e)
        if stages is not None and "B" not in stages and o.get("compare"):
            stages["B"] = glb
    if stages is not None:
        stages["C"] = glb
    return glb


def m3d_fix_pack(folder):
    """Blender 가 내보낸 GLB 들도 텍스처 밉맵을 켜 둬요(게임 엔진 기본값)."""
    for f in Path(folder).rglob("*.glb"):
        try:
            data = f.read_bytes()
            new = photoproj.fix_samplers(data)
            if new != data:
                f.write_bytes(new)
        except OSError:
            pass


M3D_FACE_GOOD = 1024      # 얼굴 부분이 이보다 작으면 키워서 붙여요
M3D_FACE_REC = 512        # 사진 점검: 얼굴이 이보다 작으면 알려 줘요(얼굴 선명도는 원본 얼굴 크기를 넘지 못해요)


def m3d_face_model():
    model = next((n for n in files("detection") if "mediapipe_face" in n.lower()), None)
    nodes = caps()["nodes"]
    if not model or (nodes and not all(x in nodes for x in ("LoadMediaPipeFaceLandmarker", "MediaPipeFaceLandmarker", "MediaPipeFaceMask"))):
        return None
    return model


def _mp_face(img, J, model):
    """MediaPipe 얼굴 찾기 한 번 → 그 그림 좌표의 얼굴 상자 또는 None"""
    k = min(1.0, 1536 / max(img.size))
    small = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), RS.LANCZOS) if k < 1 else img
    bg = Image.new("RGB", small.size, (128, 128, 128))
    bg.paste(small.convert("RGB"), mask=small.getchannel("A") if small.mode == "RGBA" else None)
    try:
        res = run_wf(flows.wf_face_mask(model, put_input(bg, J)), J, raw=True)
    except Exception as e:  # noqa: BLE001 — 얼굴 찾기는 덤이라 실패해도 3D 는 계속
        quiet_log("[3D 얼굴 찾기 실패]", repr(e))
        return None
    mk = next((dat for n, dat in res if n.lower().endswith(".png")), None)
    box = Image.open(io.BytesIO(mk)).convert("L").point(lambda v: 255 if v > 127 else 0).getbbox() if mk else None
    return tuple(v / k for v in box) if box else None


def m3d_face_ok(photo, box):
    """찾은 얼굴이 진짜 얼굴 같은지: 몸 크기에 비해 말이 되는 크기이고, 가운데가 피부색이어야 해요
    (작은 얼굴을 못 찾고 가슴·옷 무늬를 얼굴로 잡는 경우를 걸러요)."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    a = photo.getchannel("A").point(lambda v: 255 if v > 127 else 0) if photo.mode == "RGBA" else None
    sb = (a.getbbox() if a else None) or (0, 0, photo.width, photo.height)
    sh = max(1, sb[3] - sb[1])
    if w < 8 or h < 8 or not (0.012 * sh <= h <= 0.7 * sh):
        return False
    inner = photo.convert("RGB").crop((round(x0 + 0.2 * w), round(y0 + 0.3 * h), round(x1 - 0.2 * w), round(y1 - 0.15 * h)))
    arr = np.asarray(inner).reshape(-1, 3).astype(np.float32)
    return len(arr) > 0 and float(photoproj._skin(arr).mean()) >= 0.25


def m3d_face_box(photo, J, model=None):
    """사진에서 얼굴 상자(MediaPipe) → (x0, y0, x1, y1) 사진 좌표 또는 None.
    전체에서 찾고, 못 찾거나 진짜 얼굴 같지 않으면 몸의 위쪽만 잘라 크게 해서 다시 찾아요(전신 사진의 작은 얼굴)."""
    model = model or m3d_face_model()
    if not model:
        return None
    b = _mp_face(photo, J, model)
    if b and m3d_face_ok(photo, b):
        return b
    a = photo.getchannel("A").point(lambda v: 255 if v > 127 else 0) if photo.mode == "RGBA" else None
    sb = (a.getbbox() if a else None) or (0, 0, photo.width, photo.height)
    bw, bh = sb[2] - sb[0], sb[3] - sb[1]
    if bh < 1.3 * bw:                                  # 세로로 긴(전신) 사진일 때만 위쪽을 다시 봐요
        quiet_log("[3D 얼굴 찾기] 얼굴을 확실히 찾지 못했어요", b)
        return None
    top = (sb[0], sb[1], sb[2], min(sb[3], sb[1] + max(round(0.35 * bh), bw)))
    crop = photo.crop(top)
    b2 = _mp_face(crop, J, model)
    if b2:
        b2 = (b2[0] + top[0], b2[1] + top[1], b2[2] + top[0], b2[3] + top[1])
        if m3d_face_ok(photo, b2):
            return b2
    quiet_log("[3D 얼굴 찾기] 얼굴을 확실히 찾지 못했어요", b, b2)
    return None


def m3d_face_stats(img, J):
    """사진 점검용 얼굴 크기(px). 이미지 엔진이 켜져 있고 얼굴 찾기 모델이 있을 때만 → {face, face_box} 또는 {}"""
    try:
        if not m3d_face_model() or not alive(CUI + "/system_stats"):
            return {}
        b = m3d_face_box(img, J)
    except Exception as e:  # noqa: BLE001
        quiet_log("[3D 얼굴 크기 확인 실패]", repr(e))
        return {}
    return {"face": int(round(max(b[2] - b[0], b[3] - b[1]))), "face_box": [round(v) for v in b]} if b else {}


def m3d_face_check(checks, st):
    """얼굴이 작으면 점검 목록에 알려 줘요."""
    f = st.get("face")
    if f and f < M3D_FACE_REC:
        checks = [c for c in checks if c["level"] != "ok"] + [{"level": "warn", "text": f"얼굴이 {f}px 로 작아요. 3D 얼굴의 선명도는 사진 속 얼굴 크기를 넘지 못해요 — "
                                                                                 f"권장 {M3D_FACE_REC}px 이상(얼굴·상반신이 크게 나온 사진)이에요."}]
    return checks


def m3d_face(photo, J):
    """사진에서 얼굴을 찾아(MediaPipe) 그 부분을 업스케일로 키워요 → (얼굴 상자 또는 None, (x0, y0, x1, y1, 키운 그림) 또는 None).
    얼굴 찾기 모델·노드가 없거나 얼굴이 없으면 (None, None), 업스케일 모델이 없거나 이미 충분히 크면 (상자, None)."""
    model = m3d_face_model()
    if not model:
        J.setdefault("m3d_notes", []).append("face_model")
        return None, None
    b = m3d_face_box(photo, J, model)
    if not b:
        return None, None
    return b, m3d_face_up(photo, b, J)


def m3d_face_up(photo, b, J):
    x0, y0, x1, y1 = b
    cx, cy, side = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) * 1.5
    x0, y0 = max(0, round(cx - side / 2)), max(0, round(cy - side / 2))
    x1, y1 = min(photo.width, round(cx + side / 2)), min(photo.height, round(cy + side / 2))
    side = max(x1 - x0, y1 - y0)
    if side >= M3D_FACE_GOOD or side < 24:
        return None
    up = m3d_upscaler(redraw_ok=False)                 # 얼굴은 다시 그리는 업스케일(SeedVR2)을 쓰지 않아요 — 원래 얼굴 그대로
    if not up:
        warn(J, f"얼굴 부분이 {side}px 로 작아요. '설치와 모델'에서 일반 업스케일 모델(Real-ESRGAN)을 받으면 얼굴을 키워서 더 선명하게 붙여요"
                "(SeedVR2 는 얼굴을 조금 새로 그릴 수 있어 얼굴 확대에는 쓰지 않아요).")
        return None
    J["msg"] = f"얼굴 부분을 키우는 중 ({side}px → 약 {min(4 * side, 1536)}px)"
    crop = photo.crop((x0, y0, x1, y1)).convert("RGB")
    big = upscale(crop, J, up, round(min(4.0, 1536 / side), 2))
    return (x0, y0, x1, y1, big)


def m3d_photo(glb, photo, J, o=None, dist_e=None):
    """사진 붙이기: 3D 엔진이 다시 칠한 색 대신 앞 사진의 화소를 그대로 붙여요(얼굴·무늬가 사진처럼). 안 맞으면 원래 색 그대로."""
    box, face = None, None
    if o.get("head", True):
        try:
            box, face = m3d_face(photo, J)
        except Exception as e:  # noqa: BLE001
            quiet_log("[3D 얼굴 키우기 실패]", repr(e))
    if box:
        J["_m3d_face"] = list(box)
    J["msg"] = "사진을 3D 에 붙이는 중 — 얼굴·무늬를 사진 그대로" + (" · 머리 전용 텍스처" if box else "")
    try:
        new, info = photoproj.project(glb, photo, face, log=quiet_log, head=box, head_size=max(2048, int(o.get("tex") or 4096)), dist_e=dist_e,
                                      align=bool(o.get("align")), cam_hint=photoproj.PIXAL_CAM if o.get("_pixal") else None)
    except ValueError as e:              # 붙일 수 없는 모양(텍스처 없음 등) — 원래 색 그대로
        quiet_log("[3D 사진 붙이기 건너뜀]", e)
        J["m3d_photo_res"] = {"done": False, "text": f"이 3D 에는 붙일 수 없었어요({e})"}
        return glb
    except Exception as e:  # noqa: BLE001
        quiet_log("[3D 사진 붙이기 실패]", repr(e))
        warn(J, f"사진 붙이기를 하지 못해 3D 엔진이 칠한 색 그대로예요({str(e)[:80]}).")
        J["m3d_photo_res"] = {"done": False, "text": f"오류로 하지 못했어요({str(e)[:80]})"}
        return glb
    if info.get("skip") == "shape":
        warn(J, f"사진과 3D 모양이 충분히 겹치지 않아(겹침 {info['iou']:.0%}) 사진 붙이기는 건너뛰었어요. 어긋나게 붙으면 번져 보여서요.")
        J["m3d_photo_res"] = {"done": False, "iou": info["iou"], "text": f"사진과 3D 모양이 충분히 겹치지 않아 건너뛰었어요(겹침 {info['iou']:.0%}, 필요 85% — 머리카락이 많으면 75% + 무늬 일치). "
                                                                      "배경이 깨끗하게 지워진 사진, 물체 전체가 나온 사진에서 잘 돼요."}
        return glb
    if info.get("skip"):
        J["m3d_photo_res"] = {"done": False, "text": "사진 쪽에서 보이는 면이 없어 건너뛰었어요."}
        return glb
    J.setdefault("m3d_photo", []).append(info)
    noface = o.get("head", True) and box is None and bool(m3d_face_model())
    J["m3d_photo_res"] = {"done": True, "iou": info["iou"], "face": info.get("face"), "head": info.get("head"),
                          "text": f"앞 사진을 그대로 붙였어요(겹침 {info['iou']:.0%}{', 얼굴은 키워서' if info.get('face') else ''}"
                                  f"{', 머리는 전용 텍스처 ' + str(info['head_tex']) + 'px' if info.get('head') else ''})."
                                  + (" 얼굴을 확실히 찾지 못해 얼굴 고해상도는 건너뛰었어요(얼굴이 크게 나온 사진에서 잘 돼요)." if noface else "")
                                  + (f" 사진 속 얼굴의 각도·자리를 3D 얼굴에 맞춰 휘어 붙였어요(기울기 {abs((info.get('align') or {}).get('rot', 0)):.0f}°)." if (info.get("align") or {}).get("ok") else "")}
    if info.get("head_error"):
        quiet_log("[머리 전용 텍스처 건너뜀]", info["head_error"])
    if "face_model" in (J.get("m3d_notes") or []) and not J.get("_face_noted"):
        J["_face_noted"] = 1
        warn(J, "얼굴 찾기 모델이 없어 얼굴 확대는 건너뛰었어요. '설치와 모델'의 3D 분류에서 '얼굴 찾기(MediaPipe)'를 받으면 얼굴이 더 선명해져요.")
    return new


M3D_STAGE = {"A": ("A 엔진 원본", "A engine", "엔진원본"), "B": ("B 사진 붙이기", "B photo", "사진붙이기"), "C": ("C 얼굴 텍스처", "C head", "얼굴텍스처"),
             "D": ("D Blender 마무리", "D Blender", "Blender"), "E": ("E AI 멀티뷰", "E multiview", "멀티뷰"),
             "F": ("F TRELLIS.2", "F TRELLIS.2", "TRELLIS2"),
             "hi": ("A0 고밀도(원본, 색 없음)", "A0 dense", "원본고밀도"), "remesh": ("A1 다시 짠 뒤(색 없음)", "A1 remeshed", "다시짠뒤"),
             "dec": ("A2 면 줄인 뒤(색 없음)", "A2 decimated", "면줄인뒤")}
M3D_SHAPE = ("hi", "remesh", "dec", "A")      # 모양 단계 순서(어디서 팔다리가 사라졌는지 보려고)
M3D_HEAD_TRIS = 3000         # 사람 캐릭터의 머리(위쪽 13%)가 이보다 면이 적으면 얼굴 굴곡이 뭉개져요


def m3d_mv_check(d, sides, J=None):
    """AI 방향 그림이 앞 사진과 자세·비율이 맞는지(실루엣) — 맞는 방향만 돌려줘요. 안 맞는 그림은 3D 모양을 비틀어요."""
    vc = m3d_vcheck(d)
    bad = [s for s in sides if s in vc and not vc[s]["ok"]]
    if bad and J is not None:
        warn(J, "AI 멀티뷰 보조: " + ", ".join(f"{M3D_SIDE_KO[s]}(맞음 {vc[s]['score']:.0%})" for s in bad)
             + " 그림은 앞 사진과 자세·비율이 달라서 빼고 만들었어요. 서로 다른 그림이 섞이면 3D 모양이 비틀어져요.")
    return [s for s in sides if s not in bad]


def m3d_check_mesh(glb, kind, J):
    """그물망 검사(구멍·떨어진 조각·납작함·머리 부분 면 수) → 결과 dict(화면 표시용). 문제가 있으면 알려 줘요."""
    try:
        rep = photoproj.mesh_report(glb)
    except Exception as e:  # noqa: BLE001 — 검사는 덤
        quiet_log("[3D 검사 실패]", repr(e))
        return None
    if kind == "character":
        try:
            sc = photoproj._scene(glb, tex_max=16)
            P = np.concatenate([x[0] for x in sc])
            F = np.concatenate([x[1] + o for x, o in zip(sc, np.cumsum([0] + [len(x[0]) for x in sc])[:-1])])
            ys = P[F].mean(1)[:, 1]
            top = ys > P[:, 1].max() - 0.13 * np.ptp(P[:, 1])
            rep["head_tris"] = int(top.sum())
            if top.sum() < M3D_HEAD_TRIS:
                rep["notes"].append(f"머리 부분 면이 {int(top.sum()):,}개뿐이라 얼굴 굴곡이 뭉개질 수 있어요(면 수 20만 권장)")
        except Exception:  # noqa: BLE001
            pass
    if rep["notes"]:
        quiet_log("[3D 검사]", rep)
    return rep


def m3d_limbs(stages, J, all_stages=False):
    """사람 3D 의 팔다리 검사: 사진 카메라로 본 실루엣이 사진 속 왼다리·오른다리·왼팔·오른팔을 하나씩 덮는지.
    all_stages 면 모양 단계(고밀도 → 다시 짠 뒤 → 면 줄인 뒤 → 엔진 최종)마다 재서 어디서 사라졌는지 찾아요. → dict 또는 None"""
    A, front = stages.get("A"), stages.get("_front")
    if not A or front is None or front.mode != "RGBA":
        return None
    try:
        cam = photoproj.shape_cam(A, front, stages.get("_dist"), photoproj.PIXAL_CAM if stages.get("_pixal") else None)
        alpha = np.asarray(front.getchannel("A")).astype(np.float64) / 255
        res = {}
        for k in (M3D_SHAPE if all_stages else ("A",)):
            if stages.get(k):
                res[k] = photoproj.limbs_of(stages[k], cam, alpha)
    except Exception as e:  # noqa: BLE001 — 검사는 덤
        quiet_log("[3D 팔다리 검사 실패]", repr(e))
        return None
    wa = res.get("A", {}).get("whole", 0)
    lost = None
    for k in M3D_SHAPE:
        r = res.get(k)
        if not r:
            continue
        if r["whole"] < 0.5 <= wa:                          # 좌표가 달라 비교할 수 없는 단계(엔진 판마다 다를 수 있어요)
            r["note"] = "좌표가 달라 비교하지 못했어요"
            continue
        if r["missing"] and lost is None:
            lost = k
    return {"stages": res, "missing": res.get("A", {}).get("missing", []), "lost_at": lost}


class M3dVram:
    """3D 만드는 동안 GPU 메모리(VRAM) 사용량을 2초마다 재서 가장 많이 쓴 값을 남겨요(다른 프로그램이 쓰는 몫도 함께 잡혀요)."""
    def __init__(self):
        self.peak, self.start, self.total, self.on = 0, None, None, True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        t0 = time.time()
        while self.on and time.time() - t0 < 6 * 3600:     # 중간에 멈춰도 6시간 뒤엔 스스로 끝나요
            try:
                v = gpu_live()
            except Exception:  # noqa: BLE001
                v = None
            if v:
                self.start = v["used_mb"] if self.start is None else self.start
                self.peak, self.total = max(self.peak, v["used_mb"]), v["total_mb"]
            time.sleep(2)

    def stop(self):
        self.on = False
        return {"peak_mb": self.peak, "start_mb": self.start, "total_mb": self.total} if self.total else None


def m3d_build(p, J):
    """3D 만들기: 사진 한 장(기본) 또는 AI 멀티뷰 보조 → 텍스처 입힌 GLB → (Blender) 크기·LOD·FBX/OBJ 묶음.
    언제나: 4방향 캡처(앞·왼쪽·오른쪽·뒤), 그물망 검사, (켜 두면) 원본 고밀도 메시. 비교를 켜면 단계별 결과(A~E)와 비교표도 남겨요."""
    sid = p.get("id")
    m = m3d_meta(sid)
    J["out_label"] = m.get("name") or ""                 # 결과 폴더 이름에 3D 이름을 붙여요
    d = M3D_DIR / sid
    J["_m3d_dir"] = str(d)
    o = m3d_opts(p, m)
    have = [s for s in M3D_SIDES if (d / f"view_{s}.png").is_file()]
    use = []
    if o["mode"] == "multi":
        asked = [s for s in have if s in (p.get("sides") or have)]
        if asked and not all(trellis_files(True).values()):
            use = asked                                    # 멀티뷰 모델이 없으면 검사할 것 없이 아래(m3d_need)에서 '모델이 필요해요'로 알리고 한 장으로
        else:
            use = m3d_mv_check(d, asked, J)
            if not use:
                warn(J, "AI 멀티뷰 보조로 쓸 수 있는 방향 그림이 없어 사진 한 장으로 만들었어요.")
    mv = bool(use)
    f, mv = m3d_need(mv, J, m3d_engine(p))
    if not mv:
        use = []
    imgs = {"front": Image.open(d / "view_front.png").convert("RGBA")}
    for sd in use:
        imgs[sd] = Image.open(d / f"view_{sd}.png").convert("RGBA")
    q = {"seed": seed_of(p)}
    stages = {}
    vram = M3dVram()
    try:
        glb = m3d_glb(imgs, mv, f, o, q["seed"], J, stages=stages)
    except BaseException:
        vram.stop()
        raise
    if J.get("m3d_photo_res"):
        J.setdefault("m3d_stats", {})["photo"] = J["m3d_photo_res"]
    engine = "Pixal3D 멀티뷰" if mv else "Pixal3D" if f.get("pixal") else "TRELLIS.2"
    base_info = {"kind": "3d", "photo": bool(J.get("m3d_photo")), "face": any(x.get("face") for x in J.get("m3d_photo") or []), "engine": engine, "views": ["front"] + use,
                 "mode": "multi" if mv else "single", "res": o["res"], "faces": o["faces"], "tex": o["tex"], "seed": q["seed"], "name": m["name"], "_sub": M3D_SUB}
    items = []
    if o["blender"] and blender3d.exe(ROOT):
        work = d / f"build_{uuid.uuid4().hex[:6]}"
        work.mkdir(parents=True, exist_ok=True)
        (work / "in.glb").write_bytes(glb)
        J["msg"], J["progress"] = "Blender 로 마무리하는 중 — 크기·LOD·내보내기", 0.95
        try:
            r = blender3d.finish(ROOT, work / "in.glb", work / "pack", {"name": m["name"], "height": o["height"], "rotate": o["rotate"],
                                                                         "lods": [1.0, 0.5, 0.2] if o["lods"] else [1.0], "formats": o["formats"],
                                                                         "rig": o["rig"]},
                                 lambda: J.get("cancel"))
            m3d_fix_pack(work / "pack")
            z = d / f"{m['name']}_game_{uuid.uuid4().hex[:4]}.zip"
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for x in sorted((work / "pack").rglob("*")):
                    if x.is_file() and x.name != "result.json" and not x.name.endswith("_rig_preview.glb"):   # 확인용 움직임은 묶음에 안 넣어요
                        zf.write(x, x.relative_to(work / "pack"))
            lod0 = work / "pack" / r["lods"][0].get("glb", "")
            info = {**base_info, "blender": r.get("blender"), "lods": r["lods"], "size_m": r["size_m"]}
            J.setdefault("m3d_stats", {}).update(lods=r["lods"], size_m=r["size_m"])
            rg = r.get("rig")
            if rg:
                info["rig"] = {k: rg.get(k) for k in ("bones", "pose", "legs")}
                pv = work / "pack" / str(rg.get("preview") or "")
                if rg.get("preview") and pv.is_file():                     # 확인용 움직임은 작업 폴더에만(결과 폴더를 어지럽히지 않게)
                    shutil.copyfile(pv, d / "rig_preview.glb")
                    rg["preview"] = f"/m3d/{sid}/rig_preview.glb?t={int(time.time())}"
                else:
                    rg.pop("preview", None)
                J["m3d_stats"]["rig"] = rg
                for w in rg.get("warn") or []:
                    warn(J, w)
            main = lod0.read_bytes() if lod0.is_file() and lod0.suffix == ".glb" else glb
            if main is not glb:
                stages["D"] = main
            items.append((main, info, ".glb"))
            items.append((z, {**info, "pack": True}, ".zip"))
            J["msg"] = f"3D 를 만들었어요 — LOD {len(r['lods'])}단계 · " + " / ".join(f"{x['tris']:,}면" for x in r["lods"])
        except InterruptedError:
            raise Cancelled("사용자가 중단했어요.") from None
        except Exception as e:  # noqa: BLE001
            warn(J, f"{e} — Blender 마무리 없이 ComfyUI 결과만 저장했어요.")
            items = []
        finally:
            shutil.rmtree(work, ignore_errors=True)       # 중간 파일(묶음 zip 에 다 들어 있어요)
    elif o["blender"]:
        warn(J, "Blender 가 없어 크기 맞추기·LOD·FBX 내보내기는 건너뛰었어요. 3D 만들기 화면에서 [Blender 설치]를 누르면 다음부터 해요.")
    if not items:
        items.append((glb, base_info, ".glb"))
        J["msg"] = f"3D 를 만들었어요 — 면 약 {o['faces']:,}개 · 텍스처 {o['tex']}px"
    final = items[0][0]
    done_msg = J["msg"]
    # E: 비교할 때, 사진 한 장으로 만들었고 방향 그림이 있으면 AI 멀티뷰로도 하나 더(같은 씨앗·설정, GPU 는 차례로)
    if o["compare"] and not mv and have:
        good = m3d_mv_check(d, have, J)
        try:
            if good and all(trellis_files(True).values()):
                fE, mvE = m3d_need(True, J, m3d_engine(p))
                if mvE:
                    imE = {"front": Image.open(d / "view_front.png").convert("RGBA"), **{sd: Image.open(d / f"view_{sd}.png").convert("RGBA") for sd in good}}
                    sE = {}
                    stages["E"] = m3d_glb(imE, True, fE, {**o, "compare": False, "keep_hi": False}, q["seed"], J, label="비교용 AI 멀티뷰(E) 만드는 중", stages=sE)
                    stages["_E"] = sE
            elif good:
                warn(J, "비교용 AI 멀티뷰(E)는 'Pixal3D 멀티뷰' 모델이 없어 건너뛰었어요.")
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            warn(J, f"비교용 AI 멀티뷰(E)를 만들지 못했어요({str(e)[:80]}).")
    # F: 비교할 때 같은 사진·씨앗으로 TRELLIS.2 도 하나 더(Pixal3D 로 만들었을 때만)
    if o["compare"] and (mv or f.get("pixal")):
        try:
            if all(trellis_files(False).values()):
                fF, _ = m3d_need(False, J, "trellis")
                sF = {}
                stages["F"] = m3d_glb({"front": Image.open(d / "view_front.png").convert("RGBA")}, False, fF, {**o, "compare": False, "keep_hi": False}, q["seed"], J,
                                      label="비교용 TRELLIS.2(F) 만드는 중", stages=sF)
                stages["_F"] = sF
            else:
                warn(J, "비교용 TRELLIS.2(F)는 TRELLIS.2 모델이 없어 건너뛰었어요.")
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            warn(J, f"비교용 TRELLIS.2(F)를 만들지 못했어요({str(e)[:80]}).")
    vr = vram.stop()
    if vr:
        J.setdefault("m3d_stats", {})["vram"] = vr
    # 팔다리 검사(사람) — 빠진 부위가 있으면 알려요. 비교할 때는 모양 단계마다 재서 어디서 사라졌는지도
    if m.get("kind") == "character":
        J["msg"] = "팔다리 검사 중"
        lb = m3d_limbs(stages, J, all_stages=o["compare"])
        if lb:
            J.setdefault("m3d_stats", {})["limbs"] = lb
            if lb["missing"]:
                where = {"hi": "3D 엔진이 모양을 처음 만들 때부터", "remesh": "그물망을 다시 짤 때", "dec": "면을 줄일 때", "A": "엔진 마지막 단계에서"}.get(lb["lost_at"] or "", "")
                warn(J, f"3D 에서 {', '.join(lb['missing'])}가 빠졌거나 많이 달라요{f'({where} 사라졌어요)' if where else ''}. "
                        "씨앗을 바꿔 다시 만들거나, 다리 사이가 보이는 사진·'단계별 결과·비교표 저장'으로 확인해 보세요.")
    # 검사·4방향 캡처
    J["msg"] = "그물망 검사·4방향 캡처 중"
    rep = m3d_check_mesh(final, m.get("kind"), J)
    if rep:
        J.setdefault("m3d_stats", {})["mesh"] = rep
    rows = [(M3D_STAGE[k][0], M3D_STAGE[k][1], stages[k]) for k in ("hi", "remesh", "dec", "A", "B", "C", "D", "E", "F") if stages.get(k)] if o["compare"] else [("최종 결과", "final", final)]
    try:
        if not (o["capture"] or o["compare"]):
            raise StopIteration
        bio = io.BytesIO()
        photoproj.sheet(rows, 320 if o["compare"] else 384).save(bio, "PNG")
        items.append((bio.getvalue(), {**base_info, "kind": "3d-views", "_tag": "비교표" if o["compare"] else "4방향",
                                       "stages": [r[0] for r in rows]}, ".png"))
    except StopIteration:
        pass
    except Exception as e:  # noqa: BLE001 — 캡처는 덤
        quiet_log("[3D 캡처 실패]", repr(e))
    if o["compare"]:
        st = []
        for k in ("remesh", "dec", "A", "B", "C", "E", "F"):
            if stages.get(k) and not (k == "C" and stages[k] is final):
                rk = m3d_check_mesh(stages[k], m.get("kind"), None) if k in ("remesh", "dec", "A", "E", "F") else None
                mt = None
                if k in ("A", "E", "F"):               # 엔진 결과가 사진과 맞는 정도(실루엣·얼굴 자리) — 멀티뷰·TRELLIS.2 와 숫자로 비교
                    src = stages if k == "A" else stages.get("_" + k) or {}
                    try:
                        mt = photoproj.engine_match(src.get("A", stages[k]), src.get("_front") or imgs["front"], J.get("_m3d_face"), src.get("_dist"),
                                                    photoproj.PIXAL_CAM if src.get("_pixal") else None)
                    except Exception as e:  # noqa: BLE001
                        quiet_log("[3D 단계 비교 실패]", repr(e))
                lk = None
                if k in ("E", "F") and m.get("kind") == "character":   # E·F 도 팔다리 검사(각자 카메라로)
                    lk = (m3d_limbs(stages.get("_" + k) or {}, J) or {}).get("stages", {}).get("A")
                elif k in ("remesh", "dec", "A"):
                    lk = ((J.get("m3d_stats") or {}).get("limbs") or {}).get("stages", {}).get(k)
                items.append((stages[k], {**base_info, "stage": k, "_tag": M3D_STAGE[k][2], "match": mt}, ".glb"))
                st.append({"stage": k, "name": M3D_STAGE[k][0], "mesh": rk, "match": mt, "limbs": lk})
        hi_l = ((J.get("m3d_stats") or {}).get("limbs") or {}).get("stages", {}).get("hi")
        if stages.get("hi"):
            st.insert(0, {"stage": "hi", "name": M3D_STAGE["hi"][0], "mesh": None, "match": None, "limbs": hi_l})
        J.setdefault("m3d_stats", {})["stages"] = st
    if stages.get("hi"):
        items.append((stages["hi"], {**base_info, "hi": True, "_tag": "원본고밀도"}, ".glb"))
    J["msg"] = done_msg
    m["builds"] = m.get("builds", 0) + 1
    m3d_save_meta(sid, m)
    return items


def m3d_quick(img, p, J):
    """'사진 → 3D 모델' 기능(이미지 기능 메뉴·대화 실행 모드)용 한 번에 만들기: 앞 사진 한 장, Blender 없이."""
    J2 = J
    m3d_prep({"image": img, "kind": p.get("kind") or "object"}, J2)
    sid = J2.pop("m3d")["id"]
    q = {"id": sid, "res": p.get("res") or 1024, "faces": p.get("faces") or 20000, "tex": p.get("tex") or 2048, "blender": p.get("blender") or "", "seed": p.get("seed", -1),
         "keep_hi": "", "capture": ""}                 # 빠른 3D(이미지 기능 메뉴)는 결과 하나만
    return m3d_build(q, J2)


def do_m3d(p, J):
    fn = {"prep": m3d_prep, "views": m3d_views, "tpose": m3d_tpose, "build": m3d_build, "scene": m3d_scene, "enlarge": m3d_enlarge_op}.get(p.get("op") or "")
    if not fn:
        raise ValueError("알 수 없는 3D 작업이에요.")
    return fn(p, J)
