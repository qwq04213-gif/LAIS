# 로컬 AI 스튜디오 허브 — API 응답 · 내 PC 점검 · 앱 안 업데이트 · 캐릭터 보관함
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

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


FAMILY_CHOICES = ("sd15", "sdxl", "sd3", "flux", "krea2", "chroma", "qwen", "moss", "hidden")


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
    non_image = set(music_models()) | set(sfx_models()) | set(ltx_models())      # 소리·영상 체크포인트(폴더를 한 번씩만 훑어요)
    for n in files("checkpoints"):
        fam, allin, how = model_family("checkpoints", n)
        info["checkpoints/" + n] = dict(family=fam, all_in_one=allin, how=how)
        if fam == "hidden" or n in non_image or re.search(r"hunyuan3d|trellis|pixal3d", n.lower()):      # 소리·영상·3D 모델은 그림 모델 목록에 섞지 않아요      # 음악 모델은 그림 모델 목록에 섞지 않아요
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
        elif fam in ("hidden", "qwen", "moss", "sd15", "sdxl", "sd3", "hidream", "lumina") or re.search(r"trellis|pixal3d|ltx", n.lower()) or (fam == "unknown" and re.search(r"qwen|moss", n.lower())):
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
    loras, lu = files("loras"), lora_user()
    return {"llm": [], "checkpoints": sdxl, "loras": loras, "families": info,
            "lora_info": {n: (lu.get(n) or {}).get("family") or modelinfo.lora_family(MODELS / "loras" / n)["family"] for n in loras}, "lora_kind": lora_kinds(),
            "lora_alias": {n: (lu.get(n) or {}).get("alias") for n in loras if (lu.get(n) or {}).get("alias")},
            "upscalers": files("upscale_models"), "controlnets": files("controlnet"),
            "vaes": files("vae"), "text_encoders": files("text_encoders"), "diffusion": files("diffusion_models"),
            "fluxmodels": flux, "chromamodels": chroma, "krea2models": krea2, "anymodels": sdxl + flux + chroma + krea2,
            "flux_ready": bool(fp["t5"] and fp["clip_l"] and fp["vae"]),
            "chroma_ready": bool(fp["t5"] and fp["vae"]),
            "krea2_ready": bool(kp["te"] and kp["vae"]), "oxmodels": ox, "ox_ready": ox_ready,
            "musicmodels": music_models(), "music_nodes": all(has_node(n) for n in MUSIC_NODES), "k2control": k2_control_loras(), "vidmore": vid_more_state(), "sfx_ready": bool(sfx_models()), "k2c_nodes": all(has_node(n) for n in K2C_NODES),
            "wanmodels": wan_models(), "wan_ready": bool(wan_parts()["te"] and wan_parts()["vae"]), "wan14": wan14_state(),
            "wildcards": sorted(p.stem for p in wc.glob("*.txt")) if wc.is_dir() else [],
            "qwen": bool(qwen21_unets() and qwen21_te() and qwen21_vae()), "qwen_files": {"unet": qwen21_unets(), "te": [n for n in files("text_encoders") if re.search(r"qwen3[_-]?vl[_-]?8b", n.lower())], "vae": [n for n in files("vae") if QWEN21_RX.search(n.lower())]}}


def catalog():
    try:
        tags = {t["name"]: t.get("size", 0) for t in http(OLLAMA + "/api/tags", timeout=3).get("models", [])}
    except Exception:  # noqa: BLE001
        tags = {}
    llm = []
    for m in CATALOG["llm"]:
        sz = tags.get(m["ollama"], tags.get(m["ollama"] + ":latest"))
        llm.append({**m, "installed": sz is not None, "disk_gb": round(sz / 1e9, 1) if sz else None})
    img = []
    for m in CATALOG["image"]:
        inst = img_installed(m)
        sz = sum(fsize(MODELS / f["dir"] / cat_name(f)) for f in m["files"]) if inst else 0
        img.append({**m, "installed": inst, "cat": cat_of(m), "disk_gb": round(sz / 1e9, 1) if inst else None})
    return {"llm": llm, "image": img}


def cat_of(m):
    """추천 모델 분류: image(이미지) / video(영상) / audio(음악·효과음) / d3(3D)."""
    i = m["id"].lower()
    if re.search(r"wan|ltx|vace|s2v|rife", i):
        return "video"
    if re.search(r"ace-step|stable-audio|audio", i):
        return "audio"
    if "3d" in i or "trellis" in i:
        return "d3"
    return "image"


def catalog_remove(p):
    """추천 모델에서 설치한 항목을 지워요. 다른 설치된 항목이 같이 쓰는 파일(공용 인코더·VAE 등)은 남겨요."""
    mid = str(p.get("id") or "")
    llm = next((m for m in CATALOG["llm"] if m["id"] == mid), None)
    if llm:
        return delete_item({"kind": "ollama", "name": llm["ollama"]})
    m = next((x for x in CATALOG["image"] if x["id"] == mid), None)
    if not m:
        return {"error": "그런 항목이 없어요."}
    mine = {(f["dir"], cat_name(f)) for f in m["files"]}
    shared = set()
    for o in CATALOG["image"]:
        if o["id"] != mid and img_installed(o):
            shared |= mine & {(f["dir"], cat_name(f)) for f in o["files"]}
    gone, kept, errs = [], [], []
    for d, n in sorted(mine):
        f = MODELS / d / n
        if not f.is_file():
            continue
        if (d, n) in shared:
            kept.append(n)
            continue
        try:
            f.unlink()
            gone.append(n)
        except OSError as e:
            errs.append(f"{n}: {e.strerror or e}")
    _LC["key"] = None
    if errs:
        return {"error": "일부를 지우지 못했어요(ComfyUI 가 쓰는 중일 수 있어요): " + "; ".join(errs), "removed": gone, "kept": kept}
    return {"ok": True, "removed": gone, "kept": kept}


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
    grp("edit", "이미지 편집", "edit", [_row("Qwen-Image 2.1 (생성·편집)", bool(L.get("qwen")), "" if L.get("qwen") else "모델·텍스트 인코더·VAE 중 빠진 게 있어요.",
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
_CHLOCK = threading.Lock()


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
    with _CHLOCK:
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
