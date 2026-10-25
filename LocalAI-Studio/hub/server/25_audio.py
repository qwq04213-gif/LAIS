# 로컬 AI 스튜디오 허브 — 소리 분리·복원 (Demucs 로 목소리·악기 나누기 → ffmpeg 로 잡음·음량 고치기 → 갈래별 저장·다시 섞기·영상에 넣기)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

import audio_sep
import audiofx

AU_SUB = "소리 분리·복원"
AU_ORIG = ROOT / "cache" / "aorig"
AU_WORK = ROOT / "cache" / "audio"
AU_EXT = tuple(vmix.AUDIO_EXT) + tuple(vmix.VIDEO_EXT)


def au_orig(ff, src):
    """비교 재생용 원본(wav) — cache/aorig 에 두고 /aorig/ 로 들려줘요. 사흘 지난 건 정리해요."""
    AU_ORIG.mkdir(parents=True, exist_ok=True)
    for f in AU_ORIG.glob("*.wav"):
        try:
            if time.time() - f.stat().st_mtime > 3 * 86400:
                f.unlink()
        except OSError:
            pass
    uid = uuid.uuid4().hex[:12]
    audiofx.to_wav(ff, src, AU_ORIG / f"{uid}.wav")
    return f"/aorig/{uid}.wav"


def au_orig_file(name):
    if not re.fullmatch(r"[0-9a-f]{12}\.wav", name or ""):
        return None
    f = AU_ORIG / name
    return f if f.is_file() else None


def up_file(uid):
    """올려 둔 영상·소리를 미리 듣기·비교용으로 들려줘요(/upfile/아이디)."""
    if not re.fullmatch(r"[0-9a-f]{12}", uid or ""):
        return None
    return next((x for x in sorted(VMIX_DIR.glob(uid + ".*")) if x.suffix.lower() in AU_EXT and x.is_file()), None)


def au_opts(p):
    return {"rumble": flag(p, "rumble", False), "rumble_hz": int(clamp(num(p, "rumble_hz", 70, int), 20, 200)),
            "hum": str(p.get("hum") or "") if str(p.get("hum") or "") in ("50", "60") else "", "declick": flag(p, "declick", False),
            "denoise": p.get("denoise") if p.get("denoise") in audiofx.DENOISE else "off", "loud": p.get("loud") if p.get("loud") in audiofx.LOUD else "off"}


def au_sep(p, J, ff, src, work):
    if not audio_sep.installed(ROOT):
        raise RuntimeError("소리 분리 엔진이 아직 없어요. 소리 분리·복원 화면의 [분리 엔진 설치]를 눌러 주세요.")
    J["msg"], J["progress"] = "소리 꺼내는 중", 0.02
    wav = work / "in.wav"
    audiofx.to_wav(ff, src, wav)
    J["orig"] = au_orig(ff, src)
    free_comfy()
    free_ollama()
    STATE["last"] = None

    def say(pc, msg):
        J["msg"], J["progress"] = msg, 0.05 + 0.9 * pc
    model = p.get("model") if p.get("model") in audio_sep.MODELS else "htdemucs"
    stems = audio_sep.separate(ROOT, wav, model, flag(p, "two", False), work / "stems", say, lambda: J.get("cancel"))
    order = ["vocals", "no_vocals", "drums", "bass", "guitar", "piano", "other"]
    stems.sort(key=lambda s: order.index(s[0]) if s[0] in order else 99)
    J["tracks"] = [{"stem": n, "label": audio_sep.STEMS.get(n, n)} for n, _ in stems]
    J["msg"] = "나눴어요 — " + ", ".join(t["label"] for t in J["tracks"])
    return [(f, {"kind": "audio", "op": "sep", "stem": n, "label": audio_sep.STEMS.get(n, n), "model": model, "source": vmix_name(src), "_sub": AU_SUB}, ".wav")
            for n, f in stems]


def au_fix(p, J, ff, src, work):
    o = au_opts(p)
    J["orig"] = au_orig(ff, src)
    out = work / "fixed.wav"

    def say(pc, msg):
        check_cancel(J)
        J["msg"], J["progress"] = msg, pc
    r = audiofx.restore(ff, src, out, o, None, say)
    J["loud"] = {"before": r["before"], "after": r["after"]}
    J["tracks"] = [{"stem": "fixed", "label": "고친 소리"}]
    J["msg"] = "고쳤어요 — " + ", ".join(r["steps"]) + (f" · 음량 {r['before']} → {r['after']} LUFS" if r["before"] is not None and r["after"] is not None else "")
    return [(out, {"kind": "audio", "op": "fix", "steps": r["steps"], "loud": J["loud"], "source": vmix_name(src), "_sub": AU_SUB}, ".wav")]


def au_mix(p, J, ff, work):
    tr = []
    for x in (p.get("tracks") or [])[:8]:
        try:
            f = vmix_src(x.get("url"), vmix.AUDIO_EXT, "갈래 소리")
            tr.append((f, clamp(float(x.get("vol", 1)), 0.0, 2.0)))
        except (AttributeError, TypeError, ValueError) as e:
            raise ValueError(str(e) or "갈래 소리를 찾을 수 없어요.") from None
    J["msg"] = "다시 섞는 중"
    out = work / "mix.wav"
    audiofx.mix(ff, tr, out)
    J["msg"] = "다시 섞었어요."
    J["tracks"] = [{"stem": "mix", "label": "다시 섞은 소리"}]
    return [(out, {"kind": "audio", "op": "mix", "tracks": [[vmix_name(f), round(v, 2)] for f, v in tr], "_sub": AU_SUB}, ".wav")]


def au_mux(p, J, ff, work):
    video = vmix_src(p.get("video"), vmix.VIDEO_EXT, "영상")
    audio = vmix_src(p.get("audio"), vmix.AUDIO_EXT, "소리")
    J["msg"] = "영상에 새 소리 넣는 중"
    out = work / "mux.mp4"
    audiofx.mux(ff, video, audio, out)
    J["msg"] = "영상에 새 소리를 넣었어요. 원래 영상은 그대로예요."
    return [(out, {"kind": "audio", "op": "mux", "video": vmix_name(video), "audio": vmix_name(audio), "_sub": AU_SUB}, ".mp4")]


def do_audio(p, J):
    ff = vana_ff()
    op = p.get("op") or "sep"
    if op not in ("sep", "fix", "mix", "mux"):
        raise ValueError("알 수 없는 소리 작업이에요.")
    work = AU_WORK / J["id"]
    work.mkdir(parents=True, exist_ok=True)
    try:
        if op == "mix":
            items = au_mix(p, J, ff, work)
        elif op == "mux":
            items = au_mux(p, J, ff, work)
        else:
            src = vmix_src(p.get("src"), AU_EXT, "소리·영상")
            items = (au_sep if op == "sep" else au_fix)(p, J, ff, src, work)
        keep = AU_WORK / f"out_{J['id']}"
        keep.mkdir(parents=True, exist_ok=True)
        moved = []
        for f, info, ext in items:                       # 작업 폴더를 지워도 되게 결과만 옮겨 둬요(저장할 때 결과 폴더로 다시 옮겨요)
            dst = keep / f.name
            shutil.move(str(f), dst)
            moved.append((dst, info, ext))
        return moved
    finally:
        shutil.rmtree(work, ignore_errors=True)
