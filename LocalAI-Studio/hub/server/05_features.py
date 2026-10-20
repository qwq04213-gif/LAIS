# 로컬 AI 스튜디오 허브 — 기타 기능 (확장·비교표·크기·색·배경·보정·얼굴 교체·참고 이미지)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

# ───────────────────────── 기타 기능 (초보자용 템플릿) ─────────────────────────
FEATURES = json.loads((HUB / "features.json").read_text(encoding="utf-8"))


def features():
    """기능 목록 + 지금 쓸 수 있는지(필요한 노드·모델) 표시."""
    nodes = caps()["nodes"]
    out = []
    for f in FEATURES:
        need = f.get("needs", {})
        miss_nodes = [n for n in need.get("nodes", []) if nodes and n not in nodes]
        miss_lists = [k for k in need.get("lists", []) if not (lists().get(k))]
        out.append({**f, "missing_nodes": miss_nodes, "missing_lists": miss_lists})
    return out


def _dim8(v, lo=0, hi=2048):
    return int(clamp(num({"v": v}, "v", 0, int), lo, hi) // 8 * 8)


def feat_outpaint(p, J):
    img = load_img(p["image"])
    pad = [_dim8(p.get(k), 0, 1024) for k in ("left", "top", "right", "bottom")]
    if not any(pad):
        raise ValueError("늘릴 방향의 픽셀 수를 하나 이상 적어 주세요.")
    tw, th = img.width + pad[0] + pad[2], img.height + pad[1] + pad[3]
    s = min(1.0, (1.6e6 / (tw * th)) ** 0.5)      # 너무 크면 줄여서 처리해요
    if s < 1.0:
        img = img.resize((max(64, round(img.width * s)), max(64, round(img.height * s))), RS.LANCZOS)
        pad = [int(round(v * s / 8) * 8) for v in pad]
        warn(J, f"이미지가 커서 {s:.0%} 크기로 줄여 처리했어요.")
    rng = random.Random(num(p, "seed", -1, int))
    feather = int(clamp(num(p, "feather", 40, int), 0, 200))
    fam, p2 = fx_sel(p)
    if fam:      # FLUX·Krea·Krea 2·Chroma 모델로 확장 (단계 수·CFG 는 그 모델에 맞는 값을 써요)
        text, tags = prep(p2, J, "caption", rng)
        fq = flux_q(p2, J, fam, text, tags, seed_of(p))
        J["msg"] = "빈 공간을 그리는 중"
        g = flows.wf_flux_outpaint(fq, put_input(img, J), pad, feather)
        info_fn = lambda r: flux_info(fq, r, "feat-outpaint", Outpaint="/".join(map(str, pad)))
    else:
        q = sd(p, *prep(p, J, "tags", rng), J)
        J["msg"] = "빈 공간을 그리는 중"
        g = flows.wf_outpaint(q, put_input(img, J), pad, feather)
        info_fn = lambda r: info_sd(q, r.size, "feat-outpaint", **{"Outpaint": "/".join(map(str, pad))})
    res = run_wf(g, J)[0]
    inner = Image.new("L", img.size, 255)    # 원본 부분은 그대로 되돌려요(이음새만 부드럽게)
    if feather:
        inner = ImageChops.multiply(inner, Image.new("L", img.size, 255))
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).rectangle((feather // 2, feather // 2, img.width - feather // 2, img.height - feather // 2), fill=255)
        inner = m.filter(ImageFilter.GaussianBlur(max(1, feather / 3)))
        for side, edge in ((0, pad[0]), (1, pad[1]), (2, pad[2]), (3, pad[3])):   # 확장하지 않은 쪽 가장자리는 끝까지 원본
            if edge == 0:
                box = [(0, 0, feather, img.height), (0, 0, img.width, feather), (img.width - feather, 0, img.width, img.height), (0, img.height - feather, img.width, img.height)][side]
                ImageDraw.Draw(inner).rectangle(box, fill=255)
    res.paste(img, (pad[0], pad[1]), inner)
    return [(res, info_fn(res), g)]


def feat_regional(p, J):
    texts = [(p.get("r1") or "").strip(), (p.get("r2") or "").strip(), (p.get("r3") or "").strip()]
    layout = p.get("layout") if p.get("layout") in ("lr", "tb", "lcr") else "lr"
    n = 3 if layout == "lcr" else 2
    if not all(texts[:n]):
        raise ValueError(f"{n}개 칸의 내용을 모두 적어 주세요.")
    for t in texts[:n]:
        if blocked(t):
            raise ValueError(BLOCK_MSG)
    boxes = {"lr": [(0, 0, .5, 1), (.5, 0, .5, 1)], "tb": [(0, 0, 1, .5), (0, .5, 1, .5)],
             "lcr": [(0, 0, 1 / 3, 1), (1 / 3, 0, 1 / 3, 1), (2 / 3, 0, 1 / 3, 1)]}[layout]
    tags = []        # 칸마다 적은 <lora:이름:강도> 태그도 읽어서(그림 전체에) 적용해요. 칸 글에는 태그가 남지 않게 지워요.

    def grab(m):
        tags.append((m.group(1).strip(), float(m.group(2) or 1)))
        return ""
    texts = [re.sub(r"[ \t]{2,}", " ", LORA_TAG.sub(grab, t)).strip(" ,\n") for t in texts]
    if not all(texts[:n]):
        raise ValueError(f"{n}개 칸에 그릴 내용을 적어 주세요(LoRA 태그만 있으면 안 돼요).")
    regs = [dict(text=t, x=b[0], y=b[1], w=b[2], h=b[3]) for t, b in zip(texts[:n], boxes)]
    rng = random.Random(num(p, "seed", -1, int))
    p2 = dict(p, prompt=(p.get("common") or "").strip() or "best quality")
    ctext, ctags = prep(p2, J, "tags", rng)
    q = sd(p2, ctext, ctags + tags, J)
    w, h = _dim8(p.get("w") or 1216, 512, 2048), _dim8(p.get("h") or 832, 512, 2048)
    J["msg"] = "칸을 나눠 그리는 중"
    g = flows.wf_regional(q, regs, w, h)
    res = run_wf(g, J)[0]
    return [(res, info_sd(q, res.size, "feat-regional", **{"Regions": " | ".join(texts[:n])}), g)]


COMPARE_AXES = {"cfg": float, "steps": int, "clip_skip": int, "sampler": str, "scheduler": str}


def _vals(text, axis, limit):
    out = []
    for v in re.split(r"[,\n]", text or ""):
        v = v.strip()
        if not v:
            continue
        try:
            out.append(COMPARE_AXES[axis](v))
        except (ValueError, KeyError):
            raise ValueError(f"'{v}' 는 {axis} 값으로 쓸 수 없어요.")
    return out[:limit]


def feat_compare(p, J):
    ax1 = p.get("axis") if p.get("axis") in COMPARE_AXES else "cfg"
    ax2 = p.get("axis2") if p.get("axis2") in COMPARE_AXES and p.get("axis2") != ax1 else ""
    v1 = _vals(p.get("values") or "3,5,7,9", ax1, 6)
    v2 = _vals(p.get("values2"), ax2, 4) if ax2 else [None]
    if len(v1) < 2:
        raise ValueError("가로 값을 쉼표로 2개 이상 적어 주세요. 예: 3,5,7")
    if not v2:
        v2 = [None]
    rng = random.Random(num(p, "seed", -1, int))
    base = sd(*((p,) + prep(p, J, "tags", rng) + (J,)))
    base["seed"] = seed_of(p)
    w, h = _dim8(p.get("w") or 832, 512, 1536), _dim8(p.get("h") or 1216, 512, 1536)
    base.update(w=w, h=h)
    cells, total = [], len(v1) * len(v2)
    for ri, b2 in enumerate(v2):
        for ci, a1 in enumerate(v1):
            q = dict(base)
            q[ax1] = a1
            if ax2:
                q[ax2] = b2
            J["msg"], J["pi"], J["pn"] = f"비교표 만드는 중 ({ri * len(v1) + ci + 1}/{total})", ri * len(v1) + ci, total
            cells.append(run_wf(flows.wf_gen(q), J)[0])
    tw = min(480, w)
    th = round(h * tw / w)
    pad, head = 6, 28
    left = head if ax2 else 0
    grid = Image.new("RGB", (left + len(v1) * (tw + pad) + pad, head + len(v2) * (th + pad) + pad), (24, 24, 27))
    d = ImageDraw.Draw(grid)
    for ci, a1 in enumerate(v1):
        d.text((left + pad + ci * (tw + pad) + 4, 8), f"{ax1}={a1}", fill=(230, 230, 235))
    for ri, b2 in enumerate(v2):
        if ax2:
            d.text((4, head + pad + ri * (th + pad) + 4), f"{ax2}={b2}"[:10], fill=(230, 230, 235))
        for ci in range(len(v1)):
            grid.paste(cells[ri * len(v1) + ci].resize((tw, th), RS.LANCZOS), (left + pad + ci * (tw + pad), head + pad + ri * (th + pad)))
    info = dict(kind="feat-compare", prompt=base["prompt"], negative=base["negative"], steps=base["steps"], cfg=base["cfg"],
                sampler=base["sampler"], scheduler=base["scheduler"], seed=base["seed"], w=w, h=h, model=base["ckpt"],
                loras=[[n, x] for n, x in base["loras"]], extra={"Compare": f"{ax1}={v1}" + (f" / {ax2}={v2}" if ax2 else "")})
    return [(grid, info, None)]


def resize_steps(img, p):
    """크기 바꾸기 · 비율대로 자르기 · 회전/뒤집기. (이미지, 한 일 목록) 을 돌려줘요."""
    steps = []
    ratio = p.get("crop") or "none"
    if ratio != "none":
        a, b = (int(x) for x in ratio.split(":"))
        w, h = img.size
        if w * b > h * a:      # 너무 넓음 → 좌우를 잘라요
            nw = round(h * a / b)
            x = {"left": 0, "right": w - nw}.get(p.get("anchor"), (w - nw) // 2)
            img = img.crop((x, 0, x + nw, h))
        else:
            nh = round(w * b / a)
            y = {"top": 0, "bottom": h - nh}.get(p.get("anchor"), (h - nh) // 2)
            img = img.crop((0, y, w, y + nh))
        steps.append(f"{ratio} 로 자름")
    rot = {"90": -90, "180": 180, "270": 90}.get(str(p.get("rotate")))
    if rot:
        img = img.rotate(rot, expand=True)
        steps.append(f"{p.get('rotate')}° 회전")
    if p.get("flip") == "h":
        img, _ = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT), steps.append("좌우 뒤집기")
    elif p.get("flip") == "v":
        img, _ = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM), steps.append("상하 뒤집기")
    long_side = clamp(num(p, "long_side", 0, int), 0, 8192)
    if long_side:
        s = long_side / max(img.size)
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), RS.LANCZOS)
        steps.append(f"긴 변 {long_side}px")
    return img, steps


