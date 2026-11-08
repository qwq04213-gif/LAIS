# 로컬 AI 스튜디오 허브 — 3D 만들기 (사진 분석 → 여러 방향 그림 → TRELLIS.2/Pixal3D 로 텍스처 입힌 3D → 게임용 다듬기(ComfyUI) → Blender 마무리)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

import blender3d

M3D_DIR = ROOT / "m3d_work"
M3D_SUB = "3D"
M3D_SIDES = ("left", "back", "right")
M3D_SIDE_KO = {"front": "앞", "left": "왼쪽", "back": "뒤", "right": "오른쪽"}
M3D_SIDE_EN = {"left": "the left side (the camera moved 90 degrees to the subject's right, showing its left side)",
               "back": "the back (the camera moved 180 degrees around the subject)",
               "right": "the right side (the camera moved 90 degrees to the subject's left, showing its right side)"}
M3D_RES = (512, 1024, 1536)
M3D_FACES = (5000, 20000, 50000, 200000)
M3D_TEX = (1024, 2048, 4096)
M3D_KIND = {"character": {"faces": 20000, "height": 1.7}, "object": {"faces": 20000, "height": 0}, "big": {"faces": 50000, "height": 0}}


def trellis_files(multiview=False):
    """설치된 TRELLIS.2(또는 Pixal3D 멀티뷰) 파일. 빠진 게 있으면 값이 None."""
    dm, cv, va = files("diffusion_models"), files("clip_vision"), files("vae")
    low = str.lower
    if multiview:
        model = min((n for n in dm if "pixal3d_multiview" in low(n)), key=lambda n: ("int8" not in low(n), n), default=None)
        dino = next((n for n in cv if "dino_v3_l_naf" in low(n)), None)
    else:
        model = min((n for n in dm if re.search(r"trellis_?2", low(n))), key=lambda n: ("int8" not in low(n), n), default=None)
        dino = next((n for n in cv if "dino_v3_vit_l" in low(n)), None)
    return {"model": model, "dino": dino, "svae": next((n for n in va if "trellis_2_shape_vae" in low(n)), None),
            "tvae": next((n for n in va if "trellis_2_texture_vae" in low(n)), None)}


def m3d_ready():
    return {"trellis": all(trellis_files().values()), "multiview": all(trellis_files(True).values())}


def wf_fit(g):
    """엔진(ComfyUI)이 알려 준 노드 설명에 맞춰 그래프를 다듬어요: 모르는 칸은 빼고, 빠진 필수 칸은 기본값으로 채워요.
    ComfyUI 판마다 칸 이름이 조금씩 달라도 그래프가 깨지지 않게 하려는 안전장치예요."""
    info = caps().get("info") or {}
    for n in g.values():
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
    key = "normal"
    if not bgremove.have_ort() or not bgremove.installed(MODELS / "rmbg", key):
        r = rmbg_install({"key": key})
        if r.get("error") and "이미" not in r["error"]:
            raise RuntimeError(r["error"])
        raise RuntimeError(f"3D 로 만들려면 먼저 배경을 지워야 해요. 배경 지우기 모델(약 {bgremove.MODELS[key]['mb']}MB)을 받기 시작했어요. "
                           "설치와 모델의 진행 목록에서 끝난 걸 확인한 뒤 다시 눌러 주세요.")
    if J is not None:
        J["msg"] = "배경 지우는 중"
    return rmbg_engine(key).cut(img.convert("RGB"), None)


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
    if side < 384:
        out.append({"level": "warn", "text": f"물체 부분이 {side}px 로 작아요. 1024px 이상이면 좋아요(업스케일로 키워도 돼요)."})
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
    return out, {"w": W, "h": H, "box": [int(x0), int(y0), int(x1), int(y1)], "area": round(float(area), 3), "sharp": round(sharp, 1), "pieces": pieces}


def m3d_view(sid):
    m = m3d_meta(sid)
    d = M3D_DIR / sid
    url = lambda f: f"/m3d/{sid}/{f}?t={int((d / f).stat().st_mtime)}"   # noqa: E731
    slots = {s: (url(f"view_{s}.png") if (d / f"view_{s}.png").is_file() else None) for s in ("front",) + M3D_SIDES}
    return {**m, "id": sid, "slots": slots, "ready": m3d_ready(), "blender": blender3d.status(ROOT),
            "orig": url("orig.png") if (d / "orig.png").is_file() else None}


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
    if not re.fullmatch(r"(orig|view_(front|left|back|right))\.png", name or ""):
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
    for i, s in enumerate(sides):
        check_cancel(J)
        J["msg"], J["progress"] = f"{M3D_SIDE_KO[s]} 모습 그리는 중 ({i + 1}/{len(sides)})", i / len(sides)
        text = (f"Show {M3D_SIDE_EN[s]} of the same {what}. Keep exactly the same design, shape, proportions, colors, materials and details. "
                "Full body / whole object in frame, same scale, neutral standing pose kept, plain pure white background, soft even studio lighting, no shadow.")
        res = do_edit({"kind": "edit", "engine": "qwen", "image": src, "prompt": text, "seed": seed_of(p) + i, "fast": p.get("fast") or "", "translate": ""}, J)
        m3d_cut(res[0][0].convert("RGB"), J).save(d / f"view_{s}.png")
    m["views_made"] = sorted(set(m.get("views_made", [])) | set(sides))
    m3d_save_meta(sid, m)
    J["m3d"] = m3d_view(sid)
    J["msg"] = "여러 방향 그림을 만들었어요. 모양이 앞 사진과 다르면 빼고 3D 를 만들어 주세요."
    return []


