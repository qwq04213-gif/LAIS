# 로컬 AI 스튜디오 허브 — ComfyUI 기능 조회 · 이미지/프롬프트 처리 · ComfyUI 실행 · 진행률
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

# ───────────────────────── ComfyUI 기능 조회 ─────────────────────────
_CAPS = {"t": 0.0, "info": {}, "nodes": set(), "samplers": [], "schedulers": [], "clip_types": []}


def caps(force=False):
    if force or time.time() - _CAPS["t"] > 120:
        try:
            o = http(CUI + "/object_info", timeout=60)
            ks = o.get("KSampler", {}).get("input", {}).get("required", {})
            ct = o.get("CLIPLoader", {}).get("input", {}).get("required", {}).get("type", [[]])
            _CAPS.update(t=time.time(), info=o, nodes=set(o), samplers=list(ks.get("sampler_name", [[]])[0]),
                         schedulers=list(ks.get("scheduler", [[]])[0]), clip_types=list(ct[0]) if ct and isinstance(ct[0], list) else [])
        except Exception:
            pass
    return _CAPS


def has_node(name):
    return name in caps()["nodes"]


# ───────────────────────── 이미지 처리 ─────────────────────────
def load_img(data_url):
    im = Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[-1])))
    return ImageOps.exif_transpose(im).convert("RGB")


def load_mask(data_url, size):
    if not data_url:
        return None
    m = Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[-1]))).convert("RGB").getchannel("R")
    m = m.resize(size, RS.BILINEAR).point(lambda v: 255 if v > 127 else 0)
    return m if m.getbbox() else None