def feat_rmbg(p, J):
    """배경 지우기: 사람·물체만 남기고 배경을 투명(또는 고른 색)으로. ComfyUI 없이 바로 처리해요."""
    key = p.get("rmodel") if p.get("rmodel") in bgremove.MODELS else "normal"
    if not bgremove.have_ort() or not bgremove.installed(MODELS / "rmbg", key):
        r = rmbg_install({"key": key})
        label = bgremove.MODELS[key]["label"]
        if r.get("error") and "이미" not in r["error"]:
            raise RuntimeError(r["error"])
        raise RuntimeError(f"배경 지우기 모델({label}, 약 {bgremove.MODELS[key]['mb']}MB)을 받기 시작했어요. 설치와 모델의 진행 목록에서 끝난 걸 확인한 뒤 다시 눌러 주세요.")
    img = load_img(p["image"])
    bg = str(p.get("bg") or "transparent")
    color = {"white": (255, 255, 255), "black": (0, 0, 0)}.get(bg)
    if bg == "custom":
        m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(p.get("bgcolor") or "").strip())
        color = tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if m else (255, 255, 255)
    J["msg"] = "배경 지우는 중"
    res = rmbg_engine(key).cut(img, color)
    if p.get("crop") and res.mode == "RGBA":      # 남은 부분에 맞춰 빈 테두리 잘라내기
        box = res.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        if box:
            res = res.crop(box)
    return [(res, dict(kind="feat-rmbg", model=key, background=bg, w=res.width, h=res.height), None)]


