#!/usr/bin/env python3
"""로컬 AI 스튜디오 허브.

표준 라이브러리 + Pillow 만 사용합니다 (ComfyUI 포터블의 python_embeded 로 실행).
역할: Ollama / ComfyUI 실행, 웹 UI 제공, 모델 설치, 이미지 작업(마스크 크롭·합성·타일 리파인) 조율,
      이미지 메타데이터 읽기/제거(meta.py), ComfyUI 그래프 생성·사용자 워크플로 실행(flows.py).
"""
import base64, hashlib, io, json, os, random, re, shutil, subprocess, sys, threading, time, uuid, webbrowser
import urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

# ComfyUI 포터블의 python_embeded 는 ._pth 설정 때문에 스크립트 폴더를 import 경로에 넣지 않으므로 직접 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flows
import meta
import modelinfo
import sam

RS = Image.Resampling
HUB = Path(__file__).resolve().parent
WEB = HUB / "web"
ROOT = Path(os.environ.get("STUDIO_ROOT", HUB.parent))
HOME = ROOT / "engine" / "ComfyUI_windows_portable"
COMFY = HOME / "ComfyUI"
PY = HOME / "python_embeded" / "python.exe"
OLLAMA_EXE = ROOT / "engine" / "ollama" / ("ollama.exe" if os.name == "nt" else "ollama")
MODELS, OUT, LOGS = COMFY / "models", ROOT / "outputs", ROOT / "logs"
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
CUI = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
PORT = int(os.environ.get("HUB_PORT", 7860))
CATALOG = json.loads((HUB / "models.json").read_text(encoding="utf-8"))
# 영어 위주/한국어가 약해서 목록에서 뺀 모델(직접 고친 models.json 에 남아 있어도 숨김)
REMOVED_IDS = {"venice-24b", "magmell-12b", "cydonia-24b"}
for _k in ("llm", "image"):
    CATALOG[_k] = [m for m in CATALOG[_k] if m["id"] not in REMOVED_IDS]
CIVITAI = os.environ.get("CIVITAI_URL", "https://civitai.com")
HFURL = os.environ.get("HF_URL", "https://huggingface.co")
GHURL = os.environ.get("GITHUB_URL", "https://github.com")
NODEMAP_URL = os.environ.get("NODEMAP_URL", "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/extension-node-map.json")
PROFILES = json.loads((HUB / "profiles.json").read_text(encoding="utf-8"))
FOLDERS = {"checkpoints", "loras", "diffusion_models", "text_encoders", "vae", "upscale_models", "controlnet", "embeddings", "sam"}
EXT = (".safetensors", ".ckpt", ".pth", ".pt", ".gguf", ".bin")
DEFAULT_NEG = ("lowres, bad anatomy, bad hands, extra digits, missing fingers, worst quality, "
               "jpeg artifacts, watermark, text, signature")

try:
    VERSION = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip().splitlines()[0]
except Exception:
    VERSION = "2026.10.17"

procs, JOBS, TASKS = [], {}, []
STATE = {"last": None}
CID = uuid.uuid4().hex


def log(*a):
    print(*a, flush=True)


class Cancelled(Exception):
    pass


def check_cancel(J):
    if J.get("cancel"):
        raise Cancelled("사용자가 중단했어요.")


def register_root():
    """업데이트 파일이 이 폴더를 찾을 수 있게 설치 경로를 기억해 둡니다."""
    try:
        d = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LocalAI-Studio"
        d.mkdir(parents=True, exist_ok=True)
        (d / "path.txt").write_text(str(ROOT), encoding="utf-8")
    except Exception:
        pass


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ───────────────────────── 기본 도구 ─────────────────────────
def http(url, data=None, timeout=15):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def alive(url):
    try:
        urllib.request.urlopen(url, timeout=2).close()
        return True
    except Exception:
        return False


def num(p, k, d, cast=float):
    try:
        return cast(p.get(k, d))
    except (TypeError, ValueError):
        return d


def seed_of(p):
    s = num(p, "seed", -1, int)
    return s if s >= 0 else random.randint(0, 2**32 - 1)


def gpu():
    try:
        o = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total",
                                     "--format=csv,noheader,nounits"], text=True, timeout=8).splitlines()[0]
        name, mem = (x.strip() for x in o.rsplit(",", 1))
        return {"name": name, "vram_gb": round(int(mem) / 1024)}
    except Exception:
        return None


GPU = None
_LIVE = {"t": 0.0, "v": None}


def _num(x):
    try:
        return float(x)
    except Exception:
        return None


def gpu_live():
    """실시간 GPU 상태(VRAM·사용률·온도·전력). nvidia-smi 우선, 안 되면 ComfyUI /system_stats."""
    now = time.time()
    if now - _LIVE["t"] < 1.5:
        return _LIVE["v"]
    v = None
    try:
        o = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,power.limit",
             "--format=csv,noheader,nounits"], text=True, timeout=4).splitlines()[0]
        a = [_num(x.strip()) for x in o.split(",")]
        a += [None] * (6 - len(a))
        if a[0] is not None and a[1]:
            v = {"used_mb": int(a[0]), "total_mb": int(a[1]), "util": None if a[2] is None else int(a[2]),
                 "temp": None if a[3] is None else int(a[3]),
                 "power": None if a[4] is None else round(a[4]), "power_max": None if a[5] is None else round(a[5])}
    except Exception:
        v = None
    if v is None:
        try:
            d = (json.load(urllib.request.urlopen(CUI + "/system_stats", timeout=2)).get("devices") or [{}])[0]
            tot, free = d.get("vram_total"), d.get("vram_free")
            if tot:
                v = {"used_mb": int((tot - free) / 1048576), "total_mb": int(tot / 1048576),
                     "util": None, "temp": None, "power": None, "power_max": None}
        except Exception:
            v = None
    _LIVE["t"], _LIVE["v"] = now, v
    return v


def files(sub):
    d = MODELS / sub
    return sorted(p.name for p in d.iterdir() if p.is_file() and p.suffix.lower() in EXT) if d.is_dir() else []


def find(sub, *keys):
    return next((n for n in files(sub) if all(k in n.lower() for k in keys)), None)


def llms():
    try:
        return [m["name"] for m in http(OLLAMA + "/api/tags", timeout=3).get("models", [])]
    except Exception:
        return []


def _front_window(title, before):
    """Windows: 브라우저가 포그라운드라 탐색기가 뒤에 열려요. 새로 뜬(또는 이미 열려 있던) 탐색기 창을 찾아 앞으로 가져옵니다.
    포그라운드 잠금은 (1) 앞 창의 입력 스레드에 붙기 (2) 잠깐 '항상 위'로 올렸다 내리기 (3) SwitchToThisWindow 를 차례로 써서 풀어요."""
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.GetForegroundWindow.restype = wintypes.HWND
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    for fn in (u.ShowWindow, u.SetForegroundWindow, u.BringWindowToTop, u.IsIconic):
        fn.argtypes = [wintypes.HWND] + ([ctypes.c_int] if fn is u.ShowWindow else [])
    u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
    new, same = [], []

    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(hwnd, cls, 64)
            if cls.value in ("CabinetWClass", "ExploreWClass"):
                buf = ctypes.create_unicode_buffer(260)
                u.GetWindowTextW(hwnd, buf, 260)
                if hwnd not in before:
                    new.append(hwnd)
                elif buf.value.lower() == title.lower():
                    same.append(hwnd)
        return True
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    for _ in range(40):
        new.clear(); same.clear()
        u.EnumWindows(proto(cb), 0)
        hwnd = (new or same or [None])[0]
        if hwnd:
            break
        time.sleep(0.1)
    else:
        log("[폴더 창을 찾지 못했어요]", title)
        return
    time.sleep(0.15)   # 창이 완전히 자리 잡은 뒤에
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)
    fg = u.GetForegroundWindow()
    me, theirs = k.GetCurrentThreadId(), (u.GetWindowThreadProcessId(fg, None) if fg else 0)
    attached = bool(theirs and theirs != me and u.AttachThreadInput(me, theirs, True))
    try:
        u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)
        u.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0003 | 0x0040)   # TOPMOST, NOMOVE|NOSIZE|SHOWWINDOW
        u.SetWindowPos(hwnd, wintypes.HWND(-2), 0, 0, 0, 0, 0x0003 | 0x0040)   # NOTOPMOST
        u.BringWindowToTop(hwnd)
        ok = u.SetForegroundWindow(hwnd)
        if not ok:
            u.SwitchToThisWindow(hwnd, True)
    finally:
        if attached:
            u.AttachThreadInput(me, theirs, False)
    log("[폴더 창 앞으로]", title, "성공" if u.GetForegroundWindow() == hwnd else "시도함(앞으로 안 왔을 수 있음)")


def _explorer_windows():
    import ctypes
    from ctypes import wintypes
    u, cur = ctypes.windll.user32, set()

    def cb(hwnd, _):
        cur.add(hwnd)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return cur


def _safe(f, *a):
    try:
        f(*a)
    except Exception as e:  # noqa: BLE001
        log("[창 앞으로 가져오기 실패]", e)


def open_folder(p, select=None):
    """폴더를 열어요. select 파일이 있으면(Windows) 그 파일을 선택한 채로 열어요."""
    p.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            before = _explorer_windows()
            if select is not None and Path(select).is_file():
                subprocess.Popen(["explorer", "/select,", str(select)])
            else:
                os.startfile(str(p))  # noqa
            threading.Thread(target=lambda: _safe(_front_window, p.name or str(p), before), daemon=True).start()
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(p)])
    except Exception:
        pass


# ───────────────────────── 안전 장치 ─────────────────────────
# 미성년자 + 성적 표현이 함께 나오면 차단하는 최소한의 키워드 필터입니다(완벽하지 않음).
MINOR = re.compile(r"loli|shota|underage|under-age|pre-?teen|toddler|infant|\bminors?\b|\bchild(?:ren)?\b|\bkids?\b|"
                   r"\bteen(?:age[rd]?)?s?\b|little (?:girl|boy)|school ?(?:girl|boy)|"
                   r"미성년|어린이|초등학생|중학생|고등학생|여고생|남고생|초딩|중딩|로리|쇼타", re.I)
SEX = re.compile(r"nsfw|nude|naked|nipple|topless|porn|\bsex|erotic|explicit|lewd|genital|bdsm|hentai|"
                 r"누드|알몸|노출|야한|야동|섹스|성관계|성행위|젖꼭지|음란|에로|포르노", re.I)
AGE = re.compile(r"\b(\d{1,2})\s*[- ]?(?:years?|yrs?|yo|y/o)\b|(\d{1,2})\s*(?:살|세)", re.I)


def blocked(text):
    t = text or ""
    young = MINOR.search(t) or any(int(a or b) < 18 for a, b in AGE.findall(t))
    return bool(young and SEX.search(t))


BLOCK_MSG = "미성년자와 관련된 성적 내용은 지원하지 않습니다."


# ───────────────────────── 엔진 실행 / VRAM 관리 ─────────────────────────
def tidy():
    """실행할 때마다 쌓이는 찌꺼기를 치워요: 커진 로그 파일 교체, 남은 임시 이미지·미리보기 삭제(결과물·모델은 건드리지 않아요)."""
    now = time.time()
    try:
        for n in ("ollama.log", "comfyui.log", "hub.log"):
            f = LOGS / n
            if f.is_file() and f.stat().st_size > 10 * 1024 * 1024:
                old = LOGS / (n + ".old")
                old.unlink(missing_ok=True)
                f.replace(old)
    except OSError:
        pass
    for folder, pat, age in ((COMFY / "input", "hub_*.png", 3600), (COMFY / "temp", "*", 2 * 86400)):
        try:
            for f in folder.glob(pat):
                if f.is_file() and now - f.stat().st_mtime > age:
                    f.unlink(missing_ok=True)
        except OSError:
            pass


def speed_args():
    """ComfyUI 가 지원할 때만 쓰는 안전한 속도 옵션(fp16 누적 연산). settings.json 에 "speed_boost": false 를 적으면 꺼요."""
    if not settings().get("speed_boost", True) or not PY.exists():
        return []
    try:
        r = subprocess.run([str(PY), "-s", str(COMFY / "main.py"), "--help"], cwd=HOME, capture_output=True, text=True, timeout=40)
        if "fp16_accumulation" in (r.stdout or ""):
            return ["--fast", "fp16_accumulation"]
    except Exception:  # noqa: BLE001
        pass
    return []


def start_engines():
    LOGS.mkdir(exist_ok=True)
    tidy()
    if OLLAMA_EXE.exists() and not alive(OLLAMA + "/api/version"):
        env = {**os.environ, "OLLAMA_MODELS": str(ROOT / "models" / "llm")}
        procs.append(subprocess.Popen([str(OLLAMA_EXE), "serve"], cwd=OLLAMA_EXE.parent, env=env,
                                      stdout=open(LOGS / "ollama.log", "ab"), stderr=subprocess.STDOUT))
    if PY.exists() and not alive(CUI + "/system_stats"):
        cmd = [str(PY), "-s", str(COMFY / "main.py"), "--windows-standalone-build",
               "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"] + speed_args()
        procs.append(subprocess.Popen(cmd, cwd=HOME, stdout=open(LOGS / "comfyui.log", "ab"),
                                      stderr=subprocess.STDOUT))


