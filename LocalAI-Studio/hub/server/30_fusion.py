# 로컬 AI 스튜디오 허브 — AI 사진 합성·편집(사진 여러 장 + 자유 지시문 → 한 장)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821
#
# 사진 두 장(넷까지)을 올리고 하고 싶은 것을 말로 적으면, 사진들을 각각 따로 참고해서 한 장을 만들어요.
# · 모델: 이미 쓰고 있는 Qwen-Image 2.1(생성·편집 겸용). 공식 노드 TextEncodeQwenImage21 이 참고 사진을 한 장씩 따로(최대 16장) 받아요 —
#   사진을 미리 한 장으로 이어 붙이지 않아요. 새 모델·새 노드·새 실행기를 깔지 않아요.
# · 사진의 역할(누가 바탕이고 누가 참고인지)은 정해 두지 않아요. 올린 순서만 알려 주고 지시문대로 해석하게 해요.
# · 3D 기능과는 아무것도 같이 쓰지 않아요.

OUT_SUB["fusion"] = "사진 합성"          # 결과 폴더(outputs\사진 합성) — 갤러리에도 이 이름으로 나와요
FUSION_MAX = 4                           # 화면에서 받는 사진 수(모델은 16장까지 받지만, 12GB 그래픽 메모리에서 무리 없는 만큼만)
FUSION_MODEL_MAX = 16
FUSION_IMG_MAX = 40_000_000              # 사진 한 장의 최대 화소 수(이보다 크면 받지 않아요)
FUSION_RATIOS = {"1:1": (1, 1), "4:3": (4, 3), "3:4": (3, 4), "3:2": (3, 2), "2:3": (2, 3), "16:9": (16, 9), "9:16": (9, 16)}
FUSION_MP = {"save": 0.6, "normal": 1.0, "high": 1.5}      # 결과 크기(백만 화소): 메모리 절약 / 기본 / 크게
FUSION_ORD = ("first", "second", "third", "fourth")


def fusion_guide(n):
    """모델에 지시문 앞에 붙여 보내는 안내(사용자 지시문은 한 글자도 바꾸지 않고 그 뒤에 그대로 붙여요)."""
    names = ", ".join(f"image {i + 1} is the {FUSION_ORD[i]} uploaded photo" for i in range(n))
    return (f"There are {n} reference photos, numbered in upload order: {names}. "
            "Use all of them as visual references. Decide the role of each photo only from the instruction below — "
            "do not assume that image 1 is the canvas to edit or that image 2 is the background unless the instruction says so. "
            "Produce one finished photo that does exactly what the instruction asks, keep whatever it says to keep "
            "(faces, body proportions, clothes, products, logos), and do not add things it does not ask for.\nInstruction: ")


def fusion_model_card():
    """받아야 할 때 화면에 보여 줄 모델 정보(이름·크기·경로·라이선스·필요 사양)."""
    m = next((x for x in CATALOG["image"] if x["id"] == "qwen-image"), None) or {}
    return {"id": "qwen-image", "name": m.get("name") or "Qwen-Image 2.1 (int8)", "gb": m.get("gb"), "license": m.get("license"),
            "dirs": sorted({f.get("dir") for f in m.get("files") or [] if f.get("dir")}),
            "files": [str(f.get("name") or str(f.get("url") or "").rsplit("/", 1)[-1]) for f in m.get("files") or []],
            "need": "그래픽 메모리(VRAM) 12GB 이상 권장 · RAM 32GB 이상 권장", "node": "TextEncodeQwenImage21 (ComfyUI 기본 노드 — 따로 깔 것 없음)"}


def fusion_status():
    """이 기능을 쓸 수 있는지: 이미지 엔진(ComfyUI) 연결 · 노드 · 모델 파일 · 그래픽 메모리 · 번역 모델."""
    up = alive(CUI + "/system_stats")
    nodes = caps()["nodes"] if up else set()
    f = {"unet": qwen21_unets(), "te": [n for n in files("text_encoders") if re.search(r"qwen3[_-]?vl[_-]?8b", n.lower())], "vae": [n for n in files("vae") if QWEN21_RX.search(n.lower())]}
    have = bool(f["unet"] and qwen21_te() and qwen21_vae())
    node = (not up) or (not nodes) or "TextEncodeQwenImage21" in nodes
    g = None
    try:
        g = gpu_live()
    except Exception:  # noqa: BLE001
        pass
    why = None
    if not have:
        why = "Qwen-Image 2.1 모델이 없어요. 아래에서 받을 수 있어요."
    elif not node:
        why = "이 ComfyUI 에는 Qwen-Image 2.1 노드(TextEncodeQwenImage21)가 없어요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요."
    return {"comfy": bool(up), "node": bool(node), "model": have, "ready": bool(have and node), "why": why, "files": f,
            "using": {"unet": (f["unet"] or [None])[0], "te": qwen21_te(), "vae": qwen21_vae()} if have else None,
            "max_images": FUSION_MAX if have and node else 2, "model_max": FUSION_MODEL_MAX,
            "fast": bool(qwen_fast_lora()) or any("turbo" in n.lower() for n in f["unet"]), "te_small": any("w4a8" in n.lower() for n in f["te"]),
            "translator": bool(llms()), "card": fusion_model_card(), "need": [] if have else ["qwen-image"],
            "gpu": {"vram_total_mb": g.get("total_mb"), "vram_used_mb": g.get("used_mb"), "name": g.get("name")} if g else None}