def feat_resize(p, J):
    """크기 바꾸기 · 비율대로 자르기 · 회전/뒤집기 (ComfyUI 없이 바로 처리해요)."""
    img, steps = resize_steps(load_img(p["image"]).convert("RGB"), p)
    if not steps:
        raise ValueError("하나 이상 골라 주세요. (자를 비율, 회전, 뒤집기, 긴 변 크기)")
    return [(img, dict(kind="feat-resize", extra={"Edit": ", ".join(steps)}), None)]


def feat_color(p, J):
    """밝기·대비·채도·선명도·흐림 보정 (ComfyUI 없이 바로 처리해요)."""
    from PIL import ImageEnhance
    img = load_img(p["image"]).convert("RGB")
    vals = {k: clamp(num(p, k, 100), 0, 300) for k in ("bright", "contrast", "sat", "sharp")}
    for key, cls in (("bright", ImageEnhance.Brightness), ("contrast", ImageEnhance.Contrast), ("sat", ImageEnhance.Color), ("sharp", ImageEnhance.Sharpness)):
        if abs(vals[key] - 100) > 0.5:
            img = cls(img).enhance(vals[key] / 100)
    blur = clamp(num(p, "blur", 0), 0, 50)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if all(abs(v - 100) <= 0.5 for v in vals.values()) and not blur:
        raise ValueError("바꿀 값을 하나 이상 조절해 주세요. (100은 원래 그대로예요)")
    return [(img, dict(kind="feat-color", extra={"Adjust": f"밝기 {vals['bright']:.0f} 대비 {vals['contrast']:.0f} 채도 {vals['sat']:.0f} 선명도 {vals['sharp']:.0f} 흐림 {blur:.0f}"}), None)]


