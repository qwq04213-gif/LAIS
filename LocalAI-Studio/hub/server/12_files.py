# 로컬 AI 스튜디오 허브 — 다운로드 · 선택 도구 · 설치된 파일 · 저장 공간 · 캐시 옮기기
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

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
    base = str(p.get("base") or "")
    tok = settings().get("tokens", {}).get("civitai")
    try:
        data = api_get(CIVITAI + "/api/v1/models?" + urllib.parse.urlencode(params + ([("baseModels", base)] if base else [])), tok)
    except Exception:  # noqa: BLE001
        if not base:
            raise
        data = api_get(CIVITAI + "/api/v1/models?" + urllib.parse.urlencode(params), tok)      # Civitai 가 모르는 기반 모델 이름이면 거르지 않고 받아서 아래에서 걸러요
    items = []
    for m in data.get("items") or []:
        vers = []
        for v in (m.get("modelVersions") or [])[:6]:
            if base and (v.get("baseModel") or "") != base:
                continue
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


# ───────────────────────── 모델 지우기 (용량이 실제로 줄도록) ─────────────────────────
# 윈도우에서는 엔진이 열어 둔(메모리에 올린) 모델 파일을 지우면 목록에서만 사라지고, 엔진이 파일을 놓을 때까지 디스크 용량이 그대로예요.
# ComfyUI 는 모델을 mmap 으로 열어 두고, Ollama 는 올려 둔 모델의 조각(blob)을 지우지 못하면 조용히 남겨 둬요.
# 그래서 지우기 전에 엔진이 파일을 놓게 하고, 지운 뒤에 정말 비워졌는지 확인해요.
LLM_DIR = ROOT / "models" / "llm"
RELEASE_WAIT = 2.0          # ComfyUI 가 모델을 내리고 정리(gc)할 때까지 기다리는 시간(초)


def _disk_free(p):
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 0


def img_busy():
    return bool(QUEUE) or any(J.get("state") == "running" for J in list(JOBS.values()))


def release_comfy():
    """이미지 엔진이 잡고 있는 모델 파일을 놓게 해요(모델 내리기 + 캐시 비우기). 엔진이 꺼져 있으면 바로 돌아와요."""
    if not alive(CUI + "/system_stats"):
        return False
    used = STATE.get("last") == "image"         # 마지막으로 내린 뒤 이미지 엔진을 썼을 때만 모델이 올라가 있어요
    free_comfy()
    STATE["last"] = None
    LAST_MODEL["key"] = None
    if used:
        time.sleep(RELEASE_WAIT)
    return True


def release_llm(name):
    """대화 모델을 메모리에서 내려요(올라가 있을 때만). 내려가야 Ollama 가 모델 파일을 지울 수 있어요."""
    try:
        if not any(m.get("name") == name or m.get("model") == name for m in http(OLLAMA + "/api/ps", timeout=3).get("models", [])):
            return
        http(OLLAMA + "/api/generate", {"model": name, "keep_alive": 0}, 30)
        for _ in range(20):
            if not any(m.get("name") == name or m.get("model") == name for m in http(OLLAMA + "/api/ps", timeout=3).get("models", [])):
                return
            time.sleep(0.5)
    except Exception:
        pass


def llm_blobs():
    """Ollama 조각 파일 {이름: 크기}"""
    b = LLM_DIR / "blobs"
    return {f.name: fsize(f) for f in b.iterdir() if f.is_file()} if b.is_dir() else {}


def llm_manifests():
    """대화 모델 목록 파일 → 그 모델이 쓰는 조각 이름들. 하나라도 못 읽으면 None(그땐 아무것도 지우지 않아요)."""
    man = LLM_DIR / "manifests"
    out = {}
    for f in (man.rglob("*") if man.is_dir() else []):
        if not f.is_file():
            continue
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
            out[str(f)] = {x["digest"].replace(":", "-") for x in [m.get("config") or {}] + list(m.get("layers") or []) if x.get("digest")}
        except Exception:
            return None
    return out


def llm_orphans(min_age=600):
    """어떤 대화 모델도 쓰지 않는 Ollama 조각 파일(지우다 남은 것, 받다 만 것). 받는 중인 대화 모델이 있거나 min_age 초 안에 바뀐 파일은 빼요."""
    blobs, mf = LLM_DIR / "blobs", llm_manifests()
    if mf is None or not blobs.is_dir() or any(t.get("kind") == "ollama" and t["state"] in ("queued", "running") for t in TASKS):
        return []
    used = set().union(*mf.values()) if mf else set()
    now, out = time.time(), []
    for f in blobs.iterdir():
        try:
            if f.is_file() and f.name.startswith("sha256-") and f.name not in used and now - f.stat().st_mtime >= min_age:
                out.append(f)
        except OSError:
            pass
    return out


