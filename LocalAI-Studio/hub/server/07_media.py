# 로컬 AI 스튜디오 허브 — 결과 폴더 · 영상(Wan·LTX·VACE·S2V) · 음악·효과음 · 음성 · 3D · 영상 다듬기
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OUT_SUB = {"edit": "편집", "gen": "생성", "up": "업스케일", "wf": "워크플로", "feat": "기능", "vid": "영상", "batch": "일괄", "music": "음악", "tts": "음성", "photo": "사진 편집", "etc": "기타"}


def out_path(rel):
    """/out/ 아래 요청 경로를 안전하게 파일 경로로 바꿔요(하위 폴더는 정해진 이름만)."""
    parts = [x for x in urllib.parse.unquote(rel).split("/") if x]
    if len(parts) == 2 and parts[0] in OUT_SUB.values() or parts[:1] == ["기타"] and len(parts) == 2:
        return OUT / parts[0] / Path(parts[1]).name
    if len(parts) == 3 and parts[0] in OUT_SUB.values() and DATE_RX.match(parts[1]):      # 날짜별로 정리한 폴더
        return OUT / parts[0] / parts[1] / Path(parts[2]).name
    return OUT / Path(parts[-1] if parts else "x").name





def vace_model():
    """Wan VACE 모델 고르기: 그것만으로 돌아가는 Wan 2.1 VACE 를 먼저 써요.
    VACE '모듈'(본 모델에 덧붙이는 조각)·Wan 2.2 Fun VACE(고·저 노이즈 두 모델을 번갈아 써야 함)는 혼자 쓰면 하얗거나 뭉개진 영상이 나와 뒤로 미뤄요."""
    vs = [n for n in files("diffusion_models") if "vace" in n.lower()]
    bad = lambda n: any(k in n.lower() for k in ("module", "fun", "high_noise", "low_noise", "2.2", "2_2"))
    vs.sort(key=lambda n: (bad(n), n.lower()))
    return vs[0] if vs else None

def wan_models():
    return [n for n in files("diffusion_models") if "wan" in n.lower() and "14b" not in n.lower() and "vace" not in n.lower() and "s2v" not in n.lower()]


def wan14_parts(i2v):
    """Wan 2.2 14B 에 필요한 파일을 이름으로 찾아요: 고노이즈/저노이즈 모델, UMT5, Wan 2.1 VAE, (있으면) 4단계 가속 LoRA."""
    dm, te, va, lo = files("diffusion_models"), files("text_encoders"), files("vae"), files("loras")
    kind = "i2v" if i2v else "t2v"
    pick = lambda lst, *keys: next((n for n in lst if all(k in n.lower() for k in keys)), None)
    fast = lambda side: pick(lo, "lightx2v", kind, side) or pick(lo, "lightning", kind, side)
    return dict(high=pick(dm, "14b", kind, "high"), low=pick(dm, "14b", kind, "low"), te=pick(te, "umt5"),
                vae=pick(va, "wan_2.1") or pick(va, "wan2.1") or pick(va, "wan_2_1"),
                lora_high=fast("high"), lora_low=fast("low"))


def wan14_state():
    out = {}
    for kind in ("i2v", "t2v"):
        f = wan14_parts(kind == "i2v")
        out[kind] = bool(f["high"] and f["low"] and f["te"] and f["vae"])
        out["fast_" + kind] = bool(f["lora_high"] and f["lora_low"])
    return out


def wan_parts(p=None):
    te, va = files("text_encoders"), files("vae")
    r = dict(unet=next((n for n in wan_models() if "ti2v" in n.lower()), None),
             te=next((n for n in te if "umt5" in n.lower()), None),
             vae=next((n for n in va if "wan2.2" in n.lower() or "wan2_2" in n.lower()), None))
    if p:
        for key, field, lst in (("unet", "wan_model", wan_models()), ("te", "wan_te", te), ("vae", "wan_vae", va)):
            if p.get(field) and p[field] in lst:
                r[key] = p[field]
    return r