def fill_node(node, given):
    """ComfyUI 노드의 필수 입력을 /object_info 에서 읽어, 내가 준 값(given)은 그대로 쓰고 나머지는 기본값으로 채워요.
    (확장 노드는 버전마다 입력이 달라서, 이름을 외워 두지 않고 설치된 노드에 맞춰요.)"""
    ins = dict(given)
    spec_all = (caps()["info"].get(node) or {}).get("input", {})
    for k, spec in {**(spec_all.get("required") or {})}.items():
        if k in ins or not isinstance(spec, list) or not spec:
            continue
        t, o = spec[0], (spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {})
        if t == "COMBO":
            opts = o.get("options") or []
            ins[k] = o.get("default", opts[0] if opts else "")
        elif isinstance(t, list):
            ins[k] = t[0] if t else ""
        elif "default" in o:
            ins[k] = o["default"]
        elif t == "BOOLEAN":
            ins[k] = True
        elif t == "STRING":
            ins[k] = ""
    return ins


def combo_opts(node, key):
    """노드 입력 한 칸이 고르기(콤보)일 때 선택지 목록 (없으면 빈 목록)."""
    spec = ((caps()["info"].get(node) or {}).get("input", {}).get("required") or {}).get(key)
    if not isinstance(spec, list) or not spec:
        return []
    if isinstance(spec[0], list):
        return spec[0]
    if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
        return spec[1].get("options") or []
    return []


def feat_detailer(p, J):
    """얼굴·손 자동 보정. 감지 모델을 /object_info 에서 찾아 부위별로 FaceDetailer 를 이어 붙여요."""
    img = load_img(p["image"]).convert("RGB")
    if max(img.size) > 2048:
        k = 2048 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), RS.LANCZOS)
    dets = combo_opts("UltralyticsDetectorProvider", "model_name")
    target = p.get("target") if p.get("target") in ("face", "hand", "both") else "face"
    base = {"face": "detailed face, beautiful detailed eyes", "hand": "detailed hands, five fingers"}
    user = (p.get("prompt") or "").strip()
    passes = []
    for part in (("face", "hand") if target == "both" else (target,)):
        det = next((d for d in dets if part in d.lower() and d.lower().startswith("bbox")), None) or next((d for d in dets if part in d.lower()), None)
        if not det:
            raise RuntimeError(f"{'얼굴' if part == 'face' else '손'}을 찾는 감지 모델이 없어요. '설치와 모델' 탭의 "
                               f"'{'얼굴' if part == 'face' else '손'} 감지 모델'을 설치한 뒤 ComfyUI 를 다시 시작해 주세요.")
        passes.append((det, (base[part] + (", " + user if user else "")).strip()))
    for _, t in passes:
        if blocked(t):
            raise ValueError(BLOCK_MSG)
    fam, p2 = fx_sel(p)
    if fam:      # FLUX.1 · Krea · Krea 2 · Chroma 모델로 다시 그리기 (단계 수·CFG 는 그 모델에 맞는 값)
        fq = flux_q(p2, J, fam, passes[0][1], [], seed_of(p))
        fq["denoise"] = clamp(num(p, "denoise", 0.5), 0.1, 0.8)
        J["msg"] = "얼굴·손 찾아서 다시 그리는 중"
        g = flows.wf_detailer_flux(fq, put_input(img, J), passes, fill_node)
        res = run_wf(g, J)[0]
        return [(res, flux_info(fq, res, "feat-detailer", Detailer=" + ".join(d for d, _ in passes), Denoise=fq["denoise"]), g)]
    q = sd(dict(p, denoise=clamp(num(p, "denoise", 0.5), 0.1, 0.8)), passes[0][1], [], J)
    q["seed"] = seed_of(p)
    J["msg"] = "얼굴·손 찾아서 다시 그리는 중"
    g = flows.wf_detailer(q, put_input(img, J), passes, fill_node)
    res = run_wf(g, J)[0]
    return [(res, info_sd(q, res.size, "feat-detailer", Detailer=" + ".join(d for d, _ in passes)), g)]


