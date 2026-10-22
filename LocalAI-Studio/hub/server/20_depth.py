# 로컬 AI 스튜디오 허브 — 깊이 맵 활용: 저장·재사용, 배경 흐림·전경/배경 효과, 패럴랙스 영상, 3D 메시, 영상 깊이(일관성), 카메라 움직임 추정
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

import depthfx

DEPTH_DIR = ROOT / "cache" / "depth"
DEPTH_SUB = OUT_SUB["depth"]
DEPTH_NOTE = "AI 추정값(실제로 잰 거리 아님)"


def depth_key(img):
    b = io.BytesIO()
    img.convert("RGB").resize((256, round(256 * img.height / max(1, img.width))) if img.width else (256, 256)).save(b, "PNG")
    return hashlib.sha1(b.getvalue() + f"{img.width}x{img.height}".encode()).hexdigest()[:20]


def get_depth(p, J, img):
    """깊이 맵 구하기: 직접 올린 깊이 맵 → 같은 사진으로 만들어 둔 깊이 맵(저장분) → 새로 추정. 돌려주는 값: (흑백 깊이, 다시 썼는지, 노드)"""
    if p.get("depth_img"):
        return load_img(p["depth_img"]).convert("L").resize(img.size, RS.BICUBIC), "올린 깊이 맵", ""
    key = depth_key(img)
    f = DEPTH_DIR / f"{key}.png"
    if f.is_file():
        try:
            return Image.open(f).convert("L").resize(img.size, RS.BICUBIC), "저장된 깊이 맵", ""
        except OSError:
            pass
    J["msg"] = "깊이를 추정하는 중"
    b = io.BytesIO()
    img.save(b, "PNG")
    r = control_prep({"type": "depth", "image": "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()})
    if r.get("error"):
        raise RuntimeError(r["error"])
    d = Image.open(io.BytesIO(base64.b64decode(r["image"].split(",", 1)[1]))).convert("L").resize(img.size, RS.BICUBIC)
    d = ImageOps.autocontrast(d)
    try:
        DEPTH_DIR.mkdir(parents=True, exist_ok=True)
        d.save(f, "PNG")
        old = sorted(DEPTH_DIR.glob("*.png"), key=lambda x: x.stat().st_mtime)
        for x in old[:-300]:                       # 저장분은 최근 300장까지만
            x.unlink(missing_ok=True)
    except OSError:
        pass
    return d, "", r.get("node", "")


def _dinfo(img, how, node, **extra):
    return {"kind": "depth", "prompt": "", "w": img.width, "h": img.height, "model": node,
            "extra": {"Depth": DEPTH_NOTE, **({"Depth source": how} if how else {}), **({"Preprocessor": node} if node else {}), **extra}}


def feat_depth(p, J):
    """깊이 맵 만들기 + 깊이로 하는 효과(흑백·색·앞쪽만·배경 흐림·배경 효과)."""
    img = load_img(p["image"])
    d, how, node = get_depth(p, J, img)
    if how:
        warn(J, f"{how}을 다시 썼어요(새로 추정하지 않았어요).")
    if p.get("invert"):
        d = ImageOps.invert(d)
    out = p.get("out") if p.get("out") in ("gray", "color", "cut", "blur", "fx") else "gray"
    info = _dinfo(img, how, node, Output=out)
    J["msg"] = "깊이로 처리하는 중"
    if out == "gray":
        return [(d.convert("RGB"), {**info, "_sub": DEPTH_SUB}, None)]
    if out == "color":
        return [(depthfx.colorize(d), {**info, "_sub": DEPTH_SUB}, None)]
    if out == "blur":
        focus = None if p.get("focus") in (None, "", "auto") else clamp(num(p, "focus", 80), 0, 100) / 100
        res = depthfx.lens_blur(img, d, focus, clamp(num(p, "blur", 12), 1, 60))
        return [(res, {**info, "kind": "depth-blur"}, None)]
    if out == "fx":
        eff = p.get("effect") if p.get("effect") in ("gray", "dark", "fog", "desat", "blur") else "gray"
        res = depthfx.fg_bg(img, d, eff, clamp(num(p, "amount", 80), 0, 100) / 100, clamp(num(p, "near", 50), 1, 99), clamp(num(p, "feather", 8, int), 0, 60))
        return [(res, {**info, "kind": "depth-fx", "extra": {**info["extra"], "Effect": eff}}, None)]
    near = clamp(num(p, "near", 50), 1, 99)
    cut = round(near / 100 * 255)
    mask = d.point(lambda v: 255 if v >= cut else 0)
    fe = clamp(num(p, "feather", 4, int), 0, 60)
    if fe:
        mask = mask.filter(ImageFilter.GaussianBlur(fe))
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    return [(rgba, {**info, "extra": {**info["extra"], "Near": near}}, None)]


def _encode_frames(frames, fps, J, total, label):
    """PIL 프레임들 → mp4 바이트(ffmpeg 로 바로 넘겨요)."""
    ff = vmix.find_ffmpeg(PY, ROOT)
    if not ff:
        raise RuntimeError("영상으로 만들려면 ffmpeg 가 필요해요. 설치와 모델 > 내 PC 점검의 [빠진 부품 설치]로 imageio-ffmpeg 를 설치해 주세요.")
    work = ROOT / "cache" / "depthvid"
    work.mkdir(parents=True, exist_ok=True)
    out = work / (uuid.uuid4().hex[:10] + ".mp4")
    proc = None
    try:
        for i, fr in enumerate(frames):
            check_cancel(J)
            if proc is None:
                w, h = fr.width // 2 * 2, fr.height // 2 * 2
                proc = subprocess.Popen([ff, "-y", "-hide_banner", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
                                        stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=vmix.NOWIN)
            fr = fr.convert("RGB")
            if fr.size != (w, h):
                fr = fr.crop((0, 0, w, h))
            proc.stdin.write(fr.tobytes())
            J["msg"], J["progress"] = f"{label} {i + 1}/{total}", (i + 1) / total * 0.97
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        proc.wait()
        if proc.returncode or not out.is_file():
            raise RuntimeError("영상을 만들지 못했어요: " + err[-300:])
        return out.read_bytes()
    finally:
        if proc and proc.poll() is None:
            proc.kill()
        out.unlink(missing_ok=True)


def camera_load(ref):
    """카메라 움직임 추정 결과(.json, 결과 폴더) → [[dx,dy,scale],...]"""
    f = out_path(ref[5:]) if str(ref or "").startswith("/out/") else None
    if not f or f.suffix.lower() != ".json" or not f.is_file():
        raise ValueError("카메라 움직임 파일을 찾을 수 없어요. 영상 분석 화면에서 [카메라 움직임 추정]을 먼저 해 주세요.")
    data = json.loads(f.read_text(encoding="utf-8"))
    tr = data.get("track") if isinstance(data, dict) else None
    if not tr:
        raise ValueError("카메라 움직임 파일이 올바르지 않아요.")
    return [[t["dx"], t["dy"], t["scale"]] for t in tr]


def feat_parallax(p, J):
    """사진 → 패럴랙스(2.5D) 영상: 깊이에 따라 가까운 것은 많이, 먼 것은 조금 움직여 카메라가 움직이는 듯 보여요."""
    img = load_img(p["image"])
    d, how, node = get_depth(p, J, img)
    kind = p.get("motion") if p.get("motion") in depthfx.MOTIONS else "orbit"
    cam = camera_load(p.get("camera")) if kind == "camera" else None
    sec, fps = clamp(num(p, "sec", 4.0), 1.0, 15.0), int(clamp(num(p, "fps", 24, int), 12, 30))
    st = clamp(num(p, "strength", 5.0), 1.0, 12.0) / 100
    n = max(2, int(round(sec * fps)))
    data = _encode_frames(depthfx.parallax_frames(img, d, kind, sec, fps, st, cam), fps, J, n, "장면 만드는 중")
    info = _dinfo(img, how, node, Motion=kind, Seconds=sec, Strength=st)
    info["kind"] = "parallax"
    return [(data, info, ".mp4")]


def feat_depth3d(p, J):
    """사진 + 깊이 → 3D 메시(.glb). 정면에서 본 모양만 있는 '부조' 같은 메시예요(뒤쪽·가려진 곳은 없어요)."""
    img = load_img(p["image"])
    d, how, node = get_depth(p, J, img)
    J["msg"] = "3D 메시 만드는 중"
    data, tris = depthfx.mesh_glb(img, d, clamp(num(p, "grid", 192, int), 32, 512), clamp(num(p, "zscale", 35), 5, 100) / 100)
    info = _dinfo(img, how, node, Triangles=tris)
    info["kind"] = "depth3d"
    info["extra"]["Note"] = "깊이 추정으로 만든 정면 부조 메시(실제 3D 복원 아님)"
    return [(data, info, ".glb")]