def _unlink_all(fs):
    n = 0
    for f in fs:
        try:
            sz = fsize(f)
            f.unlink()
            n += sz
        except OSError:
            pass
    return n


def delete_llm(name):
    before, mf0 = sum(llm_blobs().values()), llm_manifests()
    release_llm(name)
    req = urllib.request.Request(OLLAMA + "/api/delete", data=json.dumps({"model": name, "name": name}).encode(), method="DELETE",
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).close()
    except urllib.error.HTTPError as e:
        return {"error": f"삭제하지 못했어요 (HTTP {e.code})"}
    except Exception:
        return {"error": "대화 엔진(Ollama)에 연결하지 못했어요."}
    mf1 = llm_manifests()       # 지운 모델만 쓰던 조각인데 Ollama 가 지우지 못하고 남긴 것(올라가 있던 모델 등)
    if mf0 is not None and mf1 is not None:
        gone = set().union(*(v for k, v in mf0.items() if k not in mf1)) if any(k not in mf1 for k in mf0) else set()
        left = gone - (set().union(*mf1.values()) if mf1 else set())
        _unlink_all([LLM_DIR / "blobs" / b for b in left if (LLM_DIR / "blobs" / b).is_file()])
    return {"ok": True, "freed": max(0, before - sum(llm_blobs().values()))}


def delete_files(fs):
    """모델 파일 지우기(이미지 엔진이 놓게 한 뒤) → (지운 이름, 오류, 비운 바이트, 아직 안 비워진 바이트)"""
    fs = [f for f in fs if f.is_file()]
    if not fs:
        return [], [], 0, 0
    if img_busy():
        return [], ["이미지 작업이 도는 중이에요. 작업이 끝난 뒤 지워 주세요(쓰는 중인 모델은 지워도 용량이 줄지 않아요)."], 0, 0
    release_comfy()
    gone, errs, size = [], [], 0
    free0 = _disk_free(fs[0].parent)
    for f in fs:
        sz = fsize(f)
        try:
            f.unlink()
            gone.append(f.name)
            size += sz
        except OSError as e:
            errs.append(f"{f.name}: {e.strerror or e}")
    gain = _disk_free(fs[0].parent) - free0 if free0 else size
    pending = size - gain if size > (200 << 20) and gain < size // 2 else 0
    if pending:
        log("[모델 지우기] 지웠지만 용량이 아직 안 줄었어요(엔진이 파일을 잡고 있음):", ", ".join(gone), f"{pending / 1e9:.1f}GB")
    return gone, errs, size, max(0, pending)


def delete_item(p):
    if p.get("kind") == "ollama":
        name = str(p.get("name", "")).strip()
        if not name:
            return {"error": "이름이 없어요."}
        return delete_llm(name)
    d, name = p.get("dir"), str(p.get("name", ""))
    if d not in FOLDERS or not name or Path(name).name != name:
        return {"error": "삭제할 수 없는 항목이에요."}
    f = MODELS / d / name
    if not f.is_file():
        return {"error": "파일을 찾을 수 없어요."}
    gone, errs, size, pending = delete_files([f])
    _LC["key"] = None
    if errs:
        return {"error": f"삭제하지 못했어요: {errs[0]}" + ("" if "작업이" in errs[0] else " 다른 프로그램(ComfyUI 등)이 사용 중일 수 있어요.")}
    return {"ok": True, "freed": size - pending, "pending": pending}


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