def m3d_slot(p):
    """방향 칸에 내 사진 넣기(배경 자동 제거) · 비우기."""
    sid, s = p.get("id"), p.get("side")
    d = m3d_dir(sid)
    if s not in ("front",) + M3D_SIDES:
        return {"error": "알 수 없는 방향이에요."}
    f = d / f"view_{s}.png"
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
    return {"res": res if res in M3D_RES else 1024, "faces": faces if faces in M3D_FACES else 20000, "tex": tex if tex in M3D_TEX else 2048,
            "remesh": 512 if flag(p, "remesh", True) else 0, "blender": flag(p, "blender", True), "height": clamp(num(p, "height", kind["height"]), 0.0, 500.0),
            "rotate": int(num(p, "rotate", 0, int)) % 360 // 90 * 90, "lods": flag(p, "lods", True),
            "formats": [x for x in ("glb", "fbx", "obj") if flag(p, "fmt_" + x, x != "obj")] or ["glb"]}


def m3d_build(p, J):
    """3D 만들기: 사진(+고른 방향 그림) → 텍스처 입힌 게임용 GLB → (Blender) 크기·LOD·FBX/OBJ 묶음."""
    sid = p.get("id")
    m = m3d_meta(sid)
    d = M3D_DIR / sid
    o = m3d_opts(p, m)
    use = [s for s in M3D_SIDES if s in (p.get("sides") or []) and (d / f"view_{s}.png").is_file()]
    mv = bool(use)
    f = trellis_files(mv)
    if mv and not all(f.values()):
        warn(J, "여러 방향으로 만들려면 'Pixal3D 멀티뷰' 모델이 필요해요. 이번엔 앞 사진 한 장으로 만들었어요.")
        mv, use = False, []
        f = trellis_files(False)
    if not all(f.values()):
        names = {"model": "TRELLIS.2 모델", "dino": "DINOv3 이미지 인코더", "svae": "모양 VAE", "tvae": "텍스처 VAE"}
        raise RuntimeError("없는 파일: " + ", ".join(names[k] for k, v in f.items() if not v) + ". '설치와 모델' 탭의 3D 분류에서 'TRELLIS.2' 를 설치해 주세요.")
    need = ["Trellis2Conditioning", "Trellis2ShapeStage", "VaeDecodeShapeTrellis", "BakeTextureFromVoxel", "SaveGLB"] + (["Pixal3DMultiViewConditioning"] if mv else [])
    miss = [n for n in need if caps()["nodes"] and n not in caps()["nodes"]]
    if miss:
        raise RuntimeError("이 ComfyUI 에는 3D 노드(" + ", ".join(miss) + ")가 없어요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
    views = {"front": put_input(Image.open(d / "view_front.png"), J)}
    for s in use:
        views[s] = put_input(Image.open(d / f"view_{s}.png"), J)
    q = {"files": f, "views": views, "multiview": mv, "seed": seed_of(p), "steps": (12, 12, 12), "cfg": (7.5, 7.5, 1.0),
         "res": o["res"], "remesh": o["remesh"], "faces": o["faces"], "tex": o["tex"]}
    free_ollama()
    J["msg"] = f"3D 만드는 중 — 모양 {o['res']} · 면 {o['faces']:,}개 · 텍스처 {o['tex']}px (몇 분 걸려요)"
    res = run_wf(wf_fit(flows.wf_trellis(q)), J, raw=True)
    glb = next((dat for n, dat in res if n.lower().endswith(".glb")), None)
    if not glb:
        raise RuntimeError("3D 결과(GLB)를 받지 못했어요.")
    _clean_tmp(J)
    base_info = {"kind": "3d", "engine": "Pixal3D 멀티뷰" if mv else "TRELLIS.2", "views": ["front"] + use, "res": o["res"], "faces": o["faces"],
                 "tex": o["tex"], "seed": q["seed"], "name": m["name"], "_sub": M3D_SUB}
    items = []
    if o["blender"] and blender3d.exe(ROOT):
        work = d / f"build_{uuid.uuid4().hex[:6]}"
        work.mkdir(parents=True, exist_ok=True)
        (work / "in.glb").write_bytes(glb)
        J["msg"], J["progress"] = "Blender 로 마무리하는 중 — 크기·LOD·내보내기", 0.95
        try:
            r = blender3d.finish(ROOT, work / "in.glb", work / "pack", {"name": m["name"], "height": o["height"], "rotate": o["rotate"],
                                                                         "lods": [1.0, 0.5, 0.2] if o["lods"] else [1.0], "formats": o["formats"]},
                                 lambda: J.get("cancel"))
            z = d / f"{m['name']}_game_{uuid.uuid4().hex[:4]}.zip"
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for x in sorted((work / "pack").rglob("*")):
                    if x.is_file() and x.name != "result.json":
                        zf.write(x, x.relative_to(work / "pack"))
            lod0 = work / "pack" / r["lods"][0].get("glb", "")
            info = {**base_info, "blender": r.get("blender"), "lods": r["lods"], "size_m": r["size_m"]}
            J["m3d_stats"] = {"lods": r["lods"], "size_m": r["size_m"]}
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
    fn = {"prep": m3d_prep, "views": m3d_views, "build": m3d_build}.get(p.get("op") or "")
    if not fn:
        raise ValueError("알 수 없는 3D 작업이에요.")
    return fn(p, J)