def grow_feather(m, grow, feather=None):
    """마스크를 grow 만큼 넓히고 가장자리를 부드럽게(자연스러운 경계 합성용). feather 가 없으면 영역 크기에 맞춰 자동."""
    if grow > 0:
        m = m.filter(ImageFilter.GaussianBlur(grow)).point(lambda v: 255 if v > 6 else 0)
    x0, y0, x1, y1 = m.getbbox()
    return m.filter(ImageFilter.GaussianBlur(feather if feather else max(3, min(x1 - x0, y1 - y0) // 16)))


def plan(img, mask, grow, ctx=0.35, target=1024, feather=None, mult=8):
    """마스크 주변만 잘라 모델 해상도(≈target²)로 맞춥니다. 작은 영역도 고해상도로 그려져 디테일이 좋아집니다."""
    W, H = img.size
    bx0, by0, bx1, by1 = mask.getbbox()
    pad = int(max(bx1 - bx0, by1 - by0) * ctx) + 24
    x0, y0, x1, y1 = max(0, bx0 - pad), max(0, by0 - pad), min(W, bx1 + pad), min(H, by1 + pad)
    ms = min(512, W, H)
    if x1 - x0 < ms:
        x0 = max(0, min((x0 + x1 - ms) // 2, W - ms)); x1 = x0 + ms
    if y1 - y0 < ms:
        y0 = max(0, min((y0 + y1 - ms) // 2, H - ms)); y1 = y0 + ms
    w, h = x1 - x0, y1 - y0
    s = min((target * target / (w * h)) ** 0.5, 2048 / max(w, h))
    size = (max(64, round(w * s / mult) * mult), max(64, round(h * s / mult) * mult))
    crop = img.crop((x0, y0, x1, y1))
    soft = grow_feather(mask.crop((x0, y0, x1, y1)), grow, feather)
    return (x0, y0), crop, soft, size


def finish(img, pos, crop, soft, res):
    """생성 결과를 부드러운 마스크로 원본에 합성 — 마스크 밖 픽셀은 원본 그대로 유지됩니다."""
    merged = Image.composite(res.resize(crop.size, RS.LANCZOS), crop, soft)
    out = img.copy()
    out.paste(merged, pos)
    return out


def qsize(size, mp=1.0):
    w, h = size
    s = (mp * 1e6 / (w * h)) ** 0.5
    return max(256, round(w * s / 16) * 16), max(256, round(h * s / 16) * 16)


def cover(im, size):
    w, h = size
    s = max(w / im.width, h / im.height)
    r = im.resize((max(w, round(im.width * s)), max(h, round(im.height * s))), RS.LANCZOS)
    x, y = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


def fit_area(im, w, h):
    s = (w * h / (im.width * im.height)) ** 0.5
    return im.resize((max(64, round(im.width * s / 8) * 8), max(64, round(im.height * s / 8) * 8)), RS.LANCZOS)


def spans(n, tile, ov):
    """길이 n 을 tile 크기 조각으로 ov 이상 겹치게 나눕니다."""
    if n <= tile:
        return [(0, n)]
    k = -(-(n - tile) // (tile - ov)) + 1
    return [(round(i * (n - tile) / (k - 1)), round(i * (n - tile) / (k - 1)) + tile) for i in range(k)]


def ramp(size, ov, left, top):
    """타일을 붙일 때 이미 붙은 왼쪽/위쪽과 이어지도록 가장자리를 서서히 투명하게 만드는 마스크."""
    w, h = size
    a, b = Image.new("L", size, 255), Image.new("L", size, 255)
    if left:
        d = ImageDraw.Draw(a)
        for i in range(min(ov, w)):
            d.line([(i, 0), (i, h)], fill=int(255 * (i + 0.5) / ov))
    if top:
        d = ImageDraw.Draw(b)
        for j in range(min(ov, h)):
            d.line([(0, j), (w, j)], fill=int(255 * (j + 0.5) / ov))
    return ImageChops.multiply(a, b)


# ───────────────────────── 프롬프트 처리 ─────────────────────────
LORA_TAG = re.compile(r"<lora:([^:>]+)(?::(-?[\d.]+))?[^>]*>", re.I)


def warn(J, msg):
    if msg not in J.setdefault("warn", []):
        J["warn"].append(msg)


def lora_resolve(name):
    stem, have = Path(name).stem.lower(), files("loras")
    return next((f for f in have if Path(f).stem.lower() == stem), None) or next((f for f in have if stem in f.lower()), None)


def dyn_expand(text, rng):
    """{a|b|c} 중 하나 선택, __이름__ 은 wildcards/이름.txt 의 무작위 한 줄."""
    def wc(m):
        f = ROOT / "wildcards" / (Path(m.group(1)).name + ".txt")
        if f.is_file():
            opts = [l.strip() for l in f.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if l.strip() and not l.lstrip().startswith("#")]
            if opts:
                return rng.choice(opts)
        return m.group(0)

    for _ in range(4):
        new = re.sub(r"__([\w\-.]+)__", wc, text)
        new = re.sub(r"\{([^{}|]*(?:\|[^{}]*)+)\}", lambda m: rng.choice(m.group(1).split("|")).strip(), new)
        if new == text:
            break
        text = new
    return text


def prep(p, J, style, rng):
    """원본 프롬프트 → (정리된 문장, LoRA 태그 목록). 순서: LoRA 태그 추출 → 다이나믹 → 번역."""
    raw = (p.get("prompt") or "").strip()
    if not raw:
        raise ValueError("프롬프트를 입력해 주세요.")
    if blocked(raw):
        raise ValueError(BLOCK_MSG)
    tags = []

    def grab(m):
        tags.append((m.group(1).strip(), float(m.group(2) or 1)))
        return ""

    t = LORA_TAG.sub(grab, raw)
    if p.get("dyn"):
        t = dyn_expand(t, rng)
    t = re.sub(r"[ \t]{2,}", " ", t).strip(" ,\n")
    if p.get("translate") and re.search("[가-힣]", t):
        J["msg"] = "프롬프트 번역 중"
        t = translate_keep_quotes(t, style)
    return t, tags


QUOTE_RX = re.compile(r"\"[^\"\n]{1,200}\"|“[^”\n]{1,200}”|‘[^’\n]{1,200}’|「[^」\n]{1,200}」|(?<![A-Za-z])'[^'\n]{1,200}'(?![A-Za-z])")


def translate_keep_quotes(t, style):
    """따옴표 안 글자(그림에 그대로 넣을 글자)는 번역하지 않고 그대로 둬요. 예: '오늘 영업' 이라고 쓴 간판 → … sign that says "오늘 영업"."""
    keep = []

    def hold(m):
        keep.append(m.group(0)[1:-1])
        return f" QTXT{len(keep) - 1} "
    body = QUOTE_RX.sub(hold, t)
    if not keep:
        return translate(t, style)
    if not re.search("[가-힣]", body):          # 따옴표 밖에는 번역할 한글이 없어요
        return t
    out = translate(body, style)
    lost = []
    for i, s in enumerate(keep):
        tok = f"QTXT{i}"
        if re.search(rf"\b{tok}\b", out):
            out = re.sub(rf"[\"“‘']?\b{tok}\b[\"”’']?", lambda _m, s=s: f'"{s}"', out, count=1)
        else:
            lost.append(s)
    if lost:                                        # 번역하면서 자리표시가 사라졌으면 끝에 붙여요
        out = out.rstrip(" .,") + ", with the text " + ", ".join(f'"{s}"' for s in lost)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def pick_profile(p):
    pid = p.get("profile") or "auto"
    if pid == "none":
        return None
    if pid == "auto":
        name = (p.get("ckpt") or "").lower()
        return next((x for x in PROFILES if x.get("match") and re.search(x["match"], name, re.I)), None)
    return next((x for x in PROFILES if x["id"] == pid), None)


def lora_slots(p):
    """lora1, lora2, ... 번호가 몇 개든(개수 제한 없음) 순서대로 읽습니다."""
    ks = sorted((int(m.group(1)), k) for k in p for m in [re.fullmatch(r"lora(\d+)", k)] if m)
    return [(str(p[k]).strip(), num(p, f"{k}_w", 0.8)) for _, k in ks if str(p.get(k) or "").strip()]


def collect_loras(p, tags, J):
    out = lora_slots(p)
    for name, wt in tags:
        f = lora_resolve(name)
        if f:
            out.append((f, wt))
        else:
            warn(J, f"LoRA '{name}' 파일을 찾지 못해 건너뛰었어요.")
    seen, res = set(), []
    for n, w in out:
        if n not in seen:
            seen.add(n)
            res.append((n, w))
    return res[:64]


def sd(p, text, tags, J):
    """SDXL 계열 파라미터를 하나의 dict(q)로 정리."""
    prof = pick_profile(p) or {}
    final = (prof.get("prefix", "") + text + prof.get("suffix", "")).strip()
    if blocked(final):
        raise ValueError(BLOCK_MSG)
    base, user = prof.get("negative") or DEFAULT_NEG, (p.get("negative") or "").strip()
    neg = (base + ", " + user if p.get("pneg") else user) if user else base
    if flows_sex(final):
        neg += ", child, loli, shota, underage, aged down"
    ck = p.get("ckpt") or (files("checkpoints") or [None])[0]
    if not ck:
        raise RuntimeError("체크포인트가 없습니다. '설치와 모델' 탭에서 설치하거나 ComfyUI\\models\\checkpoints 에 넣어 주세요.")
    vpred = bool(p.get("vpred"))
    pag = clamp(num(p, "pag", 0.0), 0.0, 10.0)
    if pag and not has_node("PerturbedAttentionGuidance"):
        warn(J, "이 ComfyUI 에는 PAG 노드가 없어 건너뛰었어요(ComfyUI 업데이트 필요).")
        pag = 0.0
    return dict(ckpt=ck, vae=p.get("vae") or None, loras=collect_loras(p, tags, J),
                clip_skip=clamp(num(p, "clip_skip", 2, int), 1, 12), vpred=vpred,
                rescale=clamp(num(p, "rescale", 0.7 if vpred else 0.0), 0.0, 1.0), pag=pag,
                prompt=final, negative=neg, seed=seed_of(p), steps=clamp(num(p, "steps", 28, int), 1, 150),
                cfg=clamp(num(p, "cfg", 5.5), 0.0, 30.0), sampler=p.get("sampler") or "euler_ancestral",
                scheduler=p.get("scheduler") or "normal", denoise=clamp(num(p, "denoise", 0.9), 0.0, 1.0))


def flows_sex(text):
    return bool(SEX.search(text))


def info_sd(q, size, kind, **extra):
    ex = dict(extra)
    if q["vpred"]:
        ex["V-Prediction"] = "true"
    if q["rescale"]:
        ex["CFG rescale"] = q["rescale"]
    if q["pag"]:
        ex["PAG scale"] = q["pag"]
    if q.get("vae"):
        ex["VAE"] = q["vae"]
    return dict(kind=kind, prompt=q["prompt"], negative=q["negative"], steps=q["steps"], cfg=q["cfg"],
                sampler=q["sampler"], scheduler=q["scheduler"], seed=q["seed"], w=size[0], h=size[1],
                model=q["ckpt"], clip_skip=q["clip_skip"], loras=[[n, w] for n, w in q["loras"]], extra=ex)


# ───────────────────────── ComfyUI 실행 ─────────────────────────
def wait_comfy():
    for _ in range(180):
        if alive(CUI + "/system_stats"):
            return
        if not PY.exists():
            break
        time.sleep(1)
    raise RuntimeError("이미지 엔진(ComfyUI)이 실행 중이 아닙니다. install.bat 실행 여부와 logs\\comfyui.log 를 확인하세요.")


def put_input(img, J):
    name = f"hub_{uuid.uuid4().hex[:10]}.png"
    (COMFY / "input").mkdir(parents=True, exist_ok=True)
    img.save(COMFY / "input" / name, compress_level=1)   # 임시 파일이라 압축을 줄여 저장 시간을 아껴요
    J["tmp"].append(COMFY / "input" / name)
    return name


def comfy_err(e):
    try:
        d = json.loads(e.read())
        parts = [d.get("error", {}).get("message", "")]
        for v in d.get("node_errors", {}).values():
            parts += [f'{v.get("class_type")}: {x.get("message")} {x.get("details", "")}' for x in v.get("errors", [])]
        return "ComfyUI: " + " | ".join(p for p in parts if p)
    except Exception:
        return f"ComfyUI HTTP {e.code}"


def comfy_cancel(pid):
    """대기 중이면 대기열에서 빼고, 실행 중이면 ComfyUI 에 중단 신호를 보냅니다."""
    try:
        q = http(CUI + "/queue", timeout=5)
        if pid in [x[1] for x in q.get("queue_pending", [])]:
            http(CUI + "/queue", {"delete": [pid]}, 5)
        if pid in [x[1] for x in q.get("queue_running", [])]:
            http(CUI + "/interrupt", {}, 5)
    except Exception:
        pass


# ── ComfyUI 진행률(웹소켓). 표준 라이브러리만으로 최소 구현: 연결 실패하면 시간 기반 추정으로 대신해요 ──
WSP = {}          # prompt_id -> (value, max)
EXE = {}          # prompt_id -> 지금 실행 중인 노드 번호(문자열)
LOAD_CLS = {"CheckpointLoaderSimple", "UNETLoader", "CLIPLoader", "DualCLIPLoader", "VAELoader", "LoraLoader", "LoraLoaderModelOnly",
            "ControlNetLoader", "UpscaleModelLoader", "CLIPTextEncode", "TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus", "TextEncodeQwenImage21", "VAEEncode"}
WS_STATE = {"on": False, "ok": False}


def _ws_read(sock):
    def rd(n):
        b = b""
        while len(b) < n:
            c = sock.recv(n - len(b))
            if not c:
                raise ConnectionError
            b += c
        return b
    while True:
        h = rd(2)
        op, ln = h[0] & 15, h[1] & 127
        if ln == 126:
            ln = int.from_bytes(rd(2), "big")
        elif ln == 127:
            ln = int.from_bytes(rd(8), "big")
        if h[1] & 128:
            mask = rd(4)
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(rd(ln)))
        else:
            data = rd(ln)
        if op == 8:
            raise ConnectionError
        if op == 9:   # ping -> pong (클라이언트 프레임은 마스크 필요)
            m = os.urandom(4)
            sock.sendall(bytes([0x8A, 0x80 | len(data)]) + m + bytes(b ^ m[i % 4] for i, b in enumerate(data)))
        elif op == 1:
            yield data.decode("utf-8", "replace")


def ws_loop():
    import base64 as b64
    import socket
    while True:
        try:
            u = urllib.parse.urlparse(CUI)
            sock = socket.create_connection((u.hostname, u.port or 80), timeout=5)
            key = b64.b64encode(os.urandom(16)).decode()
            sock.sendall((f"GET /ws?clientId={CID} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                          f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                c = sock.recv(1)
                if not c:
                    raise ConnectionError
                buf += c
            if b" 101 " not in buf.split(b"\r\n")[0]:
                raise ConnectionError
            sock.settimeout(None)
            WS_STATE["ok"] = True
            for msg in _ws_read(sock):
                try:
                    d = json.loads(msg)
                except ValueError:
                    continue
                x = d.get("data") or {}
                if d.get("type") == "progress" and x.get("prompt_id"):
                    WSP[x["prompt_id"]] = (x.get("value", 0), max(1, x.get("max", 1)), str(x.get("node") or ""))
                elif d.get("type") == "executing" and x.get("prompt_id"):
                    if x.get("node") is None:
                        EXE.pop(x["prompt_id"], None)
                    else:
                        EXE[x["prompt_id"]] = str(x["node"])
        except Exception:
            WS_STATE["ok"] = False
            time.sleep(3)


def ws_start():
    if not WS_STATE["on"]:
        WS_STATE["on"] = True
        threading.Thread(target=ws_loop, daemon=True).start()


def phase_of(wf, pid):
    """지금 하는 일: wait(대기) / load(모델 불러오는 중) / gen(그리는 중). 웹소켓이 없으면 구분하지 않고 gen 으로 둬요."""
    if not WS_STATE["ok"] or pid in WSP:
        return "gen"
    ex = EXE.get(pid)
    if ex is None:
        return "wait"
    c = wf.get(ex, {}).get("class_type", "")
    return "load" if c in LOAD_CLS or c.startswith("KSampler") else "gen"


def set_progress(J, frac, est=False):
    """작업 전체 진행률. 여러 번 나눠 실행하는 작업(여러 장, 타일)은 pi/pn 으로 몫을 나눠요."""
    pi, pn = J.get("pi", 0), max(1, J.get("pn", 1))
    J["progress"] = round(min(1.0, (pi + max(0.0, min(1.0, frac))) / pn), 3)
    J["pest"] = est


USED_FILE = ROOT / "models_used.json"
_USED_LOCK = threading.Lock()


def used_load():
    try:
        d = json.loads(USED_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def used_save(d):
    try:
        USED_FILE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def note_models_used(wf, now=None):
    """작업에 쓰인 모델 파일의 '마지막으로 쓴 날'을 기록해요(모델 정리 도우미가 써요). 실패해도 작업에는 영향이 없어요."""
    try:
        names = set()
        for node in wf.values():
            for v in (node.get("inputs") or {}).values():
                if isinstance(v, str) and Path(v.replace("\\", "/")).suffix.lower() in EXT:
                    names.add(Path(v.replace("\\", "/")).name)
        if not names:
            return
        now = now or time.time()
        with _USED_LOCK:
            d = used_load()
            for fd in FOLDERS:
                base = MODELS / fd
                if base.is_dir():
                    for n in names:
                        if (base / n).is_file():
                            d[fd + "/" + n] = now
            used_save(d)
    except Exception:
        pass


MAIN_KEYS = ("ckpt_name", "unet_name")
SIDE_KEYS = ("lora_name", "model_name", "control_net_name")


def wf_models(wf):
    """워크플로가 불러오는 모델 이름(본 모델 먼저, 그다음 LoRA·업스케일·ControlNet). 확장자는 빼요."""
    main, side = [], []
    for node in wf.values():
        for k, v in (node.get("inputs") or {}).items():
            if isinstance(v, str) and Path(v.replace("\\", "/")).suffix.lower() in EXT:
                n = Path(v.replace("\\", "/")).stem
                (main if k in MAIN_KEYS else side if k in SIDE_KEYS else []).append(n)
    return list(dict.fromkeys(main)) + [x for x in dict.fromkeys(side) if x not in main]


def run_wf(wf, J, raw=False):
    """raw=True 이면 이미지 대신 결과 파일(영상) 바이트를 [(파일명, 바이트)] 로 돌려줘요."""
    check_cancel(J)
    note_models_used(wf)
    try:
        ms = wf_models(wf)
        if ms:
            J["models"] = ms[:6]
            J["model_desc"] = ms[0] + (f" + {len(ms) - 1}개" if len(ms) > 1 else "")
    except Exception:  # noqa: BLE001
        pass
    try:
        pid = http(CUI + "/prompt", {"prompt": wf, "client_id": CID}, 30)["prompt_id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(comfy_err(e)) from None
    J["pid"] = pid
    t0 = time.time()
    # 그리는 단계(KSampler 등)가 여러 개인 작업(긴 말하는 영상, 하이레스 픽스 …)은 단계마다 0→100% 가 반복돼 보이지 않게 전체 몫으로 나눠요
    samp = sorted((k for k, n in wf.items() if "Sampler" in n.get("class_type", "") and "Select" not in n.get("class_type", "")), key=lambda k: [int(x) if x.isdigit() else 0 for x in str(k).split(":")])
    base_msg = J.get("msg", "")
    while True:
        if J.get("cancel"):
            comfy_cancel(pid)
            raise Cancelled("사용자가 중단했어요.")
        h = http(CUI + f"/history/{pid}", timeout=15).get(pid)
        J["phase"] = phase_of(wf, pid) if not h else "gen"
        if pid in WSP:
            v, m, nd = (WSP[pid] + ("",))[:3]
            multi = len(samp) > 1 and nd in samp
            fr = ((samp.index(nd) + v / m) / len(samp)) if multi else v / m
            set_progress(J, fr * 0.97)                    # 남은 시간은 작업 전체 진행률로 한 곳에서 어림해요(eta_update)
            if multi:
                J["msg"] = base_msg + f" · {samp.index(nd) + 1}/{len(samp)}단계"
        elif not h:   # 웹소켓 신호가 없으면 시간 기반 추정(실제보다 부정확해요)
            set_progress(J, 0.95 * (1 - 2.718 ** (-(time.time() - t0) / 40)), est=True)
        if h:
            WSP.pop(pid, None)
            set_progress(J, 1.0, est=J.get("pest", False))
            for ev, d in h.get("status", {}).get("messages", []):
                if ev == "execution_error":
                    msg = d.get("exception_message", "실행 오류")
                    raise RuntimeError(msg)
            imgs = []
            for o in h.get("outputs", {}).values():
                if o.get("text"):                     # '값 미리보기' 노드의 글(예: 어림한 화각)
                    J.setdefault("wf_text", []).extend(str(x) for x in o["text"])
                for im in (o.get("images", []) + (o.get("audio", []) + o.get("3d", []) if raw else [])):
                    with urllib.request.urlopen(CUI + "/view?" + urllib.parse.urlencode(im), timeout=300 if raw else 60) as f:
                        data = f.read()
                    imgs.append((Path(im["filename"]).name, data) if raw else Image.open(io.BytesIO(data)).convert("RGB"))
                    if im.get("type") in ("temp", "output") and (raw or im.get("type") == "temp"):   # 미리보기·영상 파일은 읽은 즉시 지워요 (안 그러면 계속 쌓여요)
                        try:
                            (COMFY / im["type"] / im.get("subfolder", "") / Path(im["filename"]).name).unlink(missing_ok=True)
                        except OSError:
                            pass
            try:   # ComfyUI 메모리에 쌓이는 기록도 바로 비워요
                http(CUI + "/history", {"delete": [pid]}, 5)
            except Exception:
                pass
            if not imgs:
                raise RuntimeError("결과 파일이 없습니다." if raw else "결과 이미지가 없습니다.")
            return imgs
        time.sleep(0.3)


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
