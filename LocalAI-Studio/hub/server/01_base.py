# 로컬 AI 스튜디오 허브 — 기본 경로·설정·공용 도구
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

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
FOLDERS = {"checkpoints", "loras", "diffusion_models", "text_encoders", "vae", "upscale_models", "controlnet", "embeddings", "sam", "rmbg", "background_removal", "ultralytics/bbox", "ipadapter", "clip_vision", "style_models", "audio_encoders"}
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


MODEL_ALIAS = {"text_encoders": ("clip",), "diffusion_models": ("unet",)}      # ComfyUI 는 옛 이름 폴더(clip, unet)도 같은 목록으로 보여 줘요


def files(sub):
    out = set()
    for s in (sub, *MODEL_ALIAS.get(sub, ())):
        d = MODELS / s
        if d.is_dir():
            out.update(p.name for p in d.iterdir() if p.is_file() and p.suffix.lower() in EXT)
    return sorted(out)


def mpath(sub, name):
    """모델 파일의 실제 위치(옛 이름 폴더 포함)."""
    for s in (sub, *MODEL_ALIAS.get(sub, ())):
        if (MODELS / s / name).is_file():
            return MODELS / s / name
    return MODELS / sub / name


def find(sub, *keys):
    return next((n for n in files(sub) if all(k in n.lower() for k in keys)), None)


def llms():
    try:
        return [m["name"] for m in http(OLLAMA + "/api/tags", timeout=3).get("models", [])]
    except Exception:
        return []


def quiet_log(*a):
    """콘솔(검은 창)에는 찍지 않고 logs\\hub-debug.log 에만 남겨요(너무 커지면 새로 시작)."""
    try:
        LOGS.mkdir(exist_ok=True)
        f = LOGS / "hub-debug.log"
        if f.exists() and f.stat().st_size > 200_000:
            f.write_text("", encoding="utf-8")
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
    except OSError:
        pass


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
        quiet_log("[폴더 창을 찾지 못했어요]", title)
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
    quiet_log("[폴더 창 앞으로]", title, "성공" if u.GetForegroundWindow() == hwnd else "시도함(앞으로 안 왔을 수 있음)")


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
        quiet_log("[창 앞으로 가져오기 실패]", e)


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
