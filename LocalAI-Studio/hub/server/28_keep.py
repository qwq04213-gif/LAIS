# 로컬 AI 스튜디오 허브 — 올린 사진 기억하기: 화면마다 올려 둔 사진(편집할 사진·참조 그림·영상 시작 그림 등)을
# kept_inputs 폴더에 두고, 프로그램을 다시 켜면 그 화면에 그대로 불러와요. 사용자가 빼거나 [지우기]를 눌러야만 지워요(자동 삭제 없음).
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요.
# ruff: noqa: F821

KEEP_DIR = ROOT / "kept_inputs"
KEEP_MAX = 60 * 1024 * 1024                         # 한 장 최대 60MB
KEEP_EXT = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
KEEP_TYPE = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}


def _keep_slot(slot):
    s = str(slot or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,23}(\.[a-z0-9_-]{1,40}){0,2}", s):
        raise ValueError("알 수 없는 자리예요.")
    return s


def _keep_files(slot):
    return [KEEP_DIR / (slot + e) for e in KEEP_TYPE if (KEEP_DIR / (slot + e)).is_file()]


def keep_list():
    """{자리: 주소} — 다시 켰을 때 화면이 불러가요."""
    out = {}
    if KEEP_DIR.is_dir():
        for f in sorted(KEEP_DIR.iterdir()):
            if f.suffix in KEEP_TYPE and f.is_file():
                out[f.stem] = f"/kept/{f.name}?t={int(f.stat().st_mtime)}"
    return {"items": out}


def keep_post(p):
    """{slot, image(data URL)} 저장 · {slot, clear} 빼기 · {all: 1, clear} 모두 지우기."""
    if p.get("all") and p.get("clear"):
        n = 0
        if KEEP_DIR.is_dir():
            for f in KEEP_DIR.iterdir():
                if f.suffix in KEEP_TYPE and f.is_file():
                    f.unlink()
                    n += 1
        return {"ok": True, "removed": n}
    try:
        slot = _keep_slot(p.get("slot"))
    except ValueError as e:
        return {"error": str(e)}
    if p.get("clear"):
        for f in _keep_files(slot):
            f.unlink()
        return {"ok": True}
    try:
        raw = base64.b64decode(str(p.get("image") or "").split(",", 1)[-1], validate=False)
        if not raw or len(raw) > KEEP_MAX:
            return {"error": "사진이 너무 크거나 비어 있어요."}
        im = Image.open(io.BytesIO(raw))
        im.verify()
        fmt = Image.open(io.BytesIO(raw)).format
    except Exception:  # noqa: BLE001
        return {"error": "사진을 읽을 수 없어요."}
    KEEP_DIR.mkdir(parents=True, exist_ok=True)
    ext = KEEP_EXT.get(fmt)
    for f in _keep_files(slot):
        f.unlink()
    dst = KEEP_DIR / (slot + (ext or ".png"))
    tmp = dst.with_name(dst.name + ".part")
    if ext:
        tmp.write_bytes(raw)                       # 원본 그대로(화질 그대로)
    else:
        Image.open(io.BytesIO(raw)).save(tmp, "PNG")
    tmp.replace(dst)
    return {"ok": True, "url": f"/kept/{dst.name}?t={int(dst.stat().st_mtime)}"}


def keep_file(name):
    m = re.fullmatch(r"(.+)(\.png|\.jpg|\.webp)", name or "")
    if not m:
        return None
    try:
        slot = _keep_slot(m.group(1))
    except ValueError:
        return None
    f = KEEP_DIR / (slot + m.group(2))
    return f if f.is_file() else None


def keep_size():
    """모아 둔 사진 수·크기(설정 화면 안내용)."""
    fs = [f for f in KEEP_DIR.iterdir() if f.suffix in KEEP_TYPE and f.is_file()] if KEEP_DIR.is_dir() else []
    return {"count": len(fs), "bytes": sum(f.stat().st_size for f in fs)}
