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


def m3d_vcheck(d):
    """방향 그림이 앞 사진과 맞는지 실루엣으로 어림해요 → {방향: {"ok": bool, "score": 0~1, "text"}}.
    뒤 = 앞을 좌우로 뒤집은 모양, 오른쪽 = 왼쪽을 좌우로 뒤집은 모양과 비슷해야 해요. 키(세로 길이) 비율도 봐요."""
    out = {}
    try:
        ims = {s: Image.open(d / f"view_{s}.png").convert("RGBA") for s in ("front",) + M3D_SIDES if (d / f"view_{s}.png").is_file()}
    except Exception:  # noqa: BLE001
        return out
    if "front" not in ims:
        return out
    f, fr = _sil(ims["front"], True)
    if "back" in ims and f is not None:
        b, br = _sil(ims["back"])
        sc = _iou(f, b) if b is not None else 0.0
        if b is not None and fr and br and not (0.7 < br / fr < 1.43):
            sc = min(sc, 0.4)
        out["back"] = {"score": round(sc, 2), "ok": sc >= M3D_VFIT,
                       "text": "앞모습과 실루엣이 잘 맞아요." if sc >= M3D_VFIT else "앞모습과 실루엣(자세·비율)이 많이 달라요. 다시 그리거나 체크를 풀어 주세요."}
    if "left" in ims and "right" in ims:
        lft, lr = _sil(ims["left"], True)
        rgt, rr = _sil(ims["right"])
        sc = _iou(lft, rgt) if lft is not None and rgt is not None else 0.0
        if lr and rr and not (0.7 < rr / lr < 1.43):
            sc = min(sc, 0.4)
        t = ("왼쪽·오른쪽 모습이 서로 거울처럼 잘 맞아요." if sc >= M3D_VFIT else
             "왼쪽·오른쪽 모습이 서로 맞지 않아요(방향이 뒤바뀌었거나 자세가 달라요). 다시 그리거나 체크를 풀어 주세요.")
        for s in ("left", "right"):
            out[s] = {"score": round(sc, 2), "ok": sc >= M3D_VFIT, "text": t}
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
            "proportions, colors, materials, details and viewing angle. Whole object in frame, plain pure white background, soft even lighting, no shadow, nothing else.")


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
    if max(img.size) > 2048:
        k = 2048 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), RS.LANCZOS)
    cut = m3d_cut(img, J)
    checks, stats = m3d_analyze(cut)
    sid = uuid.uuid4().hex[:12]
    d = M3D_DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(d / "orig.png")
    cut.save(d / "view_front.png")
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
                "Full body / whole object in frame, same height and scale as the reference, plain pure white background, soft even studio lighting, no shadow.")
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
        m["checks"], m["stats"] = m3d_analyze(img)
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
            "rig": flag(p, "rig", m.get("kind") == "character"), "photo": flag(p, "photo", True)}


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


def m3d_upscaler():
    """작은 사진을 키울 업스케일 모델: SeedVR2(복원까지) → 일반 업스케일 모델. 없으면 None."""
    sv = seedvr_names()
    return sv[0] if sv else (files("upscale_models") or [None])[0]


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
    return big, k


def m3d_glb(imgs, mv, f, o, seed, J, label=None):
    """사진(배경 지운 RGBA, {방향: 그림}) → ComfyUI TRELLIS.2/Pixal3D → 텍스처 입힌 GLB 바이트."""
    grown = []
    for sd in list(imgs):                              # 물체가 작게 나온 사진은 먼저 키워요(3D 모델은 물체를 1024px 로 봐요)
        imgs[sd], k = m3d_enlarge(imgs[sd], J)
        if k:
            grown.append(f"{M3D_SIDE_KO.get(sd, sd)} {k:g}배")
    if grown:
        warn(J, "물체 부분이 작아서 업스케일로 키워 만들었어요(" + ", ".join(grown) + ").")
    if mv:                                              # 멀티뷰: 모든 방향을 같은 배율로 맞춰서 넣어요
        fr = m3d_frame(imgs)
        views = {sd: put_input(fr[sd], J) for sd in imgs}
    else:
        views = {"front": put_input(imgs["front"], J)}
    # 단계 수(구조, 모양 512, 재질, 모양 올려 그리기)·cfg — 원본 TRELLIS.2 기본값
    nodes = caps()["nodes"]
    co = not nodes or "CFGOverride" in nodes
    q = {"files": f, "views": views, "multiview": mv, "pixal1": bool(f.get("pixal")) and not mv, "moge": f.get("moge"), "framed": mv, "seed": seed,
         "steps": (12, 20, 12, 12), "cfg": (7.5, 7.5, 1.0),
         "res": o["res"], "remesh": o["remesh"], "faces": o["faces"], "tex": o["tex"], "cfg_override": co}
    if not co:
        warn(J, "이 ComfyUI 에는 CFGOverride 노드가 없어서 원본 설정 일부(앞쪽 단계에만 가이드 걸기) 없이 만들었어요. "
                "ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 으로 업데이트하면 모양이 더 좋아져요.")
    free_ollama()
    J["msg"] = label or f"3D 만드는 중 — 모양 {o['res']} · 면 {o['faces']:,}개 · 텍스처 {o['tex']}px (몇 분 걸려요)"
    fixed = []
    res = run_wf(wf_fit(flows.wf_trellis(q), fixed), J, raw=True)
    if any(x.startswith("RemeshMesh.") for x in fixed):
        warn(J, "이 ComfyUI 는 '닫힌 몸체로 다시 짜기(solid)'를 몰라서 예전 방식(udf + 안쪽 껍질 지우기)으로 만들었어요. "
                "ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 으로 업데이트하면 더 고르게 나와요.")
    glb = next((dat for n, dat in res if n.lower().endswith(".glb")), None)
    if not glb:
        raise RuntimeError("3D 결과(GLB)를 받지 못했어요.")
    _clean_tmp(J)
    if o.get("photo", True):
        glb = m3d_photo(glb, imgs["front"], J)
    return glb


