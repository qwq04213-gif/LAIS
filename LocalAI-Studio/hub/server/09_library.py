# 로컬 AI 스튜디오 허브 — 일괄 처리 · 프롬프트 보관함 · 기록 갤러리
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

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


RM_BEST = {"label": "최고(BiRefNet)", "mb": 424, "file": "birefnet.safetensors", "id": "birefnet"}
RM_KEYS = tuple(bgremove.MODELS) + ("best",)


def rmbg_best_ready():
    return (MODELS / "background_removal" / RM_BEST["file"]).is_file()


def rmbg_ready(key):
    return rmbg_best_ready() if key == "best" else bgremove.have_ort() and bgremove.installed(MODELS / "rmbg", key)


def rmbg_default():
    """고르지 않았을 때: BiRefNet 이 있으면 그걸, 없으면 '보통'."""
    return "best" if rmbg_best_ready() else "normal"


def rmbg_status():
    busy = any((t.get("kind") == "rmbg" or t.get("mid") == RM_BEST["id"]) and t["state"] in ("queued", "running") for t in TASKS)
    ort = bgremove.have_ort()
    ms = {k: {"label": m["label"], "mb": m["mb"], "installed": bgremove.installed(MODELS / "rmbg", k)} for k, m in bgremove.MODELS.items()}
    ms["best"] = {"label": RM_BEST["label"], "mb": RM_BEST["mb"], "installed": rmbg_best_ready(), "comfy": True}
    return {"ort": ort, "busy": busy, "models": ms, "default": rmbg_default()}


def rmbg_install(p):
    if p.get("key") == "best":
        return install({"ids": [RM_BEST["id"]]})
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


class RmbgComfy:
    """배경 지우기 '최고': ComfyUI 의 BiRefNet(그래픽카드). 경계는 bgremove.refine 으로 색 번짐만 걷어내요."""

    def mask(self, img, J=None):
        J = J if J is not None else {"tmp": []}
        J.setdefault("tmp", [])
        wait_comfy()
        claim("image")
        name = put_input(img.convert("RGB"), J)
        try:
            res = run_wf(flows.wf_rmbg({"image": name, "model": RM_BEST["file"]}), J)
        finally:
            _clean_tmp(J)
        return res[0].convert("L").resize(img.size, RS.LANCZOS)

    def cut(self, img, bg=None, J=None, refine_edges=True):
        return bgremove.compose(img, self.mask(img, J), bg, refine_edges, coarse=False)


def rmbg_cut(key, img, bg=None, J=None):
    """배경 지우기 한 장(엔진 종류와 상관없이)."""
    eng = rmbg_engine(key)
    return eng.cut(img, bg, J=J) if isinstance(eng, RmbgComfy) else eng.cut(img, bg)


def rmbg_engine(key):
    if key == "best":
        return RmbgComfy()
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
        rm_key = p.get("rmodel") if p.get("rmodel") in RM_KEYS else rmbg_default()
        if not rmbg_ready(rm_key):
            raise RuntimeError("배경 지우기 모델이 아직 설치되지 않았어요. 일괄 처리 화면의 [설치] 버튼을 눌러 주세요.")
        rm_bg = {"white": (255, 255, 255), "black": (0, 0, 0)}.get(p.get("bg"))
        jpg = jpg and rm_bg is not None          # 투명 배경은 PNG 만 가능해요
        suffix = "_배경없음"
    else:
        probe, steps = resize_steps(Image.new("RGB", (64, 64)), p)
        if not steps:
            raise ValueError("하나 이상 골라 주세요. (자를 비율, 회전, 뒤집기, 긴 변 크기)")
        suffix = "_크기변경"
    out_dir = OUT / OUT_SUB["batch"] / job_dir_name(time.strftime("%Y%m%d-%H%M%S"), op)      # 작업 한 번 = 폴더 하나
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
                res = rmbg_cut(rm_key, img, rm_bg, J)
            else:
                res, _ = resize_steps(img, p)
            ext = ".jpg" if jpg else ".png"
            if jpg and res.mode != "RGB":
                res = res.convert("RGB")
            dst = _unique(out_dir / (f.stem + suffix + ext))
            res.save(dst, "JPEG", quality=95) if jpg else res.save(dst, "PNG")
            J["images"].append("/out/" + urllib.parse.quote(OUT_SUB["batch"]) + "/" + urllib.parse.quote(out_dir.name) + "/" + urllib.parse.quote(dst.name))
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
GAL_IMG = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
GAL_VID = {".mp4", ".webm"}
GAL_AUD = {".wav", ".mp3", ".flac", ".opus", ".ogg", ".m4a"}
GAL_3D = {".glb"}
GAL_EXT = GAL_IMG | GAL_VID | GAL_AUD | GAL_3D