# ───────────────────────── 얼굴 교체 모델(inswapper) 직접 받기 ─────────────────────────
SWAP_URL = "https://huggingface.co/datasets/Gourieff/ReActor/resolve/main/models/inswapper_128.onnx"
SWAP_MIN = 100 << 20
SWAP_JOB = {"state": "", "msg": ""}


def swap_file():
    return MODELS / "insightface" / "inswapper_128.onnx"


def swap_status():
    f = swap_file()
    have = f.is_file() and f.stat().st_size >= SWAP_MIN
    try:
        listed = bool(combo_opts("ReActorFaceSwap", "swap_model"))
    except Exception:
        listed = False
    deps = [{"module": m, "pip": REACTOR_MODS[m]} for m in mods_missing(REACTOR_MODS)] if _repo_dir(REACTOR_REPO).is_dir() else []
    return {"deps_missing": deps, "file": have, "listed": listed, "size": f.stat().st_size if have else 0, "state": SWAP_JOB["state"], "msg": SWAP_JOB["msg"],
            "pack": _pack_done(REACTOR_REPO), "path": str(f)}


def _swap_run():
    J = SWAP_JOB
    try:
        f = swap_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        part = f.with_name(f.name + ".part")
        for _try in range(3):
            have = part.stat().st_size if part.exists() else 0
            rq = urllib.request.Request(SWAP_URL, headers={"User-Agent": "LocalAI-Studio", **({"Range": f"bytes={have}-"} if have else {})})
            try:
                with urllib.request.urlopen(rq, timeout=60) as r:
                    code = getattr(r, "status", 200)
                    if have and code != 206:
                        have = 0
                    total = int(r.headers.get("Content-Length") or 0) + have
                    with open(part, "ab" if have else "wb") as o:
                        done = have
                        while True:
                            c = r.read(1 << 20)
                            if not c:
                                break
                            o.write(c)
                            done += len(c)
                            J["msg"] = f"받는 중… {done >> 20}MB" + (f" / {total >> 20}MB" if total else "")
                if total and part.stat().st_size < total:
                    continue
                break
            except urllib.error.HTTPError as e:
                if e.code == 416:       # 이미 다 받은 상태
                    break
                raise
        if not part.exists() or part.stat().st_size < SWAP_MIN:
            raise RuntimeError("받은 파일이 너무 작아요. 인터넷 연결을 확인하고 다시 눌러 주세요.")
        os.replace(part, f)
        J["state"], J["msg"] = "done", "받았어요. [이미지 엔진 다시 시작]을 눌러야 목록에 나타나요."
        _CAPS["t"] = 0
    except Exception as e:  # noqa: BLE001
        J["state"], J["msg"] = "error", f"받지 못했어요: {e}. 같은 버튼을 다시 누르면 이어서 받아요. (huggingface.co 에 접속할 수 있는지 확인해 주세요.)"
        log("[얼굴 교체 모델 받기 오류]", repr(e))


def swap_download():
    if SWAP_JOB["state"] == "running":
        return {"ok": True}
    if swap_status()["file"]:
        return {"error": "이미 받아 둔 모델이 있어요. 목록에 안 나오면 [이미지 엔진 다시 시작]을 눌러 주세요."}
    SWAP_JOB.update(state="running", msg="시작해요…")
    threading.Thread(target=_swap_run, daemon=True).start()
    return {"ok": True}