M3D_OLD = ROOT / "m3d_work"      # 예전 3D 만들기가 쓰던 작업 폴더(기능은 뺐지만 PC 에 남아 있을 수 있어서 정리 항목은 둬요)


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
             ("input", "임시 입력 파일 (ComfyUI input)", COMFY / "input", "이 프로그램이 넣은 hub_* 파일(그림·영상·소리)만 지워요.", "input", ()),
             ("backup", "업데이트 되돌리기용 백업", ROOT / "backup", "가장 최근 1개만 남기고 지워요.", "backup", ()),
             ("logs", "로그", LOGS, "지워도 안전해요.", "logs", ()),
             ("cache", "작업용 캐시 (이 프로그램 폴더의 cache)", ROOT / "cache", "갤러리 미리보기, 내려받다 만 확장, 음성·GIF 임시 파일이에요. 지워도 다시 만들어져요.", "cache",
              (VR_WORK, AU_WORK, DEPTH_DIR)),
             ("vrestore", "영상 복원 작업 파일 (이어서 하기용)", VR_WORK, "끊긴 복원을 이어서 하려고 남겨 둔 중간 영상이에요. 지워도 결과물은 그대로예요(이어서 하기만 안 돼요).", "vrestore", ()),
             ("audio_work", "소리 분리 작업 파일", AU_WORK, "소리 분리·복원의 중간 파일이에요. 지워도 결과물은 그대로예요.", "audio_work", ()),
             ("depth", "깊이 지도 저장분", DEPTH_DIR, "같은 사진을 다시 쓸 때 빨리 하려고 둔 깊이 지도예요. 지워도 필요할 때 다시 만들어요.", "depth", ()),
             ("m3d", "예전 3D 만들기 작업 (사진·방향 그림)", M3D_OLD, "만든 3D 파일은 결과물(outputs)에 따로 있어요. 정리는 30일 넘게 손대지 않은 작업만 지워요.", "m3d_old", ()),
             ("kept", "올려 둔 사진 (다시 켜도 불러오기)", KEEP_DIR, "위의 [올려 둔 사진 모두 지우기]로 지워요.", None, ()),
             ("analysis", "영상 분석 기록", VANA_DIR, "영상 분석 화면의 이전 분석 목록에서 지울 수 있어요.", None, ()),
             ("explore", "프롬프트 탐색 기록", EXP_DIR, "프롬프트 탐색 화면에서 지울 수 있어요.", None, ()),
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
    lo = llm_orphans()
    llm_left = {"n": len(lo), "bytes": sum(fsize(f) for f in lo)}
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
    return dict(items=items, ext=ext, big=big[:15], dups=dups, parts=parts, llm_left=llm_left, free=free, total=total, root=str(ROOT),
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
        busy = busy_count()
        for f in (COMFY / "input").glob("hub_*"):
            if f.is_file() and not (busy and time.time() - f.stat().st_mtime < 3600):      # 작업 중이면 방금 넣은 파일은 남겨요
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
        for sub in ("thumbs", "nodes", "tts", "vmix", "batch-in"):
            d = ROOT / "cache" / sub
            for f in (d.rglob("*") if d.is_dir() else []):
                if f.is_file():
                    rm(f)
        for f in (ROOT / "cache").glob("gif_*.gif"):
            rm(f)
        rm(ROOT / "cache" / "extension-node-map.json")
    elif what in ("vrestore", "audio_work", "depth"):
        if what != "depth" and (any(t.get("state") in ("running", "queued") for t in TASKS) or busy_count()):
            return {"error": "작업이 진행 중일 때는 지우지 않아요. 끝난 뒤에 다시 눌러 주세요."}
        d = {"vrestore": VR_WORK, "audio_work": AU_WORK, "depth": DEPTH_DIR}[what]
        for f in (d.rglob("*") if d.is_dir() else []):
            if f.is_file():
                rm(f)
        for sub in sorted((x for x in d.rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)) if d.is_dir() else []:
            try:
                sub.rmdir()
            except OSError:
                pass
    elif what == "m3d_old":
        old = time.time() - 30 * 86400
        for s in (list(M3D_OLD.iterdir()) if M3D_OLD.is_dir() else []):
            mf = s / "meta.json"
            if s.is_dir() and mf.is_file() and max(f.stat().st_mtime for f in s.iterdir()) < old:
                freed += dir_size(s)
                shutil.rmtree(s, ignore_errors=True)
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
    elif what == "llm_orphans":         # 어떤 대화 모델도 쓰지 않는 Ollama 조각(지우다 남은 것·받다 만 것)
        if any(t.get("kind") == "ollama" and t.get("state") in ("running", "queued") for t in TASKS):
            return {"error": "대화 모델을 받는 중일 때는 남은 조각을 지우지 않아요."}
        freed += _unlink_all(llm_orphans())
    elif what == "parts":
        if any(t.get("state") in ("running", "queued") for t in TASKS):
            return {"error": "설치·다운로드가 진행 중일 때는 받다 만 파일을 지우지 않아요."}
        for d in FOLDERS:
            for f in (MODELS / d).glob("*.part") if (MODELS / d).is_dir() else []:
                rm(f)
    else:
        return {"error": "알 수 없는 정리 항목이에요."}
    return {"ok": True, "freed": freed}