def do_vid14(p, J):
    """Wan 2.2 14B (고노이즈 + 저노이즈 2단계). 시작 이미지가 있으면 이미지→영상, 없으면 글→영상. ※ 실제 PC 로 검증하지 못한 기능이에요."""
    for node in ("KSamplerAdvanced", "CreateVideo", "SaveVideo", "ModelSamplingSD3"):
        if not has_node(node):
            raise RuntimeError(f"이 ComfyUI 에는 필요한 노드({node})가 없어요. ComfyUI 를 업데이트해 주세요.")
    img = load_img(p["image"]) if p.get("image") else None
    need = "WanImageToVideo" if img is not None else "EmptyHunyuanLatentVideo"
    if not has_node(need):
        raise RuntimeError(f"이 ComfyUI 에는 영상 노드({need})가 없어요. ComfyUI 를 업데이트해 주세요.")
    ct = caps().get("clip_types") or []
    if ct and "wan" not in ct:
        raise RuntimeError("이 ComfyUI 는 Wan 텍스트 인코더 형식을 지원하지 않아요. ComfyUI 를 업데이트해 주세요.")
    f = wan14_parts(img is not None)
    kind = "이미지→영상" if img is not None else "글→영상"
    miss = [n for n, k in ((f"Wan 2.2 14B {kind} 고노이즈 모델", "high"), (f"Wan 2.2 14B {kind} 저노이즈 모델", "low"),
                           ("UMT5 텍스트 인코더", "te"), ("Wan 2.1 VAE", "vae")) if not f[k]]
    if miss:
        raise RuntimeError("없는 파일: " + ", ".join(miss) + f". '설치와 모델' 탭에서 'Wan 2.2 14B {kind}'를 설치해 주세요.")
    fast = bool(p.get("fast"))
    if fast and not (f["lora_high"] and f["lora_low"]):
        warn(J, "4단계 가속 LoRA 가 없어 일반 단계로 만들어요. '설치와 모델'에서 'Wan 2.2 4단계 가속 LoRA'를 설치하면 빨라져요.")
        fast = False
    rng = random.Random(seed_of(p))
    text, _ = prep(p, J, "caption", rng)
    if not text.strip():
        raise ValueError("어떤 영상을 만들지 프롬프트를 적어 주세요.")
    if blocked(text):
        raise ValueError(BLOCK_MSG)
    try:
        w, h = (int(x) for x in (p.get("size") or "832x480").split("x"))
    except ValueError:
        w, h = 832, 480
    if img is not None and p.get("keep_ratio"):
        k = (w * h / (img.width * img.height)) ** 0.5
        w, h = img.width * k, img.height * k
    w, h = (clamp(int(round(x / 16)) * 16, 256, 1280) for x in (w, h))
    fps = clamp(num(p, "fps", 16, int), 8, 30)
    sec = clamp(num(p, "sec", 3.0), 1.0, 8.0)
    frames = clamp(int(round(sec * fps / 4)) * 4 + 1, 9, 161)
    steps = 4 if fast else clamp(num(p, "steps", 20, int), 4, 60)
    cfg = 1.0 if fast else clamp(num(p, "cfg", 3.5), 1.0, 20.0)
    vram = (GPU or {}).get("vram_gb", 0)
    if vram and vram < 16:
        warn(J, f"14B 모델은 VRAM {vram}GB 에서는 매우 느리거나 메모리 부족이 날 수 있어요. 안 되면 5B 로 바꿔 보세요.")
    q = dict(high=f["high"], low=f["low"], te=f["te"], vae=f["vae"], prompt=text, negative=(p.get("negative") or "").strip() or flows.WAN_NEG,
             seed=seed_of(p), w=w, h=h, frames=frames, fps=fps, steps=steps, cfg=cfg, split=max(1, steps // 2),
             sampler="euler" if "euler" in (caps()["samplers"] or ["euler"]) else (caps()["samplers"] or ["euler"])[0], scheduler="simple",
             shift=clamp(num(p, "shift", 5.0), 1.0, 20.0), lora_high=f["lora_high"] if fast else None, lora_low=f["lora_low"] if fast else None)
    start = put_input(ImageOps.fit(img, (w, h), RS.LANCZOS), J) if img is not None else None
    J["msg"] = f"14B 영상 만드는 중 ({w}×{h}, {frames}프레임, 2단계) — 꽤 오래 걸려요"
    res = run_wf(flows.wf_video14(q, start), J, raw=True)
    info = dict(kind="vid", prompt=text, negative=q["negative"], seed=q["seed"], w=w, h=h, steps=steps, cfg=cfg, model=f"{f['high']} + {f['low']}",
                frames=frames, fps=fps, start_image=bool(start), fast=fast)
    return [(data, info, Path(name).suffix.lower() or ".mp4") for name, data in res[:1]]


MUSIC_NODES = ("TextEncodeAceStepAudio1.5", "EmptyAceStep1.5LatentAudio", "ConditioningZeroOut", "VAEDecodeAudio", "SaveAudioAdvanced")
MUSIC_LANGS = ("ko", "en", "ja", "zh", "es", "fr", "de", "ru", "pt", "it", "unknown")
KEYSCALES = [f"{r} {q}" for q in ("major", "minor") for r in ("C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B")]


def music_models():
    """checkpoints 폴더의 ACE-Step 1.5 올인원 파일(텍스트 인코더·VAE 포함)."""
    return [n for n in files("checkpoints") if "ace_step" in n.lower() or "acestep" in n.lower()]


def sfx_models():
    """checkpoints 폴더의 Stable Audio Open 파일."""
    return [n for n in files("checkpoints") if re.search(r"stable[_-]?audio", n.lower())]


SFX_NODES = ("EmptyLatentAudio", "ConditioningStableAudio", "VAEDecodeAudio")


def do_sfx(p, J):
    """Stable Audio Open 1.0 으로 효과음 만들기(최대 47초). 결과: [(바이트, 정보, 확장자)]"""
    gone = [n for n in SFX_NODES if not has_node(n)]
    if gone:
        raise RuntimeError(f"이 ComfyUI 에는 효과음에 필요한 노드({', '.join(gone)})가 없어요. ComfyUI 를 업데이트해 주세요.")
    models = sfx_models()
    if not models:
        raise RuntimeError("Stable Audio 모델이 없어요. '설치와 모델' 탭에서 'Stable Audio Open 1.0'을 설치해 주세요.")
    te = _pick(files("text_encoders"), "t5_base", "t5-base", ("t5", "base"))
    if not te:
        raise RuntimeError("T5-base 텍스트 인코더가 없어요. '설치와 모델' 탭에서 'Stable Audio Open 1.0'을 다시 설치해 주세요.")
    text = (p.get("tags") or "").strip()
    if not text:
        raise ValueError("어떤 소리인지 적어 주세요. 예: heavy rain on a tin roof")
    if blocked(text):
        raise ValueError(BLOCK_MSG)
    sec = clamp(num(p, "sfx_seconds", 10.0), 1.0, 47.0)
    q = dict(ckpt=models[0], te=te, prompt=text, negative="low quality, distorted, noise", seed=seed_of(p), seconds=sec,
             steps=clamp(num(p, "sfx_steps", 50, int), 10, 150), cfg=7.0,
             sampler="dpmpp_3m_sde_gpu" if "dpmpp_3m_sde_gpu" in (caps()["samplers"] or []) else "euler",
             scheduler="exponential" if "exponential" in (caps()["schedulers"] or []) else "simple",
             fmt=p.get("format") if p.get("format") in ("mp3", "flac") else "mp3")
    J["msg"] = f"효과음 만드는 중 ({sec:.0f}초)"
    res = run_wf(flows.wf_sfx(q), J, raw=True)
    info = dict(kind="sfx", prompt=text, seed=q["seed"], seconds=sec, steps=q["steps"], model=q["ckpt"])
    return [(data, info, Path(name).suffix.lower() or ".mp3") for name, data in res[:1]]


def do_music(p, J):
    """ACE-Step 1.5 로 음악 만들기. 결과: [(바이트, 정보, 확장자)]"""
    if p.get("mengine") == "sfx":
        return do_sfx(p, J)
    gone = [n for n in MUSIC_NODES if not has_node(n)]
    if gone:
        raise RuntimeError(f"이 ComfyUI 에는 음악 만들기에 필요한 노드({', '.join(gone)})가 없어요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
    models = music_models()
    sel = p.get("music_model") or (models[0] if models else None)
    if not sel or sel not in models:
        raise RuntimeError("ACE-Step 음악 모델이 없어요. '설치와 모델' 탭에서 'ACE-Step 1.5 Turbo'를 설치해 주세요.")
    tags = (p.get("tags") or "").strip()
    if not tags:
        raise ValueError("어떤 음악인지 적어 주세요. 예: lo-fi, chill, piano, relaxing")
    lyrics = "" if p.get("instrumental") else (p.get("lyrics") or "").strip()
    if blocked(tags + " " + lyrics):
        raise ValueError(BLOCK_MSG)
    sec = clamp(num(p, "seconds", 60.0), 5.0, 300.0)
    lang = p.get("language") if p.get("language") in MUSIC_LANGS else "ko"
    key = p.get("keyscale") if p.get("keyscale") in KEYSCALES else "C major"
    q = dict(ckpt=sel, tags=tags, lyrics=lyrics, seed=seed_of(p), seconds=sec, bpm=clamp(num(p, "bpm", 120, int), 40, 240),
             timesig=str(p.get("timesignature") if str(p.get("timesignature")) in ("2", "3", "4", "6") else "4"), language=lang, keyscale=key,
             steps=clamp(num(p, "steps", 8, int), 1, 100), cfg=clamp(num(p, "cfg", 1.0), 0.0, 20.0), fmt=p.get("format") if p.get("format") in ("mp3", "flac") else "mp3",
             codes=not bool(p.get("no_codes")),
             sampler="euler" if "euler" in (caps()["samplers"] or ["euler"]) else (caps()["samplers"] or ["euler"])[0],
             scheduler="simple" if "simple" in (caps()["schedulers"] or ["simple"]) else (caps()["schedulers"] or ["simple"])[0])
    J["msg"] = f"음악 만드는 중 ({int(sec)}초)"
    res = run_wf(flows.wf_music(q), J, raw=True)
    info = dict(kind="music", prompt=tags, lyrics=lyrics, seed=q["seed"], seconds=sec, bpm=q["bpm"], keyscale=key, language=lang, steps=q["steps"], cfg=q["cfg"], model=sel)
    return [(data, info, Path(name).suffix.lower() or ".mp3") for name, data in res[:1]]


TTS_DIR = ROOT / "cache" / "tts"


def tts_voices():
    sap = [{"name": n, "culture": c} for n, c in tts.sapi_voices(TTS_DIR)]
    return {"sapi": sap, "sapi_ok": bool(sap), "windows": os.name == "nt", "edge": [{"name": n, "label": l} for n, l in tts.EDGE_VOICES], "edge_ok": tts.edge_ready()}


def do_tts(p, J):
    """글을 소리로. 결과: [(바이트, 정보, 확장자)]"""
    text = (p.get("text") or "").strip()
    if not text:
        raise ValueError("읽을 글을 적어 주세요.")
    if len(text) > tts.MAX_CHARS:
        raise ValueError(f"글이 너무 길어요({len(text)}자). {tts.MAX_CHARS}자 이하로 나눠서 만들어 주세요.")
    if blocked(text):
        raise ValueError(BLOCK_MSG)
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    engine = p.get("engine") if p.get("engine") in ("edge", *tts_models.ENGINES) else "sapi"
    speed, vol = clamp(num(p, "speed", 0, int), -10, 10), clamp(num(p, "volume", 100, int), 0, 100)
    J["msg"] = "목소리 만드는 중"
    if engine in tts_models.ENGINES:
        return do_tts_model(p, J, engine, text, speed)
    if engine == "edge":
        voice = p.get("voice") if p.get("voice") in {n for n, _ in tts.EDGE_VOICES} else "ko-KR-SunHiNeural"
        pitch = clamp(num(p, "pitch", 0, int), -50, 50)
        data = tts.speak_edge(text, voice, speed * 5, vol - 100, pitch, TTS_DIR)
        ext = ".mp3"
    else:
        if os.name != "nt" and not getattr(tts, "FORCE_SAPI", False):
            raise RuntimeError("윈도우 내장 음성은 윈도우에서만 쓸 수 있어요. Edge 읽어 주기를 골라 주세요.")
        names = [n for n, _ in tts.sapi_voices(TTS_DIR)]
        voice = p.get("voice") if p.get("voice") in names else (names[0] if names else "")
        data = tts.speak_sapi(text, voice, speed, vol, TTS_DIR)
        ext = ".wav"
    info = dict(kind="tts", prompt=text[:200], text=text[:5000], engine=engine, voice=voice, speed=speed, volume=vol)
    return [(data, info, ext)]


def tts_ref_upload(p):
    """목소리 샘플(wav)을 받아 cache/tts/ref 에 둬요."""
    try:
        raw = base64.b64decode(str(p.get("data") or "").split(",", 1)[-1], validate=False)
    except Exception:  # noqa: BLE001
        return {"error": "파일을 읽지 못했어요."}
    if len(raw) > 25 << 20:
        return {"error": "파일이 너무 커요(25MB 이하)."}
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        return {"error": "wav 파일만 쓸 수 있어요. mp3 등은 wav 로 바꿔서 올려 주세요."}
    if len(raw) < 100_000:
        return {"error": "너무 짧아요. 5~15초쯤 또렷하게 말한 파일이 좋아요."}
    rid = uuid.uuid4().hex[:12]
    (TTS_DIR / "ref").mkdir(parents=True, exist_ok=True)
    (TTS_DIR / "ref" / (rid + ".wav")).write_bytes(raw)
    return {"ok": True, "id": rid}


def do_tts_model(p, J, engine, text, speed):
    """Qwen3-TTS · XTTS-v2 · Chatterbox · Kokoro (전용 파이썬 환경에서 실행)."""
    meta = tts_models.ENGINES[engine]
    if meta["need_license"] and not p.get("license_ok"):
        raise ValueError(f"{meta['title'].split(' — ')[0]} 는 {meta['license']} 모델이에요. 사용 조건 확인 칸에 체크해 주세요.")
    lang = p.get("language") if p.get("language") in {c for c, _n in meta["langs"]} else meta["langs"][0][0]
    ref = None
    if p.get("ref"):
        if not meta["clone"]:
            raise ValueError("이 모델은 목소리 따라 하기를 지원하지 않아요.")
        if not re.fullmatch(r"[0-9a-f]{12}", str(p["ref"])):
            raise ValueError("목소리 샘플 정보가 올바르지 않아요. 다시 올려 주세요.")
        ref = TTS_DIR / "ref" / (str(p["ref"]) + ".wav")
        if not ref.is_file():
            raise ValueError("올린 목소리 샘플을 찾지 못했어요. 다시 올려 주세요.")
    speaker = str(p.get("speaker") or "")
    if speaker and not re.fullmatch(r"[\w .'\-]{1,60}", speaker):
        speaker = ""
    (TTS_DIR / "gen").mkdir(parents=True, exist_ok=True)
    out = TTS_DIR / "gen" / (uuid.uuid4().hex[:12] + ".wav")
    job = dict(text=text, language=lang, speaker=speaker, ref=str(ref) if ref else "", speed=round(1 + speed * 0.075, 3), emotion=str(p.get("emotion") or ""),
               ref_text=str(p.get("ref_text") or "").strip()[:500],
               exaggeration={"calm": 0.3, "normal": 0.5, "rich": 0.8}.get(p.get("emotion"), 0.5))
    def say(m):
        J["msg"] = m
    try:
        data = tts_models.generate(ROOT, engine, job, out, say, cancel=lambda: J.get("cancel"))
    finally:
        out.unlink(missing_ok=True)
    if J.get("cancel"):
        raise Cancelled("중단했어요.")
    info = dict(kind="tts", prompt=text[:200], text=text[:5000], engine=engine, voice=speaker or ("내 목소리 샘플" if ref else "기본"), language=lang, speed=speed)
    return [(data, info, ".wav")]


def do_vid(p, J):
    if p.get("wan_ver") == "14b":
        return do_vid14(p, J)
    if p.get("wan_ver") in ("ltx", "vace", "s2v"):
        return do_vid_more(p, J)
    """Wan 2.2 5B 로 영상 만들기(글→영상, 이미지를 올리면 그 이미지에서 시작). 결과: [(바이트, 확장자, 정보)]"""
    for node, why in (("Wan22ImageToVideoLatent", "Wan 2.2 영상 노드"), ("CreateVideo", "영상 만들기 노드"), ("SaveVideo", "영상 저장 노드")):
        if not has_node(node):
            raise RuntimeError(f"이 ComfyUI 에는 {why}({node})가 없어요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
    ct = caps().get("clip_types") or []
    if ct and "wan" not in ct:
        raise RuntimeError("이 ComfyUI 는 Wan 텍스트 인코더 형식을 지원하지 않아요. ComfyUI 를 업데이트해 주세요.")
    f = wan_parts(p)
    miss = [n for n, k in (("Wan 2.2 5B 모델", "unet"), ("UMT5 텍스트 인코더", "te"), ("Wan 2.2 VAE", "vae")) if not f[k]]
    if miss:
        raise RuntimeError("없는 파일: " + ", ".join(miss) + ". '설치와 모델' 탭에서 'Wan 2.2 영상'을 설치해 주세요.")
    rng = random.Random(seed_of(p))
    text, _ = prep(p, J, "caption", rng)
    if not text.strip():
        raise ValueError("어떤 영상을 만들지 프롬프트를 적어 주세요.")
    if blocked(text):
        raise ValueError(BLOCK_MSG)
    try:
        w, h = (int(x) for x in (p.get("size") or "832x480").split("x"))
    except ValueError:
        w, h = 832, 480
    img = load_img(p["image"]) if p.get("image") else None
    if img is not None and p.get("keep_ratio"):      # 올린 이미지의 가로세로 비율을 따라가요 (면적은 고른 크기와 비슷하게)
        k = (w * h / (img.width * img.height)) ** 0.5
        w, h = img.width * k, img.height * k
    w, h = (clamp(int(round(x / 32)) * 32, 256, 1280) for x in (w, h))
    fps = clamp(num(p, "fps", 24, int), 8, 30)
    sec = clamp(num(p, "sec", 3.0), 1.0, 10.0)
    frames = clamp(int(round(sec * fps / 4)) * 4 + 1, 9, 241)
    seed = seed_of(p)
    vram = (GPU or {}).get("vram_gb", 0)
    if vram and w * h * frames > 832 * 480 * 49 * (2.6 if vram >= 16 else 1.7 if vram >= 12 else 1.0):
        warn(J, f"이 길이·크기는 VRAM {vram}GB 에 버거울 수 있어요. 메모리 부족 오류가 나면 길이를 줄이거나 크기를 낮춰 보세요.")
    q = dict(unet=f["unet"], te=f["te"], vae=f["vae"], prompt=text, negative=(p.get("negative") or "").strip() or flows.WAN_NEG,
             seed=seed, w=w, h=h, frames=frames, fps=fps, steps=clamp(num(p, "steps", 20, int), 1, 60), cfg=clamp(num(p, "cfg", 5.0), 1.0, 20.0),
             sampler=p.get("sampler") or "uni_pc", scheduler=p.get("scheduler") or "simple", shift=clamp(num(p, "shift", 8.0), 1.0, 20.0))
    if q["sampler"] not in (caps()["samplers"] or [q["sampler"]]):
        q["sampler"] = "euler"
    start = put_input(ImageOps.fit(img, (w, h), RS.LANCZOS), J) if img is not None else None
    J["msg"] = f"영상 만드는 중 ({w}×{h}, {frames}프레임) — 몇 분 걸릴 수 있어요"
    res = run_wf(flows.wf_video(q, start), J, raw=True)
    info = dict(kind="vid", prompt=text, negative=q["negative"], seed=seed, w=w, h=h, steps=q["steps"], cfg=q["cfg"], model=f["unet"],
                frames=frames, fps=fps, start_image=bool(start))
    return [(data, info, Path(name).suffix.lower() or ".mp4") for name, data in res[:1]]


def ltx_models():
    return [n for n in files("checkpoints") if "ltx" in n.lower()]


def put_audio(data_url, J):
    """올린 소리(data URL)를 ComfyUI 입력 폴더에 저장하고 파일 이름을 돌려줘요."""
    head, _, b64 = str(data_url or "").partition(",")
    ext = next((e for k, e in (("wav", ".wav"), ("mpeg", ".mp3"), ("mp3", ".mp3"), ("ogg", ".ogg"), ("flac", ".flac"), ("mp4", ".m4a"), ("aac", ".m4a"), ("webm", ".webm")) if k in head), ".wav")
    try:
        raw = base64.b64decode(b64)
    except Exception:  # noqa: BLE001
        raise ValueError("소리 파일을 읽지 못했어요.")
    if len(raw) < 1000:
        raise ValueError("소리 파일이 비어 있어요.")
    name = f"hub_{uuid.uuid4().hex[:10]}{ext}"
    (COMFY / "input").mkdir(parents=True, exist_ok=True)
    (COMFY / "input" / name).write_bytes(raw)
    J["tmp"].append(COMFY / "input" / name)
    return name


VID_MORE = {"ltx": ("LTX-Video", ("LTXVConditioning", "LTXVScheduler", "EmptyLTXVLatentVideo", "SamplerCustom")),
            "vace": ("Wan VACE", ("WanVaceToVideo", "TrimVideoLatent")),
            "s2v": ("Wan 2.2 S2V", ("WanSoundImageToVideo", "WanSoundImageToVideoExtend", "LatentConcat", "AudioEncoderLoader", "AudioEncoderEncode", "LoadAudio"))}


def vid_more_state():
    """LTX-Video · Wan VACE · Wan S2V 모델이 있는지(화면 안내용)."""
    dm, te, va = files("diffusion_models"), files("text_encoders"), files("vae")
    wan = bool(_pick(te, "umt5")) and bool(_pick(va, "wan_2.1_vae", "wan2.1", ("wan", "2.1")))
    return {"ltx": bool(ltx_models()) and bool(_pick(te, "t5xxl")), "vace": wan and any("vace" in n.lower() for n in dm),
            "s2v": wan and any("s2v" in n.lower() for n in dm) and bool(_pick(files("audio_encoders"), "wav2vec"))}


def do_vid_more(p, J):
    """LTX-Video(빠른 글·이미지→영상) / Wan VACE(참고 이미지 유지 영상) / Wan 2.2 S2V(사진+목소리 → 말하는 영상)."""
    ver = p["wan_ver"]
    title, nodes = VID_MORE[ver]
    gone = [n for n in nodes + ("CreateVideo", "SaveVideo") if not has_node(n)]
    if gone:
        raise RuntimeError(f"이 ComfyUI 에는 {title} 에 필요한 노드({', '.join(gone)})가 없어요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
    rng = random.Random(seed_of(p))
    text, _ = prep(p, J, "caption", rng)
    if not text.strip():
        raise ValueError("어떤 영상을 만들지 프롬프트를 적어 주세요.")
    if blocked(text):
        raise ValueError(BLOCK_MSG)
    try:
        w, h = (int(x) for x in (p.get("size") or "832x480").split("x"))
    except ValueError:
        w, h = 832, 480
    img = load_img(p["image"]) if p.get("image") else None
    if img is not None and p.get("keep_ratio"):
        k = (w * h / (img.width * img.height)) ** 0.5
        w, h = img.width * k, img.height * k
    w, h = (clamp(int(round(x / 32)) * 32, 256, 1280) for x in (w, h))
    seed, te, va = seed_of(p), files("text_encoders"), files("vae")
    neg = (p.get("negative") or "").strip()
    if ver == "ltx":
        ms = ltx_models()
        t5 = _pick(te, "t5xxl_fp16", "t5xxl")
        miss = [n for n, v in (("LTX-Video 모델", ms), ("T5-XXL 텍스트 인코더", t5)) if not v]
        if miss:
            raise RuntimeError("없는 파일: " + ", ".join(miss) + ". '설치와 모델' 탭의 영상 분류에서 'LTX-Video'를 설치해 주세요.")
        fps = clamp(num(p, "fps", 24, int), 8, 30)
        frames = clamp(int(round(clamp(num(p, "sec", 4.0), 1.0, 10.0) * fps / 8)) * 8 + 1, 9, 257)
        dist = "distill" in ms[0].lower()
        q = dict(ckpt=ms[0], te=t5, prompt=text, negative=neg or "worst quality, inconsistent motion, blurry, jittery, distorted", seed=seed,
                 w=w, h=h, frames=frames, fps=fps, steps=clamp(num(p, "steps", 8 if dist else 30, int), 1, 60), cfg=1.0 if dist else clamp(num(p, "cfg", 3.0), 1.0, 10.0))
        start = put_input(ImageOps.fit(img, (w, h), RS.LANCZOS), J) if img is not None else None
        J["msg"] = f"LTX-Video 로 영상 만드는 중 ({w}×{h}, {frames}프레임)"
        g, model = flows.wf_ltx(q, start), ms[0]
    else:
        unet = vace_model() if ver == "vace" else next((n for n in files("diffusion_models") if ver in n.lower()), None)
        umt5 = _pick(te, "umt5")
        vae21 = _pick(va, "wan_2.1_vae", "wan2.1", ("wan", "2.1"))
        need = [("Wan VACE 모델" if ver == "vace" else "Wan 2.2 S2V 모델", unet), ("UMT5 텍스트 인코더", umt5), ("Wan 2.1 VAE", vae21)]
        enc = None
        if ver == "s2v":
            enc = _pick(files("audio_encoders"), "wav2vec2", "wav2vec")
            need.append(("음성 인코더(wav2vec2)", enc))
        miss = [n for n, v in need if not v]
        if miss:
            raise RuntimeError("없는 파일: " + ", ".join(miss) + f". '설치와 모델' 탭의 영상 분류에서 '{title}'을 설치해 주세요.")
        if img is None:
            raise ValueError("참고할 사진을 올려 주세요." if ver == "vace" else "말하게 할 인물 사진을 올려 주세요.")
        fps = 16
        if ver == "s2v":
            if not p.get("audio"):
                raise ValueError("목소리(소리 파일)를 올려 주세요. 음성 만들기 결과나 녹음 파일을 쓸 수 있어요.")
            sec = clamp(num(p, "sec", 4.8), 1.0, 30.0)
            chunks = max(1, math.ceil(sec / 4.8 - 0.05))                    # 약 5초(77프레임)씩 이어 그려요, 최대 30초
            frames = 77 if chunks > 1 else clamp(int(round(sec * fps / 4)) * 4 + 1, 17, 77)
        else:
            chunks = 1
            frames = clamp(int(round(clamp(num(p, "sec", 5.0), 1.0, 6.0) * fps / 4)) * 4 + 1, 17, 97)
        q = dict(unet=unet, te=umt5, vae=vae21, prompt=text, negative=neg or flows.WAN_NEG, seed=seed, w=w, h=h, frames=frames, fps=fps,
                 steps=clamp(num(p, "steps", 20, int), 1, 60), cfg=clamp(num(p, "cfg", 5.0 if ver == "vace" else 4.5), 1.0, 20.0),
                 sampler="uni_pc" if "uni_pc" in (caps()["samplers"] or ["uni_pc"]) else "euler", scheduler="simple", shift=8.0, audio_encoder=enc,
                 chunks=chunks if ver == "s2v" else 1)
        ref = put_input(ImageOps.fit(img, (w, h), RS.LANCZOS), J)
        J["msg"] = f"{title} 로 영상 만드는 중 ({w}×{h}, {frames * q['chunks'] if ver == 's2v' else frames}프레임) — 몇 분 걸릴 수 있어요"
        g = flows.wf_vace(q, ref) if ver == "vace" else flows.wf_s2v(q, ref, put_audio(p["audio"], J))
        model = unet
    res = run_wf(g, J, raw=True)
    info = dict(kind="vid", prompt=text, negative=q["negative"], seed=seed, w=w, h=h, steps=q["steps"], cfg=q["cfg"], model=model,
                frames=q["frames"] * q.get("chunks", 1), fps=q["fps"], start_image=img is not None, video_model=title)
    return [(data, info, Path(name).suffix.lower() or ".mp4") for name, data in res[:1]]


def feat_3d(p, J):
    """사진 한 장 → 3D 모델(GLB, Hunyuan3D 2). 결과: [(바이트, 정보, '.glb')]"""
    ck = next((n for n in files("checkpoints") if "hunyuan3d" in n.lower() or "hy3d" in n.lower()), None)
    if not ck:
        raise RuntimeError("Hunyuan3D 모델이 없어요. '설치와 모델' 탭의 3D 분류에서 'Hunyuan3D 2'를 설치해 주세요.")
    img = load_img(p["image"])
    if max(img.size) > 1024:
        k = 1024 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), RS.LANCZOS)
    q = dict(ckpt=ck, seed=seed_of(p), steps=clamp(num(p, "steps", 30, int), 5, 100), cfg=clamp(num(p, "cfg", 5.0), 1.0, 15.0),
             octree=int(p.get("octree") or 256) if str(p.get("octree") or "256") in ("128", "256", "384", "512") else 256)
    J["msg"] = "3D 모델 만드는 중 — 1~3분 걸릴 수 있어요"
    res = run_wf(flows.wf_3d(q, put_input(img, J)), J, raw=True)
    glb = [(n, d) for n, d in res if n.lower().endswith(".glb")] or res
    info = dict(kind="3d", seed=q["seed"], steps=q["steps"], cfg=q["cfg"], model=ck, octree=q["octree"])
    return [(glb[0][1], info, ".glb")]


VPOST = {"interp": ("RIFE VFI", "ComfyUI-Frame-Interpolation", "프레임 늘리기"), "upscale": ("ImageUpscaleWithModel", "", "업스케일"),
         "webp": ("SaveAnimatedWEBP", "", "WebP 변환"), "gif": ("", "", "GIF 변환")}


def vpost_gif(src, p, J):
    """영상 → GIF (ffmpeg 로 색표를 만들어 화질을 살려요, ComfyUI 없이)."""
    ff = vmix.find_ffmpeg(PY, ROOT)
    if not ff:
        raise RuntimeError("GIF 로 바꾸려면 ffmpeg 가 필요해요. 설치와 모델 > 내 PC 점검의 [빠진 부품 설치]로 imageio-ffmpeg 를 설치해 주세요.")
    fps, width = clamp(num(p, "gif_fps", 12, int), 5, 30), clamp(num(p, "gif_w", 480, int), 160, 1280)
    out = ROOT / "cache" / f"gif_{uuid.uuid4().hex[:8]}.gif"
    out.parent.mkdir(parents=True, exist_ok=True)
    J["msg"] = "GIF 로 바꾸는 중"
    vf = f"fps={fps},scale='min(iw,{width})':-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=sierra2_4a"
    try:
        r = subprocess.run([str(ff), "-y", "-v", "error", "-i", str(src), "-vf", vf, "-loop", "0", str(out)], capture_output=True, text=True, timeout=600,
                           **({"creationflags": 0x08000000} if os.name == "nt" else {}))
        if r.returncode != 0 or not out.is_file():
            raise RuntimeError("GIF 로 바꾸지 못했어요: " + (r.stderr or "").strip()[-300:])
        data = out.read_bytes()
    finally:
        out.unlink(missing_ok=True)
    return [(data, dict(kind="vpost", op="gif", fps=fps, width=width, source=src.name), ".gif")]


def do_vpost(p, J):
    """만든 영상을 다듬어요: 프레임 늘리기(RIFE)·업스케일·움직이는 WebP. 결과: [(바이트, 정보, 확장자)]"""
    op = p.get("op")
    if op not in VPOST:
        raise ValueError("알 수 없는 영상 작업이에요.")
    src = out_path(str(p.get("video") or "")[5:] if str(p.get("video") or "").startswith("/out/") else "")
    if src.suffix.lower() not in (".mp4", ".webm") or not src.is_file():
        raise ValueError("다듬을 영상을 찾을 수 없어요. (이 앱으로 만든 영상만 다듬을 수 있어요)")
    if op == "gif":
        return vpost_gif(src, p, J)
    node, pack, title = VPOST[op]
    need = ["LoadVideo", "GetVideoComponents", node] + (["CreateVideo", "SaveVideo"] if op != "webp" else []) + (["UpscaleModelLoader"] if op == "upscale" else [])
    miss = [n for n in need if caps()["nodes"] and n not in caps()["nodes"]]
    if miss:
        raise RuntimeError("이 ComfyUI 에는 필요한 노드가 없어요: " + ", ".join(miss) + ". " +
                           (f"확장 '{pack}' 을(를) 설치하고 ComfyUI 를 다시 시작해 주세요." if pack and node in miss else "ComfyUI 를 업데이트해 주세요."))
    try:
        base = json.loads(Path(str(src) + ".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        base = {}
    q = dict(fps=clamp(int(num(base, "fps", 24, int)), 1, 60))
    if op == "upscale":
        q["model"] = p.get("upm") or (files("upscale_models") or [None])[0]
        if not q["model"]:
            raise RuntimeError("업스케일 모델이 없어요. '설치와 모델' 탭에서 업스케일 모델을 설치해 주세요.")
        if base.get("w") and base.get("h") and base.get("frames") and int(base["w"]) * int(base["h"]) * int(base["frames"]) > 832 * 480 * 130:
            warn(J, "프레임이 많은 영상은 업스케일 때 메모리가 많이 들어요. 메모리 부족 오류가 나면 2배 모델을 써 보세요.")
    name = f"hub_{uuid.uuid4().hex[:10]}{src.suffix.lower()}"
    (COMFY / "input").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, COMFY / "input" / name)
    J["tmp"].append(COMFY / "input" / name)
    q["file"] = name
    J["msg"] = f"{title} 중 — 영상 길이에 따라 몇 분 걸릴 수 있어요"
    res = run_wf(flows.wf_vpost(op, q), J, raw=True)
    if not res:
        raise RuntimeError("결과 영상을 받지 못했어요.")
    info = dict(base, kind="vid", post=title, source=src.name)
    if op == "interp":
        info["fps"] = q["fps"] * 2
    return [(res[0][1], info, Path(res[0][0]).suffix.lower() or (".webp" if op == "webp" else ".mp4"))]