M3D_FACE_GOOD = 1024      # 얼굴 부분이 이보다 작으면 키워서 붙여요


def m3d_face(photo, J):
    """사진에서 얼굴을 찾아(MediaPipe) 그 부분을 업스케일로 키워요 → (x0, y0, x1, y1, 키운 그림) 또는 None.
    얼굴 찾기 모델·노드·업스케일 모델이 없거나, 얼굴이 없거나, 이미 충분히 크면 None."""
    model = next((n for n in files("detection") if "mediapipe_face" in n.lower()), None)
    nodes = caps()["nodes"]
    if not model or (nodes and not all(x in nodes for x in ("LoadMediaPipeFaceLandmarker", "MediaPipeFaceLandmarker", "MediaPipeFaceMask"))):
        J.setdefault("m3d_notes", []).append("face_model")
        return None
    k = min(1.0, 1536 / max(photo.size))
    small = photo.resize((max(1, round(photo.width * k)), max(1, round(photo.height * k))), RS.LANCZOS) if k < 1 else photo
    bg = Image.new("RGB", small.size, (128, 128, 128))
    bg.paste(small.convert("RGB"), mask=small.getchannel("A") if small.mode == "RGBA" else None)
    try:
        res = run_wf(flows.wf_face_mask(model, put_input(bg, J)), J, raw=True)
    except Exception as e:  # noqa: BLE001 — 얼굴 찾기는 덤이라 실패해도 3D 는 계속
        quiet_log("[3D 얼굴 찾기 실패]", repr(e))
        return None
    mk = next((dat for n, dat in res if n.lower().endswith(".png")), None)
    box = Image.open(io.BytesIO(mk)).convert("L").point(lambda v: 255 if v > 127 else 0).getbbox() if mk else None
    if not box:
        return None
    x0, y0, x1, y1 = (v / k for v in box)
    cx, cy, side = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) * 1.5
    x0, y0 = max(0, round(cx - side / 2)), max(0, round(cy - side / 2))
    x1, y1 = min(photo.width, round(cx + side / 2)), min(photo.height, round(cy + side / 2))
    side = max(x1 - x0, y1 - y0)
    if side >= M3D_FACE_GOOD or side < 24:
        return None
    up = m3d_upscaler()
    if not up:
        warn(J, f"얼굴 부분이 {side}px 로 작아요. '설치와 모델'에서 업스케일 모델(SeedVR2 또는 Real-ESRGAN)을 받으면 얼굴을 키워서 더 선명하게 붙여요.")
        return None
    J["msg"] = f"얼굴 부분을 키우는 중 ({side}px → 약 {min(4 * side, 1536)}px)"
    crop = photo.crop((x0, y0, x1, y1)).convert("RGB")
    big = upscale(crop, J, up, round(min(4.0, 1536 / side), 2))
    return (x0, y0, x1, y1, big)