def feat_faceswap(p, J):
    """얼굴 교체(ReActor). 사진 속 얼굴을 다른 사진의 얼굴로 바꿔요. (본인·허락받은 성인·성인 가상 인물만: 처음 시작할 때 안내)"""
    if not p.get("image") or not p.get("source"):
        raise ValueError("얼굴을 바꿀 사진과, 가져올 얼굴 사진을 둘 다 올려 주세요.")
    if mods_missing(REACTOR_MODS):      # 설치 때 pip 가 조용히 실패한 부품(예: onnx)이 있으면 지금 채워 넣어요
        J["msg"] = "빠진 부품을 설치하는 중…(처음 한 번, 몇 분 걸릴 수 있어요)"
        bad = ensure_mods(REACTOR_MODS, J)
        if bad:
            raise RuntimeError("얼굴 교체에 필요한 파이썬 부품을 설치하지 못했어요 — " + " / ".join(f"{p}: {e}" for p, e in bad)[:400] + " (자세한 내용: logs\\nodes.log). 인터넷 연결을 확인하고 다시 시도해 주세요.")
    swaps = combo_opts("ReActorFaceSwap", "swap_model")
    if not swaps:
        if swap_file().is_file() and swap_file().stat().st_size >= SWAP_MIN:
            raise RuntimeError("얼굴 교체 모델 파일은 있는데 엔진이 아직 못 봤어요. 이 화면의 [이미지 엔진 다시 시작]을 눌러 주세요.")
        raise RuntimeError("얼굴 교체 모델(inswapper_128.onnx)이 아직 없어요. 이 화면의 [모델 받기] 버튼으로 받은 뒤 [이미지 엔진 다시 시작]을 눌러 주세요.")
    swap = next((x for x in swaps if x.lower().startswith("inswapper")), swaps[0])
    rests = combo_opts("ReActorFaceSwap", "face_restore_model")
    want = {"gfpgan": "gfpganv1.4", "codeformer": "codeformer", "none": "none"}.get(p.get("restore") or "gfpgan", "gfpganv1.4")
    rest = next((x for x in rests if x.lower().startswith(want)), "none" if "none" in rests else (rests[0] if rests else "none"))
    idx = lambda k: (str(p.get(k) or "0").replace(" ", "") if re.fullmatch(r"\d+(,\d+)*", str(p.get(k) or "0").replace(" ", "")) else "0")
    tgt, src = load_img(p["image"]).convert("RGB"), load_img(p["source"]).convert("RGB")
    for im in (tgt, src):
        if max(im.size) > 4096:
            raise ValueError("사진이 너무 커요(긴 변 4096px 이하). 줄여서 올려 주세요.")
    J["msg"] = "얼굴 찾아서 바꾸는 중"
    g = flows.wf_faceswap(put_input(tgt, J), put_input(src, J), swap, rest, clamp(num(p, "vis", 1.0), 0.1, 1.0), clamp(num(p, "cf", 0.5), 0.0, 1.0),
                          idx("target_face"), idx("source_face"), fill_node)
    res = run_wf(g, J)[0]
    if res.getbbox() is None or not res.convert("L").getextrema()[1]:
        raise RuntimeError("결과가 비어 있어요. 안전 검사에서 걸러졌거나, 사진에서 얼굴을 찾지 못한 거예요. 다른 사진으로 해 보세요.")
    return [(res, dict(kind="feat-faceswap", extra={"FaceSwap": f"{swap} + {rest}"}), g)]


REF_STYLE = "Keep the same art style, color palette, lighting and mood as the reference image. "
REF_FACE = "Keep the exact same person from the reference image: the same face, hairstyle and identity. "


def pick_file(names, *pats):
    """파일 이름 목록에서 패턴(정규식)에 처음 맞는 것을 골라요."""
    for pat in pats:
        for n in names:
            if re.search(pat, n, re.I):
                return n
    return None