def gal_type(f):
    """갤러리 칸의 종류: image · video · audio · 3d"""
    s = Path(f).suffix.lower()
    return "video" if s in GAL_VID else "audio" if s in GAL_AUD else "3d" if s in GAL_3D else "image"


def gal_sides(f):
    """결과 파일 옆에 붙는 설정(.json)·자막(.srt) 파일. 3D(.glb)는 같은 작업에서 함께 만든 게임용 묶음(.zip)과 그 설정 파일까지."""
    out = [x for x in (f.with_name(f.name + ".json"), f.with_suffix(".srt")) if x != f and x.is_file()]
    m = re.match(r"^(\d{8}-\d{6})-[0-9a-f]{4}-m3d-\d+\.glb$", f.name)
    if m:
        for z in f.parent.glob(m.group(1) + "-*-m3d-*.zip"):
            if z.is_file():
                out.append(z)
                if z.with_name(z.name + ".json").is_file():
                    out.append(z.with_name(z.name + ".json"))
    return out
_GMETA = {}


def gal_favs():
    try:
        return set(json.loads(GAL_FILE.read_text(encoding="utf-8")).get("favs", []))
    except (OSError, ValueError):
        return set()


def gal_fav(p):
    rel = str(p.get("file") or "")
    parts = [x for x in urllib.parse.unquote(rel[5:] if rel.startswith("/out/") else rel).split("/") if x]
    if len(parts) not in (2, 3) or parts[0] not in OUT_SUB.values() or (len(parts) == 3 and not (DATE_RX.match(parts[1]) or JOB_RX.match(parts[1]))):
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
        else:
            sc = path.with_name(path.name + ".json")
            txt = json.loads(sc.read_text(encoding="utf-8")).get("prompt", "") if sc.is_file() else ""
    except Exception:
        txt = ""
    if len(_GMETA) > 5000:
        _GMETA.clear()
    _GMETA[k] = txt
    return txt


def out_files(d, exts=None):
    """결과 하위 폴더(예: 생성)의 이미지·영상 파일. 날짜별로 정리한 폴더(2026-10-18)·작업 폴더(작업 한 번 = 폴더 하나)도 한 단계 들여다봐요."""
    exts = exts or GAL_EXT
    try:
        for f in d.iterdir():
            if f.is_file():
                if f.suffix.lower() in exts:
                    yield f
            elif f.is_dir() and (DATE_RX.match(f.name) or JOB_RX.match(f.name)):
                for g in f.iterdir():
                    if g.is_file() and g.suffix.lower() in exts:
                        yield g
    except OSError:
        return


def gal_delete(p):
    """갤러리에서 고른 파일을 컴퓨터에서 지워요(영상의 설정 파일·즐겨찾기 표시도 함께). 복구할 수 없어요."""
    gone, bad = 0, 0
    keys, done = [], []
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
            for side in gal_sides(fp):
                side.unlink()
            keys.append(parts[0] + "/" + fp.name)
            gone += 1
            done.append(rel)
        except OSError:
            bad += 1
        if len(parts) == 3:      # 비어 버린 날짜·작업 폴더는 치워요(작업 폴더에 남은 게 설정·묶음 파일뿐이면 그것도 함께)
            try:
                if JOB_RX.match(fp.parent.name) and not any(x.suffix.lower() in GAL_EXT for x in fp.parent.iterdir() if x.is_file()):
                    for x in fp.parent.iterdir():
                        if x.is_file() and (x.suffix.lower() in (".json", ".srt", ".zip")):
                            x.unlink()
                fp.parent.rmdir()
            except OSError:
                pass
    if keys:
        with _PLOCK:
            fav = gal_favs()
            if fav & set(keys):
                GAL_FILE.write_text(json.dumps({"favs": sorted(fav - set(keys))}, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "deleted": gone, "failed": bad, "urls": done}


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
                    sides = gal_sides(f)
                    f.rename(dst)
                    for side in sides:
                        if side.name == f.name + ".json":
                            side.rename(dst.with_name(dst.name + ".json"))
                        elif side.suffix == ".srt" and side.stem == f.stem:
                            side.rename(dst.with_suffix(".srt"))
                        else:                                  # 3D 게임용 묶음(.zip)·그 설정 파일은 이름 그대로 같은 날짜 폴더로
                            side.rename(_unique(dd / side.name))
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
    ftype = (q.get("type") or [""])[0]
    favs, rows = gal_favs(), []
    for sub in OUT_SUB.values():
        if kind and kind != sub:
            continue
        d = OUT / sub
        if not d.is_dir():
            continue
        for f in out_files(d):
            if ftype and gal_type(f) != ftype:
                continue
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
              "fav": key in favs, "video": f.suffix.lower() in GAL_VID, "type": gal_type(f),
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