def free_ollama():
    try:
        for m in http(OLLAMA + "/api/ps", timeout=3).get("models", []):
            http(OLLAMA + "/api/generate", {"model": m["name"], "keep_alive": 0}, 30)
    except Exception:
        pass


def free_comfy():
    try:
        http(CUI + "/free", {"unload_models": True, "free_memory": True}, 5)
    except Exception:
        pass


def claim(who):
    """대화 ↔ 이미지 기능을 오갈 때 상대 엔진이 잡고 있는 VRAM 을 비웁니다."""
    if STATE["last"] != who:
        (free_ollama if who == "image" else free_comfy)()
        STATE["last"] = who


_TR = {}


def translate(text, style):
    key = (text, style)
    if key in _TR:
        return _TR[key]
    names = llms()
    if not names:
        return text
    free_comfy()  # 번역용 LLM 이 쓸 VRAM 확보 (이미지 모델은 작업 때 다시 올라옵니다)
    what = {"sentence": "an image editing instruction. Write one clear imperative sentence.",
            "caption": "an image generation prompt written as natural, descriptive English sentences."
            }.get(style, "an image generation prompt. Output comma-separated Danbooru-style tags.")
    sysmsg = f"Translate the user's Korean text into English as {what} Keep every detail. Output only the result."
    try:
        r = http(OLLAMA + "/api/generate", {"model": names[0], "system": sysmsg, "prompt": text, "stream": False,
                                            "keep_alive": 0, "options": {"temperature": 0.2}}, 180)
        out = re.sub(r"<think>.*?</think>", "", r.get("response", ""), flags=re.S).strip().strip('"')
    except Exception:
        return text
    if out and out != text:
        if len(_TR) > 64:
            _TR.clear()
        _TR[key] = out
    return out or text


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
        t = translate(t, style)
    return t, tags


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
            "ControlNetLoader", "UpscaleModelLoader", "CLIPTextEncode", "TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus", "VAEEncode"}
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
                    WSP[x["prompt_id"]] = (x.get("value", 0), max(1, x.get("max", 1)))
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