def fusion_ram_mb():
    """컴퓨터 전체에서 쓰고 있는 메모리(MB) — 잴 수 없으면 None. (모델은 ComfyUI 쪽에 올라가니 허브 혼자 쓰는 양이 아니라 전체를 봐요)"""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in (
                    "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]
            m = MS()
            m.dwLength = ctypes.sizeof(m)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return round((m.ullTotalPhys - m.ullAvailPhys) / 2 ** 20)
            return None
        d = {}
        with open("/proc/meminfo", encoding="ascii") as fh:
            for ln in fh:
                k, v = ln.split(":", 1)
                d[k] = int(v.split()[0])
        return round((d["MemTotal"] - d.get("MemAvailable", d.get("MemFree", 0))) / 1024)
    except Exception:  # noqa: BLE001
        return None


class FusionWatch:
    """작업하는 동안 그래픽 메모리·RAM 을 2초마다 재서 가장 많이 쓴 때를 기억해요."""

    def __init__(self):
        self.vram = self.total = self.ram = 0
        self.on = True
        self.t0 = time.time()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.on:
            try:
                g = gpu_live()
                if g and g.get("used_mb"):
                    self.vram, self.total = max(self.vram, g["used_mb"]), g.get("total_mb") or self.total
            except Exception:  # noqa: BLE001
                pass
            r = fusion_ram_mb()
            if r:
                self.ram = max(self.ram, r)
            time.sleep(2)

    def stop(self):
        self.on = False
        return {"seconds": round(time.time() - self.t0, 1), "vram_peak_mb": self.vram or None, "vram_total_mb": self.total or None, "ram_peak_mb": self.ram or None}


def fusion_load(p):
    """보낸 사진들(image1 … image4) → [PIL]. 빈칸은 건너뛰고 올린 순서를 지켜요. 못 읽는 사진은 몇 번째인지 알려요."""
    imgs = []
    for i in range(1, FUSION_MODEL_MAX + 1):
        v = p.get(f"image{i}")
        if not v:
            continue
        if len(imgs) >= FUSION_MAX:
            raise ValueError(f"사진은 {FUSION_MAX}장까지 넣을 수 있어요.")
        try:
            im = load_img(v)
            im.load()
        except Exception:  # noqa: BLE001
            raise ValueError(f"사진 {i} 을(를) 읽지 못했어요. 손상됐거나 지원하지 않는 형식이에요(PNG·JPG·WEBP 를 써 주세요).") from None
        if im.width < 32 or im.height < 32:
            raise ValueError(f"사진 {i} 이(가) 너무 작아요({im.width}×{im.height}).")
        if im.width * im.height > FUSION_IMG_MAX:
            raise ValueError(f"사진 {i} 이(가) 너무 커요({im.width}×{im.height}). 4천만 화소 아래로 줄여 주세요.")
        imgs.append(im)
    if len(imgs) < 2:
        raise ValueError("사진을 두 장 이상 올려 주세요.")
    return imgs


def fusion_size(p, imgs):
    """결과 크기(32 배수). 비율: auto = 사진 1 의 비율, imgN = N번째 사진의 비율, 또는 1:1 같은 정해진 비율. → ((w, h), 비율 이름, 백만 화소)"""
    mp = FUSION_MP.get(p.get("size") or "", None)
    if mp is None:
        mp = FUSION_MP["save"] if p.get("memory") == "save" else FUSION_MP["normal"]
    r = str(p.get("ratio") or "auto")
    m = re.fullmatch(r"img(\d)", r)
    if r in FUSION_RATIOS:
        base = FUSION_RATIOS[r]
    elif m and 1 <= int(m.group(1)) <= len(imgs):
        base = imgs[int(m.group(1)) - 1].size
    else:
        r, base = "auto", imgs[0].size
    return qsize32(base, mp), r, mp


def do_fusion(p, J):
    """사진 여러 장 + 지시문 → 결과 1~4장. 사진은 올린 순서대로 한 장씩 따로 모델에 넘겨요."""
    raw = (p.get("prompt") or "").strip()
    if not raw:
        raise ValueError("어떻게 합성하거나 편집할지 지시문을 적어 주세요.")
    imgs = fusion_load(p)
    rng = random.Random(num(p, "seed", -1, int))
    text, tags = prep({**p, "translate": "", "dyn": ""}, J, "sentence", rng)      # 금지어 확인 · <lora:…> 꼬리표 떼기(번역·자동 바꾸기는 여기서 하지 않아요)
    sent, translated = text, False
    if p.get("translate") and re.search("[가-힣]", text):          # 한국어 지시문: 번역 모델이 있으면 뜻 그대로 영어로 옮겨요(없으면 한국어 그대로)
        if llms():
            J["msg"] = "지시문을 영어로 옮기는 중(뜻은 그대로)"
            out = translate_keep_quotes(text, "fusion")
            if out and out != text and len(out) >= 0.8 * len(text):      # 영어는 같은 뜻이면 한글보다 글자 수가 많아요 — 더 짧으면 내용이 빠진 것으로 보고 쓰지 않아요
                sent, translated = out, True
            else:
                warn(J, "영어로 옮긴 글이 원문보다 짧아(내용이 빠졌을 수 있어) 한국어 그대로 보냈어요.")
    save = p.get("memory") == "save"
    size, ratio, mp = fusion_size(p, imgs)
    pq = {"fast": p.get("fast"), "seed": p.get("seed"), "q_steps": p.get("steps"), "q_mp": mp}
    if save:                                                        # 메모리 절약: 가벼운 텍스트 인코더가 있으면 그것으로
        small = next((n for n in files("text_encoders") if re.search(r"qwen3[_-]?vl[_-]?8b", n.lower()) and "w4a8" in n.lower()), None)
        if small:
            pq["q_te"] = small
    q = qwen_params(pq, fusion_guide(len(imgs)) + sent, tags, J)
    q["resolution"] = 0                                             # 참고 사진은 우리가 맞춘 크기 그대로
    ref_mp = min(mp, 1.0)
    refs = [im.convert("RGB").resize(qsize32(im.size, ref_mp), RS.LANCZOS) for im in imgs]
    first_size = refs[0].size
    names = [put_input(r, J) for r in refs]
    n = int(clamp(num(p, "count", 1, int), 1, 4))
    watch = FusionWatch()
    out, seeds = [], []
    try:
        for k in range(n):
            check_cancel(J)
            qk = {**q, "seed": q["seed"] + k}
            J["msg"] = f"사진 {len(imgs)}장을 참고해 만드는 중" + (f" ({k + 1}/{n})" if n > 1 else "") + " — 처음에는 모델을 올리느라 오래 걸려요"
            wf = flows.wf_qwen21(qk, names, size=None if size == first_size else size, key=qwen21_img_key)
            res = run_wf(wf, J)
            if not res:
                raise RuntimeError("결과 그림을 받지 못했어요. 다시 시도해 주세요.")
            out.append(res[0])
            seeds.append(qk["seed"])
    finally:
        st = watch.stop()
    J["fusion"] = {"original": raw, "sent": q["prompt"], "translated": translated, "inputs": [list(im.size) for im in imgs], "refs": [list(r.size) for r in refs],
                   "out": list(out[0].size), "ratio": ratio, "megapixels": mp, "count": n, "seeds": seeds, "steps": q["steps"], "cfg": q["cfg"], "fast": q["fast"],
                   "memory": "save" if save else "normal", "model": q["files"], "engine": "Qwen-Image 2.1", **st}
    J["msg"] = f"끝났어요 — {st['seconds']:.0f}초"
    items = []
    for im, sd_ in zip(out, seeds):
        info = dict(kind="fusion-qwen", prompt=raw, negative="", steps=q["steps"], cfg=q["cfg"], sampler=q["sampler"], scheduler=q["scheduler"], seed=sd_,
                    w=im.width, h=im.height, model=q["files"]["unet"], loras=[[a, b] for a, b in q["loras"]],
                    extra={"Refs": len(imgs), "Engine": "Qwen-Image 2.1", "Sent prompt": q["prompt"][:1500], "Inputs": " / ".join(f"{a}x{b}" for a, b in (im_.size for im_ in imgs))})
        items.append((im, info, None))
    return items
