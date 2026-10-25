# 로컬 AI 스튜디오 허브 — LoRA 만들기 (사진 모으기 → 자동 캡션 → 학습 설정 → 학습(대기열) → loras 폴더에 등록)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

import lora_train
import wd14

LORA_DATA = ROOT / "lora_data"
LORA_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
LORA_MAX_IMG = 300
LORA_KINDS = {"character": "인물·캐릭터", "style": "그림체·스타일", "other": "사물·옷·기타"}


def lset_dir(sid):
    if not re.fullmatch(r"[0-9a-f]{10}", str(sid or "")):
        raise ValueError("학습 세트를 찾을 수 없어요.")
    return LORA_DATA / sid


def lset_meta(sid):
    try:
        return json.loads((lset_dir(sid) / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("학습 세트를 찾을 수 없어요.") from None


def lset_save(m):
    d = lset_dir(m["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.tmp").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    (d / "meta.tmp").replace(d / "meta.json")


def lset_imgs(sid):
    d = lset_dir(sid) / "img"
    return sorted((f for f in d.iterdir() if f.suffix.lower() in LORA_IMG_EXT), key=lambda f: f.name) if d.is_dir() else []


def lora_file_name(s):
    s = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(s or "")).strip("_")[:48]
    return s


def lset_view(sid):
    m = lset_meta(sid)
    rows = []
    for f in lset_imgs(sid):
        cap = f.with_suffix(".txt")
        try:
            w, h = Image.open(f).size
        except OSError:
            w = h = 0
        rows.append({"file": f.name, "url": f"/lora_data/{sid}/img/{urllib.parse.quote(f.name)}", "caption": cap.read_text(encoding="utf-8").strip() if cap.is_file() else "",
                     "w": w, "h": h})
    samples = sorted((lset_dir(sid) / "train" / "out" / "sample").glob("*.png")) if (lset_dir(sid) / "train" / "out" / "sample").is_dir() else []
    return {**m, "images": rows, "samples": [f"/lora_data/{sid}/train/out/sample/{urllib.parse.quote(f.name)}" for f in samples[-12:]],
            "kinds": LORA_KINDS}


def lset_list():
    out = []
    if LORA_DATA.is_dir():
        for d in sorted(LORA_DATA.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                out.append({"id": m["id"], "name": m["name"], "n": len(lset_imgs(m["id"])), "done": m.get("lora_file", ""), "t": m.get("t", 0)})
            except (OSError, ValueError, KeyError):
                continue
    return {"items": out[:50]}


def lset_check_text(*xs):
    for x in xs:
        if x and blocked(x):
            raise ValueError(BLOCK_MSG)


def lset_new(p):
    name = re.sub(r"\s+", " ", str(p.get("name") or "")).strip()[:60]
    trig = re.sub(r"\s+", " ", str(p.get("trigger") or "")).strip()[:40]
    if not name:
        return {"error": "LoRA 이름을 적어 주세요."}
    lset_check_text(name, trig)
    m = {"id": uuid.uuid4().hex[:10], "name": name, "trigger": trig or lora_file_name(name).lower() or "mylora", "kind": p.get("kind") if p.get("kind") in LORA_KINDS else "character",
         "file": lora_file_name(p.get("file") or name) or "my_lora", "t": time.time()}
    lset_save(m)
    (lset_dir(m["id"]) / "img").mkdir(parents=True, exist_ok=True)
    return lset_view(m["id"])


def lset_update(p):
    m = lset_meta(p.get("id"))
    for k, n in (("name", 60), ("trigger", 40)):
        if k in p:
            v = re.sub(r"\s+", " ", str(p.get(k) or "")).strip()[:n]
            lset_check_text(v)
            if v:
                m[k] = v
    if p.get("kind") in LORA_KINDS:
        m["kind"] = p["kind"]
    if "file" in p:
        m["file"] = lora_file_name(p.get("file")) or m["file"]
    caps = p.get("captions") if isinstance(p.get("captions"), dict) else {}
    d = lset_dir(m["id"]) / "img"
    names = {f.name for f in lset_imgs(m["id"])}
    for fn, txt in caps.items():
        if fn in names:
            t = re.sub(r"\s+", " ", str(txt or "")).strip()[:2000]
            lset_check_text(t)
            (d / fn).with_suffix(".txt").write_text(t, encoding="utf-8")
    m["t"] = time.time()
    lset_save(m)
    return lset_view(m["id"])


def lset_add_bytes(sid, name, data):
    m = lset_meta(sid)
    if len(lset_imgs(sid)) >= LORA_MAX_IMG:
        raise ValueError(f"사진은 {LORA_MAX_IMG}장까지 넣을 수 있어요.")
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        im = ImageOps.exif_transpose(im)
    except Exception:  # noqa: BLE001
        raise ValueError(f"사진으로 읽을 수 없어요: {name}") from None
    if min(im.size) < 256:
        raise ValueError(f"사진이 너무 작아요(짧은 쪽 256px 이상): {name}")
    d = lset_dir(sid) / "img"
    d.mkdir(parents=True, exist_ok=True)
    stem = f"{int(time.time() * 1000) % 10**9:09d}{uuid.uuid4().hex[:3]}_" + (re.sub(r"[^A-Za-z0-9_\-]+", "_", Path(name).stem)[:30] or "img")
    out = d / (stem + ".png")
    k = 2048 / max(im.size)
    if k < 1:
        im = im.resize((round(im.width * k), round(im.height * k)), RS.LANCZOS)
    im.convert("RGB").save(out, "PNG")
    m["t"] = time.time()
    lset_save(m)
    return out.name


def lset_upload(h):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(h.path).query)
    sid, name = (q.get("id") or [""])[0], Path((q.get("name") or ["img"])[0]).name
    n = int(h.headers.get("Content-Length") or 0)
    if n <= 0 or n > 60 << 20:
        return {"error": "사진 파일이 너무 커요(60MB 이하)."}
    data = h.rfile.read(n)
    try:
        return {"ok": True, "file": lset_add_bytes(sid, name, data)}
    except ValueError as e:
        return {"error": str(e)}


def lset_from_gallery(p):
    added, bad = [], []
    for u in (p.get("urls") or [])[:LORA_MAX_IMG]:
        f = out_path(str(u)[5:]) if str(u).startswith("/out/") else None
        if not f or not f.is_file() or f.suffix.lower() not in GAL_IMG:
            bad.append(str(u)[-40:])
            continue
        try:
            added.append(lset_add_bytes(p.get("id"), f.name, f.read_bytes()))
        except ValueError as e:
            bad.append(str(e))
    return {"ok": True, "added": len(added), "bad": bad}


def lset_remove(p):
    sid = p.get("id")
    lset_meta(sid)
    fn = Path(str(p.get("file") or "")).name
    f = lset_dir(sid) / "img" / fn
    if f.suffix.lower() in LORA_IMG_EXT and f.is_file():
        f.unlink()
        f.with_suffix(".txt").unlink(missing_ok=True)
    return lset_view(sid)


def lset_delete(p):
    sid = p.get("id")
    lset_meta(sid)
    if any(J.get("state") in ("queued", "running") and J.get("lset") == sid for J in list(JOBS.values())):
        return {"error": "학습 중인 세트는 지울 수 없어요."}
    shutil.rmtree(lset_dir(sid), ignore_errors=True)       # 만든 LoRA 파일(loras 폴더)은 그대로 남아요
    return {"ok": True}


def lset_file(sid, rel):
    """화면에 보여 줄 사진·미리보기(세트 폴더 안의 img/ 와 train/out/sample/ 만)."""
    d = lset_dir(sid)
    rel = urllib.parse.unquote(rel)
    if not (rel.startswith("img/") or rel.startswith("train/out/sample/")) or ".." in rel:
        return None
    f = (d / rel).resolve()
    try:
        f.relative_to(d.resolve())
    except ValueError:
        return None
    return f if f.is_file() and f.suffix.lower() in LORA_IMG_EXT else None


def lora_caption(p, J):
    sid = p.get("id")
    m = lset_meta(sid)
    imgs = lset_imgs(sid)
    if not imgs:
        raise ValueError("먼저 사진을 넣어 주세요.")
    how = p.get("method") if p.get("method") in ("wd14", "tags", "sentence") else "wd14"
    over = flag(p, "overwrite", False)
    todo = [f for f in imgs if over or not f.with_suffix(".txt").is_file() or not f.with_suffix(".txt").read_text(encoding="utf-8").strip()]
    if how == "wd14":
        ensure_ort(J)
        if not wd14.ready(MODELS):
            wd14.download(MODELS, lambda m_: J.update(msg=m_))
    done = 0
    for i, f in enumerate(todo):
        check_cancel(J)
        J["msg"], J["progress"] = f"캡션 다는 중 {i + 1}/{len(todo)}", (i + 1) / max(1, len(todo))
        if how == "wd14":
            tg = wd14.tags(MODELS, Image.open(f), general=clamp(num(p, "thr", 0.35), 0.1, 0.9))
            if m["kind"] == "character":     # 인물 LoRA: 얼굴·머리 같은 고유 특징은 트리거 단어가 배우도록 캡션에서 빼는 게 보통이에요(선택)
                drop = set(x.strip() for x in str(p.get("drop") or "").split(",") if x.strip())
                tg = [t for t in tg if t not in drop]
            text = ", ".join(tg)
        else:
            b = io.BytesIO()
            Image.open(f).convert("RGB").save(b, "JPEG", quality=90)
            r = describe_image({"image": "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode(), "style": how, "model": p.get("model")})
            if r.get("error"):
                raise RuntimeError(r["error"])
            text = r["text"].replace("\n", " ").strip()
        if blocked(text):
            raise ValueError(BLOCK_MSG)
        f.with_suffix(".txt").write_text(text, encoding="utf-8")
        done += 1
    J["msg"] = f"캡션 {done}장 달았어요" + ("" if done == len(imgs) else f"(이미 있던 {len(imgs) - done}장은 그대로)")
    return []


def lora_train_job(p, J):
    sid = p.get("id")
    m = lset_meta(sid)
    J["lset"] = sid
    if not lora_train.installed(ROOT):
        raise RuntimeError("LoRA 학습 엔진이 아직 없어요. LoRA 만들기 화면의 [학습 엔진 설치]를 눌러 주세요.")
    imgs = lset_imgs(sid)
    if len(imgs) < 5:
        raise ValueError(f"사진이 {len(imgs)}장이에요. 최소 5장(추천 15~40장)이 필요해요.")
    ckpt = str(p.get("ckpt") or "")
    if ckpt not in files("checkpoints"):
        raise ValueError("기반 모델(체크포인트)을 골라 주세요.")
    fam = model_family("checkpoints", ckpt)[0]
    if fam not in ("sdxl", "sd15"):
        raise ValueError("지금은 SD1.5 · SDXL 계열(Illustrious·Pony·NoobAI 포함) 체크포인트로만 LoRA 를 만들 수 있어요.")
    lset_check_text(m["trigger"])
    work = lset_dir(sid) / "train"
    shutil.rmtree(work, ignore_errors=True)
    tdir = work / "img"
    tdir.mkdir(parents=True)
    for f in imgs:
        shutil.copy2(f, tdir / f.name)
        cap = f.with_suffix(".txt").read_text(encoding="utf-8").strip() if f.with_suffix(".txt").is_file() else ""
        (tdir / f.name).with_suffix(".txt").write_text(", ".join(x for x in (m["trigger"], cap) if x), encoding="utf-8")
    pr = lora_train.PRESETS.get(p.get("preset")) or lora_train.PRESETS["normal"]
    steps = clamp(num(p, "steps", 0, int), 0, 20000) or lora_train.plan_steps(len(imgs), p.get("preset"))
    res = int(p.get("res")) if str(p.get("res")) in ("512", "768", "1024") else (1024 if fam == "sdxl" else 512)
    dim = clamp(num(p, "dim", pr["dim"], int), 4, 128)
    a = {"family": fam, "ckpt": str(mpath("checkpoints", ckpt)), "work": str(work), "name": m["file"], "steps": steps, "dim": dim,
         "alpha": clamp(num(p, "alpha", dim // 2, int), 1, 128), "lr": clamp(num(p, "lr", pr["lr"]), 1e-6, 1e-2), "res": res,
         "unet_only": flag(p, "unet_only", True), "seed": clamp(num(p, "seed", 42, int), 0, 2**31 - 1), "optimizer": "AdamW8bit",
         "sample_every": max(10, steps // 5) if flag(p, "sample", True) else 0,
         "sample_prompt": (m["trigger"] + ", " + str(p.get("sample_prompt") or "").strip()).strip(", ") if flag(p, "sample", True) else ""}
    (work / "dataset.toml").write_text(lora_train.dataset_toml(tdir, res, 1, 1, flip=m["kind"] == "style" and flag(p, "flip", False)), encoding="utf-8")
    cmd = lora_train.build_cmd(ROOT, a)
    m["last"] = {"ckpt": ckpt, "steps": steps, "dim": dim, "lr": a["lr"], "res": res, "t": time.time()}
    lset_save(m)
    J["msg"] = "그래픽 메모리 비우는 중"
    free_comfy()
    free_ollama()
    STATE["last"] = None
    t0 = time.time()
    samp_dir = work / "out" / "sample"

    def say(pc, st, tot, loss, msg):
        J["msg"] = msg
        if pc is not None:
            J["progress"] = min(0.99, pc)
            el = time.time() - t0
            J["eta"] = round(el / pc * (1 - pc)) if pc > 0.03 else None
        J["step"], J["loss"] = st, loss
        if samp_dir.is_dir():
            J["samples"] = [f"/lora_data/{sid}/train/out/sample/{urllib.parse.quote(f.name)}" for f in sorted(samp_dir.glob("*.png"))[-8:]]
    out = lora_train.train(ROOT, cmd, work, say, lambda: J.get("cancel"))
    dest_name = m["file"] + ".safetensors"
    k = 2
    while (MODELS / "loras" / dest_name).exists():
        dest_name = f'{m["file"]}_v{k}.safetensors'
        k += 1
    (MODELS / "loras").mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, MODELS / "loras" / dest_name)
    lora_user_api({"name": dest_name, "alias": m["name"], "trigger": [m["trigger"]], "kind": m["kind"], "family": fam,
                   "memo": f"직접 만든 LoRA · 사진 {len(imgs)}장 · 기반 {ckpt} · {steps}단계 · {time.strftime('%Y-%m-%d')}"})
    m["lora_file"] = dest_name
    m["t"] = time.time()
    lset_save(m)
    J["lora_file"] = dest_name
    J["msg"] = f"LoRA 를 만들었어요: {dest_name} (트리거 단어: {m['trigger']})"
    return []


def do_lora(p, J):
    fn = {"caption": lora_caption, "train": lora_train_job}.get(p.get("op"))
    if not fn:
        raise ValueError("알 수 없는 작업이에요.")
    return fn(p, J)
