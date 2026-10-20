#!/usr/bin/env python3
"""로컬 AI 스튜디오 허브.

표준 라이브러리 + Pillow 만 사용합니다 (ComfyUI 포터블의 python_embeded 로 실행).
역할: Ollama / ComfyUI 실행, 웹 UI 제공, 모델 설치, 이미지 작업(마스크 크롭·합성·타일 리파인) 조율,
      이미지 메타데이터 읽기/제거(meta.py), ComfyUI 그래프 생성·사용자 워크플로 실행(flows.py).
"""
import base64, csv, hashlib, importlib, io, json, os, random, re, shutil, subprocess, sys, tempfile, threading, time, uuid, webbrowser, zipfile
import urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

# ComfyUI 포터블의 python_embeded 는 ._pth 설정 때문에 스크립트 폴더를 import 경로에 넣지 않으므로 직접 추가
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flows
import meta
import bgremove
import modelinfo
import sam
import tts
import tts_models
import vmix

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
FOLDERS = {"checkpoints", "loras", "diffusion_models", "text_encoders", "vae", "upscale_models", "controlnet", "embeddings", "sam", "rmbg", "ultralytics/bbox", "ipadapter", "clip_vision", "style_models"}
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


# ───────────────────────── 안전 장치 ─────────────────────────
# 미성년자 + 성적 표현이 함께 나오면 차단하는 최소한의 키워드 필터입니다(완벽하지 않음).
MINOR = re.compile(r"loli|shota|underage|under-age|pre-?teen|toddler|infant|\bminors?\b|\bchild(?:ren)?\b|\bkids?\b|"
                   r"\bteen(?:age[rd]?)?s?\b|little (?:girl|boy)|school ?(?:girl|boy)|"
                   r"미성년|어린이|초등학생|중학생|고등학생|여고생|남고생|초딩|중딩|로리|쇼타", re.I)
SEX = re.compile(r"nsfw|\bnude|naked|nipple|topless|porn|\bsex(?:ual|y)?\b|erotic|\blewd|genital|bdsm|hentai|"
                 r"누드|알몸|야한|야동|섹스|성관계|성행위|젖꼭지|음란|에로|포르노|전라|가슴 ?노출|성기 ?노출", re.I)   # '노출'(사진 노출)·'explicit' 같은 평범한 말은 뺐어요
AGE = re.compile(r"\b(\d{1,2})\s*[- ]?(?:years?|yrs?|yo|y/o)\b|(\d{1,2})\s*(?:살|세)", re.I)


def blocked(text):
    t = text or ""
    young = MINOR.search(t) or any(int(a or b) < 18 for a, b in AGE.findall(t))
    return bool(young and SEX.search(t))


BLOCK_MSG = "미성년자와 관련된 성적 내용은 지원하지 않습니다."


# ───────────────────────── 엔진 실행 / VRAM 관리 ─────────────────────────
def tidy(logs=True, tmp=True):
    """실행할 때마다 쌓이는 찌꺼기를 치워요: 커진 로그 파일 교체, 남은 임시 이미지·미리보기 삭제(결과물·모델은 건드리지 않아요)."""
    now = time.time()
    try:
        for n in (("ollama.log", "comfyui.log", "hub.log") if logs else ()):
            f = LOGS / n
            if f.is_file() and f.stat().st_size > 10 * 1024 * 1024:
                old = LOGS / (n + ".old")
                old.unlink(missing_ok=True)
                f.replace(old)
    except OSError:
        pass
    for folder, pat, age in (((COMFY / "input", "hub_*.png", 3600), (COMFY / "temp", "*", 2 * 86400)) if tmp else ()):
        try:
            for f in folder.glob(pat):
                if f.is_file() and now - f.stat().st_mtime > age:
                    f.unlink(missing_ok=True)
        except OSError:
            pass


def speed_args():
    """ComfyUI 가 지원할 때만 쓰는 안전한 속도 옵션(fp16 누적 연산). settings.json 에 "speed_boost": false 를 적으면 꺼요.
    ComfyUI 에 '--help' 를 물어 보는 데 몇 초 걸려서, main.py 가 바뀌지 않았으면 지난번 결과를 그대로 써요."""
    if not settings().get("speed_boost", True) or not PY.exists():
        return []
    mp = COMFY / "main.py"
    try:
        st = mp.stat(); sig = f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        sig = ""
    cache = LOGS / "speed_args.json"
    try:
        c = json.loads(cache.read_text(encoding="utf-8"))
        if sig and c.get("sig") == sig:
            return list(c.get("args", []))
    except (OSError, ValueError):
        pass
    args = []
    try:
        r = subprocess.run([str(PY), "-s", str(mp), "--help"], cwd=HOME, capture_output=True, text=True, timeout=40)
        if "fp16_accumulation" in (r.stdout or ""):
            args = ["--fast", "fp16_accumulation"]
        if sig:
            try:
                LOGS.mkdir(exist_ok=True)
                cache.write_text(json.dumps({"sig": sig, "args": args}), encoding="utf-8")
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass
    return args


ENG_T = {}   # 이미지 엔진 시작 시간 기록(단계별 초) — 느려졌을 때 어디서 걸리는지 보려고 남겨요


def _boot_watch(t0):
    """엔진이 뜨는 데 걸린 시간을 재서 로그에 남기고, 뜨자마자 기능 목록(object_info)을 미리 읽어 첫 작업을 빠르게 해요."""
    for _ in range(600):
        if alive(CUI + "/system_stats"):
            ENG_T["ready"] = round(time.time() - t0, 1)
            t1 = time.time(); caps(force=True); ENG_T["nodes"] = round(time.time() - t1, 1)
            log(f"[시작 시간] 이미지 엔진 준비 {ENG_T['ready']}초 (시작 옵션 확인 {ENG_T.get('args', 0)}초, 노드 목록 읽기 {ENG_T['nodes']}초)")
            return
        time.sleep(0.5)


def start_engines():
    LOGS.mkdir(exist_ok=True)
    tidy(tmp=False)         # 커진 로그 파일 교체만 먼저(엔진이 파일을 잡기 전에)
    if OLLAMA_EXE.exists() and not alive(OLLAMA + "/api/version"):
        env = {**os.environ, "OLLAMA_MODELS": str(ROOT / "models" / "llm")}
        procs.append(subprocess.Popen([str(OLLAMA_EXE), "serve"], cwd=OLLAMA_EXE.parent, env=env,
                                      stdout=open(LOGS / "ollama.log", "ab"), stderr=subprocess.STDOUT))
    if PY.exists() and not alive(CUI + "/system_stats"):
        t0 = time.time(); sa = speed_args(); ENG_T["args"] = round(time.time() - t0, 1)
        cmd = [str(PY), "-s", str(COMFY / "main.py"), "--windows-standalone-build",
               "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"] + sa
        procs.append(subprocess.Popen(cmd, cwd=HOME, stdout=open(LOGS / "comfyui.log", "ab"),
                                      stderr=subprocess.STDOUT))
        threading.Thread(target=_boot_watch, args=(t0,), daemon=True).start()
    threading.Thread(target=lambda: tidy(logs=False), daemon=True).start()      # 오래된 임시 파일 정리는 엔진을 켠 뒤 뒤에서 해요


def free_ollama():
    try:
        for m in http(OLLAMA + "/api/ps", timeout=3).get("models", []):
            http(OLLAMA + "/api/generate", {"model": m["name"], "keep_alive": 0}, 30)
    except Exception:
        pass


IMG_KEEP = {"0": 0, "5m": 300, "30m": 1800, "2h": 7200, "-1": None}   # 이미지 모델을 메모리에 두는 시간(초). None = 계속


def idle_unload_loop():
    """이미지 작업이 한동안 없으면 이미지 모델이 잡고 있는 그래픽 메모리를 비워요(게임·다른 프로그램을 쓸 수 있게). 다음 작업 때는 모델을 다시 불러와요."""
    while True:
        time.sleep(30)
        try:
            keep = IMG_KEEP.get(settings().get("image_keep_alive", "30m"), 1800)
            ts = STATE.get("idle_since")
            if keep is None or ts is None or time.time() - ts < max(keep, 30):
                continue
            if QUEUE or any(J.get("state") == "running" for J in list(JOBS.values())) or STATE.get("last") != "image":
                continue
            free_comfy()
            STATE["last"] = None
            STATE["idle_since"] = None
            LAST_MODEL["key"] = None
            log("[메모리 비우기] 이미지 작업이 없어서 이미지 모델을 메모리에서 내렸어요")
        except Exception as e:  # noqa: BLE001
            log("[메모리 비우기 오류]", repr(e))


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


def llm_needs_room(name):
    """번역용 대화 모델을 올릴 만큼 그래픽 메모리가 남아 있나. 넉넉하면 이미지 모델을 내리지 않아서 다음 그림이 빨리 시작해요(모르겠으면 비워요)."""
    try:
        live = gpu_live()
        size = next((m.get("size", 0) for m in http(OLLAMA + "/api/tags", timeout=3).get("models", []) if m.get("name") == name), 0)
        if not live or not size:
            return True
        free_mb = live["total_mb"] - live["used_mb"]
        return free_mb < size / 1048576 * 1.3 + 1500
    except Exception:  # noqa: BLE001
        return True


_TR = {}


def translate(text, style):
    key = (text, style)
    if key in _TR:
        return _TR[key]
    names = llms()
    if not names:
        return text
    if llm_needs_room(names[0]):
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


def run_wf(wf, J, raw=False):
    """raw=True 이면 이미지 대신 결과 파일(영상) 바이트를 [(파일명, 바이트)] 로 돌려줘요."""
    check_cancel(J)
    note_models_used(wf)
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
                    raise RuntimeError(msg)
            imgs = []
            for o in h.get("outputs", {}).values():
                for im in (o.get("images", []) + (o.get("audio", []) if raw else [])):
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


SCALE_MIN, SCALE_MAX, SIDE_MAX = 0.1, 8.0, 8192


def scale_of(p, default=4.0):
    """배율 칸의 값(예: 2, 1.5, 0.5, '3배')을 숫자로. 1보다 작으면 줄이기예요."""
    raw = str(p.get("scale") if p.get("scale") not in (None, "") else default).strip().lower().replace("배", "").replace("x", "").replace("×", "").replace(",", ".").strip()
    try:
        v = float(raw)
    except ValueError:
        raise ValueError("배율은 숫자로 적어 주세요. (예: 2, 1.5, 0.5)") from None
    if not (SCALE_MIN <= v <= SCALE_MAX):
        raise ValueError(f"배율은 {SCALE_MIN:g} ~ {SCALE_MAX:g} 사이로 적어 주세요. (1보다 작으면 줄여요)")
    return round(v, 3)


def scale_check(size, scale):
    """결과 크기를 (가로, 세로)로 돌려주고, 너무 크거나 작으면 안내해요."""
    out = (max(1, round(size[0] * scale)), max(1, round(size[1] * scale)))
    if max(out) > SIDE_MAX:
        raise ValueError(f"결과가 {SIDE_MAX}px 를 넘어요({out[0]}×{out[1]}). 배율을 낮추거나 더 작은 이미지를 써 주세요.")
    if min(out) < 16:
        raise ValueError(f"결과가 너무 작아져요({out[0]}×{out[1]}). 배율을 키워 주세요.")
    return out


def upscale(img, J, model, scale):
    """scale > 1: 업스케일 모델로 키운 뒤 원하는 배율에 맞춰요(모델이 4배라면 2배·1.5배·6배도 가능). scale <= 1: 모델 없이 줄이기(Lanczos)."""
    scale = float(scale)
    target = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    if scale <= 1.0:
        return img if target == img.size else img.resize(target, RS.LANCZOS)
    model = model or (files("upscale_models") or [None])[0]
    if not model:
        raise RuntimeError("업스케일 모델이 없습니다. '설치와 모델' 탭에서 Real-ESRGAN 을 설치해 주세요.")
    res = run_wf(flows.wf_upscale(model, put_input(img, J)), J)[0]
    return res if res.size == target else res.resize(target, RS.LANCZOS)


FX_DEFAULTS = {"flux": (20, 3.5, 1, "simple"), "chroma": (26, 0, 4, "beta"), "krea2": (8, 0, 1, "simple")}   # 단계, 가이던스, CFG, 스케줄러
FLUX_FAMS = ("flux", "krea2", "chroma")


def fx_sel(p, key="ckpt"):
    """모델 칸 값이 'fx:종류:파일' 이면 (종류, 그 모델에 맞는 단계 수·CFG 를 채운 설정)을, SDXL 체크포인트면 (None, p)를 돌려줘요."""
    fx = re.match(r"fx:(flux|krea2|chroma):(.*)$", str(p.get(key) or ""), re.S)
    if not fx:
        return None, p
    fam = fx.group(1)
    d = FX_DEFAULTS[fam]
    p2 = dict(p, fx_model=fx.group(2), fx_steps=d[0], fx_guidance=d[1], fx_cfg=d[2], fx_scheduler=d[3])
    if fam == "krea2" and re.search("raw", fx.group(2), re.I):
        p2.update(fx_steps=30, fx_cfg=4)
    return fam, p2


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
    q["denoise"] = clamp(num(p, "fx_edn", num(p, "fx_denoise", 0.6)), 0.1, 1.0)     # 기본 0.6: 1.0 이면 칠한 곳을 원본과 상관없이 통째로 새로 그려요
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
            q["cn"] = dict(model=p["cn_model"], image=put_input(cc, J), canny=canny, union=cn_union(p),
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
          "detailer": feat_detailer, "ipadapter": feat_ipadapter, "faceswap": feat_faceswap}.get(p.get("feature"))
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


CN_UNION = {"pose": "openpose", "depth": "depth", "canny": "canny/lineart/anime_lineart/mlsd", "lineart": "canny/lineart/anime_lineart/mlsd"}
CN_PREP = {"canny": ["Canny"], "pose": ["DWPreprocessor", "OpenposePreprocessor"],
           "depth": ["DepthAnythingV2Preprocessor", "DepthAnythingPreprocessor", "Zoe-DepthMapPreprocessor", "MiDaS-DepthMapPreprocessor"],
           "lineart": ["LineArtPreprocessor", "AnimeLineArtPreprocessor"]}


def cn_union(p):
    """쉬운 모드에서 고른 지도 종류 → 통합(union) ControlNet 모델에 알려 줄 값. 통합 모델이 아니거나 노드가 없으면 None."""
    t = CN_UNION.get(str(p.get("cn_type") or ""))
    name = str(p.get("cn_model") or "").lower()
    return t if t and ("union" in name or "promax" in name) and has_node("SetUnionControlNetType") else None


