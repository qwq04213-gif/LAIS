# 로컬 AI 스튜디오 허브 — 안전 장치 · 엔진 실행 / VRAM 관리
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

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
    for folder, pat, age in (((COMFY / "input", "hub_*", 3600), (COMFY / "temp", "*", 2 * 86400), (ROOT / "cache", "gif_*.gif", 86400)) if tmp else ()):
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
               "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"] + sa + mem_args()
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


class GpuBusy(RuntimeError):
    """그래픽카드를 혼자 써야 하는 작업(인체 3D)이 돌고 있어서 지금은 대화 모델을 올릴 수 없어요."""


# 그래픽카드 '혼자 쓰기': 인체 3D 처럼 VRAM 을 거의 다 쓰는 작업이 도는 동안 대화 모델(Ollama)이 새로 올라오지 못하게 막아요.
#   · 이미지·영상 작업끼리는 작업 대기열이 한 줄로 세워서 이미 겹치지 않아요. 대화만 대기열 밖에서 돌기 때문에 따로 막아요.
#   · LLM_USERS: 지금 그래픽카드로 답을 만들고 있는 대화 요청 수. 혼자 쓰기는 이게 0 이 될 때까지 기다렸다가 시작해요.
GPU_HOLD = {"who": None, "label": "", "since": 0.0, "owner": None}
LLM_USERS = {"n": 0}
_GPU_CV = threading.Condition()
GPU_HOLD_MSG = "지금 {label} 작업이 그래픽카드를 혼자 쓰고 있어서 대화 모델을 올릴 수 없어요. 작업이 끝난 뒤 다시 보내 주세요. (설정에서 대화를 'CPU 로만'으로 바꾸면 함께 쓸 수 있어요)"


def gpu_hold_view():
    h = GPU_HOLD
    return {"who": h["who"], "label": h["label"], "seconds": round(time.time() - h["since"]) if h["who"] else 0, "llm_users": LLM_USERS["n"]}


def gpu_busy_msg():
    return GPU_HOLD_MSG.format(label=GPU_HOLD["label"] or "다른") if GPU_HOLD["who"] else None


def ollama_loaded():
    """지금 Ollama 가 그래픽카드에 올려 둔 모델 이름들(모르면 빈 목록)."""
    try:
        return [m.get("name") for m in http(OLLAMA + "/api/ps", timeout=3).get("models", []) if m.get("size_vram", 1)]
    except Exception:  # noqa: BLE001
        return []


def gpu_exclusive_begin(who, label, owner=None, wait=180, should_stop=None, on_wait=None):
    """그래픽카드 혼자 쓰기 시작. 먼저 '혼자 쓰기' 표시를 걸어 새 대화가 못 들어오게 하고, 이미 답을 만들고 있는 대화가 끝나기를 기다린 뒤,
    Ollama·ComfyUI 가 올려 둔 모델을 내려요. 기다리다 wait 초가 지나거나 should_stop() 이 참이면 표시를 풀고 예외를 내요."""
    with _GPU_CV:
        if GPU_HOLD["who"]:
            raise GpuBusy(f"이미 {GPU_HOLD['label']} 작업이 그래픽카드를 혼자 쓰고 있어요.")
        GPU_HOLD.update(who=who, label=label, since=time.time(), owner=owner)
    try:
        t0 = time.time()
        with _GPU_CV:
            while LLM_USERS["n"] > 0:
                if should_stop and should_stop():
                    raise Cancelled("사용자가 중단했어요.")
                if time.time() - t0 > wait:
                    raise RuntimeError(f"대화가 {int(wait / 60)}분 넘게 끝나지 않아 {label} 을(를) 시작하지 못했어요. 대화를 멈추고 다시 해 주세요.")
                if on_wait:
                    on_wait(LLM_USERS["n"])
                _GPU_CV.wait(0.5)
        free_ollama()
        free_comfy()
        for _ in range(20):                           # Ollama 가 실제로 내릴 때까지 잠깐 기다려요(최대 10초)
            if not ollama_loaded():
                break
            time.sleep(0.5)
        STATE["last"] = who
    except BaseException:
        gpu_exclusive_end(who, owner)
        raise


def gpu_exclusive_end(who, owner=None):
    """혼자 쓰기 끝(완료·중단·실패 어느 경우든 꼭 불러요). 건 쪽(owner)이 다르면 건드리지 않아요."""
    with _GPU_CV:
        if GPU_HOLD["who"] == who and (owner is None or GPU_HOLD["owner"] == owner):
            GPU_HOLD.update(who=None, label="", since=0.0, owner=None)
            if STATE.get("last") == who:
                STATE["last"] = None
            _GPU_CV.notify_all()


class llm_use:
    """대화 모델이 그래픽카드로 답을 만드는 동안을 감싸요: 혼자 쓰기 중이면 GpuBusy, 아니면 사용 중 수를 올렸다 내려요.
    gpu=False(대화를 CPU 로만 돌리는 설정)면 막지도 세지도 않아요."""

    def __init__(self, gpu=True):
        self.gpu = gpu

    def __enter__(self):
        if self.gpu:
            with _GPU_CV:
                if GPU_HOLD["who"]:
                    raise GpuBusy(gpu_busy_msg())
                LLM_USERS["n"] += 1
        return self

    def __exit__(self, *a):
        if self.gpu:
            with _GPU_CV:
                LLM_USERS["n"] = max(0, LLM_USERS["n"] - 1)
                _GPU_CV.notify_all()
        return False


def llm_http(path, body, timeout=300):
    """Ollama 에 답을 시키는 요청은 모두 이 함수로 — 혼자 쓰기 중이면 모델을 올리지 않고 GpuBusy 를 내요."""
    cpu = isinstance(body.get("options"), dict) and body["options"].get("num_gpu") == 0
    with llm_use(gpu=not cpu):
        return http(OLLAMA + path, body, timeout)


def claim(who):
    """대화 ↔ 이미지 기능을 오갈 때 상대 엔진이 잡고 있는 VRAM 을 비웁니다."""
    if GPU_HOLD["who"] and who == "chat":
        raise GpuBusy(gpu_busy_msg())
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
    if GPU_HOLD["who"]:                               # 그래픽카드 혼자 쓰기 중에는 번역을 건너뛰어요(원문 그대로)
        return text
    if llm_needs_room(names[0]):
        free_comfy()  # 번역용 LLM 이 쓸 VRAM 확보 (이미지 모델은 작업 때 다시 올라옵니다)
    what = {"sentence": "an image editing instruction. Write one clear imperative sentence.",
            "caption": "an image generation prompt written as natural, descriptive English sentences."
            }.get(style, "an image generation prompt. Output comma-separated Danbooru-style tags.")
    sysmsg = f"Translate the user's Korean text into English as {what} Keep every detail. Output only the result."
    try:
        r = llm_http("/api/generate", {"model": names[0], "system": sysmsg, "prompt": text, "stream": False,
                                            "keep_alive": 0, "options": {"temperature": 0.2}}, 180)
        out = re.sub(r"<think>.*?</think>", "", r.get("response", ""), flags=re.S).strip().strip('"')
    except Exception:
        return text
    if out and out != text:
        if len(_TR) > 64:
            _TR.clear()
        _TR[key] = out
    return out or text