def m3d_photo(glb, photo, J):
    """사진 붙이기: 3D 엔진이 다시 칠한 색 대신 앞 사진의 화소를 그대로 붙여요(얼굴·무늬가 사진처럼). 안 맞으면 원래 색 그대로."""
    face = None
    try:
        face = m3d_face(photo, J)
    except Exception as e:  # noqa: BLE001
        quiet_log("[3D 얼굴 키우기 실패]", repr(e))
    J["msg"] = "사진을 3D 에 붙이는 중 — 얼굴·무늬를 사진 그대로"
    try:
        new, info = photoproj.project(glb, photo, face, log=quiet_log)
    except ValueError as e:              # 붙일 수 없는 모양(텍스처 없음 등) — 원래 색 그대로
        quiet_log("[3D 사진 붙이기 건너뜀]", e)
        return glb
    except Exception as e:  # noqa: BLE001
        quiet_log("[3D 사진 붙이기 실패]", repr(e))
        warn(J, f"사진 붙이기를 하지 못해 3D 엔진이 칠한 색 그대로예요({str(e)[:80]}).")
        return glb
    if info.get("skip") == "shape":
        warn(J, f"사진과 3D 모양이 충분히 겹치지 않아(겹침 {info['iou']:.0%}) 사진 붙이기는 건너뛰었어요. 어긋나게 붙으면 번져 보여서요.")
        return glb
    if info.get("skip"):
        return glb
    J.setdefault("m3d_photo", []).append(info)
    if "face_model" in (J.get("m3d_notes") or []) and not J.get("_face_noted"):
        J["_face_noted"] = 1
        warn(J, "얼굴 찾기 모델이 없어 얼굴 확대는 건너뛰었어요. '설치와 모델'의 3D 분류에서 '얼굴 찾기(MediaPipe)'를 받으면 얼굴이 더 선명해져요.")
    return new


def m3d_build(p, J):
    """3D 만들기: 사진(+고른 방향 그림) → 텍스처 입힌 게임용 GLB → (Blender) 크기·LOD·FBX/OBJ 묶음."""
    sid = p.get("id")
    m = m3d_meta(sid)
    d = M3D_DIR / sid
    o = m3d_opts(p, m)
    use = [s for s in M3D_SIDES if s in (p.get("sides") or []) and (d / f"view_{s}.png").is_file()]
    mv = bool(use)
    f, mv = m3d_need(mv, J, m3d_engine(p))
    if not mv:
        use = []
    imgs = {"front": Image.open(d / "view_front.png").convert("RGBA")}
    for sd in use:
        imgs[sd] = Image.open(d / f"view_{sd}.png").convert("RGBA")
    q = {"seed": seed_of(p)}
    glb = m3d_glb(imgs, mv, f, o, q["seed"], J)
    base_info = {"kind": "3d", "photo": bool(J.get("m3d_photo")), "face": any(x.get("face") for x in J.get("m3d_photo") or []), "engine": "Pixal3D 멀티뷰" if mv else "Pixal3D" if f.get("pixal") else "TRELLIS.2", "views": ["front"] + use, "res": o["res"], "faces": o["faces"],
                 "tex": o["tex"], "seed": q["seed"], "name": m["name"], "_sub": M3D_SUB}
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
            z = d / f"{m['name']}_game_{uuid.uuid4().hex[:4]}.zip"
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for x in sorted((work / "pack").rglob("*")):
                    if x.is_file() and x.name != "result.json" and not x.name.endswith("_rig_preview.glb"):   # 확인용 움직임은 묶음에 안 넣어요
                        zf.write(x, x.relative_to(work / "pack"))
            lod0 = work / "pack" / r["lods"][0].get("glb", "")
            info = {**base_info, "blender": r.get("blender"), "lods": r["lods"], "size_m": r["size_m"]}
            J["m3d_stats"] = {"lods": r["lods"], "size_m": r["size_m"]}
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
            items.append((lod0.read_bytes() if lod0.is_file() and lod0.suffix == ".glb" else glb, info, ".glb"))
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
    m["builds"] = m.get("builds", 0) + 1
    m3d_save_meta(sid, m)
    return items


def m3d_quick(img, p, J):
    """'사진 → 3D 모델' 기능(이미지 기능 메뉴·대화 실행 모드)용 한 번에 만들기: 앞 사진 한 장, Blender 없이."""
    J2 = J
    m3d_prep({"image": img, "kind": p.get("kind") or "object"}, J2)
    sid = J2.pop("m3d")["id"]
    q = {"id": sid, "res": p.get("res") or 1024, "faces": p.get("faces") or 20000, "tex": p.get("tex") or 2048, "blender": p.get("blender") or "", "seed": p.get("seed", -1)}
    return m3d_build(q, J2)


def do_m3d(p, J):
    fn = {"prep": m3d_prep, "views": m3d_views, "tpose": m3d_tpose, "build": m3d_build, "scene": m3d_scene, "enlarge": m3d_enlarge_op}.get(p.get("op") or "")
    if not fn:
        raise ValueError("알 수 없는 3D 작업이에요.")
    return fn(p, J)