def control_prep(p):
    """사진 한 장에서 ControlNet 용 지도(포즈·윤곽선·깊이·선화)를 뽑아 미리보기로 돌려줘요."""
    kind = str(p.get("type") or "")
    if kind not in CN_PREP:
        return {"error": "알 수 없는 종류예요."}
    try:
        img = load_img(p["image"])
    except Exception:
        return {"error": "이미지를 읽을 수 없어요."}
    if max(img.size) > 1536:
        k = 1536 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), RS.LANCZOS)
    try:
        wait_comfy()
    except RuntimeError as e:
        return {"error": str(e)}
    node = next((n for n in CN_PREP[kind] if has_node(n)), None)
    if not node:
        return {"error": "이 ComfyUI 에는 이 지도를 만드는 노드가 없어요." if kind == "canny" else
                "이 지도를 만드는 확장(ComfyUI's ControlNet Auxiliary Preprocessors)이 설치되어 있지 않아요.",
                "missing": CN_PREP[kind][0], "need_pack": kind != "canny"}
    claim("image")
    J = {"id": "prep", "state": "running", "msg": "", "images": [], "tmp": []}
    w = flows.WF()
    li = w.add("LoadImage", image=put_input(img, J))
    ins = {"image": [li, 0]}
    res = clamp(max(img.size) // 64 * 64, 512, 1024)
    inp = (caps()["info"].get(node) or {}).get("input", {}) or {}
    opt = inp.get("optional", {}) or {}
    # 선택 입력(예: 선화의 coarse)도 확장 코드가 kwargs["이름"] 으로 바로 읽는 경우가 있어 기본값을 채워 줘요
    for k, spec in {**opt, **(inp.get("required", {}) or {})}.items():
        if k == "image" or not isinstance(spec, list) or not spec:
            continue
        t, o = spec[0], (spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {})
        if isinstance(t, list):
            if k in opt and k not in (inp.get("required") or {}):
                ins[k] = o["default"] if o.get("default") in t else (t[0] if t else "")
            else:
                ins[k] = "enable" if "enable" in t else (t[0] if t else "")
        elif k == "resolution":
            ins[k] = res
        elif "default" in o:
            ins[k] = o["default"]
        elif t == "BOOLEAN":
            ins[k] = True
    if node == "Canny":
        ins.setdefault("low_threshold", 0.4)
        ins.setdefault("high_threshold", 0.8)
    out = w.add(node, **ins)
    w.add("PreviewImage", images=[out, 0])
    try:
        r = run_wf(w.n, J)[0]
    except RuntimeError as e:
        pm = pymod_missing(e)
        return {"error": f"지도를 만들지 못했어요: {e}" + (" — 아래 버튼으로 빠진 부품을 설치할 수 있어요." if pm else ""), **({"pymod": pm} if pm else {})}
    finally:
        _clean_tmp(J)
    b = io.BytesIO()
    r.save(b, "PNG")
    return {"image": "data:image/png;base64," + base64.b64encode(b.getvalue()).decode(), "node": node, "w": r.width, "h": r.height}


def do_gen(p, J):
    if p.get("gengine") in ("flux", "chroma", "krea2"):
        return do_gen_flux(p, J)
    if p.get("gengine") in OX_FAMS:
        return do_gen_other(p, J)
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
            q["cn"] = dict(model=p["cn_model"], image=put_input(cover(cnimg, (w0, h0)), J), canny=prep_canny, union=cn_union(p),
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
    return next((n for n in files("vae") if n.lower() in ("ae.safetensors", "flux_ae.safetensors") or n.lower().startswith("ae.") or "flux" in n.lower()), None)


def flux_parts(p=None):
    """FLUX 계열 공용 파일. 자동으로 찾고, 화면에서 직접 고른 파일(fx_vae/fx_t5/fx_clip)이 있으면 그걸 써요."""
    te = files("text_encoders")
    low = lambda n: n.lower()
    is_t5 = lambda n: ("t5" in low(n) or "xxl" in low(n)) and "umt5" not in low(n)
    r = dict(t5=next((n for n in te if "t5xxl" in low(n)), None) or next((n for n in te if is_t5(n)), None),
             clip_l=next((n for n in te if low(n).startswith("clip_l")), None) or next((n for n in te if "clip" in low(n) and not is_t5(n)), None)
             or next((n for n in te if re.search(r"vit-?l|clipl|text_?encoder", low(n)) and not is_t5(n) and "qwen" not in low(n)), None),
             vae=flux_vae() or next((n for n in files("vae") if not re.search(r"qwen|sdxl|wan|sd15|sd_xl", n.lower())), None))
    if p:
        for key, field, sub in (("t5", "fx_t5", "text_encoders"), ("clip_l", "fx_clip", "text_encoders"), ("vae", "fx_vae", "vae")):
            v = p.get(field)
            if v and v in files(sub):
                # 엉뚱한 종류를 골랐으면(예: T5 칸에 Qwen) 무시하고 자동으로 찾아요 — 그대로 쓰면 'meta tensor' 오류가 나요
                if key == "t5" and re.search(r"qwen|umt5|clip|llama|gemma|mistral|vl[_-]?\d|_vl|-vl", low(v)):
                    continue
                if key == "clip_l" and (is_t5(v) or re.search(r"qwen|umt5", low(v))):
                    continue
                r[key] = v
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


K2C_NODES = ("Krea2ControlLoRALoader", "Krea2ControlImageEncode", "Krea2ControlApply")
K2C_REPO = "https://github.com/facok/comfyui-krea2-controlnet"
# 허브가 직접 확인해 둔 확장(코드를 읽어 네트워크·실행 호출이 없는 것을 확인한 커밋으로 고정). 목록에 없는 주소는 여전히 설치하지 않아요.
SUBPACK_REPO = "https://github.com/ltdrdata/ComfyUI-Impact-Subpack"
REACTOR_REPO = "https://github.com/Gourieff/ComfyUI-ReActor"
KNOWN_PACKS = {REACTOR_REPO: {"ref": "3be5f356fe5b120a7a274d2509c0ecef5d0a7498", "title": "ReActor (얼굴 교체, 안전 필터 포함)", "nodes": ("ReActorFaceSwap",), "install_py": True},
               SUBPACK_REPO: {"ref": "50c7b71a6a224734cc9b21963c6d1926816a97f1", "title": "Impact Subpack (얼굴·손 감지 노드)", "nodes": ("UltralyticsDetectorProvider",)},
               K2C_REPO: {"ref": "79ebfd3bd80d2180b334dd7ce57f3c9ddaa0848f", "title": "Krea2 Control (comfyui-krea2-controlnet)", "nodes": K2C_NODES}}


def k2_control_loras():
    """loras 폴더에서 Krea 2 컨트롤 LoRA(깊이·캐니·포즈 등)로 보이는 파일."""
    return [n for n in files("loras") if re.search(r"control|depth|canny|pose|lineart|normal", n, re.I)]


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
        if not model_family("checkpoints", sel)[1]:
            # checkpoints 폴더에 있어도 텍스트 인코더·VAE 가 없는 '모델만' 파일이면 공용 파일을 따로 붙여요(모델은 체크포인트 로더로 읽음)
            allin = False
            f = dict(unet=sel, ckpt_only=True, **flux_parts(p))
        else:
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
    cnimg = None
    if p.get("cn_model") and p.get("cn_image"):
        if fam == "krea2":      # Krea 2 는 ControlNet 대신 '컨트롤 LoRA' 를 써요(확장 노드 필요)
            if p["cn_model"] not in k2_control_loras():
                raise ValueError("고른 파일은 Krea 2 컨트롤 LoRA 가 아닌 것 같아요. 설치와 모델의 'Krea 2 깊이 컨트롤 LoRA'를 설치하거나 사용 안 함으로 바꿔 주세요.")
            gone = [n for n in K2C_NODES if not has_node(n)]
            if gone:
                raise RuntimeError("Krea 2 컨트롤에는 'comfyui-krea2-controlnet' 확장 노드가 필요해요. 이미지 생성 화면 ControlNet 칸의 [설치] 버튼으로 설치하고 이미지 엔진을 다시 시작해 주세요.")
            cnimg = load_img(p["cn_image"])
        elif fam != "flux":      # Chroma 는 구조가 달라 FLUX.1 용 ControlNet 이 맞지 않아요
            warn(J, "ControlNet 은 FLUX.1·Krea(FLUX.1)·Krea 2 에서만 쓸 수 있어 이번에는 쓰지 않았어요.")
        else:
            if not re.search(r"flux", str(p["cn_model"]), re.I):
                raise ValueError("고른 ControlNet 모델은 FLUX 용이 아닌 것 같아요. 이름에 'FLUX'가 들어간 모델을 고르거나(설치와 모델 → FLUX ControlNet), 사용 안 함으로 바꿔 주세요.")
            if not has_node("ControlNetApplyAdvanced"):
                raise RuntimeError("이 ComfyUI 에는 ControlNet 노드가 없어요. ComfyUI 를 업데이트해 주세요.")
            cnimg = load_img(p["cn_image"])
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
        w0, h0 = w, h
        if init is not None:
            small = fit_area(init, w, h)
            q["init"] = put_input(small, J)
            q["init_denoise"] = clamp(num(p, "init_denoise", 0.7), 0.05, 1.0)
            w0, h0 = small.size
        cn_note = None
        if cnimg is not None:
            prep_canny = p.get("cn_prep") == "canny"
            if prep_canny and not has_node("Canny"):
                warn(J, "이 ComfyUI 에는 Canny 노드가 없어 전처리 없이 사용했어요.")
                prep_canny = False
            if fam == "krea2":
                q["k2c"] = dict(lora=p["cn_model"], image=put_input(cover(cnimg, (w0, h0)), J), canny=prep_canny,
                                strength=clamp(num(p, "cn_strength", 1.0), 0.0, 2.0), depth="depth" in p["cn_model"].lower() or p.get("cn_type") == "depth")
                cn_note = f'{p["cn_model"]} {q["k2c"]["strength"]}'
            else:
                q["cn"] = dict(model=p["cn_model"], image=put_input(cover(cnimg, (w0, h0)), J), canny=prep_canny, union=None,
                               strength=clamp(num(p, "cn_strength", 0.7), 0.0, 2.0),
                               start=clamp(num(p, "cn_start", 0.0), 0.0, 1.0), end=clamp(num(p, "cn_end", 1.0), 0.0, 1.0))
                cn_note = f'{p["cn_model"]} {q["cn"]["strength"]}'
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
                    extra={"Family": fam, **({"Distilled CFG": q["guidance"]} if fam == "flux" else {}), **({"ControlNet": cn_note} if cn_note else {})})
        out.append((res, info, g if init is None and cnimg is None else None))
    return out


OX_FAMS = ("sd35", "hidream", "lumina")
OX_NAMES = {"sd35": "SD3.5", "hidream": "HiDream", "lumina": "Lumina 2"}
# 계열별 기본값: (단계, CFG, 샘플러, 스케줄러, shift). HiDream 은 파일 이름(full/dev/fast)에 따라 달라요.
OX_DEFAULTS = {"sd35": (28, 4.5, "euler", "sgm_uniform", None), "lumina": (25, 4.0, "res_multistep", "simple", 6.0)}
HIDREAM_DEFAULTS = {"full": (50, 5.0, "uni_pc", "simple", 3.0), "dev": (28, 1.0, "lcm", "normal", 3.0), "fast": (16, 1.0, "lcm", "normal", 3.0)}


def ox_defaults(fam, model):
    if fam == "hidream":
        n = (model or "").lower()
        return HIDREAM_DEFAULTS["fast" if "fast" in n else "dev" if "dev" in n else "full"]
    return OX_DEFAULTS[fam]


def _pick(lst, *prefs):
    """prefs: 키워드 묶음(튜플)을 앞에서부터 시도해 이름에 모두 들어 있는 첫 파일. 없으면 None."""
    for keys in prefs:
        keys = (keys,) if isinstance(keys, str) else keys
        for n in lst:
            if all(k in n.lower() for k in keys):
                return n
    return None


def ox_parts(fam):
    """SD3.5·HiDream·Lumina 2 가 쓸 텍스트 인코더·VAE 를 폴더에서 찾아요."""
    te, va = files("text_encoders"), files("vae")
    nohd = [n for n in te if "hidream" not in n.lower()]
    r = {"vae": _pick(va, "ae.safetensors", "flux", "ae")}
    if fam == "hidream":
        r["te"] = {"clip_l": _pick(te, ("clip_l", "hidream"), "clip_l"), "clip_g": _pick(te, ("clip_g", "hidream"), "clip_g"),
                   "t5": _pick(te, ("t5xxl", "fp8_e4m3fn_scaled"), "t5xxl"), "llama": _pick(te, ("llama", "3.1"), "llama")}
    elif fam == "lumina":
        r["te"] = {"gemma": _pick(te, "gemma")}
    else:
        r["te"] = {"clip_l": _pick(nohd, "clip_l"), "clip_g": _pick(nohd, "clip_g"), "t5": _pick(nohd, ("t5xxl", "fp8_e4m3fn_scaled"), "t5xxl")}
    return r


def other_models():
    """{'sd35': [...], 'hidream': [...], 'lumina': [...]} — SD3.5 는 체크포인트 폴더, HiDream·Lumina 2 는 디퓨전 모델 폴더에서 찾아요."""
    out = {k: [] for k in OX_FAMS}
    for n in files("checkpoints"):
        if model_family("checkpoints", n)[0] == "sd3":
            out["sd35"].append(n)
    for n in files("diffusion_models"):
        fam = model_family("diffusion_models", n)[0]
        if fam in ("hidream", "lumina"):
            out[fam].append(n)
    return out


def ox_setup(p, J, fam):
    """고른 모델 파일과 보조 파일을 확인해서 (모델 파일, 텍스트 인코더 dict, VAE) 를 돌려줘요. 빠진 게 있으면 설명과 함께 에러."""
    models = other_models()[fam]
    sel = p.get("fx_model") or (models[0] if models else None)
    if sel and sel.startswith("ckpt::"):
        sel = sel[6:]
    if not sel or sel not in models:
        raise RuntimeError(f"{OX_NAMES[fam]} 모델 파일이 없어요. '설치와 모델' 탭에서 설치해 주세요.")
    parts = ox_parts(fam)
    te, vae = parts["te"], parts["vae"]
    if fam == "sd35":
        _, allin, _ = model_family("checkpoints", sel)
        if allin or "incl_clips" in sel.lower():
            te, vae = {}, None
        elif not all(te.values()):
            raise RuntimeError("SD3.5 텍스트 인코더가 없어요(" + ", ".join(k for k, v in te.items() if not v) + "). '설치와 모델' 탭의 'SD3.5 공용 파일'을 설치해 주세요.")
    else:
        names = {"clip_l": "CLIP-L", "clip_g": "CLIP-G", "t5": "T5", "llama": "Llama 3.1", "gemma": "Gemma 2"}
        miss = [names[k] for k, v in te.items() if not v] + (["VAE(ae.safetensors)"] if not vae else [])
        if miss:
            raise RuntimeError("없는 파일: " + ", ".join(miss) + f". '설치와 모델' 탭에서 {OX_NAMES[fam]} 공용 파일을 설치해 주세요.")
    if fam == "lumina":
        ct = caps().get("clip_types") or []
        if ct and "lumina2" not in ct:
            raise RuntimeError("이 ComfyUI 는 Lumina 2 를 아직 지원하지 않아요. ComfyUI 폴더의 update 폴더 안 update_comfyui.bat 을 실행해 업데이트해 주세요.")
    need = {"sd35": [], "hidream": ["QuadrupleCLIPLoader", "ModelSamplingSD3"], "lumina": ["ModelSamplingAuraFlow"]}[fam]
    if fam == "sd35" and te:
        need = ["TripleCLIPLoader"]
    gone = [n for n in need if not has_node(n)]
    if gone:
        raise RuntimeError(f"이 ComfyUI 에는 {OX_NAMES[fam]} 에 필요한 노드({', '.join(gone)})가 없어요. ComfyUI 를 업데이트해 주세요.")
    return sel, te, vae


def do_gen_other(p, J):
    """SD3.5 / HiDream / Lumina 2 생성(LoRA·다이나믹 프롬프트·번역 지원). 설정 칸은 FLUX 계열과 같은 fx_* 를 써요."""
    fam = p["gengine"]
    sel, te, vae = ox_setup(p, J, fam)
    dsteps, dcfg, dsamp, dsch, dshift = ox_defaults(fam, sel)
    base, n = seed_of(p), clamp(num(p, "n", 1, int), 1, 8)
    w, h = (clamp(num(p, k, 1024, int) // 16 * 16, 256, 2048) for k in ("w", "h"))
    sch = p.get("fx_scheduler") or dsch
    have = caps()["schedulers"]
    if have and sch not in have:
        warn(J, f"이 ComfyUI 에는 스케줄러 '{sch}' 가 없어 simple 로 바꿨어요.")
        sch = "simple"
    sampler = p.get("fx_sampler") or dsamp
    if caps()["samplers"] and sampler not in caps()["samplers"]:
        warn(J, f"이 ComfyUI 에는 샘플러 '{sampler}' 가 없어 euler 로 바꿨어요.")
        sampler = "euler"
    out = []
    for i in range(n):
        rng = random.Random(base + i)
        text, tags = prep(p, J, "caption", rng)
        if blocked(text):
            raise ValueError(BLOCK_MSG)
        neg = (p.get("negative") or "").strip()
        q = dict(family=fam, te=te, vae=vae, loras=collect_loras(p, tags, J), prompt=text, negative=neg, seed=base + i, w=w, h=h,
                 steps=clamp(num(p, "fx_steps", dsteps, int), 1, 150), cfg=clamp(num(p, "fx_cfg", dcfg), 0.0, 30.0),
                 sampler=sampler, scheduler=sch, shift=clamp(num(p, "ox_shift", dshift or 3.0), 0.1, 20.0))
        if fam == "sd35":
            q["ckpt"] = sel
        else:
            q["unet"] = sel
        J["msg"] = f"생성 중 ({i + 1}/{n})"
        J["pi"], J["pn"] = i, n
        g = flows.wf_other(q)
        try:
            res = run_wf(g, J)[0]
        except Cancelled:
            if out:
                warn(J, f"중단해서 완료된 {len(out)}장만 저장했어요.")
                break
            raise
        info = dict(kind="gen-" + fam, prompt=text, negative=neg, steps=q["steps"], cfg=q["cfg"], sampler=sampler, scheduler=sch,
                    seed=q["seed"], w=res.width, h=res.height, model=sel, loras=[[a, b] for a, b in q["loras"]],
                    extra={"Family": fam})
        out.append((res, info, g))
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
    scale = scale_of(p)
    scale_check(img.size, scale)
    J["msg"] = "업스케일 중" if scale > 1 else "줄이는 중"
    big = upscale(img, J, p.get("upm"), scale)
    if p.get("mode") != "refine":
        return [(big, dict(kind="upscale", extra={**({"Upscaler": p.get("upm") or "auto"} if scale > 1 else {"Downscale": "Lanczos"}), "Scale": scale}), None)]
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
        raise RuntimeError("설치되지 않은 노드가 있어요: " + ", ".join(miss) + " ([워크플로] 탭에서 [분석]을 누르면 설치할 곳을 찾아 줘요)")
    J["msg"] = "워크플로 실행 중"
    return [(im, dict(kind="wf"), g) for im in run_wf(g, J)]


DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OUT_SUB = {"edit": "편집", "gen": "생성", "up": "업스케일", "wf": "워크플로", "feat": "기능", "vid": "영상", "batch": "일괄", "music": "음악", "tts": "음성"}


def out_path(rel):
    """/out/ 아래 요청 경로를 안전하게 파일 경로로 바꿔요(하위 폴더는 정해진 이름만)."""
    parts = [x for x in urllib.parse.unquote(rel).split("/") if x]
    if len(parts) == 2 and parts[0] in OUT_SUB.values() or parts[:1] == ["기타"] and len(parts) == 2:
        return OUT / parts[0] / Path(parts[1]).name
    if len(parts) == 3 and parts[0] in OUT_SUB.values() and DATE_RX.match(parts[1]):      # 날짜별로 정리한 폴더
        return OUT / parts[0] / parts[1] / Path(parts[2]).name
    return OUT / Path(parts[-1] if parts else "x").name


WAN_SIZES = {"832x480": "가로 480p", "480x832": "세로 480p", "640x640": "정사각", "1280x704": "가로 720p (VRAM 많이 필요)"}


def wan_models():
    return [n for n in files("diffusion_models") if "wan" in n.lower() and "14b" not in n.lower()]


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


def do_music(p, J):
    """ACE-Step 1.5 로 음악 만들기. 결과: [(바이트, 정보, 확장자)]"""
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
    engine = p.get("engine") if p.get("engine") in ("edge", "xtts", "chatterbox", "kokoro") else "sapi"
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
    """XTTS-v2 · Chatterbox · Kokoro (전용 파이썬 환경에서 실행)."""
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
    job = dict(text=text, language=lang, speaker=speaker, ref=str(ref) if ref else "", speed=round(1 + speed * 0.075, 3),
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


VPOST = {"interp": ("RIFE VFI", "ComfyUI-Frame-Interpolation", "프레임 늘리기"), "upscale": ("ImageUpscaleWithModel", "", "업스케일"),
         "webp": ("SaveAnimatedWEBP", "", "WebP 변환")}


def do_vpost(p, J):
    """만든 영상을 다듬어요: 프레임 늘리기(RIFE)·업스케일·움직이는 WebP. 결과: [(바이트, 정보, 확장자)]"""
    op = p.get("op")
    if op not in VPOST:
        raise ValueError("알 수 없는 영상 작업이에요.")
    src = out_path(str(p.get("video") or "")[5:] if str(p.get("video") or "").startswith("/out/") else "")
    if src.suffix.lower() not in (".mp4", ".webm") or not src.is_file():
        raise ValueError("다듬을 영상을 찾을 수 없어요. (이 앱으로 만든 영상만 다듬을 수 있어요)")
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

# ───────────────────── 영상에 소리 · 자막 넣기 ─────────────────────
VMIX_DIR = ROOT / "cache" / "vmix"
VMIX_MAX = 500 << 20


def vmix_src(ref, exts, what):
    """작업에 쓸 파일: 결과 폴더의 파일(/out/…) 또는 올려 둔 파일(up:아이디)."""
    ref = str(ref or "")
    f = None
    if ref.startswith("/out/"):
        f = out_path(ref[5:])
    elif re.fullmatch(r"up:[0-9a-f]{12}", ref):
        f = next((x for x in sorted(VMIX_DIR.glob(ref[3:] + ".*")) if x.suffix.lower() in exts), None)
    if not f or f.suffix.lower() not in exts or not f.is_file():
        raise ValueError(f"{what} 파일을 찾을 수 없어요. 목록에서 다시 골라 주세요.")
    return f


def vmix_name(f):
    """올려 둔 파일이면 원래 이름을, 아니면 파일 이름을."""
    try:
        return (f.with_suffix(".nm")).read_text(encoding="utf-8").strip() or f.name
    except OSError:
        return f.name


def flag(p, k, d=True):
    v = p.get(k, d)
    return v not in (False, 0, "0", "", "false", "False", "off", None)


def do_vmix(p, J):
    """영상에 소리(음성·음악)와 자막을 합쳐 새 영상으로. 결과: [(바이트, 정보, 확장자)]"""
    video = vmix_src(p.get("video"), vmix.VIDEO_EXT, "영상")
    audio = vmix_src(p.get("audio"), vmix.AUDIO_EXT, "소리") if p.get("audio") else None
    subs = str(p.get("subs") or "").strip()[:20000]
    if not audio and not subs:
        raise ValueError("넣을 소리나 자막을 하나 이상 골라 주세요.")
    if subs and blocked(subs):
        raise ValueError(BLOCK_MSG)
    ff = vmix.find_ffmpeg(PY, ROOT)
    if not ff:
        raise RuntimeError("영상을 합치려면 ffmpeg 가 필요해요. 아래 [빠진 부품 설치] 버튼으로 imageio-ffmpeg 를 설치해 주세요. (No module named 'imageio_ffmpeg')")
    job = dict(video=video, audio=audio, amode="mix" if p.get("amode") == "mix" else "replace", vol=clamp(num(p, "vol", 100, int), 0, 300) / 100,
               ovol=clamp(num(p, "ovol", 100, int), 0, 300) / 100, delay=clamp(num(p, "delay", 0, float), 0, 600), fit="audio" if p.get("fit") == "audio" else "video",
               fade=flag(p, "fade"), subs=subs, size=clamp(num(p, "sub_size", 5.5, float), 2, 15), pos=p.get("sub_pos") if p.get("sub_pos") in ("top", "middle", "bottom") else "bottom",
               color=p.get("sub_color") or "#ffffff", outline=flag(p, "sub_outline"), bg=flag(p, "sub_bg", False))
    work = VMIX_DIR / ("job-" + uuid.uuid4().hex[:8])

    def say(m, pc=None):
        J["msg"] = m
        if pc is not None:
            J["progress"] = pc
    try:
        res = vmix.make(ff, job, work, say, lambda: J.get("cancel"))
        data = res["out"].read_bytes()
    except vmix.Cancelled as e:
        raise Cancelled(str(e))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for w in res["warn"]:
        warn(J, w)
    try:
        base = json.loads(Path(str(video) + ".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        base = {}
    info = dict(base, kind="vid", post="소리·자막", source=vmix_name(video))
    if audio:
        info["audio"] = vmix_name(audio)
    if subs:
        info["subs"] = subs[:2000]
        info.setdefault("prompt", subs.splitlines()[0][:200])
    if res["srt"] and flag(p, "save_srt", False):
        info["_extra"] = {".srt": res["srt"]}
    return [(data, info, ".mp4")]


def vmix_list():
    """영상·소리 고르기 목록(결과 폴더). 소리는 음성·음악, 음성은 만들 때 쓴 글도 같이 줘요."""
    def rows(sub, exts, limit=150):
        d, out = OUT / sub, []
        for f in out_files(d, exts) if d.is_dir() else []:
            try:
                out.append((f.stat().st_mtime, f))
            except OSError:
                continue
        out.sort(key=lambda r: r[0], reverse=True)
        res = []
        for mt, f in out[:limit]:
            try:
                meta_ = json.loads(Path(str(f) + ".json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta_ = {}
            res.append({"url": "/out/" + "/".join(urllib.parse.quote(x) for x in f.relative_to(OUT).parts), "name": f.name, "kind": sub, "time": int(mt),
                        "text": str(meta_.get("text") or meta_.get("prompt") or "")[:3000]})
        return res
    return {"videos": rows(OUT_SUB["vid"], vmix.VIDEO_EXT), "audios": sorted(rows(OUT_SUB["tts"], vmix.AUDIO_EXT) + rows(OUT_SUB["music"], vmix.AUDIO_EXT), key=lambda x: -x["time"])[:200],
            "ffmpeg": bool(vmix.find_ffmpeg(PY, ROOT))}


def vmix_upload(h):
    """내 컴퓨터의 영상·소리 파일을 받아 cache/vmix 에 둬요(본문이 파일 그대로)."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    kind, name = (q.get("kind") or [""])[0], Path((q.get("name") or ["file"])[0]).name
    ext = Path(name).suffix.lower()
    if ext not in (vmix.VIDEO_EXT if kind == "video" else vmix.AUDIO_EXT if kind == "audio" else ()):
        return {"error": "이 파일 형식은 쓸 수 없어요. " + ("영상은 mp4 · webm · mov · mkv" if kind == "video" else "소리는 wav · mp3 · m4a · ogg · flac") + " 파일을 올려 주세요."}
    n = int(h.headers.get("Content-Length") or 0)
    if n <= 0 or n > VMIX_MAX:
        return {"error": "파일이 너무 커요(500MB 이하만 올릴 수 있어요)."}
    VMIX_DIR.mkdir(parents=True, exist_ok=True)
    for f in VMIX_DIR.glob("*"):                      # 사흘 지난 올린 파일은 정리
        try:
            if f.is_file() and re.fullmatch(r"[0-9a-f]{12}", f.stem) and time.time() - f.stat().st_mtime > 3 * 86400:
                f.unlink()
        except OSError:
            pass
    uid = uuid.uuid4().hex[:12]
    dest = VMIX_DIR / (uid + ext)
    left = n
    with open(dest, "wb") as fh:
        while left:
            chunk = h.rfile.read(min(1 << 20, left))
            if not chunk:
                break
            fh.write(chunk)
            left -= len(chunk)
    if left:
        dest.unlink(missing_ok=True)
        return {"error": "파일을 끝까지 받지 못했어요. 다시 올려 주세요."}
    (VMIX_DIR / (uid + ".nm")).write_text(name, encoding="utf-8")
    return {"ok": True, "id": "up:" + uid, "name": name, "kind": kind}


def job_thread(J, p):
    try:
        J["state"], J["msg"] = "running", "엔진 준비 중"
        if p["kind"] in ("tts", "vmix"):
            pass                                          # 음성 만들기·영상 소리/자막 넣기는 ComfyUI 를 쓰지 않아요
        elif (p["kind"] == "batch" and (p.get("op") != "upscale" or scale_of(p) <= 1.0)) or (p["kind"] == "up" and p.get("mode") != "refine" and scale_of(p) <= 1.0):
            pass                                          # 일괄 처리의 배경 지우기·크기 변경, 줄이기(1배 이하)는 ComfyUI 가 필요 없어요
        else:
            wait_comfy()
            claim("image")
        items = {"edit": do_edit, "gen": do_gen, "up": do_up, "wf": do_wf, "feat": do_feat, "vid": do_vid, "vpost": do_vpost, "vmix": do_vmix, "music": do_music, "tts": do_tts, "batch": do_batch}[p["kind"]](p, J)
        sub = OUT_SUB["vid"] if p["kind"] in ("vpost", "vmix") else OUT_SUB.get(p["kind"], "기타")
        (OUT / sub).mkdir(parents=True, exist_ok=True)
        stamp, embed = time.strftime("%Y%m%d-%H%M%S"), bool(p.get("embed"))
        for i, (im, info, graph) in enumerate(items):
            if p["kind"] in ("vid", "vpost", "vmix", "music", "tts"):      # 영상·음악: 받은 파일을 그대로 저장하고, 설정은 옆에 .json 으로 남겨요
                name = f'{stamp}-{uuid.uuid4().hex[:4]}-{p["kind"] if p["kind"] in ("music", "tts") else "vid"}-{i}{graph}'
                (OUT / sub / name).write_bytes(im)
                (OUT / sub / (name + ".json")).write_text(json.dumps({k: v for k, v in info.items() if k != "_extra"}, ensure_ascii=False), encoding="utf-8")
                for xext, xdata in (info.get("_extra") or {}).items():      # 자막 파일(.srt) 같은 덧붙이는 파일
                    (OUT / sub / (Path(name).stem + xext)).write_text(xdata, encoding="utf-8")
                J["images"].append("/out/" + urllib.parse.quote(sub) + "/" + name)
                J.setdefault("used", []).append(info.get("prompt", ""))
                continue
            if p["kind"] == "gen" and not p.get("init"):      # 모델은 8·16 배수 크기로만 그려서, 입력한 정확한 크기와 조금 다르면 그 크기로 맞춰 저장해요
                try:
                    rw, rh = int(float(p.get("w"))), int(float(p.get("h")))
                    if (rw, rh) != im.size and 64 <= rw <= 4096 and 64 <= rh <= 4096 and abs(rw - im.width) <= 32 and abs(rh - im.height) <= 32:
                        im = im.resize((rw, rh), RS.LANCZOS)
                except (TypeError, ValueError):
                    pass
            name = f'{stamp}-{uuid.uuid4().hex[:4]}-{p["kind"]}-{i}.png'
            im.save(OUT / sub / name, "PNG", pnginfo=meta.pnginfo(info, graph) if embed else None)
            J["images"].append("/out/" + urllib.parse.quote(sub) + "/" + name)
            J.setdefault("used", []).append(info.get("prompt", ""))
        J["state"], J["progress"] = "done", 1.0
    except Cancelled as e:
        J["state"], J["error"] = "cancelled", str(e)
        if p["kind"] == "batch" and J.get("images"):
            J["msg"] = f"중단했어요. 지금까지 {len(J['images'])}장은 저장돼 있어요."
    except Exception as e:
        J["state"], J["error"] = "error", str(e) or e.__class__.__name__
        if pymod_missing(J["error"]):
            J["pymod"] = pymod_missing(J["error"])
        og = oom_guide(J["error"], p)
        if og:
            J["oom"] = og
        log("[작업 오류]", J["error"])
    finally:
        _clean_tmp(J)
        if p.get("stage"):      # 올려 둔 파일은 내가 만든 임시 사본이라 끝나면 정리해요
            shutil.rmtree(BATCH_IN / str(p["stage"]), ignore_errors=True)


def _clean_tmp(J):
    for f in J["tmp"]:
        try:
            f.unlink()
        except OSError:
            pass
    J["tmp"].clear()


# ───────────────────────── 작업 대기열 ─────────────────────────
QUEUE, QP = [], {}
_QCV = threading.Condition()
_QW = {"t": None}
KIND_NAME = {"edit": "이미지 편집", "gen": "이미지 생성", "up": "업스케일", "wf": "워크플로", "feat": "기능", "vid": "영상 만들기", "vpost": "영상 다듬기", "vmix": "영상 소리·자막", "music": "음악 만들기", "tts": "음성 만들기", "batch": "일괄 처리"}
DONE_STATES = ("done", "error", "cancelled")


def job_label(p):
    k = p.get("kind")
    name = KIND_NAME.get(k, "작업")
    if k == "batch":
        return f"{name} · {BATCH_OPS.get(p.get('op'), '')} ({p.get('count', 0)}장)"
    if k == "feat":
        name = next((f["title"] for f in FEATURES if f["id"] == p.get("feature")), name)
    txt = " ".join(str(p.get("prompt") or "").split())
    return name + (f" · {txt[:36]}{'…' if len(txt) > 36 else ''}" if txt else "")


def enqueue(J, p):
    J["kind"], J["label"], J["t_add"] = p["kind"], job_label(p), time.time()
    with _QCV:
        QP[J["id"]] = p
        QUEUE.append(J["id"])
        _QCV.notify_all()
        if not (_QW["t"] and _QW["t"].is_alive()):
            _QW["t"] = threading.Thread(target=job_worker, daemon=True)
            _QW["t"].start()


LAST_MODEL = {"key": None}      # 방금 돌린 작업이 쓴 모델(다음 작업이 같은 모델이면 다시 안 불러도 돼요)
SAME_LOOK = 6                   # 앞에서부터 이만큼 안에서만 같은 모델 작업을 찾아요
SAME_SKIP_MAX = 2               # 한 작업이 이 횟수보다 더 밀리지는 않아요


def model_key(p):
    """이 작업이 쓰는 모델을 나타내는 값. 모델을 알 수 없는 작업(음성·일괄 처리·워크플로 등)은 None."""
    k = p.get("kind")
    if k not in ("gen", "edit", "feat", "up", "vid"):
        return None
    vals = tuple(str(p.get(n)) for n in ("engine", "gengine", "rengine", "fengine", "ckpt", "model", "fx_model", "rmodel", "upm", "wan_ver") if p.get(n))
    return (k, vals) if vals else None


def pick_next():
    """대기열에서 다음에 돌릴 위치. 기본은 맨 앞이에요. 방금 돌린 것과 같은 모델을 쓰는 작업이 바로 뒤쪽(앞 6개 안)에 있으면 그걸 먼저 해서
    모델을 다시 불러오는 시간을 아껴요. 직접 순서를 바꾼 작업과 이미 두 번 밀린 작업은 건너뛰지 않아요. (대기열 잠금을 쥔 채로 불러요)"""
    last = LAST_MODEL["key"]
    if last is None or len(QUEUE) < 2:
        return 0
    front = QP.get(QUEUE[0])
    if front is None or model_key(front) in (None, last):
        return 0
    for i in range(1, min(len(QUEUE), SAME_LOOK)):
        pi = QP.get(QUEUE[i])
        if pi is not None and model_key(pi) == last:
            before = [JOBS.get(j) for j in QUEUE[:i]]
            if any(J is None or J.get("pin") or J.get("skipped", 0) >= SAME_SKIP_MAX for J in before):
                return 0
            for J in before:
                J["skipped"] = J.get("skipped", 0) + 1
            return i
    return 0


def job_worker():
    """대기열 맨 앞 작업부터 하나씩 실행해요(엔진은 어차피 한 번에 하나만 그리니까, 순서를 바꾸거나 빼기 쉽게 한 줄로 세워요).
    다만 같은 모델을 쓰는 작업이 곧 뒤에 있으면 먼저 해서 모델을 다시 불러오는 시간을 줄여요(pick_next)."""
    while True:
        with _QCV:
            while not QUEUE:
                _QCV.wait()
            i = pick_next()
            jid = QUEUE.pop(i)
            p = QP.pop(jid, None)
            if i and jid in JOBS:
                JOBS[jid]["msg"] = "같은 모델이라 먼저 해요"
        J = JOBS.get(jid)
        if not J or p is None or J.get("state") != "queued":
            continue
        if J.get("cancel"):
            J["state"], J["error"] = "cancelled", "사용자가 중단했어요."
            continue
        try:
            J["t_start"] = time.time()
            mk = model_key(p)
            job_thread(J, p)
            if mk is not None:
                LAST_MODEL["key"] = mk
        except BaseException as e:  # noqa: BLE001
            J["state"], J["error"] = "error", repr(e)
            log("[대기열 오류]", repr(e))
        J["t_end"] = time.time()
        STATE["idle_since"] = time.time()


def queue_cancel(J):
    J["cancel"] = True
    if J.get("state") == "queued":
        with _QCV:
            if J["id"] in QUEUE:
                QUEUE.remove(J["id"])
                QP.pop(J["id"], None)
        J["state"], J["error"] = "cancelled", "사용자가 중단했어요."
    elif J.get("pid"):
        threading.Thread(target=comfy_cancel, args=(J["pid"],), daemon=True).start()


def queue_move(p):
    to = p.get("to")
    with _QCV:
        if p.get("id") not in QUEUE:
            return {"error": "이미 시작했거나 끝난 작업이에요."}
        i = QUEUE.index(p["id"])
        j = {"up": max(0, i - 1), "down": min(len(QUEUE) - 1, i + 1), "top": 0, "bottom": len(QUEUE) - 1}.get(to)
        if j is None:
            return {"error": "알 수 없는 동작"}
        QUEUE.insert(j, QUEUE.pop(i))
        if JOBS.get(p["id"]):
            JOBS[p["id"]]["pin"] = True       # 직접 옮긴 순서는 그대로 지켜요
    return {"ok": True}


def _qrow(J, pos=0):
    return {"id": J["id"], "kind": J.get("kind"), "label": J.get("label") or "작업", "state": J["state"], "pos": pos,
            "msg": J.get("msg", ""), "progress": J.get("progress"), "error": str(J.get("error") or "")[:200],
            "images": len(J.get("images") or []), "t_end": J.get("t_end"), "feature": J.get("feature") or ""}


def queue_view():
    run = [_qrow(J) for J in list(JOBS.values()) if J.get("state") == "running"]
    wait = [_qrow(JOBS[i], n + 1) for n, i in enumerate(list(QUEUE)) if i in JOBS]
    fin = [_qrow(J) for J in list(JOBS.values()) if J.get("state") in DONE_STATES and J.get("label")][-8:][::-1]
    return {"running": len(run), "queued": len(wait), "items": run + wait + fin}


# ───────────────────────── 일괄(폴더) 처리 ─────────────────────────
BATCH_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
BATCH_MAX = 2000
BATCH_IN = ROOT / "cache" / "batch-in"
BATCH_OPS = {"upscale": "업스케일", "rmbg": "배경 지우기", "resize": "크기·자르기·회전"}
RM = {"engine": None, "key": None, "factory": None}
RM_LOCK = threading.Lock()


def batch_folder(p):
    """처리할 이미지가 들어 있는 폴더: 내 컴퓨터의 폴더(folder) 또는 화면에서 올려 둔 묶음(stage)."""
    if p.get("stage"):
        sid = str(p["stage"])
        if not re.fullmatch(r"[0-9a-f]{8,16}", sid) or not (BATCH_IN / sid).is_dir():
            raise ValueError("올려 둔 파일을 찾을 수 없어요. 다시 올려 주세요.")
        return BATCH_IN / sid
    if p.get("outsub"):      # 이 프로그램의 결과 폴더(생성·편집·업스케일 …)
        if p["outsub"] not in OUT_SUB.values():
            raise ValueError("알 수 없는 결과 폴더예요.")
        d = OUT / p["outsub"]
        if not d.is_dir():
            raise ValueError("아직 그 결과 폴더가 없어요(만든 사진이 없어요).")
        return d
    raw = str(p.get("folder") or "").strip().strip('"')
    if not raw:
        raise ValueError("폴더 경로를 적어 주세요.")
    d = Path(raw).expanduser()
    if not d.is_absolute():
        raise ValueError("전체 경로로 적어 주세요. 예: E:\\사진\\여행")
    if not d.is_dir():
        raise ValueError("그런 폴더를 찾을 수 없어요.")
    return d


def batch_files(d, sub=False):
    try:
        it = d.rglob("*") if sub else d.iterdir()
        return sorted((f for f in it if f.is_file() and f.suffix.lower() in BATCH_EXT and not f.name.startswith(".")),
                      key=lambda f: str(f).lower())
    except OSError:
        return []


def batch_scan(p):
    try:
        d = batch_folder(p)
    except ValueError as e:
        return {"error": str(e)}
    fs = batch_files(d, bool(p.get("sub") or p.get("outsub")))
    return {"folder": str(d), "count": len(fs), "names": [f.name for f in fs[:4]], "mb": round(sum(fsize(f) for f in fs) / 1048576, 1), "over": len(fs) > BATCH_MAX}


def batch_upload(p):
    """화면에서 고른 이미지 한 장을 임시 폴더(cache/batch-in/<묶음 id>)에 올려 둬요. 끝나면 자동으로 정리돼요."""
    sid = str(p.get("stage") or uuid.uuid4().hex[:10])
    if not re.fullmatch(r"[0-9a-f]{8,16}", sid):
        return {"error": "잘못된 묶음이에요."}
    d = BATCH_IN / sid
    if d.is_dir() and len(list(d.iterdir())) >= BATCH_MAX:
        return {"error": f"한 번에 {BATCH_MAX}장까지만 올릴 수 있어요."}
    try:
        raw = base64.b64decode(str(p.get("image") or "").split(",", 1)[-1])
        with Image.open(io.BytesIO(raw)) as im:
            im.verify()
    except Exception:
        return {"error": "이미지를 읽을 수 없어요."}
    d.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", Path(str(p.get("name") or "image")).stem)[:80] or "image"
    ext = Path(str(p.get("name") or "")).suffix.lower()
    ext = ext if ext in BATCH_EXT else ".png"
    f, n = d / (stem + ext), 1
    while f.exists():
        n += 1
        f = d / f"{stem}-{n}{ext}"
    f.write_bytes(raw)
    for old in BATCH_IN.iterdir():      # 하루 넘게 남은 임시 묶음 정리(이 프로그램이 만든 사본만)
        try:
            if old.is_dir() and old != d and time.time() - old.stat().st_mtime > 86400:
                shutil.rmtree(old, ignore_errors=True)
        except OSError:
            pass
    return {"stage": sid, "count": len(list(d.iterdir()))}


def rmbg_status():
    busy = any(t.get("kind") == "rmbg" and t["state"] in ("queued", "running") for t in TASKS)
    ort = bgremove.have_ort()
    return {"ort": ort, "busy": busy, "models": {k: {"label": m["label"], "mb": m["mb"], "installed": bgremove.installed(MODELS / "rmbg", k)} for k, m in bgremove.MODELS.items()}}


def rmbg_install(p):
    key = p.get("key") if p.get("key") in bgremove.MODELS else "normal"
    if any(t.get("kind") == "rmbg" and t["state"] in ("queued", "running") for t in TASKS):
        return {"ok": True}
    if shutil.disk_usage(ROOT).free < 1e9:
        return {"error": "디스크 여유 공간이 부족해요."}
    add_task(f"배경 지우기 모델 설치 ({bgremove.MODELS[key]['label']})", kind="rmbg", key=key)
    return {"ok": True}


def ensure_ort(t):
    if bgremove.have_ort():
        return
    t["msg"] = "분석 엔진(onnxruntime) 설치 중"
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--no-warn-script-location", "onnxruntime"], capture_output=True, text=True, timeout=1200)
    if r.returncode != 0:
        log("[pip 오류]", (r.stdout + r.stderr)[-600:])
        raise RuntimeError("onnxruntime 설치에 실패했어요. 인터넷 연결을 확인하거나 스튜디오 창의 오류 내용을 알려 주세요.")
    import importlib
    importlib.invalidate_caches()
    if not bgremove.have_ort():
        raise RuntimeError("onnxruntime 설치 후에도 불러오지 못했어요. 스튜디오를 다시 시작해 보세요.")


def rmbg_run_install(t):
    ensure_ort(t)
    m = bgremove.MODELS[t.get("key") or "normal"]
    t.update(url=bgremove.REPO + m["file"], dir="rmbg", name=None, msg=f"{m['file']} 받는 중", done=0, total=0)
    download(t)
    RM["engine"] = None


def rmbg_engine(key):
    with RM_LOCK:
        if RM["engine"] is None or RM["key"] != key:
            RM["engine"] = bgremove.Remover(MODELS / "rmbg", key, RM.get("factory"))
            RM["key"] = key
        return RM["engine"]


def _unique(path):
    f, n = path, 1
    while f.exists():
        n += 1
        f = path.with_name(f"{path.stem}-{n}{path.suffix}")
    return f


def do_batch(p, J):
    """폴더의 이미지를 하나씩 처리해 결과 폴더(일괄)에 새 파일로 저장해요. 원본은 건드리지 않아요."""
    op = p.get("op")
    if op not in BATCH_OPS:
        raise ValueError("알 수 없는 처리예요.")
    imgs = batch_files(batch_folder(p), bool(p.get("sub") or p.get("outsub")))[:BATCH_MAX]
    if not imgs:
        raise ValueError("처리할 이미지가 없어요. (png · jpg · webp · bmp)")
    jpg = p.get("fmt") == "jpg"
    scale, model, rm_key, rm_bg = 4, None, None, None
    if op == "upscale":
        scale = scale_of(p)
        model = p.get("upm") or (files("upscale_models") or [None])[0]
        if not model and scale > 1:
            raise RuntimeError("업스케일 모델이 없습니다. '설치와 모델' 탭에서 Real-ESRGAN 을 설치해 주세요.")
        suffix = f"_업스케일x{scale:g}" if scale > 1 else f"_축소x{scale:g}"
    elif op == "rmbg":
        rm_key = p.get("rmodel") if p.get("rmodel") in bgremove.MODELS else "normal"
        if not bgremove.have_ort() or not bgremove.installed(MODELS / "rmbg", rm_key):
            raise RuntimeError("배경 지우기 모델이 아직 설치되지 않았어요. 일괄 처리 화면의 [설치] 버튼을 눌러 주세요.")
        rm_bg = {"white": (255, 255, 255), "black": (0, 0, 0)}.get(p.get("bg"))
        jpg = jpg and rm_bg is not None          # 투명 배경은 PNG 만 가능해요
        suffix = "_배경없음"
    else:
        probe, steps = resize_steps(Image.new("RGB", (64, 64)), p)
        if not steps:
            raise ValueError("하나 이상 골라 주세요. (자를 비율, 회전, 뒤집기, 긴 변 크기)")
        suffix = "_크기변경"
    out_dir = OUT / OUT_SUB["batch"]
    out_dir.mkdir(parents=True, exist_ok=True)
    n, fails = len(imgs), []
    J["batch"] = {"total": n, "ok": 0, "failed": fails}
    for i, f in enumerate(imgs):
        check_cancel(J)
        J["msg"], J["progress"] = f"{i + 1}/{n} · {f.name}", i / n
        try:
            with Image.open(f) as im0:
                img = ImageOps.exif_transpose(im0).convert("RGB")
            if op == "upscale":
                scale_check(img.size, scale)
                res = upscale(img, J, model, scale)
            elif op == "rmbg":
                res = rmbg_engine(rm_key).cut(img, rm_bg)
            else:
                res, _ = resize_steps(img, p)
            ext = ".jpg" if jpg else ".png"
            if jpg and res.mode != "RGB":
                res = res.convert("RGB")
            dst = _unique(out_dir / (f.stem + suffix + ext))
            res.save(dst, "JPEG", quality=95) if jpg else res.save(dst, "PNG")
            J["images"].append("/out/" + urllib.parse.quote(OUT_SUB["batch"]) + "/" + urllib.parse.quote(dst.name))
            J["batch"]["ok"] += 1
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            fails.append([f.name, (str(e) or e.__class__.__name__)[:140]])
        finally:
            _clean_tmp(J)
    ok = J["batch"]["ok"]
    if not ok:
        raise RuntimeError("처리한 이미지가 없어요. " + (fails[0][1] if fails else ""))
    J["msg"] = f"{ok}장 완료" + (f", {len(fails)}장 실패" if fails else "")
    return []


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
    if len(parts) not in (2, 3) or parts[0] not in OUT_SUB.values() or (len(parts) == 3 and not DATE_RX.match(parts[1])):
        return {"error": "알 수 없는 파일"}
    key = parts[0] + "/" + Path(parts[-1]).name
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


def out_files(d, exts=None):
    """결과 하위 폴더(예: 생성)의 이미지·영상 파일. 날짜별로 정리한 폴더(2026-10-18)도 한 단계 들여다봐요."""
    exts = exts or GAL_EXT
    try:
        for f in d.iterdir():
            if f.is_file():
                if f.suffix.lower() in exts:
                    yield f
            elif f.is_dir() and DATE_RX.match(f.name):
                for g in f.iterdir():
                    if g.is_file() and g.suffix.lower() in exts:
                        yield g
    except OSError:
        return


def gal_delete(p):
    """갤러리에서 고른 파일을 컴퓨터에서 지워요(영상의 설정 파일·즐겨찾기 표시도 함께). 복구할 수 없어요."""
    gone, bad = 0, 0
    keys = []
    for rel in [str(x) for x in (p.get("files") or [])][:200]:
        if not rel.startswith("/out/"):
            bad += 1
            continue
        parts = [x for x in urllib.parse.unquote(rel[5:]).split("/") if x]
        fp = out_path(rel[5:])
        if not (len(parts) in (2, 3) and parts[0] in OUT_SUB.values() and fp.suffix.lower() in GAL_EXT and fp.is_file()):
            bad += 1
            continue
        try:
            thumb_drop(fp)
            fp.unlink()
            side = fp.with_name(fp.name + ".json")
            if side.is_file():
                side.unlink()
            keys.append(parts[0] + "/" + fp.name)
            gone += 1
        except OSError:
            bad += 1
        if len(parts) == 3:      # 비어 버린 날짜 폴더는 치워요
            try:
                fp.parent.rmdir()
            except OSError:
                pass
    if keys:
        with _PLOCK:
            fav = gal_favs()
            if fav & set(keys):
                GAL_FILE.write_text(json.dumps({"favs": sorted(fav - set(keys))}, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "deleted": gone, "failed": bad}


def organize_outputs(p):
    """결과 폴더(생성·편집 …)에 쌓인 파일을 만든 날짜별 폴더(예: 생성/2026-10-18)로 옮겨요. 이동만 하고 지우지 않아요."""
    run = p.get("mode") == "run"
    keep_today = bool(p.get("keep_today", True))
    today = time.strftime("%Y-%m-%d")
    plan, total = {}, 0
    for sub in OUT_SUB.values():
        d = OUT / sub
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if not (f.is_file() and f.suffix.lower() in GAL_EXT):
                continue
            day = time.strftime("%Y-%m-%d", time.localtime(f.stat().st_mtime))
            if keep_today and day == today:
                continue
            plan.setdefault(sub, {}).setdefault(day, []).append(f)
            total += 1
    if not run:
        return {"total": total, "days": {s: {d: len(v) for d, v in sorted(m.items())} for s, m in plan.items()}}
    moved = failed = 0
    for sub, m in plan.items():
        for day, fs in m.items():
            dd = OUT / sub / day
            dd.mkdir(exist_ok=True)
            for f in fs:
                try:
                    dst = _unique(dd / f.name)
                    side = f.with_name(f.name + ".json")
                    f.rename(dst)
                    if side.is_file():
                        side.rename(dst.with_name(dst.name + ".json"))
                    moved += 1
                except OSError:
                    failed += 1
    if moved:
        thumb_sweep_bg()
    return {"ok": True, "moved": moved, "failed": failed}


def gallery(q):
    kind, text, off = (q.get("kind") or [""])[0], (q.get("q") or [""])[0].strip().lower(), int((q.get("offset") or ["0"])[0] or 0)
    only_fav, lim = (q.get("fav") or [""])[0] == "1", 60
    day = (q.get("date") or [""])[0]
    day = day if DATE_RX.match(day) else ""
    favs, rows = gal_favs(), []
    for sub in OUT_SUB.values():
        if kind and kind != sub:
            continue
        d = OUT / sub
        if not d.is_dir():
            continue
        for f in out_files(d):
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
    dayof = lambda t: time.strftime("%Y-%m-%d", time.localtime(t))
    days = {}
    for mt, *_ in out:      # 날짜 고르기 목록(날짜 필터는 빼고, 검색·종류·즐겨찾기 조건만 반영)
        days[dayof(mt)] = days.get(dayof(mt), 0) + 1
    if day:
        out = [r for r in out if dayof(r[0]) == day]
    sort = (q.get("sort") or ["new"])[0]
    if sort == "old":
        out.sort(key=lambda r: r[0])
    elif sort == "name":
        out.sort(key=lambda r: r[2].name.lower())
    ginfo = {}
    if (q.get("same") or [""])[0] == "1":      # 같은 프롬프트끼리 모아 보기: 모음은 가장 앞선 그림 기준으로 놓고, 모음 안은 같은 정렬
        order, groups = [], {}
        for r in out:
            pr = r[4] if r[4] is not None else gal_prompt(r[2], r[0])
            k = re.sub(r"\s+", " ", pr.strip().lower())[:200]
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(r)
        order.sort(key=lambda k: (k == "",))                      # 프롬프트 정보 없는 그림 모음은 맨 뒤
        out = [r for k in order for r in groups[k]]
        for k in order:
            gid = hashlib.md5(k.encode("utf-8")).hexdigest()[:8]
            for r in groups[k]:
                ginfo[r[3]] = (gid, len(groups[k]), k)
    page = out[off:off + lim]
    items = [{"day": dayof(mt), "url": "/out/" + "/".join(urllib.parse.quote(x) for x in f.relative_to(OUT).parts), "kind": sub, "name": f.name, "time": int(mt),
              "fav": key in favs, "video": f.suffix.lower() in (".mp4", ".webm"),
              "prompt": (pr if pr is not None else gal_prompt(f, mt))[:200],
              **({"g": ginfo[key][0], "gn": ginfo[key][1], "gp": ginfo[key][2][:120]} if key in ginfo else {})} for mt, sub, f, key, pr in page]
    return {"items": items, "total": len(out), "more": off + lim < len(out), "days": [[d, n] for d, n in list(days.items())[:400]]}


VER_RX = re.compile(r"^\[(\d{4}\.\d{2}\.\d{2}(?:\.\d+)?|\d{1,3}(?:\.\d+)+)([^\]]*)\]\s*(.*)$")


def vkey(v):
    """버전 정렬 키. 예전 날짜식(2026.10.18.24)은 새 번호식(2.0, 2.0.1)보다 항상 옛 버전으로 쳐요."""
    n = tuple(int(x) for x in re.findall(r"\d+", v or ""))
    return ((0,) if n and n[0] >= 1000 else (1,)) + n


def changelog():
    """README.txt 의 [2026.10.18.14] 같은 구역을 읽어 버전별 변경 사항 목록(최신 순)으로 돌려줘요."""
    try:
        lines = (ROOT / "README.txt").read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return {"error": "README.txt 를 찾지 못했어요.", "versions": [], "current": VERSION}
    vers, cur = [], None
    for ln in lines:
        m = VER_RX.match(ln)
        if m:
            cur = {"version": m.group(1), "title": (m.group(2) + " " + m.group(3)).strip(), "items": []}
            vers.append(cur)
            continue
        if re.match(r"^\[[^\]]+\]", ln) or ln.startswith("====="):      # 다른 구역(설치 방법 등)이 시작되면 끝
            cur = None
            continue
        if cur is None or not ln.strip():
            continue
        if re.match(r"^\s*-\s+", ln):
            cur["items"].append(re.sub(r"^\s*-\s+", "", ln).strip())
        elif cur["items"]:
            cur["items"][-1] += " " + ln.strip()      # 줄바꿈된 항목은 이어 붙여요
        else:
            cur["items"].append(ln.strip())
    vers.sort(key=lambda v: vkey(v["version"]), reverse=True)
    return {"versions": vers, "current": VERSION}


# ───────────────────────── 진단 파일 (문제가 생겼을 때 보내는 zip) ─────────────────────────
def _redact(text):
    """로그에서 컴퓨터 사용자 이름·설치 폴더 경로를 가려요."""
    t = str(text)
    for real, mask in ((str(ROOT), "<설치폴더>"), (str(ROOT).replace("\\", "/"), "<설치폴더>")):
        t = t.replace(real, mask)
    return re.sub(r"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s\"']+", r"\1<사용자>", t)


def _tail(path, n=300):
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def diag_export():
    """버전·GPU·설치된 확장/모델 이름·최근 오류·로그 끝부분을 zip 하나로 묶어요. 프롬프트·이미지·API 키는 넣지 않아요."""
    import platform
    info = [f"스튜디오 버전: {VERSION}", f"만든 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}", f"운영체제: {platform.platform()}",
            f"파이썬: {sys.version.split()[0]}", f"GPU: {json.dumps(GPU, ensure_ascii=False) if GPU else '확인 못 함'}",
            f"ComfyUI 켜짐: {alive(CUI + '/system_stats')}", f"Ollama 켜짐: {alive(OLLAMA + '/api/version')}"]
    try:
        ss = http(CUI + "/system_stats", None, 5)
        info.append("ComfyUI 정보: " + json.dumps({"system": {k: v for k, v in (ss.get("system") or {}).items() if k in ("comfyui_version", "pytorch_version", "python_version", "argv")},
                                                 "devices": [{k: d.get(k) for k in ("name", "vram_total", "vram_free")} for d in ss.get("devices", [])]}, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        info.append("ComfyUI 정보: 가져오지 못했어요")
    nodes = sorted(p.name for p in (COMFY / "custom_nodes").iterdir()) if (COMFY / "custom_nodes").is_dir() else []
    miss = []
    try:
        for f in features():
            if f["missing_nodes"] or f["missing_lists"]:
                miss.append(f"{f['id']}: 없는 노드 {f['missing_nodes'] or '-'} / 없는 목록 {f['missing_lists'] or '-'}")
    except Exception as e:  # noqa: BLE001
        miss.append("확인 실패: " + repr(e))
    models = []
    for d in sorted(FOLDERS):
        base = MODELS / d
        if base.is_dir():
            models.append(f"[{d}]")
            models += [f"  {f.name}  ({fsize(f) // (1024 * 1024)}MB)" for f in sorted(base.iterdir()) if f.is_file() and f.suffix != ".part"]
    errs = [f"{j.get('kind', '?')}: {j.get('error')}" for j in list(JOBS.values())[-60:] if j.get("state") == "error" and j.get("error")][-30:]
    chk = []
    try:                                                    # [내 PC 점검]과 같은 결과를 글로 — 어디가 비었는지 한눈에 보여요
        for g in selfcheck()["groups"]:
            chk.append(f"[{ {'ok': '정상', 'warn': '확인', 'bad': '문제'}.get(g['state'], g['state']) }] {g['title']}")
            chk += [f"   {'O' if r['ok'] else '-' if r['ok'] is None else 'X'} {r['label']}: {r.get('detail') or ''}".rstrip(": ") for r in g["rows"]]
    except Exception as e:  # noqa: BLE001
        chk.append("점검 실패: " + repr(e))
    tools = []
    try:
        ffx = vmix.find_ffmpeg(PY, ROOT)
        tools.append("ffmpeg: " + (f"{ffx} (버전 {'.'.join(map(str, vmix.ff_version(ffx)))})" if ffx else "찾지 못함 (영상 소리·자막 기능에 필요)"))
    except Exception as e:  # noqa: BLE001
        tools.append("ffmpeg 확인 실패: " + repr(e))
    pips = ""
    if PY.exists():
        try:
            pr = subprocess.run([str(PY), "-s", "-m", "pip", "list", "--format=freeze", "--disable-pip-version-check"], cwd=HOME, capture_output=True, text=True, timeout=40)
            pips = pr.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pips = "(가져오지 못했어요)"
    note = ("이 파일에는 버전·그래픽카드·설치된 확장과 모델 파일 이름·최근 오류 문구·로그 끝부분이 들어 있어요.\n"
            "프롬프트, 만든 이미지, API 키(settings.json)는 넣지 않았어요. 컴퓨터 사용자 이름과 설치 폴더 경로는 가렸어요.\n"
            "다만 오류 문구나 로그에 입력한 문장이 일부 섞일 수 있으니, 보내기 전에 한 번 훑어봐 주세요.\n")
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("안내.txt", note)
        z.writestr("정보.txt", _redact("\n".join(info)))
        z.writestr("설치된_확장.txt", "\n".join(nodes) or "(없음)")
        z.writestr("기능별_빠진것.txt", "\n".join(miss) or "(없음)")
        z.writestr("모델_파일.txt", "\n".join(models) or "(없음)")
        z.writestr("최근_오류.txt", _redact("\n".join(errs)) or "(없음)")
        z.writestr("내_PC_점검.txt", _redact("\n".join(chk)) or "(없음)")
        z.writestr("도구_부품.txt", _redact("\n".join(tools) + "\n\n[내장 파이썬 패키지]\n" + (pips or "(없음)")))
        if LOGS.is_dir():
            for lf in sorted(LOGS.glob("*.log")):
                z.writestr("logs/" + lf.name, _redact(_tail(lf)))
    return b.getvalue()


# ───────────────────────── 태그 자동완성 ─────────────────────────
TAGS_DIR = ROOT / "tags"
TAG_TYPES = {"0": "일반", "1": "작가", "3": "작품", "4": "캐릭터", "5": "메타"}
_TAGS = {"sig": None, "rows": []}


def _tag_sig():
    parts = []
    for f in [HUB / "tags_builtin.txt", PROMPTS_FILE, LORA_USER] + (sorted(TAGS_DIR.glob("*.csv")) if TAGS_DIR.is_dir() else []):
        try:
            st = f.stat()
            parts.append((f.name, st.st_mtime_ns, st.st_size))
        except OSError:
            pass
    wc = ROOT / "wildcards"
    parts.append(tuple(sorted(p.name for p in wc.glob("*.txt"))) if wc.is_dir() else ())
    try:
        parts.append(tuple(sorted(files("loras"))))
    except Exception:  # noqa: BLE001
        pass
    return tuple(parts)


def _tag_norm(t):
    return re.sub(r"\s+", " ", str(t).replace("_", " ")).strip().lower()


def tags_rows():
    """자동완성 후보 목록(캐시). 기본 태그 + 내 프롬프트 보관함 + LoRA 트리거 + 와일드카드 + tags 폴더의 CSV(danbooru 형식)."""
    sig = _tag_sig()
    if _TAGS["sig"] == sig:
        return _TAGS["rows"]
    rows, seen = [], {}

    def add(shown, cat, weight, key=None):
        k = _tag_norm(key or shown)
        if not k or len(k) > 60:
            return
        sk = (k, _tag_norm(shown))
        if sk in seen:
            if weight > rows[seen[sk]][3]:
                rows[seen[sk]] = (k, shown, cat, weight)
            return
        seen[sk] = len(rows)
        rows.append((k, shown, cat, weight))

    try:
        for i, ln in enumerate((HUB / "tags_builtin.txt").read_text(encoding="utf-8").splitlines()):
            t, _, c = ln.partition("|")
            if t:
                add(t, c or "일반", 1000 - i * 0.5)
    except OSError:
        pass
    if TAGS_DIR.is_dir():
        for f in sorted(TAGS_DIR.glob("*.csv")):
            try:
                for ln in f.read_text(encoding="utf-8", errors="replace").splitlines()[:400000]:
                    c = next(csv.reader([ln]), [])
                    if not c or not c[0].strip() or c[0].lower() == "tag":
                        continue
                    cnt = int(c[2]) if len(c) > 2 and c[2].strip().isdigit() else 0
                    shown, cat = _tag_norm(c[0]), TAG_TYPES.get(c[1].strip() if len(c) > 1 else "0", "일반")
                    add(shown, cat, 2000 + cnt / 1000)
                    for al in (c[3].split(",") if len(c) > 3 else [])[:6]:
                        if al.strip():
                            add(shown, cat, 1500 + cnt / 2000, key=al)      # 별칭으로 찾아도 원래 태그를 넣어 줘요
            except (OSError, ValueError, csv.Error):
                pass
    freq = {}
    for it in prompts_load():
        for part in re.split(r"[,\n]", str(it.get("text") or "") + "," + str(it.get("negative") or "")):
            t = re.sub(r"<[^>]*>|[()\[\]{}]", "", part)
            t = re.sub(r":\s*[\d.]+\s*$", "", t).strip()
            if 1 < len(t) <= 40 and not t.startswith("__"):
                freq[t] = freq.get(t, 0) + 1
    for t, n in freq.items():
        add(t, "내 프롬프트", 5000 + n * 100)
    try:
        for c in model_cards("loras")["items"]:
            for w in list(c.get("user_trigger") or []) + [x[0] if isinstance(x, (list, tuple)) else x for x in (c.get("trigger") or [])][:12]:
                if str(w).strip():
                    add(str(w).strip(), "LoRA 트리거", 6000)
    except Exception:  # noqa: BLE001
        pass
    wc = ROOT / "wildcards"
    if wc.is_dir():
        for p in sorted(wc.glob("*.txt")):
            add(f"__{p.stem}__", "와일드카드", 4000)
    _TAGS.update(sig=sig, rows=rows)
    return rows


def tags_search(q, limit=10):
    k = _tag_norm(q)
    if len(k) < 2:
        return {"items": []}
    pre, mid = [], []
    for key, shown, cat, w in tags_rows():
        if key.startswith(k):
            pre.append((w, shown, cat))
        elif k in key and (f" {k}" in key or len(k) >= 3):
            mid.append((w, shown, cat))
    out, seen = [], set()
    for w, shown, cat in sorted(pre, key=lambda x: -x[0]) + sorted(mid, key=lambda x: -x[0]):
        if shown.lower() in seen or shown.lower() == k:
            continue
        seen.add(shown.lower())
        out.append({"t": shown, "c": cat})
        if len(out) >= limit:
            break
    return {"items": out}


THUMB_DIR = ROOT / "cache" / "thumbs"
THUMB_RX = re.compile(r"^(?P<name>.+)\.(?P<w>\d+)\.(?P<mt>\d+)\.jpg$")
_TH = {"writes": 0, "busy": False}


def thumb_cap():
    """미리보기 캐시 최대 용량(바이트). 설정의 thumb_cache_mb (기본 500MB)."""
    try:
        mb = int(settings().get("thumb_cache_mb", 500))
    except (TypeError, ValueError):
        mb = 500
    return max(50, min(mb, 20000)) * 1024 * 1024


def thumb_loc(path):
    """원본 파일 위치를 그대로 따라가는 캐시 폴더·이름(결과 폴더 o/, 앱 폴더 r/, 그 밖 x/). 원본이 지워졌는지 알 수 있게 하려는 거예요."""
    path = Path(path)
    for tag, root in (("o", OUT), ("r", ROOT)):
        try:
            rel = path.relative_to(root)
            return THUMB_DIR / tag / rel.parent, rel.name
        except ValueError:
            continue
    return THUMB_DIR / "x", hashlib.sha1(str(path).encode()).hexdigest()[:20] + "_" + path.name


def _thumb_files(d, name):
    try:
        for f in d.iterdir():
            m = THUMB_RX.match(f.name)
            if m and m.group("name") == name and f.is_file():
                yield f
    except OSError:
        return


def thumb_drop(path):
    """원본을 지울 때(또는 옮길 때) 그 파일의 미리보기를 같이 지워요."""
    d, name = thumb_loc(path)
    n = 0
    for f in list(_thumb_files(d, name)):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n


def thumb_sweep():
    """원본이 없어졌거나 바뀐 미리보기와 옛 방식 파일을 치워요. 용량이 상한을 넘으면 가장 오래 안 본 것부터 지워요(원본은 건드리지 않아요)."""
    if _TH["busy"]:
        return
    _TH["busy"] = True
    removed = 0
    try:
        if not THUMB_DIR.is_dir():
            return
        for f in list(THUMB_DIR.iterdir()):          # 옛 방식(폴더 없이 이름이 해시인 파일)
            if f.is_file() and f.suffix == ".jpg":
                try:
                    f.unlink(); removed += 1
                except OSError:
                    pass
        roots = {"o": OUT, "r": ROOT}
        keep = []
        for tag, root in roots.items():
            base = THUMB_DIR / tag
            if not base.is_dir():
                continue
            for f in base.rglob("*.jpg"):
                m = THUMB_RX.match(f.name)
                try:
                    if not m:
                        f.unlink(); removed += 1; continue
                    src = root / f.parent.relative_to(base) / m.group("name")
                    if not src.is_file() or str(src.stat().st_mtime_ns) != m.group("mt"):
                        f.unlink(); removed += 1; continue
                    st = f.stat()
                    keep.append((st.st_mtime, st.st_size, f))
                except OSError:
                    pass
        xb = THUMB_DIR / "x"
        for f in (xb.glob("*.jpg") if xb.is_dir() else []):
            try:
                st = f.stat(); keep.append((st.st_mtime, st.st_size, f))
            except OSError:
                pass
        total, cap = sum(k[1] for k in keep), thumb_cap()
        if total > cap:
            for mt, sz, f in sorted(keep, key=lambda k: k[0]):
                if total <= cap * 0.9:
                    break
                try:
                    f.unlink(); total -= sz; removed += 1
                except OSError:
                    pass
        for d in sorted((x for x in THUMB_DIR.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
            try:
                d.rmdir()            # 비어 버린 폴더는 치워요(안 비었으면 그대로 남아요)
            except OSError:
                pass
        if removed:
            log(f"[미리보기 정리] {removed}개를 지웠어요")
    finally:
        _TH["busy"] = False


def _safe_warm():
    try:
        lists()
    except Exception as e:  # noqa: BLE001
        log("[목록 미리 읽기 실패]", repr(e))


def thumb_sweep_bg():
    threading.Thread(target=thumb_sweep, daemon=True).start()


def thumb_bytes(path, w=320):
    """갤러리 미리보기(작은 JPEG). 처음 볼 때 한 번 만들어 cache 폴더에 두고, 상한을 넘으면 오래 안 본 것부터 지워요."""
    st = path.stat()
    d, name = thumb_loc(path)
    cp = d / f"{name}.{w}.{st.st_mtime_ns}.jpg"
    if cp.is_file():
        try:
            if time.time() - cp.stat().st_mtime > 3600:      # '마지막으로 본 때'를 가끔 갱신해요(오래 안 본 것부터 지우려고)
                os.utime(cp, None)
            return cp.read_bytes()
        except OSError:
            pass
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((w, w))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=80)
    try:
        d.mkdir(parents=True, exist_ok=True)
        for old in list(_thumb_files(d, name)):            # 이 파일의 예전(원본이 바뀌기 전) 미리보기
            if THUMB_RX.match(old.name).group("w") == str(w):
                old.unlink(missing_ok=True)
        cp.write_bytes(b.getvalue())
        _TH["writes"] += 1
        if _TH["writes"] % 200 == 0:
            thumb_sweep_bg()
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


def _pack_done(repo):
    """확장이 폴더로 있고, 자체 설치 단계가 필요한 확장은 그 단계까지 끝났는지."""
    d = _repo_dir(repo)
    return d.is_dir() and (not (KNOWN_PACKS.get(repo) or {}).get("install_py") or (d / ".hub-setup-done").exists())


def node_sources(missing):
    """없는 노드 이름들 → 설치할 저장소별로 묶어서 돌려줘요."""
    if missing and all(any(n in v["nodes"] for v in KNOWN_PACKS.values()) for n in missing):
        m = {}           # 직접 확인해 둔 확장만 필요하면 공개 노드 목록(인터넷)을 받지 않아도 안내할 수 있어요
    else:
        m = nodemap()
    if _NM["idx"] is None and m:
        idx = {}
        for repo, v in m.items():
            for n in (v[0] if v and isinstance(v[0], list) else []):
                idx.setdefault(n, []).append(repo)
        _NM["idx"] = idx
    by, unknown = {}, []
    for n in missing:
        known = next((r for r, v in KNOWN_PACKS.items() if n in v["nodes"]), None)
        repos = [known] if known else [r for r in (_NM["idx"] or {}).get(n, []) if r.startswith(GHURL + "/")]
        if not repos:
            unknown.append(n)
            continue
        r = repos[0]
        by.setdefault(r, []).append(n)
    out = [{"repo": r, "title": (KNOWN_PACKS[r]["title"] if r in KNOWN_PACKS else ((m[r][1] or {}).get("title_aux") if len(m[r]) > 1 else "")) or Path(r).name, "nodes": ns,
            "installed": _pack_done(r), "incomplete": _repo_dir(r).is_dir() and not _pack_done(r), "state": (NODE_JOBS.get(r) or {}).get("state", "")} for r, ns in by.items()]
    return {"repos": out, "unknown": unknown}


def _node_fetch(repo, dest, J):
    import zipfile
    J["msg"] = "내려받는 중…"
    tmp = ROOT / "cache" / "nodes"
    tmp.mkdir(parents=True, exist_ok=True)
    zp = tmp / (dest.name + ".zip")
    ref = (KNOWN_PACKS.get(repo) or {}).get("ref") or "HEAD"      # 확인해 둔 확장은 확인한 커밋 그대로 받아요
    with urllib.request.urlopen(repo + "/archive/" + ref + ".zip", timeout=120) as r, open(zp, "wb") as f:
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


# ReActor 가 실행 중에 불러오는 파이썬 부품(자체 설치 스크립트가 조용히 실패해도 여기서 확인하고 다시 설치해요)
REACTOR_MODS = {"onnx": "onnx", "onnxruntime": "onnxruntime", "cv2": "opencv-python-headless", "scipy": "scipy", "segment_anything": "segment_anything",
                "albumentations": "albumentations", "colour": "colour-science", "ultralytics": "ultralytics"}


def mods_missing(mods):
    """내장 파이썬에서 불러올 수 없는 모듈 이름 목록."""
    if not PY.exists():
        return []
    try:
        r = subprocess.run([str(PY), "-s", "-c", "import importlib.util as u,json;print(json.dumps([m for m in %r if u.find_spec(m) is None]))" % sorted(mods)], cwd=HOME,
                           capture_output=True, text=True, timeout=60)
        return json.loads((r.stdout or "[]").strip().splitlines()[-1])
    except Exception:
        return []


def ensure_mods(mods, J=None):
    """빠진 부품을 하나씩 설치하고, 끝까지 안 되는 것은 (이름, 마지막 오류 줄)로 돌려줘요."""
    bad = []
    for m in mods_missing(mods):
        pip = mods[m]
        if J is not None:
            J["msg"] = f"{pip} 설치 중…"
        rc, out, note = pip_install_one(pip)
        LOGS.mkdir(exist_ok=True)
        with open(LOGS / "nodes.log", "a", encoding="utf-8") as f:
            f.write(f"\n[부품 확인] {pip} → 종료 코드 {rc}\n" + out[-3000:])
        if rc or m in mods_missing({m: pip}):
            last = [x for x in out.strip().splitlines() if x.strip()][-1:] or [""]
            bad.append((pip, note or last[0][:160]))
    return bad


def _node_install(repo):
    J = NODE_JOBS[repo]
    try:
        import zipfile
        dest = _repo_dir(repo)
        kp = KNOWN_PACKS.get(repo) or {}
        resume = dest.exists() and bool(kp.get("install_py")) and not (dest / ".hub-setup-done").exists()     # 내려받기는 됐는데 부품·모델 설치가 덜 끝난 경우
        if dest.exists() and not resume:
            raise RuntimeError("이미 설치돼 있어요. ComfyUI 를 다시 시작하면 적용돼요.")
        if not resume:
            _node_fetch(repo, dest, J)
        tmp = ROOT / "cache" / "nodes"
        tmp.mkdir(parents=True, exist_ok=True)
        req = dest / "requirements.txt"
        note = ""
        if kp.get("install_py") and (dest / "install.py").is_file():
            # 이 확장은 자기 설치 스크립트가 부품·모델(inswapper 등)을 받아요 — 확인해 둔 커밋의 스크립트만 실행해요
            if not PY.exists():
                raise RuntimeError("이미지 엔진(python_embeded)을 찾지 못해서 부품을 설치하지 못했어요.")
            J["msg"] = "설치 준비 중…"
            subprocess.run([str(PY), "-s", "-m", "pip", "install", "--no-warn-script-location", "importlib_metadata", "packaging", "tqdm", "setuptools<81"],
                           cwd=HOME, capture_output=True, text=True, timeout=900)       # install.py 가 쓰는 기본 부품(내장 파이썬엔 빠져 있을 수 있어요)
            J["msg"] = "부품과 얼굴 교체 모델을 내려받는 중…(몇 분 걸릴 수 있어요)"
            r = subprocess.run([str(PY), "-s", "install.py"], cwd=str(dest), capture_output=True, text=True, timeout=2400)
            LOGS.mkdir(exist_ok=True)
            (LOGS / "nodes.log").write_text((r.stdout or "")[-6000:] + (r.stderr or "")[-6000:], encoding="utf-8")
            if r.returncode:
                last = [x for x in (r.stderr or r.stdout or "").strip().splitlines() if x.strip()][-1:] or [""]
                raise RuntimeError("부품·모델 설치에 실패했어요. 이 버튼을 다시 누르면 이어서 시도해요. 원인: " + last[0][:200] + " (자세한 내용: logs\\nodes.log)")
            if repo == REACTOR_REPO:
                bad = ensure_mods(REACTOR_MODS, J)
                if bad:
                    raise RuntimeError("필요한 부품을 설치하지 못했어요: " + ", ".join(f"{p}({e})" for p, e in bad) + ". 이 버튼을 다시 누르면 이어서 시도해요. (자세한 내용: logs\\nodes.log)")
            (dest / ".hub-setup-done").write_text("ok", encoding="utf-8")
        elif req.is_file():
            if PY.exists():
                J["msg"] = "필요한 파이썬 패키지 설치 중…(몇 분 걸릴 수 있어요)"
                lines = [x for x in req.read_text(encoding="utf-8", errors="ignore").splitlines() if x.strip() and not x.strip().startswith(("git+", "#"))]
                req2 = tmp / (dest.name + "-req.txt")       # git 이 없는 PC 에서도 되도록 git+ 주소 줄은 빼고 설치해요
                req2.write_text("\n".join(lines) + "\n", encoding="utf-8")
                r = subprocess.run([str(PY), "-s", "-m", "pip", "install", "-r", str(req2), "--no-warn-script-location"], cwd=HOME,
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


# ───────────────────────── 설치돼 있는데 노드가 안 보일 때: 원인 확인 · 빠진 부품 설치 ─────────────────────────
PIP2MOD = {"opencv-python-headless": "cv2", "opencv-python": "cv2", "opencv-contrib-python": "cv2", "scikit-image": "skimage", "pillow": "PIL", "pyyaml": "yaml",
           "scikit-learn": "sklearn", "segment-anything": "segment_anything", "gitpython": "git", "colour-science": "colour"}


def pack_reqs(dest):
    """확장 폴더의 requirements.txt 에서 (모듈 이름 → pip 이름). git+ 줄과 주석은 빼요."""
    out = {}
    try:
        lines = (dest / "requirements.txt").read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return out
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith(("#", "git+", "-")):
            continue
        name = re.split(r"[<>=!~;\[\s@]", ln, 1)[0].strip()
        if re.match(r"^[A-Za-z0-9_.\-]+$", name) and name.lower() not in ("torch", "torchvision", "torchaudio", "numpy"):
            out[PIP2MOD.get(name.lower(), name.lower().replace("-", "_"))] = name
    return out


def comfy_import_error(dirname):
    """comfyui.log 맨 끝쪽에서 이 확장이 불러오다 실패한 이유(마지막 오류 줄)를 찾아요."""
    try:
        f = LOGS / "comfyui.log"
        with open(f, "rb") as fh:
            fh.seek(max(0, f.stat().st_size - 300_000))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    hit = ""
    for i, ln in enumerate(lines):
        if dirname.lower() in ln.lower() and re.search(r"IMPORT FAILED|Cannot import|Traceback|Error", ln, re.I):
            seg = lines[i:i + 45]
            errs = [x.strip() for x in seg if re.search(r"(ModuleNotFoundError|ImportError|Error:)", x) and "Traceback" not in x]
            hit = (errs[-1] if errs else ln.strip())[:240]
    return hit


def node_diagnose(p):
    repo = str(p.get("repo") or "")
    dest = _repo_dir(repo)
    if not repo.startswith(GHURL + "/") or not dest.is_dir():
        return {"error": "설치된 확장을 찾지 못했어요."}
    reqs = pack_reqs(dest)
    gone = mods_missing(reqs) if reqs else []
    reason = comfy_import_error(dest.name)
    m = re.search(r"No module named ['\"]([A-Za-z0-9_.]+)", reason)
    extra = [m.group(1).split(".")[0]] if m and m.group(1).split(".")[0] not in gone else []
    mods = [{"module": g, "pip": reqs[g]} for g in gone] + [{"module": g, "pip": PYMODS.get(g, g)} for g in extra if g in PYMODS or g not in reqs]
    kp = KNOWN_PACKS.get(repo) or {}
    return {"installed": True, "mine": _own_comfy() is not None, "missing": mods, "reason": reason, "running": bool(alive(CUI + "/system_stats")),
            "setup": bool(kp.get("install_py") and (dest / "install.py").is_file())}      # 자기 설치 단계(부품·모델 받기)가 있는 확장(예: ReActor)


def _deps_run(repo, mods):
    J = NODE_JOBS[repo]
    try:
        bad = []
        for m in mods:
            J["msg"] = f"{m['pip']} 설치 중…(1~3분 걸릴 수 있어요)"
            rc, out, note = pip_install_one(m["pip"])
            LOGS.mkdir(exist_ok=True)
            with open(LOGS / "nodes.log", "a", encoding="utf-8") as f:
                f.write(f"\n[확장 부품] {m['pip']} → 종료 코드 {rc}\n" + out[-3000:])
            if rc or m["module"] in mods_missing({m["module"]: m["pip"]}):
                last = [x for x in out.strip().splitlines() if x.strip()][-1:] or [""]
                bad.append(f"{m['pip']}({note or last[0][:120]})")
        if bad:
            raise RuntimeError("설치하지 못한 부품: " + ", ".join(bad) + " (자세한 내용: logs\\nodes.log)")
        J["state"], J["msg"] = "done", "부품을 설치했어요. 이미지 엔진을 다시 시작하면 적용돼요."
    except Exception as e:  # noqa: BLE001
        J["state"], J["msg"] = "error", str(e) or e.__class__.__name__


def node_fixdeps(p):
    d = node_diagnose(p)
    if d.get("error"):
        return d
    repo = str(p["repo"])
    if d.get("setup") and (d["missing"] or d["reason"]):      # ReActor 처럼 자기 설치 단계가 있는 확장은 그 단계를 다시 돌려요(확인해 둔 커밋의 스크립트만)
        if NODE_JOBS.get(repo, {}).get("state") == "running":
            return {"ok": True}
        (_repo_dir(repo) / ".hub-setup-done").unlink(missing_ok=True)
        NODE_JOBS[repo] = {"state": "running", "msg": "시작해요…"}
        threading.Thread(target=_node_install, args=(repo,), daemon=True).start()
        return {"ok": True}
    if not d["missing"]:
        return {"error": "빠진 부품이 없어요. 이미지 엔진을 다시 시작해 보세요."}
    if NODE_JOBS.get(repo, {}).get("state") == "running":
        return {"ok": True}
    NODE_JOBS[repo] = {"state": "running", "msg": "시작해요…"}
    threading.Thread(target=_deps_run, args=(repo, d["missing"]), daemon=True).start()
    return {"ok": True}


# 확장 노드가 실행 중 "No module named 'xxx'" 로 멈출 때, 화면에서 바로 설치할 수 있게 해 줘요(아래 목록의 흔한 부품만)
PYMODS = {"matplotlib": "matplotlib", "scipy": "scipy", "cv2": "opencv-python-headless", "skimage": "scikit-image", "sklearn": "scikit-learn",
          "yaml": "pyyaml", "PIL": "pillow", "einops": "einops", "timm": "timm", "addict": "addict", "yapf": "yapf", "mediapipe": "mediapipe",
          "onnxruntime": "onnxruntime", "ultralytics": "ultralytics", "trimesh": "trimesh", "omegaconf": "omegaconf", "fvcore": "fvcore",
          "svglib": "svglib", "reportlab": "reportlab", "numba": "numba",
          "imageio_ffmpeg": "imageio-ffmpeg", "onnx": "onnx", "albumentations": "albumentations", "segment_anything": "segment_anything", "colour": "colour-science"}
PYMOD_JOBS = {}


OOM_PAT = re.compile(r"out of memory|outofmemory|not enough memory|failed to allocate|allocation on device|insufficient memory|cublas_status_alloc_failed", re.I)


def oom_guide(msg, p):
    """메모리(VRAM) 부족으로 멈췄을 때, 작업 종류에 맞는 해결 방법을 돌려줘요. 아니면 None."""
    if not OOM_PAT.search(str(msg or "")):
        return None
    kind = (p or {}).get("kind")
    tips = []
    if kind == "vid":
        tips = ["영상 길이(프레임 수)를 줄이거나 크기를 낮춰 보세요. 둘 다 메모리를 크게 써요.",
                "14B 모델이면 5B 로 바꿔 보세요."]
    elif kind == "music":
        tips = ["곡 길이를 줄여 보세요(예: 120초 → 60초). 길수록 메모리를 많이 써요."]
    elif kind == "vpost":
        tips = ["프레임 보간·업스케일은 영상이 길수록 메모리를 많이 써요. 더 짧은 영상으로 해 보세요.",
                "업스케일 배율을 낮추거나 보간 배수를 2배로 해 보세요."]
    elif kind in ("up", "batch"):
        tips = ["업스케일은 큰 사진일수록 메모리를 많이 써요. 사진을 먼저 줄이거나 배율을 낮춰 보세요."]
    else:
        tips = ["해상도를 한 단계 낮춰 보세요(예: 1024 → 832). 장수는 1장씩이 가장 안전해요.",
                "ControlNet·LoRA·고해상도 보정을 켰다면 하나씩 꺼 보세요."]
    tips.append("아래 [메모리 비우기]로 쌓인 메모리를 정리한 뒤 다시 시도해 보세요. 채팅 모델이 올라가 있으면 같이 내려가요.")
    return {"tips": tips}


def memory_free():
    free_ollama()
    free_comfy()
    return {"ok": True}


def pymod_missing(msg):
    """오류 문구에서 '빠진 파이썬 부품'을 찾아요. 설치해도 되는 흔한 부품이면 {module, pip}, 아니면 None."""
    m = re.search(r"No module named ['\"]([A-Za-z0-9_]+)", str(msg or ""))
    return {"module": m.group(1), "pip": PYMODS[m.group(1)]} if m and m.group(1) in PYMODS else None


LOCK_PAT = re.compile(r"WinError 5|WinError 32|액세스가 거부|Access is denied|being used by another process|다른 프로세스가 사용", re.I)


def _pip_cmds(pipname):
    """설치 명령 묶음. albumentations 는 opencv-python-headless 를 끌어와서 이미 쓰는 cv2 파일을 덮어쓰려다 막히므로(WinError 5),
    cv2 가 이미 있으면 opencv 는 건드리지 않고 필요한 나머지만 설치해요."""
    base = [str(PY), "-s", "-m", "pip", "install"]
    if pipname == "albumentations" and not mods_missing({"cv2": "x"}):
        return [base + ["pydantic", "stringzilla", "simsimd", "--no-warn-script-location"], base + ["--no-deps", "albumentations", "albucore", "--no-warn-script-location"]]
    return [base + [pipname, "--no-warn-script-location"]]


def pip_install_one(pipname, timeout=1500):
    """부품 하나를 설치해요. 돌려주는 값: (종료 코드, 출력 합친 글, 안내문). 파일이 잠겨서 막히면 스튜디오가 켠 ComfyUI 를 잠시 끄고 한 번 더 해 봐요."""
    def go():
        out, rc = "", 0
        for cmd in _pip_cmds(pipname):
            r = subprocess.run(cmd, cwd=HOME, capture_output=True, text=True, timeout=timeout)
            out += (r.stdout or "")[-3000:] + (r.stderr or "")[-3000:]
            rc = r.returncode
            if rc:
                break
        return rc, out
    rc, out = go()
    note = ""
    if rc and LOCK_PAT.search(out):
        mine = _own_comfy()
        if mine:
            for pr in mine:
                pr.terminate()
                try:
                    pr.wait(timeout=20)
                except Exception:
                    pr.kill()
                procs.remove(pr)
            try:
                rc, out = go()
            finally:
                start_engines()
                _CAPS["t"] = 0
            if not rc:
                note = " (ComfyUI 를 잠시 껐다 켰어요)"
        elif rc:
            note = "ComfyUI 가 스튜디오 밖에서 켜져 있어서 파일을 바꿀 수 없어요. ComfyUI 창을 닫은 뒤 다시 눌러 주세요."
    return rc, out, note


def pymod_run(mod):
    J = PYMOD_JOBS[mod]
    try:
        if not PY.exists():
            raise RuntimeError("python_embeded 를 찾지 못했어요. ComfyUI 포터블이 설치돼 있는지 확인해 주세요.")
        J["msg"] = f"{PYMODS[mod]} 설치 중…(1~3분 걸릴 수 있어요)"
        rc, out, note = pip_install_one(PYMODS[mod])
        if rc:
            LOGS.mkdir(exist_ok=True)
            (LOGS / "pymod.log").write_text(out[-8000:], encoding="utf-8")
            raise RuntimeError(note or "설치에 실패했어요(인터넷 연결을 확인해 주세요. 자세한 내용은 logs\\pymod.log).")
        J["state"], J["msg"] = "done", "설치했어요." + note + " 같은 작업을 다시 해 보세요. (그래도 안 되면 [이미지 엔진 다시 시작])"
    except Exception as e:  # noqa: BLE001
        J["state"], J["msg"] = "error", str(e) or e.__class__.__name__
        log("[파이썬 부품 설치 오류]", repr(e))


def pymod_install(p):
    mod = str(p.get("module") or "")
    if mod not in PYMODS:
        return {"error": "설치할 수 있는 부품 목록에 없어요."}
    if PYMOD_JOBS.get(mod, {}).get("state") == "running":
        return {"ok": True}
    PYMOD_JOBS[mod] = {"state": "running", "msg": "시작해요…"}
    threading.Thread(target=pymod_run, args=(mod,), daemon=True).start()
    return {"ok": True}


def node_install(p):
    repo = str(p.get("repo") or "")
    try:
        ok = repo in KNOWN_PACKS or (repo in nodemap() and repo.startswith(GHURL + "/"))
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


# ───────────────────────── 설치한 확장·부품 관리 ─────────────────────────
PART_CORE = {"PIL", "yaml", "einops", "scipy"}          # ComfyUI 자체가 쓰는 부품은 목록에 올리지 않아요(지우면 엔진이 멈춰요)
PART_MODEL_SKIP = {n.split("/")[0] for n in FOLDERS} | {"configs", "vae_approx"}


def _rm_tree(p):
    def onerr(fn, path, _e):
        try:
            os.chmod(path, 0o700)
            fn(path)
        except OSError:
            pass
    shutil.rmtree(_lp(p), onerror=onerr)


def _own_comfy():
    return [pr for pr in procs if any("main.py" in str(a) for a in (pr.args if isinstance(pr.args, (list, tuple)) else [pr.args]))]


def _pip_present():
    mods = sorted(m for m in PYMODS if m not in PART_CORE)
    if not PY.exists():
        return []
    try:
        r = subprocess.run([str(PY), "-s", "-c", "import importlib.util as u,json;print(json.dumps([m for m in %r if u.find_spec(m)]))" % mods], cwd=HOME,
                           capture_output=True, text=True, timeout=60)
        return json.loads((r.stdout or "[]").strip().splitlines()[-1])
    except Exception:
        return []


def parts_list():
    cn = COMFY / "custom_nodes"
    by_dir = {_repo_dir(r).name: (r, v) for r, v in KNOWN_PACKS.items()}
    nodes = []
    if cn.is_dir():
        for d in sorted(cn.iterdir(), key=lambda x: x.name.lower()):
            if not d.is_dir() or d.name.startswith((".", "__")):
                continue
            r, v = by_dir.get(d.name, (None, None))
            nodes.append({"name": d.name, "title": (v or {}).get("title") or d.name, "size": dir_size(d), "known": bool(v),
                          "incomplete": bool(r) and not _pack_done(r), "path": str(d)})
    models = []
    if MODELS.is_dir():
        for d in sorted(MODELS.iterdir(), key=lambda x: x.name.lower()):
            if d.is_dir() and d.name not in PART_MODEL_SKIP and not d.name.startswith("."):
                models.append({"name": d.name, "size": dir_size(d), "path": str(d)})
        seg = MODELS / "ultralytics" / "segm"
        if seg.is_dir():
            models.append({"name": "ultralytics/segm", "size": dir_size(seg), "path": str(seg)})
    pips = [{"module": m, "pip": PYMODS[m]} for m in _pip_present()]
    return {"nodes": nodes, "models": models, "pips": pips, "edge": tts.edge_ready(), "busy": bool(busy_count()), "mine": bool(_own_comfy())}


def part_delete(p):
    """한 번에 하나씩, 화면에서 확인을 거친 것만 지워요. 이름은 목록에 있는 것과 정확히 같아야 해요."""
    kind, name = str(p.get("kind") or ""), str(p.get("name") or "")
    if busy_count():
        return {"error": "작업이 진행 중일 때는 지우지 않아요. 끝난 뒤에 다시 눌러 주세요."}
    if kind == "node":
        cn = COMFY / "custom_nodes"
        d = cn / name
        if not name or name != Path(name).name or name.startswith((".", "__")) or not d.is_dir() or d.parent != cn:
            return {"error": "그 확장을 찾을 수 없어요."}
        mine = _own_comfy()
        if not mine and alive(CUI + "/system_stats"):
            return {"error": "ComfyUI 가 스튜디오 밖에서 켜져 있어요. ComfyUI 창을 닫은 뒤 다시 눌러 주세요(켜져 있으면 파일이 지워지지 않아요)."}
        for pr in mine:
            pr.terminate()
            try:
                pr.wait(timeout=20)
            except Exception:
                pr.kill()
            procs.remove(pr)
        try:
            _rm_tree(d)
        except OSError as e:
            return {"error": f"지우지 못했어요: {e}"}
        finally:
            if mine:
                start_engines()
                _CAPS["t"] = 0
        return {"ok": True, "left": d.exists()}
    if kind == "model":
        ok = {m["name"]: Path(m["path"]) for m in parts_list()["models"]}
        d = ok.get(name)
        if not d or not d.is_dir():
            return {"error": "그 폴더를 찾을 수 없어요."}
        try:
            _rm_tree(d)
        except OSError as e:
            return {"error": f"지우지 못했어요: {e}"}
        _CAPS["t"] = 0
        return {"ok": True, "left": d.exists()}
    if kind == "pip":
        if name not in PYMODS or name in PART_CORE:
            return {"error": "지울 수 있는 부품이 아니에요."}
        r = subprocess.run([str(PY), "-s", "-m", "pip", "uninstall", "-y", PYMODS[name]], cwd=HOME, capture_output=True, text=True, timeout=300)
        if r.returncode:
            return {"error": "부품을 지우지 못했어요: " + ((r.stderr or r.stdout or "")[-200:])}
        _CAPS["t"] = 0
        return {"ok": True}
    if kind == "edge":
        r = subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "edge-tts"], capture_output=True, text=True, timeout=300)
        importlib.invalidate_caches()
        if r.returncode:
            return {"error": "부품을 지우지 못했어요: " + ((r.stderr or r.stdout or "")[-200:])}
        return {"ok": True}
    return {"error": "알 수 없는 종류예요."}


# ───────────────────────── 프로그램 다시 시작 · 위치 옮기기 ─────────────────────────
def _appdata():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LocalAI-Studio"


def _exit_now():
    for pr in list(procs):
        try:
            pr.terminate()
        except Exception:
            pass
    os._exit(0)


def busy_count():
    return sum(1 for j in JOBS.values() if j.get("state") in ("queued", "running")) + \
        sum(1 for t in TASKS if t.get("state") in ("queued", "running")) + sum(1 for j in NODE_JOBS.values() if j.get("state") == "running")


def spawn_helper(mode, dst=None):
    """스튜디오를 끈 뒤 옮기기·다시 켜기를 맡을 도우미를 임시 폴더에서 따로 띄워요(이 폴더 밖이라 옮겨도 안전해요)."""
    import relocate
    tmp = Path(tempfile.mkdtemp(prefix="localai-helper-"))
    shutil.copy2(HUB / "relocate.py", tmp / "relocate.py")
    py = Path(sys.executable)
    try:       # 내장 파이썬이 옮길 폴더 안에 있으면 가벼운 실행 파일 일부만 임시 폴더로 복사해서 써요
        if relocate._inside(py, ROOT):
            rt = tmp / "rt"
            rt.mkdir()
            for f in py.parent.iterdir():
                if f.is_file():
                    shutil.copy2(f, rt / f.name)
            py = rt / py.name
    except OSError:
        py = Path(sys.executable)
    ad = _appdata()
    job = {"mode": mode, "src": str(ROOT), "dst": str(dst or ROOT), "ppid": os.getppid(), "wait": 3, "log": str(ad / "move.log"),
           "result": str(ad / "last-move.json"), "path_txt": str(ad / "path.txt")}
    (tmp / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    flags = (0x00000008 | 0x00000200) if os.name == "nt" else 0      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(py), "-I", "-X", "utf8", str(tmp / "relocate.py"), str(tmp / "job.json")], cwd=str(tmp), creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)


def app_restart(p):
    n = busy_count()
    if n and not p.get("force"):
        return {"busy": n}
    spawn_helper("restart")
    threading.Timer(0.8, _exit_now).start()
    return {"ok": True}


def app_move(p, check_only):
    import relocate
    try:
        pl = relocate.plan(ROOT, p.get("dest"))
    except ValueError as e:
        return {"error": str(e)}
    except OSError as e:
        return {"error": f"그 위치를 확인하지 못했어요: {e}"}
    if check_only:
        return pl
    n = busy_count()
    if n and not p.get("force"):
        return {"busy": n}
    spawn_helper(pl["mode"], pl["dst"])
    threading.Timer(0.8, _exit_now).start()
    return {"ok": True, **pl}


def app_where():
    return {"root": str(ROOT), "parent": str(ROOT.parent), "nested_same_name": ROOT.parent.name == ROOT.name,
            "free": shutil.disk_usage(ROOT).free}


def app_notice():
    """옮기기/재시작 결과를 한 번만 알려 줘요."""
    f = _appdata() / "last-move.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        f.unlink()
        return d
    except (OSError, ValueError):
        return {}


# ───────────────────────── LoRA / 모델 정보 ─────────────────────────
PREV_EXT = (".preview.png", ".preview.jpg", ".preview.jpeg", ".png", ".jpg", ".jpeg", ".webp")


def model_preview(kind, name):
    """모델 파일과 이름이 같은 그림 파일(예: x.safetensors 옆의 x.preview.png, x.png)을 미리보기로 써요."""
    stem = Path(name).stem
    for ext in PREV_EXT:
        f = MODELS / kind / (stem + ext)
        if f.is_file():
            return f
    return None


LORA_USER = ROOT / "lora_user.json"


def lora_user():
    try:
        d = json.loads(LORA_USER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def lora_user_api(p):
    """내가 직접 적은 트리거 단어와 종류(character/style/background/other, 비우면 자동)를 LoRA 별로 저장해요."""
    name = str(p.get("name") or "")
    if name not in files("loras"):
        return {"error": "그런 LoRA 파일이 없어요."}
    with _PLOCK:
        d = lora_user()
        cur = d.get(name, {})
        if "trigger" in p:
            words = []
            for w in p.get("trigger") or []:
                w = str(w).strip()[:60]
                if w and w not in words:
                    words.append(w)
            cur["trigger"] = words[:30]
        if "kind" in p:
            k = str(p.get("kind") or "")
            if k and k not in modelinfo.KINDS:
                return {"error": "알 수 없는 종류예요."}
            cur["kind"] = k
        if "family" in p:
            f = str(p.get("family") or "")
            if f and f not in FAMILY_CHOICES:
                return {"error": "알 수 없는 계열이에요."}
            cur["family"] = f
        if cur.get("trigger") or cur.get("kind") or cur.get("family"):
            d[name] = cur
        else:
            d.pop(name, None)
        LORA_USER.parent.mkdir(parents=True, exist_ok=True)
        LORA_USER.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        _LC["key"] = None      # 목록 캐시에 들어 있는 종류·계열도 다시 만들어요
    return {"ok": True, **lora_user().get(name, {"trigger": [], "kind": "", "family": ""})}


def lora_preview_api(p):
    """모델 미리보기 그림을 올리거나(image) 지워요(remove). 파일 옆에 '이름.preview.jpg' 로 저장돼요.
    dir: loras(기본) / checkpoints / diffusion_models"""
    name = str(p.get("name") or "")
    sub = str(p.get("dir") or "loras")
    if sub not in ("loras", "checkpoints", "diffusion_models"):
        return {"error": "알 수 없는 폴더예요."}
    if name not in files(sub):
        return {"error": "그런 모델 파일이 없어요."}
    stem = Path(name).stem
    old = [MODELS / sub / (stem + e) for e in PREV_EXT]
    if p.get("remove"):
        for f in old:
            if f.is_file() and f.name.lower().startswith(stem.lower() + ".preview"):
                f.unlink(missing_ok=True)
        return {"ok": True}
    try:
        im = load_img(p["image"])
    except Exception:
        return {"error": "이미지를 읽을 수 없어요."}
    im.thumbnail((640, 640))
    for f in old:
        if f.name.lower().startswith(stem.lower() + ".preview") and f.is_file():
            f.unlink(missing_ok=True)
    im.save(MODELS / sub / (stem + ".preview.jpg"), "JPEG", quality=88)
    return {"ok": True}


def lora_final(c, user):
    u = user.get(c["name"], {})
    return u.get("kind") or c.get("kind_auto") or "unknown", bool(u.get("kind"))


def model_cards(kind):
    """kind: loras(트리거 단어·종류·학습 정보까지) / checkpoints(계열·크기)."""
    out = []
    if kind == "loras":
        user = lora_user()
        for n in files("loras"):
            try:
                c = dict(modelinfo.lora_card(MODELS / "loras" / n))
            except Exception:  # noqa: BLE001
                c = {"name": n, "family": "unknown", "trigger": [], "tags": [], "kind_auto": "unknown"}
            c["kind"], c["kind_set"] = lora_final(c, user)
            c["user_trigger"] = (user.get(n) or {}).get("trigger", [])
            uf = (user.get(n) or {}).get("family")
            c["family_auto"], c["family_set"] = c.get("family", "unknown"), bool(uf)
            if uf:
                c["family"] = uf
            c["preview"] = bool(model_preview("loras", n))
            out.append(c)
    else:
        for sub in ("checkpoints", "diffusion_models"):
            for n in files(sub):
                try:
                    sz = round((MODELS / sub / n).stat().st_size / 1048576, 1)
                    fam = model_family(sub, n)[0]
                except OSError:
                    sz, fam = 0, "unknown"
                out.append({"name": n, "dir": sub, "size_mb": sz, "family": fam, "preview": bool(model_preview(sub, n))})
    return {"items": out}


def lora_kinds():
    user = lora_user()
    out = {}
    for n in files("loras"):
        try:
            out[n] = lora_final(dict(modelinfo.lora_card(MODELS / "loras" / n)), user)[0]
        except Exception:  # noqa: BLE001
            out[n] = "unknown"
    return out


# ───────────────────────── 설정 백업 · 복원 ─────────────────────────
BACKUP_MAX = 30 * 1024 * 1024


def chats_export(limit=20 * 1024 * 1024):
    out, size = [], 0
    for c in sorted(chats_load(), key=lambda c: c.get("updated", 0), reverse=True):      # 너무 크면 최근 대화부터 담아요
        size += len(json.dumps(c, ensure_ascii=False))
        if size > limit:
            break
        out.append(c)
    return out


def backup_export():
    """프롬프트 보관함·즐겨찾기·LoRA 내 정보·와일드카드를 한 묶음으로 돌려줘요(프리셋은 화면에서 덧붙여요)."""
    wc = {}
    d = ROOT / "wildcards"
    if d.is_dir():
        for f in sorted(d.glob("*.txt")):
            try:
                wc[f.stem] = f.read_text(encoding="utf-8", errors="replace")[:200000]
            except OSError:
                pass
    return {"app": "LocalAI-Studio", "kind": "backup", "format": 1, "version": VERSION, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompts": prompts_load(), "favs": sorted(gal_favs()), "lora_user": lora_user(), "wildcards": wc, "chats": chats_export()}


def backup_import(p):
    """백업 묶음을 되살려요. mode: merge(이미 있는 건 그대로 두고 없는 것만 추가) / overwrite(같은 항목은 파일 내용으로 덮어쓰기).
    어느 쪽이든 지우지는 않고, 바꾸기 전에 지금 파일을 backups 폴더에 복사해 둬요."""
    d = p.get("data")
    if not isinstance(d, dict) or d.get("app") != "LocalAI-Studio" or d.get("kind") != "backup":
        return {"error": "이 프로그램의 백업 파일이 아니에요."}
    if len(json.dumps(d, ensure_ascii=False)) > BACKUP_MAX:
        return {"error": "백업 파일이 너무 커요."}
    over = p.get("mode") == "overwrite"
    with _PLOCK:
        snap = ROOT / "backups" / ("before-restore-" + time.strftime("%Y%m%d-%H%M%S"))
        snap.mkdir(parents=True, exist_ok=True)
        for f in (PROMPTS_FILE, GAL_FILE, LORA_USER, CHATS_FILE):
            if f.is_file():
                shutil.copy2(f, snap / f.name)
        wd = ROOT / "wildcards"
        if wd.is_dir():
            shutil.copytree(wd, snap / "wildcards", dirs_exist_ok=True)
        n = {"prompts": 0, "favs": 0, "lora_user": 0, "wildcards": 0, "chats": 0}
        # 보관함
        items = prompts_load()
        have = {x.get("id"): i for i, x in enumerate(items)}
        for it in d.get("prompts") or []:
            if not isinstance(it, dict) or not str(it.get("text") or "").strip():
                continue
            c = {"id": str(it.get("id") or uuid.uuid4().hex[:8])[:40], "name": str(it.get("name") or "")[:60] or str(it["text"])[:30],
                 "text": str(it["text"])[:8000], "negative": str(it.get("negative") or "")[:4000],
                 "tags": [str(t).strip()[:20] for t in (it.get("tags") or []) if str(t).strip()][:8]}
            if c["id"] in have:
                if over:
                    items[have[c["id"]]] = c
                    n["prompts"] += 1
            else:
                items.append(c)
                have[c["id"]] = len(items) - 1
                n["prompts"] += 1
        if n["prompts"]:
            PROMPTS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        # 즐겨찾기(합치기만)
        fav = gal_favs()
        new = {str(x) for x in (d.get("favs") or []) if isinstance(x, str) and x.split("/")[0] in OUT_SUB.values() and len(x) < 300} - fav
        if new:
            GAL_FILE.write_text(json.dumps({"favs": sorted(fav | new)}, ensure_ascii=False), encoding="utf-8")
            n["favs"] = len(new)
        # LoRA 내 정보
        lu = lora_user()
        for name, u in (d.get("lora_user") or {}).items():
            if not isinstance(u, dict) or not isinstance(name, str):
                continue
            tr = [str(w).strip()[:60] for w in (u.get("trigger") or []) if str(w).strip()][:30]
            kd = u.get("kind") if u.get("kind") in modelinfo.KINDS else ""
            cur = lu.get(name) or {}
            if over:
                cur = {"trigger": tr, "kind": kd}
            else:
                cur = {"trigger": cur.get("trigger") or tr, "kind": cur.get("kind") or kd}
            if (cur.get("trigger") or cur.get("kind")) and cur != lu.get(name):
                lu[name] = cur
                n["lora_user"] += 1
        if n["lora_user"]:
            LORA_USER.write_text(json.dumps(lu, ensure_ascii=False, indent=1), encoding="utf-8")
        n["chats"] = chats_import(d.get("chats"), over)
        # 와일드카드
        for name, text in (d.get("wildcards") or {}).items():
            if not isinstance(name, str) or not WC_NAME.match(name) or ".." in name or not isinstance(text, str):
                continue
            f = wd / (name + ".txt")
            if f.exists() and not over:
                continue
            wd.mkdir(parents=True, exist_ok=True)
            f.write_text(text[:200000].replace("\r\n", "\n"), encoding="utf-8")
            n["wildcards"] += 1
    return {"ok": True, "counts": n, "saved_to": str(snap)}


# ───────────────────────── 대화 목록 (여러 대화를 파일에 저장) ─────────────────────────
CHATS_FILE = ROOT / "chats.json"
_CLOCK = threading.Lock()
CHAT_MAX_MSGS, CHAT_MAX_BYTES = 2000, 60 * 1024 * 1024


def chats_load():
    try:
        d = json.loads(CHATS_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def chats_write(items):
    tmp = CHATS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CHATS_FILE)


def _chat_msgs(raw):
    out = []
    for m in (raw or [])[-CHAT_MAX_MSGS:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        c = str(m.get("content") or "")[:200000]
        imgs = [i for i in (m.get("images") or []) if isinstance(i, str) and i.startswith("data:image/") and len(i) < 3_000_000][:4]
        if not c.strip() and not imgs:
            continue
        out.append({"role": m["role"], "content": c, **({"images": imgs} if imgs else {})})
    return out


def chats_list(q=""):
    q = (q or "").strip().lower()
    rows = []
    for c in chats_load():
        msgs = c.get("msgs") or []
        hit = ""
        if q:
            if q in str(c.get("title", "")).lower():
                hit = ""
            else:
                m = next((m for m in msgs if q in str(m.get("content", "")).lower()), None)
                if not m:
                    continue
                t, i = str(m["content"]), str(m["content"]).lower().find(q)
                hit = ("…" if i > 20 else "") + t[max(0, i - 20): i + 50].replace("\n", " ")
        last = next((str(m.get("content", "")) for m in reversed(msgs) if m.get("content")), "")
        rows.append({"id": c.get("id"), "title": c.get("title") or "새 대화", "updated": c.get("updated", 0), "n": len(msgs),
                     "preview": hit or last[:60].replace("\n", " ")})
    rows.sort(key=lambda r: r["updated"], reverse=True)
    return {"items": rows}


def chats_get(cid):
    c = next((c for c in chats_load() if c.get("id") == cid), None)
    return c or {"error": "대화를 찾을 수 없어요."}


def chats_save(p):
    msgs = _chat_msgs(p.get("msgs"))
    if not msgs:
        return {"error": "저장할 내용이 없어요."}
    cid = re.sub(r"[^0-9a-f]", "", str(p.get("id") or ""))[:16]
    with _CLOCK:
        items = chats_load()
        cur = next((c for c in items if cid and c.get("id") == cid), None)
        if cur is None:
            cur = {"id": uuid.uuid4().hex[:12], "created": int(time.time()), "title": "", "title_custom": False}
            items.append(cur)
        first = next((m["content"] for m in msgs if m["role"] == "user" and m["content"].strip()), "") or msgs[0]["content"]
        if not cur.get("title_custom"):
            cur["title"] = re.sub(r"\s+", " ", first).strip()[:30] or "새 대화"
        cur.update(updated=round(time.time(), 3), msgs=msgs, model=str(p.get("model") or "")[:120], sys=str(p.get("sys") or "")[:20000], persona=str(p.get("persona") or "")[:60])
        if sum(len(json.dumps(c, ensure_ascii=False)) for c in items) > CHAT_MAX_BYTES:
            return {"error": "저장된 대화가 너무 많아요. 오래된 대화를 지워 주세요."}
        chats_write(items)
    return {"ok": True, "id": cur["id"], "title": cur["title"], "updated": cur["updated"]}


def chats_rename(p):
    t = re.sub(r"\s+", " ", str(p.get("title") or "")).strip()[:60]
    with _CLOCK:
        items = chats_load()
        c = next((c for c in items if c.get("id") == p.get("id")), None)
        if not c:
            return {"error": "대화를 찾을 수 없어요."}
        c["title"], c["title_custom"] = t or "새 대화", bool(t)
        chats_write(items)
    return {"ok": True, "title": c["title"]}


def chats_delete(p):
    ids = {str(i) for i in (p.get("ids") or [])}
    with _CLOCK:
        items = chats_load()
        keep = [c for c in items if c.get("id") not in ids]
        if len(keep) != len(items):
            chats_write(keep)
    return {"ok": True, "deleted": len(items) - len(keep)}


def chats_import(items_in, over):
    """백업에서 대화를 합쳐요(같은 id 는 더 최근에 바뀐 쪽을 남기고, overwrite 면 파일 쪽으로 덮어써요). 지우지는 않아요."""
    n = 0
    with _CLOCK:
        items = chats_load()
        by = {c.get("id"): c for c in items}
        for c in items_in or []:
            if not isinstance(c, dict) or not re.fullmatch(r"[0-9a-f]{1,16}", str(c.get("id") or "")):
                continue
            msgs = _chat_msgs(c.get("msgs"))
            if not msgs:
                continue
            new = {"id": c["id"], "created": int(c.get("created") or 0), "updated": float(c.get("updated") or 0), "title": str(c.get("title") or "새 대화")[:60],
                   "title_custom": bool(c.get("title_custom")), "msgs": msgs, "model": str(c.get("model") or "")[:120],
                   "sys": str(c.get("sys") or "")[:20000], "persona": str(c.get("persona") or "")[:60]}
            old = by.get(c["id"])
            if old is None:
                items.append(new)
                by[c["id"]] = new
                n += 1
            elif over or new["updated"] > float(old.get("updated") or 0):
                old.clear()
                old.update(new)
                n += 1
        if n:
            chats_write(items)
    return n


# ───────────────────────── 모델 설치 ─────────────────────────
def add_task(label, **kw):
    t = dict(id=uuid.uuid4().hex[:8], label=label, state="queued", msg="", done=0, total=0, **kw)
    TASKS.append(t)
    return t


class TaskCancelled(Exception):
    pass


def part_of(t):
    """파일 받기 작업이 임시로 받아 두는 파일(.part) 위치."""
    return MODELS / t["dir"] / (hashlib.sha1(t["url"].encode()).hexdigest()[:12] + ".part")


def cancel_task(tid):
    """받기·설치 작업 취소. 기다리는 중이면 바로 취소하고, 받는 중이면 다음 조각에서 멈춰요. 이 작업이 받던 임시 파일(.part)만 지우고 완성된 모델은 건드리지 않아요."""
    t = next((x for x in TASKS if x["id"] == tid), None)
    if not t:
        return {"error": "작업을 찾지 못했어요."}
    if t["state"] not in ("queued", "running"):
        return {"error": "이미 끝난 작업이에요."}
    if t.get("kind") not in ("file", "ollama"):
        return {"error": "이 작업은 취소할 수 없어요."}
    t["cancel"] = True
    if t["state"] == "queued":
        t["state"], t["msg"] = "cancelled", "취소했어요"
        _drop_part(t)
    return {"ok": True}


def _drop_part(t):
    if t.get("kind") != "file":
        return
    try:
        pt = part_of(t)
        if pt.is_file():
            pt.unlink()
    except OSError as e:
        log("[임시 파일 삭제 실패]", repr(e))


def pull(t):
    body = json.dumps({"name": t["model"], "model": t["model"], "stream": True}).encode()
    req = urllib.request.Request(OLLAMA + "/api/pull", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=7200) as r:
        for line in r:
            if t.get("cancel"):
                raise TaskCancelled()
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
                if t.get("cancel"):
                    raise TaskCancelled()
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
            if t.get("cancel"):
                raise TaskCancelled()
            pull(t) if t["kind"] == "ollama" else sam_run_install(t) if t["kind"] == "sam" else rmbg_run_install(t) if t["kind"] == "rmbg" else download(t)
            t["state"], t["msg"] = "done", t["msg"] if t["msg"] == "이미 설치되어 있어요" else "완료"
        except TaskCancelled:
            _drop_part(t)
            t["state"], t["msg"] = "cancelled", "취소했어요" + (" (받던 임시 파일은 지웠어요)" if t.get("kind") == "file" else "")
        except Exception as e:
            t["state"], t["msg"] = "error", str(e)
            log("[설치 오류]", t["label"], t["msg"])


def cat_name(x):
    """카탈로그 파일이 저장될 이름 (이름을 바꿔 저장해야 하는 파일은 name 이 있어요)."""
    return x.get("name") or Path(urllib.parse.urlparse(x["url"]).path).name


def img_installed(m):
    return all((MODELS / x["dir"] / cat_name(x)).exists() for x in m["files"])


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
                add_task(f'{m["name"]} ({cat_name(x)})',
                         kind="file", url=x["url"], dir=x["dir"], name=x.get("name"))
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
    try: _LC["key"] = None   # 설정이 바뀌면 목록 캐시도 다시 만들어요
    except NameError: pass
    SETTINGS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass


PREF_DEF = {"chat_keep_alive": "5m", "speed_boost": True, "ack": False, "thumb_cache_mb": 500, "image_keep_alive": "30m"}
PREF_THUMB = (200, 500, 1000, 2000)
PREF_KEEP = ("0", "5m", "30m", "2h", "-1")


def prefs():
    d = settings()
    out = dict(PREF_DEF)
    if d.get("chat_keep_alive") in PREF_KEEP:
        out["chat_keep_alive"] = d["chat_keep_alive"]
    out["speed_boost"] = bool(d.get("speed_boost", True))
    out["ack"] = bool(d.get("ack"))
    out["thumb_cache_mb"] = d["thumb_cache_mb"] if d.get("thumb_cache_mb") in PREF_THUMB else 500
    out["image_keep_alive"] = d["image_keep_alive"] if d.get("image_keep_alive") in IMG_KEEP else "30m"
    return out


def set_prefs(p):
    d = settings()
    sweep_after = False
    if "chat_keep_alive" in p:
        if p["chat_keep_alive"] not in PREF_KEEP:
            return {"error": "허용되지 않는 값이에요."}
        d["chat_keep_alive"] = p["chat_keep_alive"]
    if "speed_boost" in p:
        d["speed_boost"] = bool(p["speed_boost"])
    if "image_keep_alive" in p:
        if p["image_keep_alive"] not in IMG_KEEP:
            return {"error": "허용되지 않는 값이에요."}
        d["image_keep_alive"] = p["image_keep_alive"]
    if "thumb_cache_mb" in p:
        if p["thumb_cache_mb"] not in PREF_THUMB:
            return {"error": "허용되지 않는 값이에요."}
        d["thumb_cache_mb"] = p["thumb_cache_mb"]
        sweep_after = True
    if p.get("ack") is True:
        d["ack"] = True
    save_settings(d)
    if sweep_after:
        thumb_sweep_bg()
    return {"ok": True, "prefs": prefs()}


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
def _lp(p):
    """윈도우의 260자 경로 제한을 넘는 깊은 폴더도 읽도록 \\\\?\\ 접두를 붙여요(안 그러면 그런 파일이 조용히 빠져서 용량이 적게 나와요)."""
    p = os.path.abspath(str(p))
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        p = "\\\\?\\UNC\\" + p[2:] if p.startswith("\\\\") else "\\\\?\\" + p
    return p


def _plain(p):
    p = str(p)
    if p.startswith("\\\\?\\UNC\\"):
        return "\\\\" + p[8:]
    return p[4:] if p.startswith("\\\\?\\") else p


def dir_size(p, skip=()):
    """폴더 전체 크기(파일 속성의 '크기'와 같은 기준 — 디스크에서 차지하는 크기가 아니에요).
    심볼릭 링크·정션은 따라가지 않아요(탐색기도 그래요). skip 에 든 폴더는 빼요."""
    sk = {os.path.normcase(os.path.abspath(str(x))) for x in skip}
    total = 0
    stack = [_lp(p)]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            if os.path.normcase(_plain(e.path)) in sk:
                                continue
                            if getattr(e.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400:      # 정션 등 재분석 지점
                                continue
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


# ───────────────────────── 바깥 캐시를 프로그램 폴더 안으로 ─────────────────────────
CACHE_IN = ROOT / "engine" / "cache"
CACHE_ENV = ("HF_HUB_CACHE", "TORCH_HOME", "PIP_CACHE_DIR")
_OURS = {"HF_HUB_CACHE": str(CACHE_IN / "huggingface" / "hub"), "TORCH_HOME": str(CACHE_IN / "torch"), "PIP_CACHE_DIR": str(CACHE_IN / "pip")}
# 스튜디오가 바꾸기 전 값. 다시 시작하면 이전 스튜디오가 정한 값이 환경에 그대로 넘어오므로, 우리 위치와 같으면 '원래 없던 것'으로 봐요
ORIG_ENV = {k: (None if os.environ.get(k) == _OURS.get(k) else os.environ.get(k)) for k in CACHE_ENV + ("HF_HOME",)}
CACHE_JOB = {"state": "", "msg": ""}


_CACHE_DST = [("hf", "", "HF_HUB_CACHE", None, CACHE_IN / "huggingface" / "hub"), ("torch", "", "TORCH_HOME", None, CACHE_IN / "torch"), ("pip", "", "PIP_CACHE_DIR", None, CACHE_IN / "pip")]


def cache_map():
    """(키, 이름, 환경 변수, 원래 위치, 옮길 위치). 원래 위치는 사용자의 환경 변수·윈도우 기본값을 따라요."""
    ours = {env: str(dst) for _k, _l, env, _s, dst in _CACHE_DST}
    o = {k: (ORIG_ENV.get(k) if os.environ.get(k) == ours.get(k) else os.environ.get(k)) for k in CACHE_ENV + ("HF_HOME",)}      # 우리가 바꾼 값이면 원래 값을 써요
    home = Path.home()
    la = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else None
    hf = Path(o["HF_HUB_CACHE"]) if o.get("HF_HUB_CACHE") else (Path(o["HF_HOME"]) / "hub" if o.get("HF_HOME") else home / ".cache" / "huggingface" / "hub")
    tc = Path(o["TORCH_HOME"]) if o.get("TORCH_HOME") else home / ".cache" / "torch"
    pp = Path(o["PIP_CACHE_DIR"]) if o.get("PIP_CACHE_DIR") else ((la / "pip" / "Cache") if la else home / ".cache" / "pip")
    return [("hf", "HuggingFace 모델 캐시", "HF_HUB_CACHE", hf, CACHE_IN / "huggingface" / "hub"),
            ("torch", "PyTorch 캐시", "TORCH_HOME", tc, CACHE_IN / "torch"),
            ("pip", "pip 설치 캐시", "PIP_CACHE_DIR", pp, CACHE_IN / "pip")]


def cache_in_on():
    return bool(settings().get("cache_in"))


def apply_cache_env():
    """켜져 있으면 이 프로그램이 띄우는 프로그램(ComfyUI·pip 등)이 캐시를 프로그램 폴더 안에 쌓게 해요. 꺼져 있으면 원래대로."""
    on = cache_in_on()
    for _k, _l, env, _src, dst in cache_map():
        if os.environ.get(env) != str(dst):
            ORIG_ENV[env] = os.environ.get(env)
        if on:
            dst.mkdir(parents=True, exist_ok=True)
            os.environ[env] = str(dst)
        elif ORIG_ENV.get(env) is None:
            os.environ.pop(env, None)
        else:
            os.environ[env] = ORIG_ENV[env]


def cache_status():
    items = []
    for k, label, env, src, dst in cache_map():
        items.append({"key": k, "label": label, "src": str(src), "dst": str(dst), "src_size": dir_size(src) if src.is_dir() else 0, "dst_size": dir_size(dst) if dst.is_dir() else 0})
    return {"on": cache_in_on(), "items": items, "state": CACHE_JOB["state"], "msg": CACHE_JOB["msg"], "root": str(CACHE_IN)}


def cache_set(on):
    d = settings()
    d["cache_in"] = bool(on)
    save_settings(d)
    apply_cache_env()
    return {"ok": True, "status": cache_status(), "restart": True}


def _cache_move_run():
    J = CACHE_JOB
    moved = 0
    left = []
    try:
        for k, label, env, src, dst in cache_map():
            if not src.is_dir() or _under(src, ROOT) or os.path.normcase(str(src)) == os.path.normcase(str(dst)):
                continue
            J["msg"] = f"{label} 옮기는 중…"
            before = dir_size(src)
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copytree(_lp(src), _lp(dst), symlinks=True, dirs_exist_ok=True, copy_function=shutil.copy2)
            after = dir_size(dst)
            if after < before:
                raise RuntimeError(f"{label}: 복사한 크기가 원본보다 작아요(원본 {before}바이트, 복사본 {after}바이트). 원본은 그대로 뒀어요.")
            _rm_tree(src)
            if src.exists() and any(src.iterdir()):
                left.append(label)
            moved += before
        J["state"], J["msg"] = "done", f"{moved >> 20}MB 를 옮겼어요." + (f" (다른 프로그램이 쓰고 있어서 일부가 남았어요: {', '.join(left)})" if left else "") + " 적용하려면 프로그램을 다시 시작해 주세요."
    except Exception as e:  # noqa: BLE001
        J["state"], J["msg"] = "error", f"옮기지 못했어요: {e}"
        log("[캐시 옮기기 오류]", repr(e))


def cache_move():
    if CACHE_JOB["state"] == "running":
        return {"ok": True}
    if busy_count():
        return {"error": "작업이 진행 중일 때는 옮기지 않아요. 끝난 뒤에 다시 눌러 주세요."}
    cache_set(True)
    CACHE_JOB.update(state="running", msg="시작해요…")
    threading.Thread(target=_cache_move_run, daemon=True).start()
    return {"ok": True}


def _ext_cache_dirs():
    """프로그램 폴더 밖에 있는 큰 캐시들의 실제 위치(환경 변수와 윈도우 기본 위치를 따라가요)."""
    home = Path.home()
    la = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else None
    cm = {k: src for k, _l, _e, src, _d in cache_map()}
    out = [("o_default", "별도로 설치한 Ollama의 모델 폴더", home / ".ollama", "이 프로그램과 따로 설치한 Ollama가 같은 모델을 한 번 더 받아 둔 경우예요. 쓰지 않으면 직접 지워도 돼요.", None),
           ("x_hf", "HuggingFace 모델 캐시", cm["hf"], "다른 프로그램(확장 노드 등)이 받아 둔 모델이에요. 지워도 다음에 필요할 때 다시 받아요. 로그인 정보는 지우지 않아요.", "x_hf"),
           ("x_torch", "PyTorch 캐시", cm["torch"], "지워도 다음에 필요할 때 다시 받아요.", "x_torch")]
    pips = [cm["pip"], home / ".cache" / "pip"]
    seen = set()
    for i, pp in enumerate(x for x in pips if x and str(x) not in seen and not seen.add(str(x))):
        out.append(("x_pip" if i == 0 else "x_pip2", "pip 설치 캐시", pp, "파이썬 부품을 받을 때 쌓인 캐시예요. 지워도 안전해요.", "x_pip" if i == 0 else "x_pip2"))
    if la:
        out.append(("x_uv", "uv 캐시", la / "uv" / "cache", "음성 모델 환경을 만들 때 쌓인 캐시예요. 지워도 안전해요.", "x_uv"))
    return out


def disk_paths():
    """항목 key → (이름, 폴더, 설명, 정리 방법, 건너뛸 폴더, 프로그램 폴더 안인지). 용량 점검과 [폴더 열기]가 같은 목록을 써요."""
    rows = []
    mf = [str(MODELS / d) for d in sorted(FOLDERS)]
    for d in sorted(FOLDERS):
        rows.append(("m_" + d, "모델: " + d, MODELS / d, "필요 없는 파일은 아래 목록이나 '설치와 모델'의 설치된 파일에서 지울 수 있어요.", None, ()))
    rows.append(("m_other", "모델: 그 밖의 폴더 (얼굴 교체·감지 모델 등)", MODELS, "위 목록에 없는 모델 폴더예요(insightface, facerestore_models 등). 확장을 지우면 함께 정리할 수 있어요.", None, tuple(mf)))
    rows += [("llm", "대화 모델 (Ollama)", ROOT / "models" / "llm", "쓰지 않는 대화 모델을 지우면 가장 크게 줄어요.", None, ()),
             ("outputs", "결과물 (outputs)", OUT, "직접 만든 결과물이라 자동으로 지우지 않아요. 필요 없는 건 폴더에서 직접 지워 주세요.", None, ()),
             ("temp", "임시 미리보기 (ComfyUI temp)", COMFY / "temp", "지워도 안전해요.", "temp", ()),
             ("input", "임시 입력 이미지 (ComfyUI input)", COMFY / "input", "이 프로그램이 만든 hub_*.png 만 지워요.", "input", ()),
             ("backup", "업데이트 되돌리기용 백업", ROOT / "backup", "가장 최근 1개만 남기고 지워요.", "backup", ()),
             ("logs", "로그", LOGS, "지워도 안전해요.", "logs", ()),
             ("cache", "작업용 캐시 (이 프로그램 폴더의 cache)", ROOT / "cache", "갤러리 미리보기, 내려받다 만 확장, 음성 임시 파일이에요. 지워도 다시 만들어져요.", "cache", ()),
             ("cache_in", "옮겨 둔 바깥 캐시 (engine\\cache)", CACHE_IN, "HuggingFace·PyTorch·pip 캐시를 이 폴더에 모아 둔 곳이에요. 지워도 다음에 필요할 때 다시 받아요.", "cache_in", ()),
             ("tts_env", "음성 모델 환경 (TTS)", ROOT / "engine" / "tts", "음성 만들기용 모델 엔진이에요. [설치한 확장·부품 관리]에서 지울 수 있어요.", None, ()),
             ("comfy_engine", "ComfyUI 엔진 (python_embeded)", HOME / "python_embeded", "엔진 본체라 지우면 안 돼요.", None, ()),
             ("comfy_app", "ComfyUI 프로그램·확장 (custom_nodes 포함)", COMFY, "엔진 본체예요. 확장은 [설치한 확장·부품 관리]에서 하나씩 지울 수 있어요.", None,
              (str(MODELS), str(COMFY / "temp"), str(COMFY / "input"), str(COMFY / "output"))),
             ("comfy_out", "ComfyUI 자체 output 폴더", COMFY / "output", "이 프로그램은 쓰지 않는 폴더예요. 비어 있지 않다면 ComfyUI 화면을 따로 쓰고 계신 거예요.", None, ()),
             ("ollama_eng", "Ollama 프로그램", ROOT / "engine" / "ollama", "엔진 본체라 지우면 안 돼요.", None, ())]
    return rows


def _under(p, root):
    try:
        Path(os.path.abspath(str(p))).relative_to(Path(os.path.abspath(str(root))))
        return True
    except ValueError:
        return False


def disk_report():
    items = []
    for key, label, path, note, clean, skip in disk_paths():
        path = Path(path)
        if path.exists():
            items.append(dict(key=key, label=label, bytes=dir_size(path, skip), note=note, clean=clean, path=str(path), inside=_under(path, ROOT)))
    root_total = dir_size(ROOT)
    inside = sum(i["bytes"] for i in items if i["inside"])
    rest = max(0, root_total - inside)
    items.append(dict(key="rest", label="그 밖의 파일", bytes=rest, note="엔진 폴더의 나머지(설치 스크립트, 압축 파일, 설정 등)예요.", clean=None, path=str(ROOT), inside=True))
    outside_in_root = [i for i in items if not i["inside"]]      # 프로그램 폴더 밖으로 옮겨 둔 모델 폴더 등
    ext = []
    for key, label, pth, note, clean in _ext_cache_dirs():
        pth = Path(pth)
        if _under(pth, ROOT):           # 프로그램 폴더 안은 위 표에 이미 들어 있어요(두 번 세지 않아요)
            continue
        if pth.exists():
            sz = dir_size(pth)
            if sz or key == "o_default":        # 옮기거나 지워서 빈 폴더만 남은 캐시는 목록에서 빼요
                ext.append(dict(key=key, label=label, bytes=sz, note=note, clean=clean, path=str(pth)))
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
    items.sort(key=lambda x: (x["key"] == "rest", -x["bytes"]))
    try:
        du = shutil.disk_usage(ROOT)
        free, total = du.free, du.total
    except OSError:
        free = total = 0
    return dict(items=items, ext=ext, big=big[:15], dups=dups, parts=parts, free=free, total=total, root=str(ROOT),
                used=root_total, listed=sum(i["bytes"] for i in items if i["inside"]), outside=[i["key"] for i in outside_in_root],
                ext_total=sum(i["bytes"] for i in ext))


def disk_open(key):
    ok = {k: p for k, _l, p, _n, _c, _s in disk_paths()}
    ok.update({k: p for k, _l, p, _n, _c in _ext_cache_dirs()})
    ok["rest"] = ROOT
    p = ok.get(key)
    if not p or not Path(p).exists():
        return {"error": "폴더를 찾을 수 없어요."}
    open_folder(Path(p), None)
    return {"ok": True, "path": str(p)}


TIDY_DAYS = 60


def model_tidy(now=None):
    """지워도 될 만한 모델 파일 후보를 이유와 함께 모아요. 여기서는 아무것도 지우지 않아요(지우기는 화면에서 직접 고른 것만).
    '오래 안 쓴' 기준은 이 프로그램이 기록한 마지막 사용일이에요. 기록이 없는 파일은 지금부터 세기 시작해서(처음 본 날) 바로 후보가 되지 않아요."""
    now = now or time.time()
    cands, seen = {}, {}
    def add(d, f, reason):
        k = (d, f.name)
        c = cands.setdefault(k, dict(dir=d, name=f.name, size=fsize(f), reasons=[]))
        c["reasons"].append(reason)
    with _USED_LOCK:
        used = used_load(); dirty = False
        for d in sorted(FOLDERS):
            base = MODELS / d
            if not base.is_dir():
                continue
            for f in sorted(base.iterdir()):
                if not f.is_file():
                    continue
                if f.suffix == ".part":
                    add(d, f, "받다 만 파일이에요")
                elif f.suffix.lower() in EXT:
                    sz = fsize(f)
                    if sz > (50 << 20):
                        seen.setdefault(sz, []).append((d, f))
                    key = d + "/" + f.name
                    if key not in used:
                        used[key] = now; dirty = True        # 처음 본 날부터 세요
                    elif sz > (500 << 20) and now - used[key] > TIDY_DAYS * 86400:
                        add(d, f, f"{int((now - used[key]) // 86400)}일 동안 쓰지 않았어요")
        if dirty:
            used_save(used)
    for sz, fs in seen.items():
        if len(fs) < 2:
            continue
        g = {}
        for d, f in fs:
            g.setdefault(quick_sig(f), []).append((d, f))
        for sig, v in g.items():
            if not sig or len(v) < 2:
                continue
            for d, f in v[1:]:       # 첫 번째는 남기고 나머지를 후보로
                add(d, f, f"같은 파일이 {v[0][0]}/{v[0][1].name} 에도 있어요")
    items = sorted(cands.values(), key=lambda x: -x["size"])
    return dict(items=items, total=sum(i["size"] for i in items))


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
        for d in olds[1:]:
            freed += dir_size(str(d))
            shutil.rmtree(d, ignore_errors=True)
    elif what == "cache":
        if any(t.get("state") in ("running", "queued") for t in TASKS) or busy_count():
            return {"error": "작업이 진행 중일 때는 캐시를 지우지 않아요. 끝난 뒤에 다시 눌러 주세요."}
        for sub in ("thumbs", "nodes", "tts", "vmix"):
            d = ROOT / "cache" / sub
            for f in (d.rglob("*") if d.is_dir() else []):
                if f.is_file():
                    rm(f)
        rm(ROOT / "cache" / "extension-node-map.json")
    elif what == "cache_in":
        if busy_count():
            return {"error": "작업이 진행 중일 때는 지우지 않아요. 끝난 뒤에 다시 눌러 주세요."}
        if CACHE_JOB["state"] == "running":
            return {"error": "캐시를 옮기는 중이에요."}
        freed += dir_size(CACHE_IN) if CACHE_IN.is_dir() else 0
        for ch in (list(CACHE_IN.iterdir()) if CACHE_IN.is_dir() else []):
            for sub in (list(ch.iterdir()) if ch.is_dir() else []):
                try:
                    shutil.rmtree(sub) if sub.is_dir() and not sub.is_symlink() else sub.unlink()
                except OSError:
                    pass
        freed -= dir_size(CACHE_IN) if CACHE_IN.is_dir() else 0
    elif what in ("x_hf", "x_torch", "x_pip", "x_pip2", "x_uv"):
        if any(t.get("state") in ("running", "queued") for t in TASKS) or busy_count():
            return {"error": "작업이 진행 중일 때는 지우지 않아요. 끝난 뒤에 다시 눌러 주세요."}
        tgt = next((Path(p) for k, _l, p, _n, _c in _ext_cache_dirs() if k == what), None)
        if not tgt or not tgt.is_dir():
            return {"error": "폴더를 찾을 수 없어요."}
        freed += dir_size(tgt)
        for ch in list(tgt.iterdir()):
            try:
                shutil.rmtree(ch) if ch.is_dir() and not ch.is_symlink() else ch.unlink()
            except OSError:
                pass
        freed -= dir_size(tgt)
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
BOOT = uuid.uuid4().hex[:8]


_ALV = {}


def alive_cached(url, ttl=2.0):
    """화면이 몇 초마다 묻는 '엔진이 켜져 있나' 확인을 잠깐 기억해요(엔진이 꺼져 있으면 매번 기다리게 되니까요)."""
    now = time.time()
    c = _ALV.get(url)
    if c and now - c[0] < ttl:
        return c[1]
    v = alive(url)
    _ALV[url] = (now, v)
    return v


def status(fresh=False):
    al = alive if fresh else alive_cached
    return {"boot": BOOT, "ollama": al(OLLAMA + "/api/version"), "comfy": al(CUI + "/system_stats"), "gpu": GPU, "gpu_live": gpu_live(), "version": VERSION}


FAMILY_CHOICES = ("sd15", "sdxl", "sd3", "flux", "krea2", "chroma", "qwen", "hidream", "lumina", "hidden")


def model_family(folder, name):
    """(계열, 올인원 여부, 판단 방법). 사용자가 직접 지정한 값이 있으면 그걸 써요."""
    d = modelinfo.detect(mpath(folder, name))
    ov = settings().get("families", {}).get(f"{folder}/{name}")
    if ov in FAMILY_CHOICES:
        return ov, d["all_in_one"], "manual"
    return d["family"], d["all_in_one"], d["how"]


def set_family(p):
    folder, name, fam = p.get("folder"), str(p.get("name", "")), p.get("family") or "auto"
    if folder not in ("checkpoints", "diffusion_models") or Path(name).name != name or not mpath(folder, name).is_file():
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
        if fam == "hidden" or n in music_models():      # 음악 모델은 그림 모델 목록에 섞지 않아요
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
        elif fam in ("hidden", "qwen", "sd15", "sdxl", "sd3", "hidream", "lumina") or (fam == "unknown" and "qwen" in n.lower()):
            continue
        else:
            (chroma if fam == "chroma" or (fam == "unknown" and "chroma" in n.lower()) else flux).append(n)
    return sdxl, flux, chroma, krea2, info


_LC = {"key": None, "v": None}


def lists_key():
    """모델 폴더들이 바뀌었는지 알아보는 값(폴더 안 파일을 넣거나 빼면 폴더 수정 시각이 바뀌어요). 파일 하나하나는 열어 보지 않아요."""
    parts = [_CAPS["t"]]
    try:
        parts.append(MODELS.stat().st_mtime_ns)
        for e in os.scandir(MODELS):
            if e.is_dir():
                parts.append((e.name, e.stat().st_mtime_ns))
        wc = ROOT / "wildcards"
        parts.append(wc.stat().st_mtime_ns if wc.is_dir() else 0)
    except OSError:
        return None
    return tuple(parts)


def lists():
    """화면의 모델·LoRA 목록. 모델 폴더가 그대로면 지난번 결과를 다시 써요(탭을 누를 때마다 폴더를 훑지 않게). 대화 모델 목록만 매번 새로 물어요."""
    key = lists_key()
    if key is None or key != _LC["key"] or _LC["v"] is None:
        _LC["v"] = _lists_build()
        _LC["key"] = lists_key()      # 만드는 중에 엔진 기능 조회(caps)가 갱신될 수 있어서 끝난 뒤의 값으로 기억해요
    out = dict(_LC["v"])
    out["llm"] = llms()
    return out


def _lists_build():
    wc = ROOT / "wildcards"
    sdxl, flux, chroma, krea2, info = sorted_models()
    fp, kp = flux_parts(), krea2_parts()      # 폴더를 한 번씩만 훑어요
    ox = other_models()
    ox_ready = {}
    for k in OX_FAMS:
        pr = ox_parts(k)
        ox_ready[k] = True if k == "sd35" else bool(all(pr["te"].values()) and pr["vae"])
    loras = files("loras")
    return {"llm": llms(), "checkpoints": sdxl, "loras": loras, "families": info,
            "lora_info": {n: (lora_user().get(n) or {}).get("family") or modelinfo.lora_family(MODELS / "loras" / n)["family"] for n in loras}, "lora_kind": lora_kinds(),
            "upscalers": files("upscale_models"), "controlnets": files("controlnet"),
            "vaes": files("vae"), "text_encoders": files("text_encoders"), "diffusion": files("diffusion_models"),
            "fluxmodels": flux, "chromamodels": chroma, "krea2models": krea2, "anymodels": sdxl + flux + chroma + krea2,
            "flux_ready": bool(fp["t5"] and fp["clip_l"] and fp["vae"]),
            "chroma_ready": bool(fp["t5"] and fp["vae"]),
            "krea2_ready": bool(kp["te"] and kp["vae"]), "oxmodels": ox, "ox_ready": ox_ready,
            "musicmodels": music_models(), "music_nodes": all(has_node(n) for n in MUSIC_NODES), "k2control": k2_control_loras(), "k2c_nodes": all(has_node(n) for n in K2C_NODES),
            "wanmodels": wan_models(), "wan_ready": bool(wan_parts()["te"] and wan_parts()["vae"]), "wan14": wan14_state(),
            "wildcards": sorted(p.stem for p in wc.glob("*.txt")) if wc.is_dir() else [],
            "qwen": bool(find("diffusion_models", "qwen_image_edit") and find("text_encoders", "qwen_2.5_vl")
                         and find("vae", "qwen_image_vae"))}


def catalog():
    have = set(llms())

    ok = img_installed
    return {"llm": [{**m, "installed": m["ollama"] in have or m["ollama"] + ":latest" in have} for m in CATALOG["llm"]],
            "image": [{**m, "installed": ok(m)} for m in CATALOG["image"]]}


# ───────────────────────── 내 PC 점검 (기능별로 빠진 부품 찾기) ─────────────────────────
def _row(label, ok, detail="", fix=None, fixlabel="", opt=False):
    """ok: True 정상 / False 빠짐 / None 확인 못 함. opt=True 면 없어도 큰 문제는 아니에요."""
    return {"label": label, "ok": ok, "detail": detail, "fix": fix, "fixlabel": fixlabel, "opt": opt}


def selfcheck():
    st = status(fresh=True)      # 점검 결과는 잠깐 기억해 둔 값이 아니라 지금 상태로
    c = caps()
    comfy_up, nodes = bool(st["comfy"]), c["nodes"]
    try:
        L = lists()
    except Exception:
        L = {}
    groups = []

    def grp(gid, title, view, rows, note=""):
        bad = any(r["ok"] is False and not r["opt"] for r in rows)
        warn_ = any((r["ok"] is False and r["opt"]) or r["ok"] is None for r in rows)
        groups.append({"id": gid, "title": title, "view": view, "rows": rows, "note": note, "state": "bad" if bad else "warn" if warn_ else "ok"})

    eng = [_row("대화 엔진(Ollama)", bool(st["ollama"]), "" if st["ollama"] else "꺼져 있어요. 아래 [엔진 다시 시작]을 눌러 보세요.", {"a": "restart_all"} if not st["ollama"] else None, "프로그램 다시 시작"),
           _row("이미지 엔진(ComfyUI)", comfy_up, "" if comfy_up else "꺼져 있어요. 켜지는 데 1~2분 걸릴 수 있어요.", {"a": "restart"} if not comfy_up else None, "이미지 엔진 다시 시작"),
           _row("내장 파이썬", PY.exists(), "" if PY.exists() else "프로그램 폴더의 python 폴더가 없어요. 설치를 다시 해야 할 수 있어요.")]
    grp("engines", "엔진", None, eng)
    have_llm = bool(L.get("llm"))
    grp("chat", "대화", "chat", [_row("대화 모델", have_llm, f"{len(L.get('llm') or [])}개 있어요" if have_llm else "설치된 대화 모델이 없어요.", None if have_llm else {"a": "view", "v": "setup"}, "설치와 모델 열기")])
    am = L.get("anymodels") or []
    grp("image", "이미지 만들기", "gen", [_row("그림 모델(체크포인트)", bool(am), f"{len(am)}개 있어요" if am else "그림 모델이 없어요.", None if am else {"a": "view", "v": "setup"}, "설치와 모델 열기"),
                                           _row("확대 모델", bool(L.get("upscalers")), "" if L.get("upscalers") else "없어도 기본 확대로 동작해요.", opt=True)])
    try:
        fp, kp = flux_parts(), krea2_parts()
    except Exception:
        fp, kp = {}, {}
    fix_setup = {"a": "view", "v": "setup"}
    def prow(label, val, miss_msg):
        return _row(label, bool(val), val or miss_msg, None if val else fix_setup, "" if val else "설치와 모델 열기", opt=True)
    grp("flux", "FLUX · Chroma · Krea 2 공용 파일", "gen", [
        prow("FLUX·Chroma 모델 파일", (L.get("fluxmodels") or L.get("chromamodels") or [None])[0], "diffusion_models 폴더(또는 unet 폴더)에 모델이 없어요."),
        prow("T5 텍스트 인코더 (FLUX·Chroma)", fp.get("t5"), "text_encoders(또는 clip) 폴더에 t5xxl 파일이 없어요."),
        prow("CLIP-L 텍스트 인코더 (FLUX)", fp.get("clip_l"), "text_encoders(또는 clip) 폴더에 clip_l 파일이 없어요."),
        prow("VAE (ae.safetensors)", fp.get("vae"), "vae 폴더에 ae.safetensors 가 없어요."),
        prow("Krea 2 텍스트 인코더 (Qwen3-VL)", kp.get("te"), "Krea 2 를 쓸 때만 필요해요."),
        prow("Krea 2 VAE (Qwen Image VAE)", kp.get("vae"), "Krea 2 를 쓸 때만 필요해요.")],
        "FLUX 는 모델·T5·CLIP-L·VAE 가 모두 있어야 하고, Chroma 는 모델·T5·VAE, Krea 2 는 모델·Qwen3-VL·Qwen Image VAE 가 필요해요. 쓰지 않는 계열이 비어 있는 건 괜찮아요.")
    grp("edit", "이미지 편집", "edit", [_row("Qwen 편집 모델 묶음", bool(L.get("qwen")), "" if L.get("qwen") else "편집 모델·텍스트 인코더·VAE 중 빠진 게 있어요.",
                                            None if L.get("qwen") else {"a": "view", "v": "setup"}, "설치와 모델 열기", opt=True)])
    wan_ok = bool(L.get("wan_ready") and L.get("wanmodels"))
    wan14 = L.get("wan14") or {}
    grp("video", "영상 만들기", "vid", [_row("Wan 영상 모델", wan_ok or wan14.get("i2v") or wan14.get("t2v"), "" if wan_ok or wan14.get("i2v") or wan14.get("t2v") else "영상 모델 묶음이 없어요.",
                                               None if wan_ok or wan14.get("i2v") or wan14.get("t2v") else {"a": "view", "v": "setup"}, "설치와 모델 열기", opt=True)])
    mnodes = (None if not comfy_up else bool(L.get("music_nodes")))
    grp("music", "음악 만들기", "music", [_row("음악 노드", mnodes, "이미지 엔진이 꺼져 있어서 확인할 수 없어요." if mnodes is None else "" if mnodes else "이 ComfyUI 가 오래돼서 음악 노드가 없어요. ComfyUI 를 업데이트해 주세요.", opt=True),
                                         _row("ACE-Step 모델", bool(L.get("musicmodels")), "" if L.get("musicmodels") else "음악 모델이 없어요.",
                                              None if L.get("musicmodels") else {"a": "view", "v": "setup"}, "설치와 모델 열기", opt=True)])
    try:
        tts = [t for t in tts_models.status(ROOT) if t["installed"]]
    except Exception:
        tts = []
    grp("tts", "음성 만들기", "tts", [_row("음성 엔진", bool(tts), (", ".join(t["title"] for t in tts)) if tts else "설치된 음성 엔진이 없어요.",
                                           None if tts else {"a": "view", "v": "tts"}, "음성 화면 열기", opt=True)])
    try:
        rm = rmbg_status()
        rm_ok = any(m["installed"] for m in rm["models"].values())
    except Exception:
        rm_ok = False
    grp("rmbg", "배경 지우기", None, [_row("배경 지우기 모델", rm_ok, "" if rm_ok else "처음 쓸 때 화면에서 설치해요.", opt=True)])
    for f in FEATURES:
        need = f.get("needs", {})
        if not need:
            continue
        rows = []
        miss = [n for n in need.get("nodes", []) if nodes and n not in nodes]
        if need.get("nodes"):
            if not comfy_up or not nodes:
                rows.append(_row("필요한 노드", None, "이미지 엔진이 꺼져 있어서 확인할 수 없어요."))
            elif miss:
                rows.append(_row("필요한 노드", False, "빠진 노드: " + ", ".join(miss) + (f" (확장: {need['pack']})" if need.get("pack") else ""),
                                 {"a": "nodes", "missing": miss}, "찾아서 설치"))
            else:
                rows.append(_row("필요한 노드", True, "모두 있어요"))
        for k in need.get("lists", []):
            ok = bool(L.get(k))
            rows.append(_row({"checkpoints": "그림 모델", "anymodels": "그림 모델"}.get(k, k), ok, "" if ok else "모델이 없어요.", None if ok else {"a": "view", "v": "setup"}, "설치와 모델 열기"))
        if f["id"] == "faceswap":
            sw = swap_status()
            if sw["pack"] or _repo_dir(REACTOR_REPO).is_dir():
                dm = [d["pip"] for d in sw["deps_missing"]]
                rows.append(_row("파이썬 부품", not dm, "" if not dm else "빠진 부품: " + ", ".join(dm), {"a": "pymods", "modules": [{"module": d["module"], "pip": d["pip"]} for d in sw["deps_missing"]]} if dm else None, "부품 설치"))
                rows.append(_row("얼굴 교체 모델(inswapper_128)", sw["file"], "" if sw["file"] else "모델 파일이 없어요.", None if sw["file"] else {"a": "swap"}, "모델 받기"))
        grp("feat-" + f["id"], f["title"], "feat:" + f["id"], rows)
    return {"groups": groups, "comfy": comfy_up, "version": VERSION}


# ───────────────────────── 앱 안에서 업데이트 파일 적용 ─────────────────────────
UPD = {"tok": None, "z": None, "man": None, "t": 0.0}
UPD_MAX = 40 << 20


def _upd_open(text):
    """update.bat 을 열어 안의 zip 과 manifest 를 읽어요(코드는 실행하지 않아요)."""
    d = text.encode("utf-8", "ignore") if isinstance(text, str) else bytes(text)
    if len(d) > UPD_MAX:
        raise ValueError("파일이 너무 커요. 로컬 AI 스튜디오 업데이트 파일이 맞는지 확인해 주세요.")
    try:
        m = d.rindex(b"\n::PAYLOAD_BEGIN")
        z = zipfile.ZipFile(io.BytesIO(base64.b64decode(d[d.index(b"\n", m + 1) + 1:])))
        if sum(i.file_size for i in z.infolist()) > 200 << 20:
            raise ValueError("압축을 풀면 너무 커서 받지 않아요.")
        man = json.loads(z.read("manifest.json").decode("utf-8"))
    except ValueError as e:
        if "너무" in str(e):
            raise
        raise ValueError("로컬 AI 스튜디오 업데이트 파일이 아니에요. LocalAI-Studio-update-….bat 파일을 올려 주세요.")
    except Exception:
        raise ValueError("로컬 AI 스튜디오 업데이트 파일이 아니에요. LocalAI-Studio-update-….bat 파일을 올려 주세요.")
    files = man.get("files")
    if man.get("format") != 1 or not isinstance(files, list) or not str(man.get("version") or "").strip() or not any(f.get("path") == "hub/hub.py" for f in files if isinstance(f, dict)):
        raise ValueError("이 스튜디오가 이해하는 업데이트 파일이 아니에요. 더 새 버전이면 update.bat 을 직접 실행해 주세요.")
    return z, man


def _upd_run(z, flags):
    try:
        import updater
    except ImportError:
        raise RuntimeError("설치된 업데이트 적용기(hub\\updater.py)가 없어요. 받은 update.bat 을 직접 실행해 주세요.")
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = updater.main([str(ROOT)] + flags, payload=z, root=ROOT)
    return code, buf.getvalue()


def update_inspect(p):
    try:
        z, man = _upd_open(p.get("text") or "")
        code, log = _upd_run(z, ["--dry-run", "--in-app"] + (["--force"] if p.get("force") else []))
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    tok = uuid.uuid4().hex
    UPD.update(tok=tok, z=z, man=man, t=time.time())
    cur = VERSION
    n = len(re.findall(r"^  (?:추가|교체|합침|유지|삭제)", log, re.M))
    return {"ok": True, "token": tok, "from": cur, "to": str(man["version"]), "notes": [str(x) for x in man.get("notes", [])][:30], "code": code,
            "same": code == 0 and "이미 최신" in log, "older": code == 3, "changes": n, "log": log[-6000:], "busy": busy_count()}


def update_apply(p):
    if not UPD["tok"] or p.get("token") != UPD["tok"] or time.time() - UPD["t"] > 1800:
        return {"error": "업데이트 파일을 다시 올려 주세요."}
    z = UPD["z"]
    try:
        code, log = _upd_run(z, ["--in-app"] + (["--force"] if p.get("force") else []))
    except RuntimeError as e:
        return {"error": str(e)}
    UPD.update(tok=None, z=None, man=None)
    return {"ok": code == 0, "code": code, "log": log[-6000:]}


# ───────────────────────── 캐릭터·스타일 보관함 (프롬프트·LoRA·시드·참고 이미지 묶음) ─────────────────────────
CHARS_DIR = ROOT / "library"
CHARS_FILE = CHARS_DIR / "chars.json"
CHAR_KINDS = ("캐릭터", "스타일", "배경", "기타")
CHAR_IMG = re.compile(r"^[0-9a-f]{8}-\d{1,2}\.png$")
_CLOCK = threading.Lock()


def chars_load():
    try:
        d = json.loads(CHARS_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def char_img_path(name):
    return CHARS_DIR / "img" / name if CHAR_IMG.match(name or "") else None


def _char_clean(p, old, imgs):
    seed = p.get("seed")
    try:
        seed = int(seed) if seed not in (None, "") and int(seed) >= 0 else None
    except (TypeError, ValueError):
        seed = None
    loras = []
    for x in (p.get("loras") or [])[:6]:
        try:
            n, w = (x[0], x[1]) if isinstance(x, (list, tuple)) else (x.get("name"), x.get("weight"))
            if str(n or "").strip():
                loras.append([str(n).strip()[:200], round(clamp(float(w if w is not None else 0.8), -2, 2), 2)])
        except (TypeError, ValueError, AttributeError, IndexError):
            continue
    kind = p.get("kind") if p.get("kind") in CHAR_KINDS else "캐릭터"
    return {"id": old["id"], "name": str(p.get("name") or "").strip()[:60], "kind": kind, "prompt": str(p.get("prompt") or "").strip()[:8000],
            "negative": str(p.get("negative") or "").strip()[:4000], "seed": seed, "loras": loras, "model": str(p.get("model") or "").strip()[:200],
            "note": str(p.get("note") or "").strip()[:500], "refs": imgs, "created": old.get("created") or int(time.time()), "used": old.get("used")}


def chars_api(p):
    """보관함: list / save(id 가 있으면 덮어쓰기) / delete. 참고 이미지는 library\\img 폴더에 PNG 로 저장해요."""
    act = p.get("action")
    with _CLOCK:
        items = chars_load()
        if act == "list":
            return {"items": items, "kinds": list(CHAR_KINDS)}
        if act == "delete":
            gone = [x for x in items if x.get("id") == p.get("id")]
            for g in gone:
                for n in g.get("refs", []):
                    f = char_img_path(n)
                    if f:
                        f.unlink(missing_ok=True)
            items = [x for x in items if x.get("id") != p.get("id")]
        elif act == "use":                      # 이미지 생성·편집 등에 넣을 때 '최근 사용' 시각을 남겨요
            for x in items:
                if x.get("id") == p.get("id"):
                    x["used"] = int(time.time())
        elif act == "dup":                      # 복제: 설정과 참고 이미지를 새 항목으로 복사
            src = next((x for x in items if x.get("id") == p.get("id")), None)
            if not src:
                return {"error": "복제할 항목을 찾지 못했어요."}
            new = dict(src, id=uuid.uuid4().hex[:8], name=(str(src.get("name") or "")[:52] + " (복사)"), created=int(time.time()), used=None, refs=[])
            for i, n in enumerate(src.get("refs", []), 1):
                f = char_img_path(n)
                if f and f.is_file():
                    nn = f"{new['id']}-{i}.png"
                    shutil.copyfile(f, CHARS_DIR / "img" / nn)
                    new["refs"].append(nn)
            items = items + [new]
        elif act == "save":
            if not str(p.get("name") or "").strip():
                return {"error": "이름을 적어 주세요."}
            old = next((x for x in items if x.get("id") == p.get("id")), None) or {"id": uuid.uuid4().hex[:8]}
            cur = set(old.get("refs", []))
            imgs, fresh = [], 0
            for r in (p.get("refs") or [])[:3]:
                if isinstance(r, dict) and r.get("keep") in cur and r["keep"] not in imgs:
                    imgs.append(r["keep"])
                elif isinstance(r, dict) and r.get("data"):
                    try:
                        im = load_img(r["data"])
                    except Exception:
                        return {"error": "참고 이미지를 읽을 수 없어요."}
                    if max(im.size) > 1536:
                        im.thumbnail((1536, 1536), RS.LANCZOS)
                    n = next(f"{old['id']}-{i}.png" for i in range(1, 99) if f"{old['id']}-{i}.png" not in cur and f"{old['id']}-{i}.png" not in imgs)
                    (CHARS_DIR / "img").mkdir(parents=True, exist_ok=True)
                    im.save(CHARS_DIR / "img" / n, "PNG")
                    imgs.append(n)
                    fresh += 1
            for n in cur - set(imgs):
                f = char_img_path(n)
                if f:
                    f.unlink(missing_ok=True)
            it = _char_clean(p, old, imgs)
            items = [x for x in items if x.get("id") != it["id"]] + [it]
        else:
            return {"error": "알 수 없는 동작"}
        CHARS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CHARS_FILE.with_name(CHARS_FILE.name + ".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, CHARS_FILE)
        return {"items": items, "kinds": list(CHAR_KINDS)}


def caps_info():
    c = caps()
    return {"samplers": c["samplers"], "schedulers": c["schedulers"],
            "has": {"canny": "Canny" in c["nodes"], "pag": "PerturbedAttentionGuidance" in c["nodes"],
                    "qwen_plus": "TextEncodeQwenImageEditPlus" in c["nodes"],
                    "controlnet": "ControlNetApplyAdvanced" in c["nodes"]}}


# ───────────────────────── HTTP 서버 ─────────────────────────
def folder_map():
    m = {"outputs": OUT, "logs": LOGS, "root": ROOT, "llm": ROOT / "models" / "llm", "wildcards": ROOT / "wildcards",
         "backup": ROOT / "backup", "tags": ROOT / "tags", "music": OUT / "음악", "tts": OUT / "음성"}
    m.update({k: MODELS / k for k in FOLDERS})
    return m


MEDIA = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".opus": "audio/ogg", ".mp4": "video/mp4", ".webm": "video/webm", ".webp": "image/webp", ".gif": "image/gif"}
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.css": ("app.css", "text/css; charset=utf-8")}
_JSB = {"key": None, "data": b"", "gz": b"", "etag": ""}


def js_bundle():
    """화면 코드는 web/js/ 의 기능별 파일(00-core.js, 10-chat.js …)로 나눠 두고, 브라우저에는 하나로 이어 붙여 보내요(옛 설치의 app.js 하나도 그대로 지원).
    파일이 바뀌지 않았으면 이어 붙인 결과를 다시 만들지 않아요."""
    parts = sorted((WEB / "js").glob("*.js")) if (WEB / "js").is_dir() else []
    if not parts and (WEB / "app.js").is_file():
        parts = [WEB / "app.js"]
    key = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in parts)
    if key != _JSB["key"]:
        import gzip
        data = b"".join(f.read_bytes() for f in parts)
        _JSB.update(key=key, data=data, gz=gzip.compress(data, 6) if len(data) > 1024 else b"",
                    etag='"%x-%x"' % (hash(key) & 0xFFFFFFFF, len(data)))
    return _JSB


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        """브라우저가 연결을 끊어서 생기는 오류(WinError 10053/10054, Broken pipe)는 콘솔에 띄우지 않아요."""
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


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
        try:
            self.wfile.write(b)
        except (ConnectionError, TimeoutError):
            pass        # 브라우저가 응답을 받기 전에 탭을 닫거나 새로고침한 경우 — 정상이라 조용히 넘어가요

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
        CLIENT_SEEN.set()
        u = urllib.parse.urlparse(self.path).path
        if u == "/app.js":
            j = js_bundle()
            if not j["data"]:
                return self.send_json({"error": "not found"}, 404)
            hdr = {"Cache-Control": "no-cache", "ETag": j["etag"], "Vary": "Accept-Encoding"}
            if self.headers.get("If-None-Match") == j["etag"]:
                self.send_response(304)
                for k, v in hdr.items():
                    self.send_header(k, v)
                return self.end_headers()
            data = j["data"]
            if j["gz"] and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                data, hdr["Content-Encoding"] = j["gz"], "gzip"
            return self.send_bytes(data, "text/javascript; charset=utf-8", extra=hdr)
        if u in STATIC:
            return self.send_file(WEB / STATIC[u][0], STATIC[u][1])
        if u.startswith("/out/"):
            fp = out_path(u[5:])
            if fp.suffix.lower() in MEDIA:
                return self.send_media(fp, MEDIA[fp.suffix.lower()])
            return self.send_file(fp, "image/png")
        routes = {"/api/features": features, "/api/status": status, "/api/selfcheck": selfcheck, "/api/lists": lists, "/api/catalog": catalog, "/api/caps": caps_info,
                  "/api/profiles": lambda: PROFILES}
        if u in routes:
            return self.send_json(routes[u]())
        if u == "/api/install":
            return self.send_json([{k: v for k, v in t.items() if k not in ("url", "token")} for t in TASKS[-40:]])
        if u == "/api/sam/status":
            return self.send_json(sam_status())
        if u == "/api/dl/tokens":
            return self.send_json(token_state())
        if u == "/api/prefs":
            return self.send_json(prefs())
        if u == "/api/tts/voices":
            return self.send_json(tts_voices())
        if u == "/api/tts/models":
            return self.send_json(tts_models.status(ROOT))
        if u == "/api/model-tidy":
            return self.send_json(model_tidy())
        if u == "/api/disk":
            return self.send_json(disk_report())
        if u == "/api/faceswap/model":
            return self.send_json(swap_status())
        if u == "/api/cachein":
            return self.send_json(cache_status())
        if u == "/api/parts":
            return self.send_json(parts_list())
        if u == "/api/vmix/list":
            return self.send_json(vmix_list())
        if u == "/api/gallery":
            return self.send_json(gallery(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)))
        if u == "/api/chars/img":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            fp = char_img_path((q.get("f") or [""])[0])
            if not fp or not fp.is_file():
                return self.send_json({"error": "not found"}, 404)
            try:
                if (q.get("t") or [""])[0]:
                    return self.send_bytes(thumb_bytes(fp, 240), "image/jpeg", extra={"Cache-Control": "max-age=3600"})
                return self.send_bytes(fp.read_bytes(), "image/png", extra={"Cache-Control": "max-age=3600"})
            except Exception:
                return self.send_json({"error": "image failed"}, 500)
        if u.startswith("/thumb/"):
            fp = out_path(u[7:])
            if fp.suffix.lower() not in GAL_EXT or fp.suffix.lower() in (".mp4", ".webm") or not fp.is_file():
                return self.send_json({"error": "not found"}, 404)
            try:
                return self.send_bytes(thumb_bytes(fp), "image/jpeg", extra={"Cache-Control": "max-age=3600"})
            except Exception:
                return self.send_json({"error": "thumb failed"}, 500)
        if u == "/api/pymod/status":
            return self.send_json({m: {"state": j["state"], "msg": j["msg"]} for m, j in PYMOD_JOBS.items()})
        if u == "/api/changelog":
            return self.send_json(changelog())
        if u == "/api/nodes/status":
            return self.send_json({r: {"state": j["state"], "msg": j["msg"]} for r, j in NODE_JOBS.items()})
        if u == "/api/app/where":
            return self.send_json(app_where())
        if u == "/api/app/notice":
            return self.send_json(app_notice())
        if u == "/api/queue":
            return self.send_json(queue_view())
        if u == "/api/rmbg/status":
            return self.send_json(rmbg_status())
        if u == "/api/tags":
            return self.send_json(tags_search((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q") or [""])[0]))
        if u == "/api/chats":
            return self.send_json(chats_list((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q") or [""])[0]))
        if u.startswith("/api/chats/"):
            return self.send_json(chats_get(u[11:]))
        if u == "/api/diag/export":
            return self.send_bytes(diag_export(), "application/zip", extra={"Content-Disposition": "attachment; filename*=UTF-8''" + urllib.parse.quote("LocalAI-진단-" + time.strftime("%Y%m%d-%H%M") + ".zip")})
        if u == "/api/backup/export":
            return self.send_json(backup_export())
        if u == "/api/models/cards":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self.send_json(model_cards((qs.get("kind") or ["loras"])[0]))
        if u.startswith("/mprev/"):
            parts = urllib.parse.unquote(u[7:]).split("/")
            f = model_preview(parts[0], parts[1]) if len(parts) == 2 and parts[0] in ("loras", "checkpoints", "diffusion_models") else None
            if not f:
                return self.send_json({"error": "not found"}, 404)
            try:
                return self.send_bytes(thumb_bytes(f), "image/jpeg", extra={"Cache-Control": "no-cache"})
            except Exception:
                return self.send_json({"error": "preview failed"}, 500)
        if u == "/api/vision":
            return self.send_json({"models": vision_models()})
        if u == "/api/manage":
            return self.send_json(manage())
        if u.startswith("/api/job/"):
            J = JOBS.get(u[9:])
            if not J:
                return self.send_json({"state": "error", "error": "작업을 찾을 수 없습니다."})
            out = {k: J[k] for k in ("state", "msg", "elapsed", "images", "error", "used", "warn", "progress", "pest", "phase", "batch", "pymod", "oom") if k in J}
            if J.get("kind") == "batch":      # 수백 장이어도 응답이 무거워지지 않게 최근 24장만 보내요
                out["n_images"], out["images"] = len(J["images"]), J["images"][-24:]
            if J.get("state") == "queued":
                ahead = (QUEUE.index(J["id"]) if J["id"] in QUEUE else 0) + sum(1 for v in list(JOBS.values()) if v.get("state") == "running")
                out["msg"] = "대기 중" + (f" · 앞에 {ahead}개" if ahead else "")
            return self.send_json(out)
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.guard():
            return
        u = urllib.parse.urlparse(self.path).path
        if u == "/api/vmix/upload":
            return self.send_json(vmix_upload(self))
        try:
            p = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self.send_json({"error": "bad json"}, 400)
        if u == "/api/chat":
            return self.chat(p)
        if u == "/api/job":
            if p.get("kind") not in ("edit", "gen", "up", "wf", "feat", "vid", "vpost", "vmix", "music", "tts", "batch"):
                return self.send_json({"error": "unknown kind"}, 400)
            if len(JOBS) > 50:
                for k, v in list(JOBS.items()):
                    if v.get("state") in DONE_STATES:
                        del JOBS[k]
                        break
            if p["kind"] == "batch":
                try:
                    p["count"] = len(batch_files(batch_folder(p), bool(p.get("sub") or p.get("outsub")))[:BATCH_MAX])
                except ValueError as e:
                    return self.send_json({"error": str(e)})
                if not p["count"]:
                    return self.send_json({"error": "처리할 이미지가 없어요. (png · jpg · webp · bmp)"})
            J = {"id": uuid.uuid4().hex[:10], "state": "queued", "msg": "대기 중", "elapsed": 0, "images": [], "tmp": []}
            JOBS[J["id"]] = J
            J["feature"] = str(p.get("feature") or "")[:40]
            enqueue(J, p)
            return self.send_json({"id": J["id"]})
        if u == "/api/install":
            return self.send_json(install(p))
        if u == "/api/install/cancel":
            if p.get("all"):
                n = sum(1 for x in list(TASKS) if x["state"] in ("queued", "running") and cancel_task(x["id"]).get("ok"))
                return self.send_json({"ok": True, "n": n})
            return self.send_json(cancel_task(str(p.get("id"))))
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
        if u == "/api/prefs":
            return self.send_json(set_prefs(p))
        if u == "/api/tts/model/install":
            return self.send_json(tts_models.install(ROOT, str(p.get("id"))))
        if u == "/api/tts/model/remove":
            if busy_count():
                return self.send_json({"error": "작업이 진행 중일 때는 지우지 않아요."})
            return self.send_json(tts_models.uninstall(ROOT, str(p.get("id"))))
        if u == "/api/tts/ref":
            return self.send_json(tts_ref_upload(p))
        if u == "/api/tts/install":
            ok_, tail = tts.install_edge()
            if not ok_:
                log("[TTS 부품 설치 오류]", tail)
            return self.send_json({"ok": ok_, "error": "" if ok_ else "부품을 설치하지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요."})
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
        if u == "/api/memory/free":
            return self.send_json(memory_free())
        if u == "/api/update/inspect":
            return self.send_json(update_inspect(p))
        if u == "/api/update/apply":
            return self.send_json(update_apply(p))
        if u == "/api/app/restart":
            return self.send_json(app_restart(p))
        if u == "/api/app/move/check":
            return self.send_json(app_move(p, True))
        if u == "/api/app/move":
            return self.send_json(app_move(p, False))
        if u == "/api/nodes/sources":
            try:
                return self.send_json(node_sources([str(x) for x in (p.get("missing") or [])][:200]))
            except RuntimeError as e:
                return self.send_json({"error": str(e)})
        if u == "/api/nodes/install":
            return self.send_json(node_install(p))
        if u == "/api/nodes/diagnose":
            return self.send_json(node_diagnose(p))
        if u == "/api/nodes/fixdeps":
            return self.send_json(node_fixdeps(p))
        if u == "/api/engine/restart":
            return self.send_json(restart_comfy())
        if u == "/api/control/prep":
            return self.send_json(control_prep(p))
        if u == "/api/gallery/delete":
            return self.send_json(gal_delete(p))
        if u == "/api/gallery/organize":
            return self.send_json(organize_outputs(p))
        if u == "/api/backup/import":
            return self.send_json(backup_import(p))
        if u == "/api/lora/user":
            return self.send_json(lora_user_api(p))
        if u == "/api/lora/preview":
            return self.send_json(lora_preview_api(p))
        if u == "/api/prompts":
            return self.send_json(prompts_api(p))
        if u == "/api/chars":
            return self.send_json(chars_api(p))
        if u == "/api/wildcards":
            return self.send_json(wildcards_api(p))
        if u == "/api/describe":
            return self.send_json(describe_image(p))
        if u == "/api/gallery/fav":
            return self.send_json(gal_fav(p))
        if u == "/api/faceswap/model":
            return self.send_json(swap_download())
        if u == "/api/cachein":
            return self.send_json(cache_set(p.get("on")) if "on" in p else cache_status())
        if u == "/api/cachein/move":
            return self.send_json(cache_move())
        if u == "/api/parts/delete":
            return self.send_json(part_delete(p))
        if u == "/api/disk/open":
            return self.send_json(disk_open(p.get("key")))
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
        if u == "/api/chats/save":
            return self.send_json(chats_save(p))
        if u == "/api/chats/rename":
            return self.send_json(chats_rename(p))
        if u == "/api/chats/delete":
            return self.send_json(chats_delete(p))
        if u == "/api/pymod/install":
            return self.send_json(pymod_install(p))
        if u == "/api/wf/analyze":
            try:
                g = flows.parse_graph(p.get("graph"), caps()["info"])
                return self.send_json({"ok": True, **flows.analyze(g, caps()["nodes"] or None)})
            except flows.MissingNodes as e:      # 화면용(UI) 워크플로에 없는 노드가 있으면, 어디서 설치할지 도와줄 수 있게 목록을 같이 돌려줘요
                return self.send_json({"error": str(e), "missing": e.nodes})
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
            queue_cancel(J)
            return self.send_json({"ok": True})
        if u == "/api/queue/move":
            return self.send_json(queue_move(p))
        if u == "/api/batch/scan":
            return self.send_json(batch_scan(p))
        if u == "/api/batch/upload":
            return self.send_json(batch_upload(p))
        if u == "/api/rmbg/install":
            return self.send_json(rmbg_install(p))
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
            p = dict(p)
            ka = prefs()["chat_keep_alive"]
            p["keep_alive"] = -1 if ka == "-1" else (0 if ka == "0" else ka)
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


CLIENT_SEEN = threading.Event()      # 화면(브라우저)이 한 번이라도 연결했는지


def main():
    thumb_sweep_bg()      # 지워진 사진의 미리보기·옛 방식 파일 정리, 용량 상한 확인
    threading.Thread(target=idle_unload_loop, daemon=True).start()
    threading.Thread(target=lambda: _safe_warm(), daemon=True).start()      # 목록을 미리 한 번 읽어 둬요(첫 탭부터 빠르게)
    global GPU
    sys.stdout.reconfigure(errors="replace")
    apply_cache_env()
    start_engines()        # 엔진을 가장 먼저 켜요(켜지는 동안 아래 준비를 같이 해요)
    GPU = gpu()
    register_root()
    ws_start()
    threading.Thread(target=worker, daemon=True).start()
    try:
        srv = Server(("127.0.0.1", PORT), Handler)
    except OSError:
        sys.exit(f"포트 {PORT} 를 이미 사용 중입니다. 이미 실행 중인 스튜디오가 있는지 확인하세요.")
    url = f"http://127.0.0.1:{PORT}"
    log(f"로컬 AI 스튜디오: {url}  (종료하려면 이 창을 닫으세요)")
    if os.environ.get("HUB_RESTARTED"):
        # 다시 시작했을 때는 열려 있던 화면이 스스로 새로고침해요. 8초 안에 화면이 다시 연결되지 않았을 때만 브라우저를 새로 열어요.
        threading.Timer(8.0, lambda: None if CLIENT_SEEN.is_set() else webbrowser.open(url)).start()
    elif not os.environ.get("HUB_NOBROWSER"):
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
