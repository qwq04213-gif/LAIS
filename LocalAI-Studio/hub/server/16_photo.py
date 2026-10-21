# 로컬 AI 스튜디오 허브 — 사진 편집기 (화면에서 편집한 그림을 결과 폴더에 저장)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

PHOTO_SUB = "사진 편집"


def photo_save(p):
    """사진 편집기 결과(PNG data URL)를 outputs\\사진 편집 에 새 파일로 저장해요. 원본은 건드리지 않아요."""
    try:
        raw = base64.b64decode(str(p.get("image") or "").split(",", 1)[-1], validate=False)
    except Exception:  # noqa: BLE001
        return {"error": "그림을 읽지 못했어요."}
    if not raw or len(raw) > 80 << 20:
        return {"error": "그림이 비어 있거나 너무 커요(80MB 이하)."}
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:  # noqa: BLE001
        return {"error": "그림 형식을 읽지 못했어요."}
    if im.width * im.height > 8192 * 8192:
        return {"error": "그림이 너무 커요(가로×세로 8192 이하)."}
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", Path(str(p.get("name") or "photo")).stem)[:60] or "photo"
    d = OUT / PHOTO_SUB
    d.mkdir(parents=True, exist_ok=True)
    f = _unique(d / f'{time.strftime("%Y%m%d-%H%M%S")}-{stem}.png')
    im.save(f, "PNG")
    return {"ok": True, "url": "/out/" + urllib.parse.quote(PHOTO_SUB) + "/" + urllib.parse.quote(f.name), "w": im.width, "h": im.height}