def run_wf(wf, J, raw=False):
    """raw=True 이면 이미지 대신 결과 파일(영상) 바이트를 [(파일명, 바이트)] 로 돌려줘요."""
    check_cancel(J)
    try:
        pid = http(CUI + "/prompt", {"prompt": wf, "client_id": CID}, 30)["prompt_id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(comfy_err(e)) from None
    J["pid"] = pid
    t0 = time.time()
    while True:
        if J.get("cancel"):
            comfy_cancel(pid)
            raise Cancelled("사용자가 중단했어요.")
        h = http(CUI + f"/history/{pid}", timeout=15).get(pid)
        J["phase"] = phase_of(wf, pid) if not h else "gen"
        if pid in WSP:
            v, m = WSP[pid]
            set_progress(J, v / m * 0.97)
        elif not h:   # 웹소켓 신호가 없으면 시간 기반 추정(실제보다 부정확해요)
            set_progress(J, 0.95 * (1 - 2.718 ** (-(time.time() - t0) / 40)), est=True)
        if h:
            WSP.pop(pid, None)
            set_progress(J, 1.0, est=J.get("pest", False))
            for ev, d in h.get("status", {}).get("messages", []):
                if ev == "execution_error":
                    msg = d.get("exception_message", "실행 오류")
                    if "out of memory" in msg.lower():
                        msg += " — 해상도를 낮추거나 '빠른 모드'를 사용해 보세요."
                    raise RuntimeError(msg)
            imgs = []
            for o in h.get("outputs", {}).values():
                for im in o.get("images", []):
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
                raise RuntimeError("결과 영상이 없습니다." if raw else "결과 이미지가 없습니다.")
            return imgs
        J["elapsed"] = int(time.time() - t0)
        time.sleep(0.3)


# ───────────────────────── 작업 (편집 / 생성 / 업스케일 / 워크플로) ─────────────────────────
def qwen_params(p, text, tags, J):
    f = dict(unet=find("diffusion_models", "qwen_image_edit"), te=find("text_encoders", "qwen_2.5_vl"),
             vae=find("vae", "qwen_image_vae"))
    for key, field, sub in (("unet", "q_unet", "diffusion_models"), ("te", "q_te", "text_encoders"), ("vae", "q_vae", "vae")):
        if p.get(field) and p[field] in files(sub):   # 화면에서 직접 고른 파일이 우선
            f[key] = p[field]
    if not all(f.values()):
        names = {"unet": "Qwen 모델", "te": "텍스트 인코더", "vae": "VAE"}
        raise RuntimeError("없는 파일: " + ", ".join(names[k] for k, v in f.items() if not v) + ". '설치와 모델' 탭에서 설치하거나, Qwen 설정의 '모델 파일 직접 고르기'에서 골라 주세요.")
    if blocked(text):
        raise ValueError(BLOCK_MSG)
    fast = find("loras", "lightning", "qwen") if p.get("fast") else None
    loras = ([(fast, 1.0)] if fast else []) + collect_loras(p, tags, J)
    return dict(files=f, loras=loras, prompt=text, seed=seed_of(p),
                steps=4 if fast else clamp(num(p, "q_steps", 20, int), 1, 100),
                cfg=1.0 if fast else clamp(num(p, "q_cfg", 4.0), 0.0, 20.0),
                sampler=p.get("q_sampler") or "euler", scheduler=p.get("q_scheduler") or "simple",
                shift=clamp(num(p, "q_shift", 3.0), 0.1, 20.0))


def upscale(img, J, model, scale):
    model = model or (files("upscale_models") or [None])[0]
    if not model:
        raise RuntimeError("업스케일 모델이 없습니다. '설치와 모델' 탭에서 Real-ESRGAN 을 설치해 주세요.")
    return run_wf(flows.wf_upscale(model, put_input(img, J), scale == 2), J)[0]


FX_DEFAULTS = {"flux": (20, 3.5, 1, "simple"), "chroma": (26, 0, 4, "beta"), "krea2": (8, 0, 1, "simple")}   # 단계, 가이던스, CFG, 스케줄러
FLUX_FAMS = ("flux", "krea2", "chroma")


def flux_q(p, J, fam, text, tags, seed, w=1024, h=1024):
    """FLUX·Krea 2·Chroma 생성 그래프에 넘길 설정 한 벌(생성·편집·확장·업스케일이 같이 써요)."""
    f, allin, sch = flux_setup(p, J, fam)
    neg = ""
    if fam == "krea2":
        neg = (p.get("negative") or "").strip()
    elif fam == "chroma":
        neg = (p.get("negative") or "").strip() or CHROMA_NEG
        if flows_sex(text):
            neg += ", child, loli, shota, underage, aged down"
    return dict(family=fam, allin=allin, **f, loras=collect_loras(p, tags, J), prompt=text, negative=neg, seed=seed, w=w, h=h,
                guidance=clamp(num(p, "fx_guidance", 3.5), 0.0, 20.0), steps=clamp(num(p, "fx_steps", 20, int), 1, 100),
                cfg=clamp(num(p, "fx_cfg", 4.0), 0.0, 20.0) if fam in ("chroma", "krea2") else 1.0,
                sampler=p.get("fx_sampler") or "euler", scheduler=sch)


def flux_info(q, res, kind, **extra):
    fam = q["family"]
    return dict(kind=kind, prompt=q["prompt"], negative=q["negative"], steps=q["steps"], cfg=q["guidance"] if fam == "flux" else q["cfg"],
                sampler=q["sampler"], scheduler=q["scheduler"], seed=q["seed"], w=res.width, h=res.height, model=q["unet"],
                loras=[[a, b] for a, b in q["loras"]],
                extra={"Family": fam, **({"Distilled CFG": q["guidance"]} if fam == "flux" else {}), **extra})


def edit_flux(p, J, img, mask, grow, feather, rng):
    """FLUX·Krea 2·Chroma 로 편집. 칠한 영역은 인페인트, FLUX Kontext 모델이면 말로 지시하는 편집."""
    fam = p.get("fengine") if p.get("fengine") in FLUX_FAMS else "flux"
    text, tags = prep(p, J, "caption", rng)
    q = flux_q(p, J, fam, text, tags, seed_of(p))
    kontext = fam == "flux" and "kontext" in (p.get("fx_model") or "").lower()
    if kontext:
        if not has_node("ReferenceLatent") or not has_node("FluxKontextImageScale"):
            raise RuntimeError("FLUX Kontext 편집에는 ReferenceLatent·FluxKontextImageScale 노드가 필요해요. ComfyUI 를 업데이트해 주세요.")
        small = img.resize(qsize(img.size, 1.0), RS.LANCZOS)
        J["msg"] = "편집 중"
        res = run_wf(flows.wf_kontext(q, put_input(small, J)), J)[0]
        res = res.resize(img.size, RS.LANCZOS)
        if mask:
            res = Image.composite(res, img, grow_feather(mask, grow, feather))
        return [(res, flux_info(q, res, "edit-flux", Kontext=True), None)]
    if not mask:
        raise ValueError("칠해서 고치는 방식이에요. 편집할 영역을 마스크로 칠하거나 [선택 도구]로 골라 주세요. (말로만 지시해서 고치려면 Qwen-Image-Edit 이나 FLUX Kontext 모델을 쓰세요.)")
    q["denoise"] = clamp(num(p, "fx_denoise", 1.0), 0.1, 1.0)
    pos, crop, soft, size = plan(img, mask, grow, clamp(num(p, "ctx", 35.0), 5, 200) / 100,
                                 clamp(num(p, "res", 1024, int), 512, 2048), feather, mult=16)
    a = put_input(crop.resize(size, RS.LANCZOS), J)
    b = put_input(soft.resize(size, RS.BILINEAR), J)
    J["msg"] = "인페인트 생성 중"
    out = finish(img, pos, crop, soft, run_wf(flows.wf_flux_inpaint(q, a, b), J)[0])
    return [(out, flux_info(q, out, "edit-flux", **{"Denoising strength": q["denoise"], "Mask grow": grow}), None)]


def do_edit(p, J):
    img = load_img(p["image"])
    mask = load_mask(p.get("mask"), img.size)
    grow = clamp(num(p, "grow", 8, int), 0, 128)
    rng = random.Random(num(p, "seed", -1, int))
    feather = clamp(num(p, "feather", 0, int), 0, 200) or None
    if p.get("engine") == "flux":
        return edit_flux(p, J, img, mask, grow, feather, rng)
    if p.get("engine") == "sdxl":
        if not mask:
            raise ValueError("편집할 영역을 마스크로 칠해 주세요.")
        q = sd(p, *prep(p, J, "tags", rng), J)
        pos, crop, soft, size = plan(img, mask, grow, clamp(num(p, "ctx", 35.0), 5, 200) / 100,
                                     clamp(num(p, "res", 1024, int), 512, 2048), feather)
        a = put_input(crop.resize(size, RS.LANCZOS), J)
        b = put_input(soft.resize(size, RS.BILINEAR), J)
        extra = {"Denoising strength": q["denoise"], "Mask grow": grow}
        if p.get("cn_model"):
            own = bool(p.get("cn_image"))
            src = load_img(p["cn_image"]).resize(img.size, RS.LANCZOS) if own else img   # 올린 제어 이미지는 원본 크기에 맞춰 같은 구역을 잘라 써요
            cc = src.crop((pos[0], pos[1], pos[0] + crop.width, pos[1] + crop.height)).resize(size, RS.LANCZOS)
            canny = p.get("cn_prep") == "canny" or not own
            if canny and not has_node("Canny"):
                warn(J, "이 ComfyUI 에는 Canny 노드가 없어 전처리 없이 사용했어요.")
                canny = False
            q["cn"] = dict(model=p["cn_model"], image=put_input(cc, J), canny=canny,
                           strength=clamp(num(p, "cn_strength", 0.7), 0.0, 2.0),
                           start=clamp(num(p, "cn_start", 0.0), 0.0, 1.0), end=clamp(num(p, "cn_end", 1.0), 0.0, 1.0))
            extra["ControlNet"] = f'{p["cn_model"]} {q["cn"]["strength"]}'
        J["msg"] = "인페인트 생성 중"
        out = finish(img, pos, crop, soft, run_wf(flows.wf_inpaint(q, a, b), J)[0])
        return [(out, info_sd(q, out.size, "edit-sdxl", **extra), None)]
    text, tags = prep(p, J, "sentence", rng)
    q = qwen_params(p, text, tags, J)
    plus = has_node("TextEncodeQwenImageEditPlus")
    refs = [load_img(p[k]) for k in ("ref1", "ref2") if p.get(k)]
    if refs and not plus:
        raise RuntimeError("참조 이미지는 TextEncodeQwenImageEditPlus 노드가 필요해요. ComfyUI 를 업데이트해 주세요.")
    small = img.resize(qsize(img.size, clamp(num(p, "q_mp", 1.0), 0.3, 2.5)), RS.LANCZOS)
    wf = flows.wf_qwen(q, put_input(small, J), [put_input(r.resize(qsize(r.size), RS.LANCZOS), J) for r in refs], plus)
    J["msg"] = "편집 중"
    res = run_wf(wf, J)[0]
    if mask:  # 칠한 영역만 바꾸고 나머지는 원본 100% 유지
        res = Image.composite(res.resize(img.size, RS.LANCZOS), img, grow_feather(mask, grow, feather))
    elif p.get("hires") and files("upscale_models") and img.width * img.height > 1.3 * res.width * res.height:
        J["msg"] = "원본 해상도로 복원 중"
        res = upscale(res, J, None, 4).resize(img.size, RS.LANCZOS)
    info = dict(kind="edit-qwen", prompt=q["prompt"], negative="", steps=q["steps"], cfg=q["cfg"], sampler=q["sampler"],
                scheduler=q["scheduler"], seed=q["seed"], w=res.width, h=res.height, model=q["files"]["unet"],
                loras=[[n, w] for n, w in q["loras"]], extra={"Shift": q["shift"], "Refs": len(refs)})
    return [(res, info, None)]


# ───────────────────────── 기능 모음 (초보자용 템플릿) ─────────────────────────
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
    sel = str(p.get("ckpt") or "")
    fx = re.match(r"fx:(flux|krea2|chroma):(.*)$", sel, re.S)
    if fx:      # FLUX·Krea·Krea 2·Chroma 모델로 확장 (단계 수·CFG 는 그 모델에 맞는 값을 써요)
        fam = fx.group(1)
        d = FX_DEFAULTS[fam]
        p2 = dict(p, fx_model=fx.group(2), fx_steps=d[0], fx_guidance=d[1], fx_cfg=d[2], fx_scheduler=d[3])
        if fam == "krea2" and re.search("raw", fx.group(2), re.I):
            p2.update(fx_steps=30, fx_cfg=4)
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
    regs = [dict(text=t, x=b[0], y=b[1], w=b[2], h=b[3]) for t, b in zip(texts[:n], boxes)]
    rng = random.Random(num(p, "seed", -1, int))
    p2 = dict(p, prompt=(p.get("common") or "").strip() or "best quality")
    q = sd(p2, *prep(p2, J, "tags", rng), J)
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


def feat_resize(p, J):
    """크기 바꾸기 · 비율대로 자르기 · 회전/뒤집기 (ComfyUI 없이 바로 처리해요)."""
    img = load_img(p["image"]).convert("RGB")
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


def do_feat(p, J):
    fn = {"outpaint": feat_outpaint, "regional": feat_regional, "compare": feat_compare, "resize": feat_resize, "color": feat_color}.get(p.get("feature"))
    if not fn:
        raise ValueError("알 수 없는 기능이에요.")
    spec = next(f for f in FEATURES if f["id"] == p["feature"])
    miss = [n for n in spec.get("needs", {}).get("nodes", []) if caps()["nodes"] and n not in caps()["nodes"]]
    if miss:
        raise RuntimeError("이 ComfyUI 에는 필요한 노드가 없어요: " + ", ".join(miss) + ". ComfyUI 를 업데이트해 주세요.")
    return fn(p, J)


def do_gen(p, J):
    if p.get("gengine") in ("flux", "chroma", "krea2"):
        return do_gen_flux(p, J)
    base = seed_of(p)
    n = clamp(num(p, "n", 1, int), 1, 8)
    w, h = (clamp(num(p, k, 1024, int) // 8 * 8, 256, 2048) for k in ("w", "h"))
    init = load_img(p["init"]) if p.get("init") else None
    cnimg = load_img(p["cn_image"]) if p.get("cn_image") and p.get("cn_model") else None
    out = []
    for i in range(n):
        rng = random.Random(base + i)
        q = sd(p, *prep(p, J, "tags", rng), J)
        q.update(seed=base + i, w=w, h=h)
        extra = {}
        if init is not None:
            small = fit_area(init, w, h)
            q["init"], q["init_denoise"] = put_input(small, J), clamp(num(p, "init_denoise", 0.7), 0.05, 1.0)
            w0, h0 = small.size
            extra["Denoising strength"] = q["init_denoise"]
        else:
            w0, h0 = w, h
        if cnimg is not None:
            prep_canny = p.get("cn_prep") == "canny"
            if prep_canny and not has_node("Canny"):
                warn(J, "이 ComfyUI 에는 Canny 노드가 없어 전처리 없이 사용했어요.")
                prep_canny = False
            q["cn"] = dict(model=p["cn_model"], image=put_input(cover(cnimg, (w0, h0)), J), canny=prep_canny,
                           strength=clamp(num(p, "cn_strength", 0.7), 0.0, 2.0),
                           start=clamp(num(p, "cn_start", 0.0), 0.0, 1.0), end=clamp(num(p, "cn_end", 1.0), 0.0, 1.0))
            extra["ControlNet"] = f'{p["cn_model"]} {q["cn"]["strength"]}'
        if p.get("hires"):
            q["hires"] = dict(scale=clamp(num(p, "hires_scale", 1.5), 1.0, 3.0),
                              denoise=clamp(num(p, "hires_denoise", 0.5), 0.1, 1.0),
                              steps=clamp(num(p, "hires_steps", 15, int), 1, 100))
            extra.update({"Denoising strength": q["hires"]["denoise"], "Hires upscale": q["hires"]["scale"],
                          "Hires steps": q["hires"]["steps"], "Hires upscaler": "Latent (bislerp)"})
        J["msg"] = f"생성 중 ({i + 1}/{n})"
        J["pi"], J["pn"] = i, n
        g = flows.wf_gen(q)
        try:
            res = run_wf(g, J)[0]
        except Cancelled:
            if out:
                warn(J, f"중단해서 완료된 {len(out)}장만 저장했어요.")
                break
            raise
        out.append((res, info_sd(q, res.size, "gen", **extra), g if not (init is not None or cnimg is not None) else None))
    return out


CHROMA_NEG = "low quality, ugly, unfinished, out of focus, deformed, disfigure, blurry, smudged, restricted palette, flat colors"


def flux_vae():
    return next((n for n in files("vae") if n.lower() in ("ae.safetensors", "flux_ae.safetensors") or "flux" in n.lower()), None)


def flux_parts(p=None):
    """FLUX 계열 공용 파일. 자동으로 찾고, 화면에서 직접 고른 파일(fx_vae/fx_t5/fx_clip)이 있으면 그걸 써요."""
    te = files("text_encoders")
    r = dict(t5=next((n for n in te if "t5xxl" in n.lower()), None) or next((n for n in te if "t5" in n.lower() and "umt5" not in n.lower()), None),
             clip_l=next((n for n in te if n.lower().startswith("clip_l")), None) or next((n for n in te if "clip" in n.lower() and "t5" not in n.lower()), None),
             vae=flux_vae() or next((n for n in files("vae") if "qwen" not in n.lower() and "sdxl" not in n.lower()), None))
    if p:
        for key, field, sub in (("t5", "fx_t5", "text_encoders"), ("clip_l", "fx_clip", "text_encoders"), ("vae", "fx_vae", "vae")):
            if p.get(field) and p[field] in files(sub):
                r[key] = p[field]
    return r


def krea2_parts(p=None):
    """Krea 2 공용 파일: Qwen3-VL 텍스트 인코더 + Qwen Image VAE. 화면에서 직접 고른 파일(k2_te/k2_vae)이 우선이에요."""
    te, va = files("text_encoders"), files("vae")
    r = dict(te=next((n for n in te if "qwen3" in n.lower() and "vl" in n.lower()), None) or next((n for n in te if "qwen3" in n.lower()), None),
             vae=next((n for n in va if "qwen_image_vae" in n.lower()), None) or next((n for n in va if "qwen" in n.lower()), None))
    if p:
        for key, field, lst in (("te", "k2_te", te), ("vae", "k2_vae", va)):
            if p.get(field) and p[field] in lst:
                r[key] = p[field]
    return r


def flux_setup(p, J, fam):
    """FLUX·Chroma·Krea 2 가 쓸 파일(모델, 텍스트 인코더, VAE)을 찾아서 (파일들, 올인원 여부, 스케줄러)를 돌려줘요."""
    sel = p.get("fx_model") or None
    allin = bool(sel and sel.startswith("ckpt::")) and fam != "krea2"     # 체크포인트 폴더의 올인원 FLUX/Chroma
    if fam == "krea2":
        ct = caps().get("clip_types") or []
        if ct and "krea2" not in ct:
            raise RuntimeError("이 ComfyUI 는 Krea 2 를 아직 지원하지 않아요(버전 0.26.0 이상 필요). ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
        kp = krea2_parts(p)
        f = dict(unet=sel, t5=kp["te"], clip_l=None, vae=kp["vae"])
        miss = [n for n, k in (("Krea 2 모델", "unet"), ("Qwen3-VL 텍스트 인코더", "t5"), ("Qwen Image VAE", "vae")) if not f[k]]
        if miss:
            raise RuntimeError("없는 파일: " + ", ".join(miss) + ". '설치와 모델' 탭에서 설치하거나, 설정의 '모델 파일 직접 고르기'에서 골라 주세요.")
    elif allin:
        sel = sel[6:]
        if sel not in files("checkpoints"):
            raise RuntimeError("선택한 체크포인트 파일을 찾을 수 없어요.")
        f = dict(unet=sel, t5=None, clip_l=None, vae=None)
    else:
        f = dict(unet=sel, **flux_parts(p))
    if fam != "krea2" and not allin and not all(f[k] for k in (["unet", "t5", "vae"] + (["clip_l"] if fam == "flux" else []))):
        names = {"unet": "FLUX 모델", "t5": "T5 텍스트 인코더", "vae": "VAE", "clip_l": "CLIP-L 텍스트 인코더"}
        miss = [names[k] for k in ["unet", "t5", "vae"] + (["clip_l"] if fam == "flux" else []) if not f[k]]
        raise RuntimeError("없는 파일: " + ", ".join(miss) + ". '설치와 모델' 탭에서 설치하거나, 설정의 '모델 파일 직접 고르기'에서 골라 주세요.")
    sch = p.get("fx_scheduler") or ("beta" if fam == "chroma" else "simple")
    have = caps()["schedulers"]
    if have and sch not in have:
        warn(J, f"이 ComfyUI 에는 스케줄러 '{sch}' 가 없어 simple 로 바꿨어요.")
        sch = "simple"
    return f, allin, sch


def do_gen_flux(p, J):
    """FLUX.1 dev / Krea dev / Chroma / Krea 2 생성(이미지→이미지, LoRA, 다이나믹 프롬프트 지원)."""
    fam = p["gengine"]
    f, allin, sch = flux_setup(p, J, fam)
    base, n = seed_of(p), clamp(num(p, "n", 1, int), 1, 8)
    w, h = (clamp(num(p, k, 1024, int) // 16 * 16, 256, 2048) for k in ("w", "h"))
    init = load_img(p["init"]) if p.get("init") else None
    out = []
    for i in range(n):
        rng = random.Random(base + i)
        text, tags = prep(p, J, "caption", rng)
        if blocked(text):
            raise ValueError(BLOCK_MSG)
        neg = ""
        if fam == "krea2":
            neg = (p.get("negative") or "").strip()
        elif fam == "chroma":
            neg = (p.get("negative") or "").strip() or CHROMA_NEG
            if flows_sex(text):
                neg += ", child, loli, shota, underage, aged down"
        q = dict(family=fam, allin=allin, **f, loras=collect_loras(p, tags, J), prompt=text, negative=neg, seed=base + i, w=w, h=h,
                 guidance=clamp(num(p, "fx_guidance", 3.5), 0.0, 20.0), steps=clamp(num(p, "fx_steps", 20, int), 1, 100),
                 cfg=clamp(num(p, "fx_cfg", 4.0), 0.0, 20.0) if fam in ("chroma", "krea2") else 1.0,
                 sampler=p.get("fx_sampler") or "euler", scheduler=sch)
        if init is not None:
            q["init"] = put_input(fit_area(init, w, h), J)
            q["init_denoise"] = clamp(num(p, "init_denoise", 0.7), 0.05, 1.0)
        J["msg"] = f"생성 중 ({i + 1}/{n})"
        J["pi"], J["pn"] = i, n
        g = flows.wf_flux(q)
        try:
            res = run_wf(g, J)[0]
        except Cancelled:
            if out:
                warn(J, f"중단해서 완료된 {len(out)}장만 저장했어요.")
                break
            raise
        info = dict(kind="gen-" + fam, prompt=text, negative=neg, steps=q["steps"],
                    cfg=q["guidance"] if fam == "flux" else q["cfg"], sampler=q["sampler"], scheduler=sch, seed=q["seed"],
                    w=res.width, h=res.height, model=f["unet"], loras=[[a, b] for a, b in q["loras"]],
                    extra={"Family": fam, **({"Distilled CFG": q["guidance"]} if fam == "flux" else {})})
        out.append((res, info, g if init is None else None))
    return out


ANTI_DUP = "extra eyes, extra faces, multiple faces, duplicate, extra heads, extra limbs, deformed, mutated"


def tile_text(p, J, rng, style, generic):
    """타일 리파인에 쓸 문장. 기본(auto)은 일반 고화질 지시만 써요 — 타일마다 '얼굴·눈' 같은 프롬프트를 그대로 넣으면
    배경 조각에도 눈·얼굴을 그려 넣기 때문이에요. 'mine' 이면 내 프롬프트를 그대로 써요. 반환: (문장, LoRA 태그, 자동 모드 여부)"""
    raw = (p.get("prompt") or "").strip()
    if not raw:
        return generic, [], True
    if p.get("tileprompt") == "mine":
        text, tags = prep(p, J, style, rng)
        return text, tags, False
    if blocked(raw):
        raise ValueError(BLOCK_MSG)
    tags = []

    def grab(m):
        tags.append((m.group(1).strip(), float(m.group(2) or 1)))
        return ""
    LORA_TAG.sub(grab, raw)
    return generic, tags, True


QWEN_REFINE = "Enhance this image: make it sharper with fine natural detail and clean textures. Keep the composition, colors, faces and identity exactly the same."


def refine_tiles(img, q, tile, overlap, J, build=None, mult=8):
    """큰 이미지를 겹치는 타일로 나눠 각각 낮은 denoise 로 다시 그린 뒤 부드럽게 이어 붙입니다."""
    xs, ys = spans(img.width, tile, overlap), spans(img.height, tile, overlap)
    canvas, n, total = img.copy(), 0, len(xs) * len(ys)
    for yi, (y0, y1) in enumerate(ys):
        for xi, (x0, x1) in enumerate(xs):
            n += 1
            check_cancel(J)
            J["msg"] = f"타일 리파인 {n}/{total}"
            J["pi"], J["pn"] = n - 1, total
            t = img.crop((x0, y0, x1, y1))
            s8 = (max(64, round(t.width / mult) * mult), max(64, round(t.height / mult) * mult))
            name = put_input(t.resize(s8, RS.LANCZOS) if s8 != t.size else t, J)
            res = run_wf(build(name) if build else flows.wf_refine(q, name), J)[0]
            if res.size != t.size:
                res = res.resize(t.size, RS.LANCZOS)
            canvas.paste(res, (x0, y0), ramp(t.size, overlap, xi > 0, yi > 0))
    return canvas


def do_up(p, J):
    img = load_img(p["image"])
    scale = 2 if str(p.get("scale")) == "2" else 4
    if max(img.size) * scale > 8192:
        raise ValueError("결과가 8192px 를 넘습니다. 더 작은 이미지나 2배를 선택해 주세요.")
    J["msg"] = "업스케일 중"
    big = upscale(img, J, p.get("upm"), scale)
    if p.get("mode") != "refine":
        return [(big, dict(kind="upscale", extra={"Upscaler": p.get("upm") or "auto", "Scale": scale}), None)]
    rng = random.Random(num(p, "seed", -1, int))
    fam = p.get("rengine") if p.get("rengine") in ("flux", "chroma", "krea2", "qwen") else "sdxl"
    if fam == "qwen":      # 이미지 편집에 쓰는 Qwen-Image-Edit 으로 타일을 다시 그려요
        raw = (p.get("prompt") or "").strip()
        text, tags = prep(p, J, "sentence", rng) if raw else (QWEN_REFINE, [])
        q = qwen_params(p, text, tags, J)
        den = clamp(num(p, "rdenoise", 0.45), 0.05, 0.9)
        if p.get("fast"):          # 4단계용 모델은 일부만 다시 그릴 때 단계가 모자라서 조금 늘려요
            q["steps"] = int(min(12, max(4, round(2.5 / den))))
        q["denoise"] = den
        plus = has_node("TextEncodeQwenImageEditPlus")
        tile = clamp(num(p, "tile", 1024, int) // 16 * 16, 512, 1536)
        out = refine_tiles(big, q, tile, clamp(num(p, "overlap", 128, int), 32, tile // 2), J,
                           build=lambda n: flows.wf_qwen(q, n, [], plus), mult=16)
        info = dict(kind="upscale-refine", prompt=text, negative="", steps=q["steps"], cfg=q["cfg"], sampler=q["sampler"],
                    scheduler=q["scheduler"], seed=q["seed"], w=out.width, h=out.height, model=q["files"]["unet"],
                    loras=[[n, w] for n, w in q["loras"]], extra={"Family": "qwen", "Denoising strength": den, "Tile": tile})
        return [(out, info, None)]
    if fam != "sdxl":      # 실사 등 FLUX 계열 모델로 타일을 다시 그려요
        f, allin, sch = flux_setup(p, J, fam)
        text, tags, auto = tile_text(p, J, rng, "caption", "high quality photo, sharp focus, fine detail, natural skin texture")
        if blocked(text):
            raise ValueError(BLOCK_MSG)
        neg = (p.get("negative") or "").strip() if fam in ("krea2", "chroma") else ""
        if fam == "chroma" and not neg:
            neg = CHROMA_NEG
        if auto and fam in ("krea2", "chroma"):
            neg = (neg + ", " + ANTI_DUP).strip(", ")
        den = clamp(num(p, "rdenoise", 0.3), 0.05, 0.8)
        q = dict(family=fam, allin=allin, **f, loras=collect_loras(p, tags, J), prompt=text, negative=neg, seed=seed_of(p), w=1024, h=1024,
                 guidance=clamp(num(p, "fx_guidance", 3.5), 0.0, 20.0), steps=clamp(num(p, "fx_steps", 20, int), 1, 100),
                 cfg=clamp(num(p, "fx_cfg", 4.0), 0.0, 20.0) if fam in ("chroma", "krea2") else 1.0,
                 sampler=p.get("fx_sampler") or "euler", scheduler=sch, init_denoise=den)
        tile = clamp(num(p, "tile", 1024, int) // 16 * 16, 512, 1536)
        out = refine_tiles(big, q, tile, clamp(num(p, "overlap", 128, int), 32, tile // 2), J,
                           build=lambda n: flows.wf_flux({**q, "init": n}), mult=16)
        info = dict(kind="upscale-refine", prompt=text, negative=neg, steps=q["steps"], cfg=q["guidance"] if fam == "flux" else q["cfg"],
                    sampler=q["sampler"], scheduler=sch, seed=q["seed"], w=out.width, h=out.height, model=f["unet"],
                    loras=[[a, b] for a, b in q["loras"]], extra={"Family": fam, "Denoising strength": den, "Tile": tile})
        return [(out, info, None)]
    text, tags, auto = tile_text(p, J, rng, "tags", "highly detailed, sharp focus")
    q = sd(p, text, tags, J)
    if auto:      # 배경 조각에 눈·얼굴이 새로 생기는 것을 막는 제외 요소
        q["negative"] = (q["negative"] + ", " + ANTI_DUP).strip(", ")
    q["denoise"] = clamp(num(p, "rdenoise", 0.3), 0.05, 0.8)
    tile = clamp(num(p, "tile", 1024, int) // 8 * 8, 512, 1536)
    out = refine_tiles(big, q, tile, clamp(num(p, "overlap", 128, int), 32, tile // 2), J)
    return [(out, info_sd(q, out.size, "upscale-refine", **{"Denoising strength": q["denoise"], "Tile": tile}), None)]


def do_wf(p, J):
    g = flows.parse_graph(p.get("graph"), caps()["info"])
    g = flows.apply(g, p.get("ov") or {}, lambda data: put_input(load_img(data), J), random)
    txt = " ".join(str(v) for n in g.values() for k, v in n.get("inputs", {}).items()
                   if k in flows.TEXT_KEYS and isinstance(v, str))
    if blocked(txt):
        raise ValueError(BLOCK_MSG)
    have = caps()["nodes"]
    miss = sorted({n["class_type"] for n in g.values() if have and n["class_type"] not in have})
    if miss:
        raise RuntimeError("설치되지 않은 노드가 있어요: " + ", ".join(miss) + " (ComfyUI 화면의 Manager 에서 설치하세요)")
    J["msg"] = "워크플로 실행 중"
    return [(im, dict(kind="wf"), g) for im in run_wf(g, J)]


OUT_SUB = {"edit": "편집", "gen": "생성", "up": "업스케일", "wf": "워크플로", "feat": "기능", "vid": "영상"}


def out_path(rel):
    """/out/ 아래 요청 경로를 안전하게 파일 경로로 바꿔요(하위 폴더는 정해진 이름만)."""
    parts = [x for x in urllib.parse.unquote(rel).split("/") if x]
    if len(parts) == 2 and parts[0] in OUT_SUB.values() or parts[:1] == ["기타"] and len(parts) == 2:
        return OUT / parts[0] / Path(parts[1]).name
    return OUT / Path(parts[-1] if parts else "x").name


WAN_SIZES = {"832x480": "가로 480p", "480x832": "세로 480p", "640x640": "정사각", "1280x704": "가로 720p (VRAM 많이 필요)"}


def wan_models():
    return [n for n in files("diffusion_models") if "wan" in n.lower()]


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


def do_vid(p, J):
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


def job_thread(J, p):
    try:
        J["state"], J["msg"] = "running", "엔진 준비 중"
        wait_comfy()
        claim("image")
        items = {"edit": do_edit, "gen": do_gen, "up": do_up, "wf": do_wf, "feat": do_feat, "vid": do_vid}[p["kind"]](p, J)
        sub = OUT_SUB.get(p["kind"], "기타")
        (OUT / sub).mkdir(parents=True, exist_ok=True)
        stamp, embed = time.strftime("%Y%m%d-%H%M%S"), bool(p.get("embed"))
        for i, (im, info, graph) in enumerate(items):
            if p["kind"] == "vid":      # 영상: 받은 파일을 그대로 저장하고, 설정은 옆에 .json 으로 남겨요
                name = f'{stamp}-{uuid.uuid4().hex[:4]}-vid-{i}{graph}'
                (OUT / sub / name).write_bytes(im)
                (OUT / sub / (name + ".json")).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
                J["images"].append("/out/" + urllib.parse.quote(sub) + "/" + name)
                J.setdefault("used", []).append(info.get("prompt", ""))
                continue
            name = f'{stamp}-{uuid.uuid4().hex[:4]}-{p["kind"]}-{i}.png'
            im.save(OUT / sub / name, "PNG", pnginfo=meta.pnginfo(info, graph) if embed else None)
            J["images"].append("/out/" + urllib.parse.quote(sub) + "/" + name)
            J.setdefault("used", []).append(info.get("prompt", ""))
        J["state"], J["progress"] = "done", 1.0
    except Cancelled as e:
        J["state"], J["error"] = "cancelled", str(e)
    except Exception as e:
        J["state"], J["error"] = "error", str(e) or e.__class__.__name__
        log("[작업 오류]", J["error"])
    finally:
        for f in J["tmp"]:
            try:
                f.unlink()
            except OSError:
                pass


# ───────────────────────── 프롬프트 보관함 · 와일드카드 · 이미지→프롬프트 ─────────────────────────
PROMPTS_FILE = ROOT / "prompts.json"
_PLOCK = threading.Lock()


def prompts_load():
    try:
        d = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def prompts_api(p):
    """보관함: save(id 가 있으면 덮어쓰기) / delete."""
    with _PLOCK:
        items = prompts_load()
        act = p.get("action")
        if act == "save":
            text = str(p.get("text") or "").strip()
            name = str(p.get("name") or "").strip()[:60] or text[:30]
            if not text:
                return {"error": "저장할 프롬프트가 비어 있어요."}
            it = {"id": str(p.get("id") or uuid.uuid4().hex[:8]), "name": name, "text": text[:8000],
                  "negative": str(p.get("negative") or "").strip()[:4000], "tags": [str(t).strip()[:20] for t in (p.get("tags") or []) if str(t).strip()][:8]}
            items = [x for x in items if x.get("id") != it["id"]] + [it]
        elif act == "delete":
            items = [x for x in items if x.get("id") != p.get("id")]
        elif act != "list":
            return {"error": "알 수 없는 동작"}
        if act != "list":
            PROMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            PROMPTS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"items": items}


WC_NAME = re.compile(r"^[\w\-.]{1,60}$")


def wildcards_api(p):
    """와일드카드 파일(wildcards/이름.txt) 읽기·저장·삭제. act: list / get / save / delete"""
    d = ROOT / "wildcards"
    act, name = p.get("action"), str(p.get("name") or "")
    if act == "list":
        return {"items": sorted(x.stem for x in d.glob("*.txt")) if d.is_dir() else []}
    if not WC_NAME.match(name) or ".." in name:
        return {"error": "이름은 글자·숫자·- _ . 만 쓸 수 있어요."}
    f = d / (name + ".txt")
    if act == "get":
        return {"name": name, "text": f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""}
    if act == "save":
        d.mkdir(parents=True, exist_ok=True)
        f.write_text(str(p.get("text") or "")[:200000].replace("\r\n", "\n"), encoding="utf-8")
        return {"ok": True}
    if act == "delete":
        f.unlink(missing_ok=True)
        return {"ok": True}
    return {"error": "알 수 없는 동작"}


_VIS = {}


def vision_models():
    """설치된 Ollama 모델 중 이미지를 볼 수 있는 것(능력 목록에 vision 이 있는 것)."""
    out = []
    for n in llms():
        if n not in _VIS:
            try:
                _VIS[n] = "vision" in (http(OLLAMA + "/api/show", {"model": n}, 10).get("capabilities") or [])
            except Exception:
                _VIS[n] = False
        if _VIS[n]:
            out.append(n)
    return out


DESCRIBE = {
    "tags": "Describe this image as a comma-separated list of short English tags (like Danbooru tags): subject count, hair, eyes, clothing, pose, expression, background, lighting, art style. Output only the tags.",
    "sentence": "Write a detailed English prompt for an image generator that would recreate this image: subject, clothing, pose, expression, setting, lighting, camera angle and style, in 2-4 sentences. Output only the prompt text.",
    "video": "Write a single English paragraph prompt for a video generator that starts from this image as the first frame: describe the scene, then how the subject and the camera move over a few seconds. Output only the prompt text.",
}


def describe_image(p):
    mods = vision_models()
    if not mods:
        return {"error": "이미지를 볼 수 있는 대화 모델이 없어요. '설치와 모델' 탭에서 'Qwen2.5-VL 7B(이미지 보는 모델)'를 설치해 주세요."}
    model = p.get("model") if p.get("model") in mods else mods[0]
    style = p.get("style") if p.get("style") in DESCRIBE else "sentence"
    try:
        img = load_img(p["image"])
    except Exception:
        return {"error": "이미지를 읽을 수 없어요."}
    img.thumbnail((1344, 1344))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=90)
    claim("chat")
    try:
        r = http(OLLAMA + "/api/chat", {"model": model, "stream": False, "keep_alive": "2m",
                                       "messages": [{"role": "user", "content": DESCRIBE[style], "images": [base64.b64encode(b.getvalue()).decode()]}]}, 300)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", "")
        except Exception:
            msg = f"HTTP {e.code}"
        return {"error": msg or "설명을 만들지 못했어요."}
    except Exception:
        return {"error": "대화 엔진(Ollama)에 연결할 수 없어요."}
    text = re.sub(r"<think>.*?</think>", "", (r.get("message") or {}).get("content", ""), flags=re.S).strip()
    return {"text": text, "model": model} if text else {"error": "모델이 빈 답을 돌려줬어요. 다른 모델로 다시 해 보세요."}


# ───────────────────────── 기록 갤러리 ─────────────────────────
GAL_FILE = ROOT / "gallery.json"
GAL_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm"}
_GMETA = {}


def gal_favs():
    try:
        return set(json.loads(GAL_FILE.read_text(encoding="utf-8")).get("favs", []))
    except (OSError, ValueError):
        return set()


def gal_fav(p):
    rel = str(p.get("file") or "")
    parts = [x for x in urllib.parse.unquote(rel[5:] if rel.startswith("/out/") else rel).split("/") if x]
    if len(parts) != 2 or parts[0] not in OUT_SUB.values():
        return {"error": "알 수 없는 파일"}
    key = parts[0] + "/" + Path(parts[1]).name
    with _PLOCK:
        fav = gal_favs()
        (fav.add if p.get("on") else fav.discard)(key)
        GAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        GAL_FILE.write_text(json.dumps({"favs": sorted(fav)}, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "fav": bool(p.get("on"))}


def gal_prompt(path, mtime):
    """파일에 기록된 프롬프트(검색용). 한 번 읽으면 기억해 둬요."""
    k = (str(path), mtime)
    if k in _GMETA:
        return _GMETA[k]
    txt = ""
    try:
        if path.suffix.lower() == ".png":
            with Image.open(path) as im:
                h = im.info.get("hub")
                txt = json.loads(h).get("prompt", "") if h else ""
                if not txt and im.info.get("parameters"):
                    txt = str(im.info["parameters"]).split("\nNegative prompt:")[0]
        elif path.suffix.lower() in (".mp4", ".webm"):
            sc = path.with_name(path.name + ".json")
            txt = json.loads(sc.read_text(encoding="utf-8")).get("prompt", "") if sc.is_file() else ""
    except Exception:
        txt = ""
    if len(_GMETA) > 5000:
        _GMETA.clear()
    _GMETA[k] = txt
    return txt


def gallery(q):
    kind, text, off = (q.get("kind") or [""])[0], (q.get("q") or [""])[0].strip().lower(), int((q.get("offset") or ["0"])[0] or 0)
    only_fav, lim = (q.get("fav") or [""])[0] == "1", 60
    favs, rows = gal_favs(), []
    for sub in OUT_SUB.values():
        if kind and kind != sub:
            continue
        d = OUT / sub
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.suffix.lower() in GAL_EXT and f.is_file():
                try:
                    st = f.stat()
                except OSError:
                    continue
                rows.append((st.st_mtime, sub, f))
    rows.sort(key=lambda r: r[0], reverse=True)
    out = []
    for mt, sub, f in rows:
        key = sub + "/" + f.name
        if only_fav and key not in favs:
            continue
        pr = None
        if text:
            pr = gal_prompt(f, mt)
            if text not in f.name.lower() and text not in pr.lower():
                continue
        out.append((mt, sub, f, key, pr))
    page = out[off:off + lim]
    items = [{"url": "/out/" + urllib.parse.quote(sub) + "/" + urllib.parse.quote(f.name), "kind": sub, "name": f.name, "time": int(mt),
              "fav": key in favs, "video": f.suffix.lower() in (".mp4", ".webm"),
              "prompt": (pr if pr is not None else gal_prompt(f, mt))[:200]} for mt, sub, f, key, pr in page]
    return {"items": items, "total": len(out), "more": off + lim < len(out)}


def thumb_bytes(path, w=320):
    """갤러리 미리보기(작은 JPEG). 한 번 만들면 cache 폴더에 둬요."""
    st = path.stat()
    key = hashlib.sha1(f"{path}|{st.st_mtime_ns}|{w}".encode()).hexdigest()[:20]
    cp = ROOT / "cache" / "thumbs" / (key + ".jpg")
    if cp.is_file():
        return cp.read_bytes()
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((w, w))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=80)
    cp.parent.mkdir(parents=True, exist_ok=True)
    try:
        cp.write_bytes(b.getvalue())
    except OSError:
        pass
    return b.getvalue()


# ───────────────────────── 커스텀 노드 도우미 ─────────────────────────
_NM = {"t": 0.0, "map": None, "idx": None}
NODE_JOBS = {}


def nodemap():
    """ComfyUI-Manager 가 관리하는 '노드 이름 → 설치 저장소' 목록(하루 동안 기억해요)."""
    if _NM["map"] is not None and time.time() - _NM["t"] < 86400:
        return _NM["map"]
    cp = ROOT / "cache" / "extension-node-map.json"
    try:
        if cp.is_file() and time.time() - cp.stat().st_mtime < 86400 * 3:
            m = json.loads(cp.read_text(encoding="utf-8"))
        else:
            with urllib.request.urlopen(NODEMAP_URL, timeout=60) as r:
                raw = r.read()
            m = json.loads(raw)
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_bytes(raw)
    except Exception:
        if cp.is_file():
            try:
                m = json.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                raise RuntimeError("노드 목록을 불러오지 못했어요. 인터넷 연결을 확인해 주세요.") from None
        else:
            raise RuntimeError("노드 목록을 불러오지 못했어요. 인터넷 연결을 확인해 주세요.") from None
    _NM.update(t=time.time(), map=m, idx=None)
    return m


def _repo_dir(url):
    return COMFY / "custom_nodes" / Path(urllib.parse.urlparse(url).path).name.removesuffix(".git")


def node_sources(missing):
    """없는 노드 이름들 → 설치할 저장소별로 묶어서 돌려줘요."""
    m = nodemap()
    if _NM["idx"] is None:
        idx = {}
        for repo, v in m.items():
            for n in (v[0] if v and isinstance(v[0], list) else []):
                idx.setdefault(n, []).append(repo)
        _NM["idx"] = idx
    by, unknown = {}, []
    for n in missing:
        repos = [r for r in _NM["idx"].get(n, []) if r.startswith(GHURL + "/")]
        if not repos:
            unknown.append(n)
            continue
        r = repos[0]
        by.setdefault(r, []).append(n)
    out = [{"repo": r, "title": ((m[r][1] or {}).get("title_aux") if len(m[r]) > 1 else "") or Path(r).name, "nodes": ns,
            "installed": _repo_dir(r).is_dir(), "state": (NODE_JOBS.get(r) or {}).get("state", "")} for r, ns in by.items()]
    return {"repos": out, "unknown": unknown}


def _node_install(repo):
    J = NODE_JOBS[repo]
    try:
        import zipfile
        dest = _repo_dir(repo)
        if dest.exists():
            raise RuntimeError("이미 설치돼 있어요. ComfyUI 를 다시 시작하면 적용돼요.")
        J["msg"] = "내려받는 중…"
        tmp = ROOT / "cache" / "nodes"
        tmp.mkdir(parents=True, exist_ok=True)
        zp = tmp / (dest.name + ".zip")
        with urllib.request.urlopen(repo + "/archive/HEAD.zip", timeout=120) as r, open(zp, "wb") as f:
            total = 0
            while True:
                c = r.read(1 << 20)
                if not c:
                    break
                total += len(c)
                if total > 300 << 20:
                    raise RuntimeError("파일이 너무 커서 중단했어요.")
                f.write(c)
        J["msg"] = "압축 푸는 중…"
        (COMFY / "custom_nodes").mkdir(exist_ok=True)
        stage = tmp / (dest.name + "-x")
        shutil.rmtree(stage, ignore_errors=True)
        with zipfile.ZipFile(zp) as z:
            names = z.namelist()
            top = names[0].split("/")[0] if names else ""
            for n in names:
                t = (stage / n).resolve()
                if not str(t).startswith(str(stage.resolve())):
                    raise RuntimeError("압축 파일 경로가 올바르지 않아요.")
            z.extractall(stage)
        src = stage / top if top and (stage / top).is_dir() else stage
        shutil.move(str(src), str(dest))
        shutil.rmtree(stage, ignore_errors=True)
        zp.unlink(missing_ok=True)
        req = dest / "requirements.txt"
        note = ""
        if req.is_file():
            if PY.exists():
                J["msg"] = "필요한 파이썬 패키지 설치 중…(몇 분 걸릴 수 있어요)"
                r = subprocess.run([str(PY), "-s", "-m", "pip", "install", "-r", str(req), "--no-warn-script-location"], cwd=HOME,
                                   capture_output=True, text=True, timeout=1500)
                if r.returncode:
                    note = " 다만 필요한 패키지 설치에 실패했어요(logs\\nodes.log 참고). 노드가 동작하지 않으면 ComfyUI Manager 로 설치해 보세요."
                    LOGS.mkdir(exist_ok=True)
                    (LOGS / "nodes.log").write_text((r.stdout or "")[-4000:] + (r.stderr or "")[-4000:], encoding="utf-8")
            else:
                note = " (python_embeded 를 찾지 못해 패키지 설치는 건너뛰었어요.)"
        J["state"], J["msg"] = "done", "설치했어요. 아래 [이미지 엔진 다시 시작]을 눌러야 적용돼요." + note
    except Exception as e:  # noqa: BLE001
        J["state"], J["msg"] = "error", str(e) or e.__class__.__name__
        log("[노드 설치 오류]", repr(e))


def node_install(p):
    repo = str(p.get("repo") or "")
    try:
        ok = repo in nodemap() and repo.startswith(GHURL + "/")
    except RuntimeError as e:
        return {"error": str(e)}
    if not ok:
        return {"error": "목록에 없는 주소는 설치하지 않아요."}
    if NODE_JOBS.get(repo, {}).get("state") == "running":
        return {"ok": True}
    NODE_JOBS[repo] = {"state": "running", "msg": "시작해요…"}
    threading.Thread(target=_node_install, args=(repo,), daemon=True).start()
    return {"ok": True}


def restart_comfy():
    """허브가 띄운 ComfyUI 를 껐다가 다시 켜요(새로 설치한 노드를 읽게 하려고)."""
    mine = [pr for pr in procs if any("main.py" in str(a) for a in (pr.args if isinstance(pr.args, (list, tuple)) else [pr.args]))]
    if not mine and alive(CUI + "/system_stats"):
        return {"error": "이 ComfyUI 는 스튜디오가 켠 게 아니라서 여기서 다시 시작할 수 없어요. ComfyUI 창을 닫고 다시 실행해 주세요."}
    for pr in mine:
        pr.terminate()
        try:
            pr.wait(timeout=20)
        except Exception:
            pr.kill()
        procs.remove(pr)
    start_engines()
    _CAPS["t"] = 0
    return {"ok": True}


# ───────────────────────── 모델 설치 ─────────────────────────
def add_task(label, **kw):
    t = dict(id=uuid.uuid4().hex[:8], label=label, state="queued", msg="", done=0, total=0, **kw)
    TASKS.append(t)
    return t


def pull(t):
    body = json.dumps({"name": t["model"], "model": t["model"], "stream": True}).encode()
    req = urllib.request.Request(OLLAMA + "/api/pull", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=7200) as r:
        for line in r:
            d = json.loads(line)
            if "error" in d:
                raise RuntimeError(d["error"])
            t["msg"] = d.get("status", "")
            if d.get("total"):
                t.update(done=d.get("completed", 0), total=d["total"])


class _Redirect(urllib.request.HTTPRedirectHandler):
    """다른 서버(CDN)로 넘어갈 때 Authorization 헤더를 빼요. 남겨 두면 CDN 이 거부하고, 토큰이 새어 나가기도 해요."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        n = super().redirect_request(req, fp, code, msg, headers, newurl)
        if n is not None and urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            n.headers.pop("Authorization", None)
            n.unredirected_hdrs.pop("Authorization", None)
        return n


OPENER = urllib.request.build_opener(_Redirect)


def host_of(url):
    return urllib.parse.urlparse(url).netloc.lower()


def token_for(url):
    """주소의 사이트에 맞는 저장된 API 키를 돌려줘요(Civitai / HuggingFace)."""
    h, tk = host_of(url), settings().get("tokens", {})
    if h.endswith("civitai.com") or h.endswith(urllib.parse.urlparse(CIVITAI).netloc):
        return "civitai", tk.get("civitai")
    if h.endswith("huggingface.co") or h.endswith(urllib.parse.urlparse(HFURL).netloc):
        return "hf", tk.get("hf")
    return None, None


def download(t):
    url = t["url"]
    site, saved = token_for(url)
    tok = t.get("token") or saved
    hdr = {}
    if tok and site == "civitai" or (tok and t.get("token") and site is None):
        url += ("&" if "?" in url else "?") + "token=" + urllib.parse.quote(tok)
    elif tok and site == "hf":
        hdr["Authorization"] = "Bearer " + tok
    d = MODELS / t["dir"]
    d.mkdir(parents=True, exist_ok=True)
    part = d / (hashlib.sha1(t["url"].encode()).hexdigest()[:12] + ".part")
    final = d / (t.get("name") or Path(urllib.parse.urlparse(t["url"]).path).name)
    if final.exists():
        t["msg"] = "이미 설치되어 있어요"
        return
    pos = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": "LocalAI-Studio/1.0", **hdr,
                                               **({"Range": f"bytes={pos}-"} if pos else {})})
    try:
        r = OPENER.open(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and pos:
            part.replace(final)
            return
        if e.code in (401, 403):
            raise RuntimeError(f"권한이 없어요 (HTTP {e.code}). 다운로드 탭에서 {'Civitai' if site == 'civitai' else 'HuggingFace' if site == 'hf' else '해당 사이트'} API 키를 넣었는지, "
                               "모델 페이지에서 사용 동의(게이트)를 눌렀는지 확인하세요.") from None
        raise RuntimeError(f"다운로드 실패 (HTTP {e.code}). URL 을 확인하세요.") from None
    with r:
        if "text/html" in r.headers.get("Content-Type", ""):
            raise RuntimeError("파일 대신 웹페이지가 응답됐어요. 로그인/API 키가 필요한 링크일 수 있습니다.")
        cd = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", r.headers.get("Content-Disposition", ""))
        if cd and not t.get("name"):
            final = d / Path(urllib.parse.unquote(cd.group(1))).name
        if pos and r.status != 206:
            pos = 0
        total = pos + int(r.headers.get("Content-Length") or 0)
        done = pos
        with open(part, "ab" if pos else "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                t.update(done=done, total=total, msg="다운로드 중")
    if total and done < total:
        raise RuntimeError("전송이 중단됐어요. 다시 설치하면 이어받습니다.")
    part.replace(final)


def worker():
    while True:
        t = next((x for x in TASKS if x["state"] == "queued"), None)
        if not t:
            time.sleep(0.5)
            continue
        t["state"] = "running"
        try:
            pull(t) if t["kind"] == "ollama" else sam_run_install(t) if t["kind"] == "sam" else download(t)
            t["state"], t["msg"] = "done", t["msg"] if t["msg"] == "이미 설치되어 있어요" else "완료"
        except Exception as e:
            t["state"], t["msg"] = "error", str(e)
            log("[설치 오류]", t["label"], t["msg"])


def img_installed(m):
    return all((MODELS / x["dir"] / Path(urllib.parse.urlparse(x["url"]).path).name).exists() for x in m["files"])


def expand_ids(ids):
    """선택한 항목이 필요로 하는 항목(requires)까지 포함해 순서대로 돌려줍니다."""
    allm = {m["id"]: m for m in CATALOG["llm"] + CATALOG["image"]}
    out, queue = [], list(ids)
    while queue:
        i = queue.pop(0)
        if i in allm and i not in out:
            out.append(i)
            queue += allm[i].get("requires", [])
    return out


def install(p):
    allm = {m["id"]: m for m in CATALOG["llm"] + CATALOG["image"]}
    items = [allm[i] for i in expand_ids(p.get("ids", []))]
    need = sum(m.get("gb", 0) for m in items if "ollama" in m or not img_installed(m))
    free = shutil.disk_usage(ROOT).free / 1e9
    if need + 3 > free:
        return {"error": f"디스크 여유 공간이 부족해요. 필요 약 {need:.0f}GB / 여유 {free:.0f}GB"}
    for m in items:
        if "ollama" in m:
            add_task(m["name"], kind="ollama", model=m["ollama"])
        else:
            for x in m["files"]:
                add_task(f'{m["name"]} ({Path(urllib.parse.urlparse(x["url"]).path).name})',
                         kind="file", url=x["url"], dir=x["dir"])
    c = p.get("custom") or {}
    if str(c.get("url", "")).startswith("http") and c.get("dir") in FOLDERS:
        add_task("직접 추가: " + c["url"][:60], kind="file", url=c["url"], dir=c["dir"],
                 token=c.get("token") or None, name=Path(c.get("name") or "").name or None)
    if (p.get("ollama") or "").strip():
        add_task(p["ollama"].strip(), kind="ollama", model=p["ollama"].strip())
    return {"ok": True}


# ───────────────────────── 설정(API 키) ─────────────────────────
SETTINGS_FILE = ROOT / "settings.json"


def settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(d):
    SETTINGS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass


def set_token(name, value):
    if name not in ("civitai", "hf"):
        return {"error": "알 수 없는 사이트"}
    d = settings()
    d.setdefault("tokens", {})
    value = (value or "").strip()
    if value:
        d["tokens"][name] = value
    else:
        d["tokens"].pop(name, None)
    save_settings(d)
    return {"ok": True, "tokens": token_state()}


def token_state():
    tk = settings().get("tokens", {})
    return {"civitai": bool(tk.get("civitai")), "hf": bool(tk.get("hf"))}


# ───────────────────────── 다운로드 탭: Civitai / HuggingFace 검색 ─────────────────────────
CIVITAI_TYPES = {"checkpoints": ["Checkpoint"], "loras": ["LORA"], "embeddings": ["TextualInversion"],
                 "controlnet": ["Controlnet"], "vae": ["VAE"], "upscale_models": ["Upscaler"]}
CIVITAI_DIR = {"Checkpoint": "checkpoints", "LORA": "loras", "LoCon": "loras", "TextualInversion": "embeddings",
               "Controlnet": "controlnet", "VAE": "vae", "Upscaler": "upscale_models"}
CIVITAI_SORT = {"popular": "Most Downloaded", "rated": "Highest Rated", "new": "Newest"}


def api_get(url, token=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 LocalAI-Studio/1.0",
                                               "Accept": "application/json", "Accept-Language": "en-US,en;q=0.8",
                                               **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with OPENER.open(req, timeout=25) as r:
            raw = r.read()
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            log("[검색 응답이 JSON이 아니에요]", url.split("?")[0], r.status, r.headers.get("Content-Type"), raw[:200])
            head = re.sub(r"\s+", " ", raw[:90].decode("utf-8", "replace")).strip()
            raise RuntimeError(f"검색 서버가 예상과 다른 응답을 줬어요 ({r.headers.get('Content-Type')}: {head}). 이 문구를 알려 주시면 고칠 수 있어요.") from None
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("로그인(API 키)이 필요하거나 권한이 없어요. 키를 넣은 뒤 다시 검색하세요.") from None
        raise RuntimeError(f"검색 서버 응답 오류 (HTTP {e.code})") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("검색 서버에 연결하지 못했어요. 인터넷 연결을 확인하세요.") from None
    except ValueError:
        raise RuntimeError("검색 서버가 예상과 다른 응답을 줬어요. 잠시 뒤 다시 시도하거나 다른 검색어를 써 보세요.") from None


def have_file(d, name):
    return bool(name) and (MODELS / d / Path(name).name).exists()


def _lvl(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def dl_search(p):
    q, page = (p.get("query") or "").strip(), clamp(num(p, "page", 1, int), 1, 200)
    kind = p.get("dir") if p.get("dir") in CIVITAI_TYPES else "loras"
    if p.get("source") == "hf":
        params = {"search": q, "limit": 20, "sort": "downloads", "direction": -1}
        if not q:
            params["filter"] = {"checkpoints": "text-to-image", "loras": "lora", "diffusion_models": "text-to-image"}.get(kind, "text-to-image")
        if q and kind == "loras":
            params["filter"] = "lora"
        if page > 1:
            params["offset"] = (page - 1) * 20
        data = api_get(HFURL + "/api/models?" + urllib.parse.urlencode(params), settings().get("tokens", {}).get("hf"))
        return {"source": "hf", "page": page, "items": [
            {"id": m.get("id"), "title": m.get("id"), "downloads": m.get("downloads", 0), "likes": m.get("likes", 0),
             "tags": (m.get("tags") or [])[:6], "url": f'{HFURL}/{m.get("id")}'} for m in data if m.get("id")]}
    # 검색어(query)가 있으면 Civitai 는 page 를 거부해요(HTTP 400). 이때는 cursor 로 이어 받아요.
    params = [("limit", 20), ("sort", CIVITAI_SORT.get(p.get("sort"), "Most Downloaded")), ("nsfw", "true" if p.get("nsfw") else "false")]
    params += [("types", t) for t in CIVITAI_TYPES[kind]]
    if q:
        params.append(("query", q))
        if p.get("cursor"):
            params.append(("cursor", str(p["cursor"])))
    elif page > 1:
        params.append(("page", page))
    if p.get("base"):
        params.append(("baseModels", str(p["base"])))
    data = api_get(CIVITAI + "/api/v1/models?" + urllib.parse.urlencode(params), settings().get("tokens", {}).get("civitai"))
    items = []
    for m in data.get("items") or []:
        vers = []
        for v in (m.get("modelVersions") or [])[:6]:
            fl = []
            for f in v.get("files") or []:
                nm = f.get("name") or ""
                if not nm.lower().endswith(EXT) or f.get("type") not in (None, "Model", "Pruned Model"):
                    continue
                d = CIVITAI_DIR.get(m.get("type"), kind)
                fl.append({"name": nm, "mb": round((f.get("sizeKB") or 0) / 1024), "url": f.get("downloadUrl") or v.get("downloadUrl"),
                           "primary": bool(f.get("primary")), "installed": have_file(d, nm), "dir": d})
            if fl:
                im = next((i for i in (v.get("images") or []) if (i.get("type") or "image") == "image"), None)
                vers.append({"id": v.get("id"), "name": v.get("name"), "base": v.get("baseModel"), "files": fl,
                             "thumb": im.get("url") if im else None, "thumb_nsfw": bool(im and (im.get("nsfw") not in (None, False, "None", "none") or _lvl(im.get("nsfwLevel")) > 1))})
        if vers:
            st = m.get("stats") or {}
            items.append({"id": m.get("id"), "title": m.get("name"), "type": m.get("type"), "nsfw": bool(m.get("nsfw")),
                          "downloads": st.get("downloadCount") or 0, "likes": st.get("thumbsUpCount") or 0, "versions": vers,
                          "url": f'{CIVITAI}/models/{m.get("id")}'})
    md = data.get("metadata") or {}
    return {"source": "civitai", "page": page, "items": items, "more": bool(md.get("nextCursor") if q else md.get("nextPage")), "cursor": md.get("nextCursor")}


def dl_hf_files(p):
    repo = (p.get("repo") or "").strip()
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        return {"error": "저장소 이름이 올바르지 않아요."}
    d = api_get(f"{HFURL}/api/models/{repo}?blobs=true", settings().get("tokens", {}).get("hf"))
    out = []
    for sb in d.get("siblings", []):
        n = sb.get("rfilename", "")
        if n.lower().endswith(EXT):
            dest = guess_dir(n, d.get("tags") or [])
            out.append({"name": Path(n).name, "path": n, "mb": round((sb.get("size") or 0) / 1048576), "dir": dest,
                        "url": f"{HFURL}/{repo}/resolve/main/{urllib.parse.quote(n)}", "installed": have_file(dest, Path(n).name)})
    return {"repo": repo, "gated": bool(d.get("gated")), "files": out}


def guess_dir(name, tags):
    n = name.lower()
    if any(k in n for k in ("vae", "ae.safetensors")):
        return "vae"
    if any(k in n for k in ("t5xxl", "clip_l", "umt5", "text_encoder", "qwen_2.5")):
        return "text_encoders"
    if "controlnet" in n or "control" in n:
        return "controlnet"
    if n.endswith((".pth", ".pt")) and any(k in n for k in ("esrgan", "upscal", "sharp")):
        return "upscale_models"
    if "lora" in n or "lora" in tags:
        return "loras"
    if "diffusion_models" in n or "unet" in n or n.endswith(".gguf"):
        return "diffusion_models"
    return "checkpoints"


def dl_get(p):
    url, d = str(p.get("url", "")), p.get("dir")
    if not url.startswith("https://") and not url.startswith("http://"):
        return {"error": "주소가 올바르지 않아요."}
    if d not in FOLDERS:
        return {"error": "저장 위치가 올바르지 않아요."}
    nm = Path(p.get("name") or "").name or None
    add_task(("다운로드: " + (nm or url[:60])), kind="file", url=url, dir=d, name=nm, token=p.get("token") or None)
    return {"ok": True}


# ───────────────────────── 선택 도구 (MobileSAM) ─────────────────────────
SAM = {"engine": None}
SAM_LOCK = threading.Lock()


def sam_status():
    busy = any(t.get("kind") == "sam" and t["state"] in ("queued", "running") for t in TASKS)
    files_ok, ort = sam.installed(MODELS / "sam"), sam.have_ort()
    return {"ort": ort, "files": files_ok, "ready": ort and files_ok, "busy": busy, "mb": 45}


def sam_install():
    if any(t.get("kind") == "sam" and t["state"] in ("queued", "running") for t in TASKS):
        return {"ok": True}
    if shutil.disk_usage(ROOT).free < 1e9:
        return {"error": "디스크 여유 공간이 부족해요."}
    add_task("선택 도구 설치 (MobileSAM)", kind="sam")
    return {"ok": True}


def sam_run_install(t):
    if not sam.have_ort():
        t["msg"] = "분석 엔진(onnxruntime) 설치 중"
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--no-warn-script-location", "onnxruntime"],
                           capture_output=True, text=True, timeout=1200)
        if r.returncode != 0:
            log("[pip 오류]", (r.stdout + r.stderr)[-600:])
            raise RuntimeError("onnxruntime 설치에 실패했어요. 인터넷 연결을 확인하거나 스튜디오 창의 오류 내용을 알려 주세요.")
        import importlib
        importlib.invalidate_caches()
        if not sam.have_ort():
            raise RuntimeError("onnxruntime 설치 후에도 불러오지 못했어요. 스튜디오를 다시 시작해 보세요.")
    for name in (sam.ENCODER, sam.DECODER):
        t.update(url=sam.REPO + name, dir="sam", name=None, msg=f"{name} 받는 중", done=0, total=0)
        download(t)
    SAM["engine"] = None


def sam_segment(p):
    st = sam_status()
    if not st["ready"]:
        return {"error": "선택 도구가 아직 설치되지 않았어요.", "need": True}
    with SAM_LOCK:
        if SAM["engine"] is None:
            SAM["engine"] = sam.Sam(MODELS / "sam", SAM.get("factory"))
        eng = SAM["engine"]
        key = p.get("id")
        if key not in eng.cache:
            if not p.get("image"):
                return {"error": "이미지를 다시 보내 주세요.", "resend": True}
            key = eng.embed(load_img(p["image"]))
        pts = []
        for x, y, l in (p.get("points") or [])[:20]:
            pts.append((clamp(float(x), 0.0, 1.0), clamp(float(y), 0.0, 1.0), 1 if l else 0))
        if not pts:
            return {"error": "점이 없어요."}
        m = eng.segment(key, pts, num(p, "level", 1, int))
    im = Image.fromarray((m * 255).astype("uint8"), "L")
    if max(im.size) > 1024:
        k = 1024 / max(im.size)
        im = im.resize((round(im.width * k), round(im.height * k)), RS.NEAREST)
    bio = io.BytesIO()
    im.save(bio, "PNG")
    return {"id": key, "mask": "data:image/png;base64," + base64.b64encode(bio.getvalue()).decode()}


# ───────────────────────── 설치된 파일 관리(삭제) ─────────────────────────
def fsize(p):
    try:
        return p.stat().st_size
    except OSError:
        return 0


def manage():
    out = {"folders": {}, "llm": []}
    for d in sorted(FOLDERS):
        base = MODELS / d
        out["folders"][d] = sorted(({"name": f.name, "size": fsize(f)} for f in base.iterdir()
                                    if f.is_file() and (f.suffix.lower() in EXT or f.suffix == ".part")), key=lambda x: x["name"].lower()) if base.is_dir() else []
        if d in ("checkpoints", "diffusion_models"):
            for e in out["folders"][d]:
                if not e["name"].endswith(".part"):
                    fam, allin, how = model_family(d, e["name"])
                    e.update(family=fam, all_in_one=allin, how=how, override=settings().get("families", {}).get(f"{d}/{e['name']}", "auto"))
    try:
        out["llm"] = [{"name": m["name"], "size": m.get("size", 0)} for m in http(OLLAMA + "/api/tags", timeout=3).get("models", [])]
    except Exception:
        pass
    return out


def delete_item(p):
    if p.get("kind") == "ollama":
        name = str(p.get("name", "")).strip()
        if not name:
            return {"error": "이름이 없어요."}
        req = urllib.request.Request(OLLAMA + "/api/delete", data=json.dumps({"model": name, "name": name}).encode(), method="DELETE",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=30).close()
        except urllib.error.HTTPError as e:
            return {"error": f"삭제하지 못했어요 (HTTP {e.code})"}
        except Exception:
            return {"error": "대화 엔진(Ollama)에 연결하지 못했어요."}
        return {"ok": True}
    d, name = p.get("dir"), str(p.get("name", ""))
    if d not in FOLDERS or not name or Path(name).name != name:
        return {"error": "삭제할 수 없는 항목이에요."}
    f = MODELS / d / name
    if not f.is_file():
        return {"error": "파일을 찾을 수 없어요."}
    try:
        f.unlink()
    except OSError as e:
        return {"error": f"삭제하지 못했어요: {e.strerror or e}. 다른 프로그램(ComfyUI 등)이 사용 중일 수 있어요."}
    return {"ok": True}


# ───────────────────────── 저장 공간 점검 / 정리 ─────────────────────────
def dir_size(p, skip=()):
    """폴더 전체 크기. 심볼릭 링크는 따라가지 않아요."""
    total = 0
    stack = [p]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            if e.path not in skip:
                                stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def quick_sig(f):
    """같은 파일인지 빠르게 비교: 크기 + 앞뒤 1MB 지문."""
    h = hashlib.sha1()
    try:
        with open(f, "rb") as fh:
            h.update(fh.read(1 << 20))
            if fsize(f) > (2 << 20):
                fh.seek(-(1 << 20), 2)
                h.update(fh.read(1 << 20))
    except OSError:
        return None
    return f"{fsize(f)}:{h.hexdigest()}"


def disk_report():
    import shutil
    items, skip_models = [], str(MODELS)
    def add(key, label, path, note="", clean=None, skip=()):
        path = Path(path)
        if path.exists():
            items.append(dict(key=key, label=label, bytes=dir_size(str(path), skip), note=note, clean=clean))
    for d in sorted(FOLDERS):
        add("m_" + d, "모델: " + d, MODELS / d, "필요 없는 파일은 아래 목록이나 '설치와 모델'의 설치된 파일에서 지울 수 있어요.")
    add("llm", "대화 모델 (Ollama)", ROOT / "models" / "llm", "쓰지 않는 대화 모델을 지우면 가장 크게 줄어요.")
    add("outputs", "결과 이미지 (outputs)", OUT, "직접 만든 결과물이라 자동으로 지우지 않아요. 필요 없는 건 폴더에서 직접 지워 주세요.")
    add("temp", "임시 미리보기 (ComfyUI temp)", COMFY / "temp", "지워도 안전해요.", "temp")
    add("input", "임시 입력 이미지 (ComfyUI input)", COMFY / "input", "이 프로그램이 만든 hub_*.png 만 지워요.", "input")
    add("backup", "업데이트 되돌리기용 백업", ROOT / "backup", "가장 최근 1개만 남기고 지워요.", "backup")
    add("logs", "로그", LOGS, "지워도 안전해요.", "logs")
    add("comfy_engine", "ComfyUI 엔진 (python_embeded)", HOME / "python_embeded", "엔진 본체라 지우면 안 돼요.")
    add("comfy_app", "ComfyUI 프로그램·확장", COMFY, "엔진 본체라 지우면 안 돼요.", skip=(str(MODELS), str(COMFY / "temp"), str(COMFY / "input"), str(COMFY / "output")))
    add("comfy_out", "ComfyUI 자체 output 폴더", COMFY / "output", "이 프로그램은 쓰지 않는 폴더예요. 비어 있지 않다면 ComfyUI 화면을 따로 쓰고 계신 거예요.")
    add("ollama_eng", "Ollama 프로그램", ROOT / "engine" / "ollama", "엔진 본체라 지우면 안 돼요.")
    home = Path.home()
    for k, label, pth, note in (("o_default", "별도로 설치한 Ollama의 모델 폴더 (~/.ollama)", home / ".ollama", "이 프로그램과 따로 설치한 Ollama가 같은 모델을 한 번 더 받아 둔 경우예요. 쓰지 않으면 직접 지워도 돼요."),
                                ("hf", "HuggingFace 캐시 (~/.cache/huggingface)", home / ".cache" / "huggingface", "다른 프로그램이 받은 캐시예요. 필요 없으면 직접 지워도 돼요."),
                                ("pip", "pip 캐시", home / ".cache" / "pip", "필요 없으면 직접 지워도 돼요.")):
        add(k, label, pth, note)
    parts = [dict(dir=d, name=f.name, size=fsize(f)) for d in sorted(FOLDERS) if (MODELS / d).is_dir()
             for f in (MODELS / d).iterdir() if f.is_file() and f.suffix == ".part"]
    # 가장 큰 파일 15개 + 중복 의심 파일
    big, sigs = [], {}
    for d in sorted(FOLDERS):
        base = MODELS / d
        if not base.is_dir():
            continue
        for f in base.iterdir():
            if f.is_file() and f.suffix.lower() in EXT:
                sz = fsize(f)
                big.append(dict(dir=d, name=f.name, size=sz))
                if sz > (50 << 20):
                    sigs.setdefault(sz, []).append((d, f))
    big.sort(key=lambda x: -x["size"])
    dups = []
    for sz, fs in sigs.items():
        if len(fs) > 1:
            g = {}
            for d, f in fs:
                g.setdefault(quick_sig(f), []).append(dict(dir=d, name=f.name, size=sz))
            dups += [v for k, v in g.items() if k and len(v) > 1]
    items.sort(key=lambda x: -x["bytes"])
    try:
        du = shutil.disk_usage(ROOT)
        free, total = du.free, du.total
    except OSError:
        free = total = 0
    return dict(items=items, big=big[:15], dups=dups, parts=parts, free=free, total=total,
                used=sum(i["bytes"] for i in items if i["key"] not in ("o_default", "hf", "pip")))


def clean_item(what):
    """안전한 임시 파일만 지워요. 돌려주는 값: 확보한 바이트."""
    freed = 0
    def rm(f):
        nonlocal freed
        try:
            sz = fsize(f)
            f.unlink()
            freed += sz
        except OSError:
            pass
    if what == "temp":
        for f in (COMFY / "temp").rglob("*"):
            if f.is_file():
                rm(f)
    elif what == "input":
        for f in (COMFY / "input").glob("hub_*.png"):
            rm(f)
    elif what == "logs":
        for f in LOGS.glob("*.old"):
            rm(f)
        for n in ("hub.log", "comfyui.log", "ollama.log"):   # 실행 중인 로그는 비워서 줄여요
            f = LOGS / n
            try:
                if f.is_file() and f.stat().st_size > 1 << 20:
                    sz = f.stat().st_size
                    open(f, "wb").close()
                    freed += sz
            except OSError:
                pass
    elif what == "backup":
        bk = ROOT / "backup"
        olds = sorted((d for d in bk.iterdir() if d.is_dir() and (d / "_restore.json").is_file()), reverse=True) if bk.is_dir() else []
        import shutil
        for d in olds[1:]:
            freed += dir_size(str(d))
            shutil.rmtree(d, ignore_errors=True)
    elif what == "parts":
        if any(t.get("state") in ("running", "queued") for t in TASKS):
            return {"error": "설치·다운로드가 진행 중일 때는 받다 만 파일을 지우지 않아요."}
        for d in FOLDERS:
            for f in (MODELS / d).glob("*.part") if (MODELS / d).is_dir() else []:
                rm(f)
    else:
        return {"error": "알 수 없는 정리 항목이에요."}
    return {"ok": True, "freed": freed}


# ───────────────────────── API 응답 ─────────────────────────
def status():
    return {"ollama": alive(OLLAMA + "/api/version"), "comfy": alive(CUI + "/system_stats"), "gpu": GPU, "gpu_live": gpu_live(), "version": VERSION}


FAMILY_CHOICES = ("sd15", "sdxl", "flux", "krea2", "chroma", "qwen", "hidden")


def model_family(folder, name):
    """(계열, 올인원 여부, 판단 방법). 사용자가 직접 지정한 값이 있으면 그걸 써요."""
    d = modelinfo.detect(MODELS / folder / name)
    ov = settings().get("families", {}).get(f"{folder}/{name}")
    if ov in FAMILY_CHOICES:
        return ov, d["all_in_one"], "manual"
    return d["family"], d["all_in_one"], d["how"]


def set_family(p):
    folder, name, fam = p.get("folder"), str(p.get("name", "")), p.get("family") or "auto"
    if folder not in ("checkpoints", "diffusion_models") or Path(name).name != name or not (MODELS / folder / name).is_file():
        return {"error": "파일을 찾을 수 없어요."}
    if fam != "auto" and fam not in FAMILY_CHOICES:
        return {"error": "알 수 없는 계열이에요."}
    d = settings()
    d.setdefault("families", {})
    if fam == "auto":
        d["families"].pop(f"{folder}/{name}", None)
    else:
        d["families"][f"{folder}/{name}"] = fam
    save_settings(d)
    return {"ok": True}


def sorted_models():
    """모델 파일을 탭별로 나눠요: SDXL / FLUX / Chroma / Krea 2. (체크포인트 폴더의 FLUX 올인원은 'ckpt::이름')"""
    sdxl, flux, chroma, krea2, info = [], [], [], [], {}
    for n in files("checkpoints"):
        fam, allin, how = model_family("checkpoints", n)
        info["checkpoints/" + n] = dict(family=fam, all_in_one=allin, how=how)
        if fam == "hidden":
            continue
        if fam == "flux":
            flux.append("ckpt::" + n)
        elif fam == "chroma":
            chroma.append("ckpt::" + n)
        elif fam in ("sd15", "sdxl", "unknown"):
            sdxl.append(n)
    for n in files("diffusion_models"):
        fam, allin, how = model_family("diffusion_models", n)
        info["diffusion_models/" + n] = dict(family=fam, all_in_one=allin, how=how)
        if fam == "krea2":
            krea2.append(n)
        elif fam in ("hidden", "qwen", "sd15", "sdxl", "sd3") or (fam == "unknown" and "qwen" in n.lower()):
            continue
        else:
            (chroma if fam == "chroma" or (fam == "unknown" and "chroma" in n.lower()) else flux).append(n)
    return sdxl, flux, chroma, krea2, info


def lists():
    wc = ROOT / "wildcards"
    sdxl, flux, chroma, krea2, info = sorted_models()
    fp, kp = flux_parts(), krea2_parts()      # 폴더를 한 번씩만 훑어요
    loras = files("loras")
    return {"llm": llms(), "checkpoints": sdxl, "loras": loras, "families": info,
            "lora_info": {n: modelinfo.lora_family(MODELS / "loras" / n)["family"] for n in loras},
            "upscalers": files("upscale_models"), "controlnets": files("controlnet"),
            "vaes": files("vae"), "text_encoders": files("text_encoders"), "diffusion": files("diffusion_models"),
            "fluxmodels": flux, "chromamodels": chroma, "krea2models": krea2, "anymodels": sdxl + flux + chroma + krea2,
            "flux_ready": bool(fp["t5"] and fp["clip_l"] and fp["vae"]),
            "chroma_ready": bool(fp["t5"] and fp["vae"]),
            "krea2_ready": bool(kp["te"] and kp["vae"]),
            "wanmodels": wan_models(), "wan_ready": bool(wan_parts()["te"] and wan_parts()["vae"]),
            "wildcards": sorted(p.stem for p in wc.glob("*.txt")) if wc.is_dir() else [],
            "qwen": bool(find("diffusion_models", "qwen_image_edit") and find("text_encoders", "qwen_2.5_vl")
                         and find("vae", "qwen_image_vae"))}


def catalog():
    have = set(llms())

    ok = img_installed
    return {"llm": [{**m, "installed": m["ollama"] in have or m["ollama"] + ":latest" in have} for m in CATALOG["llm"]],
            "image": [{**m, "installed": ok(m)} for m in CATALOG["image"]]}


def caps_info():
    c = caps()
    return {"samplers": c["samplers"], "schedulers": c["schedulers"],
            "has": {"canny": "Canny" in c["nodes"], "pag": "PerturbedAttentionGuidance" in c["nodes"],
                    "qwen_plus": "TextEncodeQwenImageEditPlus" in c["nodes"],
                    "controlnet": "ControlNetApplyAdvanced" in c["nodes"]}}


# ───────────────────────── HTTP 서버 ─────────────────────────
def folder_map():
    m = {"outputs": OUT, "logs": LOGS, "root": ROOT, "llm": ROOT / "models" / "llm", "wildcards": ROOT / "wildcards",
         "backup": ROOT / "backup"}
    m.update({k: MODELS / k for k in FOLDERS})
    return m


MEDIA = {".mp4": "video/mp4", ".webm": "video/webm", ".webp": "image/webp", ".gif": "image/gif"}
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_bytes(self, b, ctype, code=200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def send_json(self, obj, code=200):
        self.send_bytes(json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", code)

    def send_file(self, path, ctype):
        if not path.is_file():
            return self.send_json({"error": "not found"}, 404)
        st = path.stat()
        etag = '"%x-%x"' % (int(st.st_mtime), st.st_size)
        hdr = {"Cache-Control": "no-cache", "ETag": etag, "Vary": "Accept-Encoding"}
        if self.headers.get("If-None-Match") == etag:      # 바뀌지 않았으면 다시 보내지 않아요
            self.send_response(304)
            for k, v in hdr.items():
                self.send_header(k, v)
            return self.end_headers()
        data = path.read_bytes()
        if "gzip" in (self.headers.get("Accept-Encoding") or "") and len(data) > 1024:
            import gzip
            data = gzip.compress(data, 6)
            hdr["Content-Encoding"] = "gzip"
        self.send_bytes(data, ctype, extra=hdr)

    def send_media(self, path, ctype):
        """영상 파일: 브라우저가 중간으로 건너뛰며 볼 수 있게 Range 요청을 처리해요."""
        if not path.is_file():
            return self.send_json({"error": "not found"}, 404)
        size = path.stat().st_size
        a, b, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                a = int(m.group(1))
                b = int(m.group(2)) if m.group(2) else size - 1
            else:
                a = max(0, size - int(m.group(2)))
            b = min(b, size - 1)
            if a > b:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                return self.end_headers()
            code = 206
        with open(path, "rb") as f:
            f.seek(a)
            data = f.read(b - a + 1)
        extra = {"Accept-Ranges": "bytes", "Cache-Control": "no-cache"}
        if code == 206:
            extra["Content-Range"] = f"bytes {a}-{b}/{size}"
        self.send_bytes(data, ctype, code, extra)

    def guard(self):
        """다른 웹사이트가 로컬 서버를 호출하지 못하게 Host / Origin 을 검사합니다."""
        host = (self.headers.get("Host") or "").split(":")[0]
        org = self.headers.get("Origin")
        if host in ("127.0.0.1", "localhost") and (not org or org in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")):
            return True
        self.send_json({"error": "forbidden"}, 403)
        return False

    def do_GET(self):
        if not self.guard():
            return
        u = urllib.parse.urlparse(self.path).path
        if u in STATIC:
            return self.send_file(WEB / STATIC[u][0], STATIC[u][1])
        if u.startswith("/out/"):
            fp = out_path(u[5:])
            if fp.suffix.lower() in MEDIA:
                return self.send_media(fp, MEDIA[fp.suffix.lower()])
            return self.send_file(fp, "image/png")
        routes = {"/api/features": features, "/api/status": status, "/api/lists": lists, "/api/catalog": catalog, "/api/caps": caps_info,
                  "/api/profiles": lambda: PROFILES}
        if u in routes:
            return self.send_json(routes[u]())
        if u == "/api/install":
            return self.send_json([{k: v for k, v in t.items() if k not in ("url", "token")} for t in TASKS[-40:]])
        if u == "/api/sam/status":
            return self.send_json(sam_status())
        if u == "/api/dl/tokens":
            return self.send_json(token_state())
        if u == "/api/disk":
            return self.send_json(disk_report())
        if u == "/api/gallery":
            return self.send_json(gallery(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)))
        if u.startswith("/thumb/"):
            fp = out_path(u[7:])
            if fp.suffix.lower() not in GAL_EXT or fp.suffix.lower() in (".mp4", ".webm") or not fp.is_file():
                return self.send_json({"error": "not found"}, 404)
            try:
                return self.send_bytes(thumb_bytes(fp), "image/jpeg", extra={"Cache-Control": "max-age=3600"})
            except Exception:
                return self.send_json({"error": "thumb failed"}, 500)
        if u == "/api/nodes/status":
            return self.send_json({r: {"state": j["state"], "msg": j["msg"]} for r, j in NODE_JOBS.items()})
        if u == "/api/vision":
            return self.send_json({"models": vision_models()})
        if u == "/api/manage":
            return self.send_json(manage())
        if u.startswith("/api/job/"):
            J = JOBS.get(u[9:])
            if not J:
                return self.send_json({"state": "error", "error": "작업을 찾을 수 없습니다."})
            return self.send_json({k: J[k] for k in ("state", "msg", "elapsed", "images", "error", "used", "warn", "progress", "pest", "phase") if k in J})
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.guard():
            return
        u = urllib.parse.urlparse(self.path).path
        try:
            p = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self.send_json({"error": "bad json"}, 400)
        if u == "/api/chat":
            return self.chat(p)
        if u == "/api/job":
            if p.get("kind") not in ("edit", "gen", "up", "wf", "feat", "vid"):
                return self.send_json({"error": "unknown kind"}, 400)
            if len(JOBS) > 50:
                del JOBS[next(iter(JOBS))]
            J = {"id": uuid.uuid4().hex[:10], "state": "queued", "msg": "대기 중", "elapsed": 0, "images": [], "tmp": []}
            JOBS[J["id"]] = J
            threading.Thread(target=job_thread, args=(J, p), daemon=True).start()
            return self.send_json({"id": J["id"]})
        if u == "/api/install":
            return self.send_json(install(p))
        if u == "/api/dl/search":
            try:
                return self.send_json(dl_search(p))
            except Exception as e:  # noqa: BLE001
                log("[다운로드 검색 오류]", repr(e))
                return self.send_json({"error": str(e) if isinstance(e, RuntimeError) else f"검색 결과를 처리하지 못했어요 ({type(e).__name__}: {e})"})
        if u == "/api/dl/files":
            try:
                return self.send_json(dl_hf_files(p))
            except Exception as e:  # noqa: BLE001
                log("[다운로드 검색 오류]", repr(e))
                return self.send_json({"error": str(e) if isinstance(e, RuntimeError) else f"검색 결과를 처리하지 못했어요 ({type(e).__name__}: {e})"})
        if u == "/api/dl/get":
            return self.send_json(dl_get(p))
        if u == "/api/dl/token":
            return self.send_json(set_token(p.get("name"), p.get("value")))
        if u == "/api/sam/install":
            return self.send_json(sam_install())
        if u == "/api/sam/segment":
            try:
                return self.send_json(sam_segment(p))
            except Exception as e:  # noqa: BLE001
                log("[선택 도구 오류]", repr(e))
                return self.send_json({"error": f"선택하지 못했어요 ({type(e).__name__}: {e})"})
        if u == "/api/family":
            return self.send_json(set_family(p))
        if u == "/api/nodes/sources":
            try:
                return self.send_json(node_sources([str(x) for x in (p.get("missing") or [])][:200]))
            except RuntimeError as e:
                return self.send_json({"error": str(e)})
        if u == "/api/nodes/install":
            return self.send_json(node_install(p))
        if u == "/api/engine/restart":
            return self.send_json(restart_comfy())
        if u == "/api/prompts":
            return self.send_json(prompts_api(p))
        if u == "/api/wildcards":
            return self.send_json(wildcards_api(p))
        if u == "/api/describe":
            return self.send_json(describe_image(p))
        if u == "/api/gallery/fav":
            return self.send_json(gal_fav(p))
        if u == "/api/clean":
            return self.send_json(clean_item(str(p.get("what", ""))))
        if u == "/api/delete":
            return self.send_json(delete_item(p))
        if u == "/api/meta":
            try:
                return self.send_json(meta.read(base64.b64decode(p["image"].split(",", 1)[-1])))
            except Exception as e:
                return self.send_json({"error": f"이미지를 읽을 수 없어요: {e}"})
        if u == "/api/meta/strip":
            try:
                data, ext, note = meta.strip(base64.b64decode(p["image"].split(",", 1)[-1]))
                return self.send_json({"data": base64.b64encode(data).decode(), "ext": ext, "note": note})
            except Exception as e:
                return self.send_json({"error": f"처리할 수 없어요: {e}"})
        if u == "/api/wf/analyze":
            try:
                g = flows.parse_graph(p.get("graph"), caps()["info"])
                return self.send_json({"ok": True, **flows.analyze(g, caps()["nodes"] or None)})
            except (ValueError, TypeError) as e:
                return self.send_json({"error": str(e) if isinstance(e, ValueError) else "JSON 형식이 올바르지 않아요."})
        if u == "/api/open":
            path, sel = folder_map().get(p.get("which") or "outputs"), None
            if p.get("file") and str(p["file"]).startswith("/out/"):   # 결과 이미지가 들어 있는 폴더 (예: outputs\\생성)
                sel = out_path(str(p["file"])[5:])
                path = sel.parent
            if not path:
                return self.send_json({"error": "알 수 없는 폴더"}, 400)
            open_folder(path, sel)
            return self.send_json({"ok": True, "path": str(path)})
        if u == "/api/job/cancel":
            J = JOBS.get(p.get("id"))
            if not J:
                return self.send_json({"error": "작업을 찾을 수 없습니다."})
            J["cancel"] = True
            if J.get("pid"):
                threading.Thread(target=comfy_cancel, args=(J["pid"],), daemon=True).start()
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)

    def chat(self, p):
        users = [m.get("content", "") for m in p.get("messages", []) if m.get("role") == "user"][-4:]
        sent = False

        def head():
            nonlocal sent
            if not sent:
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.end_headers()
                sent = True

        def err(msg):
            head()
            self.wfile.write(json.dumps({"error": msg}, ensure_ascii=False).encode() + b"\n")

        if blocked(" ".join(users)):
            return err(BLOCK_MSG)
        claim("chat")
        try:
            req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(p).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=900) as r:
                head()
                for line in r:
                    self.wfile.write(line)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("error", "")
            except Exception:
                msg = f"HTTP {e.code}"
            err(msg or f"HTTP {e.code}")
        except Exception:
            err("대화 엔진(Ollama)에 연결할 수 없습니다. 잠시 후 다시 시도하거나 logs\\ollama.log 를 확인하세요.")


def main():
    global GPU
    sys.stdout.reconfigure(errors="replace")
    GPU = gpu()
    register_root()
    start_engines()
    ws_start()
    threading.Thread(target=worker, daemon=True).start()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        sys.exit(f"포트 {PORT} 를 이미 사용 중입니다. 이미 실행 중인 스튜디오가 있는지 확인하세요.")
    url = f"http://127.0.0.1:{PORT}"
    log(f"로컬 AI 스튜디오: {url}  (종료하려면 이 창을 닫으세요)")
    if not os.environ.get("HUB_NOBROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