def feat_reference_fx(p, p2, fam, ref, mode, J):
    """FLUX.1 · Krea 2 모델로 참고 이미지를 따라 그리기. 모델 종류마다 쓰는 방법이 달라요.
    Krea 2 : 공식 '스타일 참조' LoRA / FLUX Kontext : 참고 이미지를 조건(ReferenceLatent)으로 / 그 밖의 FLUX.1 : Redux."""
    if fam == "chroma":
        raise ValueError("Chroma 모델은 참고 이미지로 그리는 방법이 아직 없어요. FLUX.1 · Krea 2 · SDXL 모델을 골라 주세요.")
    w, h = (clamp(num(p, k, 1024, int) // 16 * 16, 256, 2048) for k in ("w", "h"))
    rng = random.Random(num(p, "seed", -1, int))
    text, tags = prep(p2, J, "caption", rng)
    weight = clamp(num(p, "weight", 1.0), 0.1, 2.0)
    name = put_input(ref, J)
    if fam == "krea2":
        for n in ("TextEncodeQwenImageEditPlus", "FluxKontextMultiReferenceLatentMethod", "ModelSamplingFlux"):
            if caps()["nodes"] and n not in caps()["nodes"]:
                raise RuntimeError(f"이 ComfyUI 에는 노드 {n} 가 없어요. Krea 2 스타일 참조에는 최신 ComfyUI 가 필요해요 — ComfyUI 를 업데이트해 주세요.")
        lora = pick_file(files("loras"), r"krea2.*style.?ref", r"style.?ref.*krea")
        if not lora:
            raise RuntimeError("Krea 2 스타일 참조 LoRA(krea2_style_reference)가 없어요. '설치와 모델' 탭에서 'Krea 2 스타일 참조'를 설치해 주세요.")
        spec = ((caps()["info"].get("FluxKontextMultiReferenceLatentMethod") or {}).get("input", {}).get("required") or {})
        mkey = next((k for k, v in spec.items() if isinstance(v, list) and v and (v[0] == "COMBO" and "index_timestep_zero" in ((v[1] or {}).get("options") or []) or isinstance(v[0], list) and "index_timestep_zero" in v[0])), "reference_latents_method")
        q = flux_q(p2, J, "krea2", text, tags, seed_of(p), w, h)
        if mode == "face":
            warn(J, "Krea 2 에는 얼굴만 따로 따르는 방식이 없어요. 스타일 참조로 그리니, 글에 '같은 사람' 같은 설명을 같이 적어 주세요.")
        strength = clamp(num(p, "kweight", 1.0), 0.1, 1.5)
        J["msg"] = "참고 이미지를 보며 그리는 중"
        g = flows.wf_krea2_ref(q, name, lora, strength, mkey)
        res = run_wf(g, J)[0]
        return [(res, flux_info(q, res, "feat-ipadapter", Reference=f"Krea 2 스타일 참조 / {lora} / {strength}"), g)]
    kontext = "kontext" in (p2.get("fx_model") or "").lower()
    q = flux_q(p2, J, "flux", (REF_FACE if mode == "face" else REF_STYLE) + text if kontext else text, tags, seed_of(p), w, h)
    if kontext:      # 참고 이미지를 조건으로 걸고 빈 화면에서 새로 그려요 (사람·물건이 그대로 이어져요)
        for n in ("ReferenceLatent", "FluxKontextImageScale"):
            if caps()["nodes"] and n not in caps()["nodes"]:
                raise RuntimeError(f"이 ComfyUI 에는 노드 {n} 가 없어요. ComfyUI 를 업데이트해 주세요.")
        small = ref.resize(qsize(ref.size, 1.0), RS.LANCZOS)
        q["ref"] = put_input(small, J)
        how = "FLUX Kontext 참고"
    else:      # Redux: 이미지의 분위기·구성을 조건으로 더해요
        for n in ("CLIPVisionLoader", "CLIPVisionEncode", "StyleModelLoader", "StyleModelApply"):
            if caps()["nodes"] and n not in caps()["nodes"]:
                raise RuntimeError(f"이 ComfyUI 에는 노드 {n} 가 없어요. ComfyUI 를 업데이트해 주세요.")
        cv = pick_file(combo_opts("CLIPVisionLoader", "clip_name"), r"sigclip", r"siglip")
        st = pick_file(combo_opts("StyleModelLoader", "style_model_name"), r"redux")
        if not cv or not st:
            raise RuntimeError("FLUX.1 Redux 파일이 없어요 — " + " / ".join(x for x, ok in (("sigclip 비전 모델", cv), ("flux1-redux-dev", st)) if not ok) +
                               ". '설치와 모델' 탭에서 'FLUX.1 Redux'를 설치한 뒤 [이미지 엔진 다시 시작]을 눌러 주세요. (얼굴은 FLUX Kontext 모델이 더 잘 따라요.)")
        node = (caps()["info"].get("StyleModelApply") or {}).get("input", {})
        have = {**(node.get("required") or {}), **(node.get("optional") or {})}
        extra = {**({"strength": weight} if "strength" in have else {}), **({"strength_type": "multiply"} if "strength_type" in have else {})}
        q["redux"] = dict(clip_vision=cv, style=st, image=put_input(ref, J), extra=extra)
        how = f"Redux / {st} / {weight}"
        if mode == "face":
            warn(J, "일반 FLUX.1 의 Redux 는 얼굴을 똑같이 따르지는 못해요(분위기만 닮아요). 얼굴은 FLUX Kontext 모델을 고르면 더 잘 따라요.")
    J["msg"] = "참고 이미지를 보며 그리는 중"
    g = flows.wf_flux(q)
    res = run_wf(g, J)[0]
    return [(res, flux_info(q, res, "feat-ipadapter", Reference=how), g)]


def feat_ipadapter(p, J):
    """참고 이미지로 그리기. SDXL 은 IPAdapter plus, FLUX.1 · Krea 2 는 각자의 방식(feat_reference_fx)을 써요."""
    ref = load_img(p["image"]).convert("RGB")
    mode = "face" if p.get("mode") == "face" else "style"
    fam, p2 = fx_sel(p)
    if fam:
        return feat_reference_fx(p, p2, fam, ref, mode, J)
    presets = combo_opts("IPAdapterUnifiedLoader", "preset")
    up = [(x, x.upper()) for x in presets]
    if mode == "face":
        preset = next((x for x, u in up if "PLUS" in u and "FACE" in u), None) or next((x for x, u in up if "FACE" in u), None)
    else:
        preset = next((x for x, u in up if u.startswith("PLUS (HIGH")), None) or next((x for x, u in up if "PLUS" in u and "FACE" not in u), None)
    preset = preset or (presets[0] if presets else ("PLUS FACE (portraits)" if mode == "face" else "PLUS (high strength)"))
    wts = combo_opts("IPAdapter", "weight_type")
    wtype = "style transfer" if mode == "style" and "style transfer" in wts else ("linear" if "linear" in wts or not wts else wts[0])
    weight = clamp(num(p, "weight", 1.0), 0.1, 2.0)
    w, h = (clamp(num(p, k, 1024, int) // 8 * 8, 256, 2048) for k in ("w", "h"))
    rng = random.Random(num(p, "seed", -1, int))
    q = sd(p, *prep(p, J, "tags", rng), J)
    J["msg"] = "참고 이미지를 보며 그리는 중"
    g = flows.wf_ipadapter(q, put_input(ref, J), preset, wtype, weight, w, h, fill_node)
    res = run_wf(g, J)[0]
    return [(res, info_sd(q, res.size, "feat-ipadapter", IPAdapter=f"{preset} / {wtype} / {weight}"), g)]


def do_feat(p, J):
    fn = {"outpaint": feat_outpaint, "regional": feat_regional, "compare": feat_compare, "resize": feat_resize, "color": feat_color,
          "detailer": feat_detailer, "ipadapter": feat_ipadapter, "faceswap": feat_faceswap, "img3d": feat_3d, "rmbg": feat_rmbg}.get(p.get("feature"))
    if not fn:
        raise ValueError("알 수 없는 기능이에요.")
    spec = next(f for f in FEATURES if f["id"] == p["feature"])
    need_nodes = [] if p["feature"] == "ipadapter" and fx_sel(p)[0] else spec.get("needs", {}).get("nodes", [])      # FLUX·Krea 2 는 IPAdapter 확장이 필요 없어요
    miss = [n for n in need_nodes if caps()["nodes"] and n not in caps()["nodes"]]
    if miss:
        pack = spec.get("needs", {}).get("pack")
        raise RuntimeError("이 ComfyUI 에는 필요한 노드가 없어요: " + ", ".join(miss) + ". " +
                           (f"확장 '{pack}' 을(를) 설치하고 ComfyUI 를 다시 시작해 주세요." if pack else "ComfyUI 를 업데이트해 주세요."))
    return fn(p, J)
