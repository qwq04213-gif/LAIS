# -*- coding: utf-8 -*-
"""영상 복원 도우미(ffmpeg 만 씀): 영상 상태 진단 → 고르게 다듬기(줄무늬·노이즈·깜빡임·밝기·흔들림·선명도)
→ 조각으로 나누기 → (서버가 조각마다 AI 업스케일·프레임 늘리기) → 이어 붙이고 원래 소리 넣기 → 소리·길이 확인 → 전후 비교 그림."""
import io
import json
import math
import os
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import vmix

NOWIN = vmix.NOWIN
_FILTERS = {}
DENOISE = {"light": "hqdn3d=2:1.5:3:2.5", "medium": "hqdn3d=4:3:6:4.5", "strong": "hqdn3d=7:5.5:10:8"}
SHARPEN = "unsharp=5:5:0.55:5:5:0.0"
COPY_AUDIO = ("aac", "mp3", "alac")


def _run(cmd, timeout=None, cwd=None):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, errors="replace", timeout=timeout, cwd=cwd, creationflags=NOWIN)


def filters(ff):
    """이 ffmpeg 에 들어 있는 필터 이름들."""
    if ff not in _FILTERS:
        r = _run([ff, "-hide_banner", "-filters"], 60)
        _FILTERS[ff] = {ln.split()[1] for ln in (r.stdout or "").splitlines() if len(ln.split()) > 2 and re.fullmatch(r"[A-Z.|]{2,4}", ln.split()[0])}
    return _FILTERS[ff]


def probe2(ff, path):
    """vmix.probe + 코덱·비트레이트·소리 코덱·인터레이스 표시."""
    info = vmix.probe(ff, path)
    t = _run([ff, "-hide_banner", "-i", str(path)], 60).stderr or ""
    m = re.search(r"bitrate:\s*(\d+)\s*kb/s", t)
    info["kbps"] = int(m.group(1)) if m else 0
    for ln in t.splitlines():
        if "Video:" in ln and "attached pic" not in ln and "vcodec" not in info:
            info["vcodec"] = (re.search(r"Video:\s*(\w+)", ln) or [None, ""])[1]
            info["interlaced_tag"] = bool(re.search(r"top first|bottom first|top coded first|bottom coded first", ln))
        elif "Audio:" in ln and "acodec" not in info:
            info["acodec"] = (re.search(r"Audio:\s*(\w+)", ln) or [None, ""])[1]
            sr = re.search(r"(\d{4,6})\s*Hz", ln)
            info["arate"] = int(sr.group(1)) if sr else 0
    return info


def grab(ff, src, t, width=0):
    """t 초의 프레임 한 장 → PIL (못 읽으면 None)."""
    vf = ["-vf", f"scale={int(width)}:-2:flags=area"] if width else []
    r = subprocess.run([str(ff), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1", *vf, "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True, timeout=120, creationflags=NOWIN)
    if r.returncode or not r.stdout:
        return None
    try:
        return Image.open(io.BytesIO(r.stdout)).convert("RGB")
    except OSError:
        return None


def burst(ff, src, start, dur, fps, w, h):
    """짧은 구간을 작은 흑백 프레임 묶음으로(깜빡임·흔들림 재기용) → [H×W float32]."""
    r = subprocess.run([str(ff), "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-vf", f"fps={fps},scale={w}:{h}:flags=area,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, timeout=300, creationflags=NOWIN)
    raw = np.frombuffer(r.stdout or b"", dtype=np.uint8)
    n = raw.size // (w * h)
    return [raw[i * w * h:(i + 1) * w * h].reshape(h, w).astype(np.float32) for i in range(n)]


def noise_sigma(g):
    """흑백 배열의 노이즈 세기(Immerkær 방식, 0~255 단위). 6 넘으면 눈에 띄고 10 넘으면 많아요."""
    g = np.asarray(g, dtype=np.float32)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    c = (g[:-2, :-2] - 2 * g[:-2, 1:-1] + g[:-2, 2:] - 2 * g[1:-1, :-2] + 4 * g[1:-1, 1:-1] - 2 * g[1:-1, 2:] + g[2:, :-2] - 2 * g[2:, 1:-1] + g[2:, 2:])
    h, w = g.shape
    return float(np.sum(np.abs(c)) * math.sqrt(math.pi / 2) / (6 * (w - 2) * (h - 2)))


def sharpness(g):
    """라플라시안 분산(클수록 선명). 크기에 따라 달라서 같은 폭(640)으로 재요."""
    g = np.asarray(g, dtype=np.float32)
    lap = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4 * g[1:-1, 1:-1]
    return float(lap.var())


def phase_shift(a, b):
    """두 프레임 사이 화면 이동(dx, dy) — 위상 상관."""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1])).astype(np.float32)
    A, B = np.fft.fft2((a - a.mean()) * win), np.fft.fft2((b - b.mean()) * win)
    R = A * np.conj(B)
    R /= np.abs(R) + 1e-6
    c = np.fft.ifft2(R).real
    y, x = np.unravel_index(int(np.argmax(c)), c.shape)
    if y > a.shape[0] // 2:
        y -= a.shape[0]
    if x > a.shape[1] // 2:
        x -= a.shape[1]
    return float(x), float(y)


def _smooth(v, k=5):
    v = np.asarray(v, dtype=np.float64)
    if v.size < 3:
        return v
    k = min(k, v.size if v.size % 2 else v.size - 1)
    pad = np.pad(v, (k // 2, k // 2), mode="edge")
    return np.convolve(pad, np.ones(k) / k, mode="valid")


def flicker_shake(frames):
    """프레임 묶음 → (깜빡임: 밝기 출렁임 표준편차, 흔들림: 흔들린 정도(폭의 %))."""
    if len(frames) < 4:
        return 0.0, 0.0
    lum = np.array([f.mean() for f in frames])
    flick = float(np.std(lum - _smooth(lum, 7)))
    sh = [phase_shift(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
    path = np.cumsum(np.array(sh), axis=0)
    jit = path - np.stack([_smooth(path[:, 0], 9), _smooth(path[:, 1], 9)], axis=1)
    shake = float(np.sqrt((jit ** 2).sum(axis=1)).mean() / frames[0].shape[1] * 100)
    return flick, shake


def idet(ff, src):
    """인터레이스(줄무늬) 비율 0~1 — ffmpeg idet 으로 앞쪽 300프레임을 봐요."""
    r = _run([ff, "-hide_banner", "-i", str(src), "-vf", "idet", "-frames:v", "300", "-an", "-f", "null", "-"], 300)
    m = re.findall(r"Multi frame detection:\s*TFF:\s*(\d+)\s*BFF:\s*(\d+)\s*Progressive:\s*(\d+)", r.stderr or "")
    if not m:
        return 0.0
    tff, bff, prog = map(int, m[-1])
    return (tff + bff) / max(1, tff + bff + prog)


def _lv(v, warn, bad):
    return "bad" if v >= bad else "warn" if v >= warn else "ok"


def analyze(ff, src, info, say=None, samples=16):
    """영상 상태 진단 → {"metrics", "items"(화면 표시용), "rec"(추천 설정)}."""
    dur, W, H, fps = float(info.get("dur") or 0), int(info.get("w") or 0), int(info.get("h") or 0), float(info.get("fps") or 24)
    if dur <= 0 or not W or not H:
        raise ValueError("영상으로 읽을 수 없는 파일이에요.")
    noise, sharp, dark = [], [], []
    n = max(4, min(samples, int(dur * 2)))
    for i in range(n):
        say and say(0.05 + 0.5 * i / n, f"장면 살펴보는 중 {i + 1}/{n}")
        im = grab(ff, src, dur * (i + 0.5) / n, min(W, 960))
        if im is None:
            continue
        g = np.asarray(im.convert("L"), dtype=np.float32)
        noise.append(noise_sigma(g))
        g640 = np.asarray(im.convert("L").resize((640, max(2, round(640 * im.height / im.width)))), dtype=np.float32)
        sharp.append(sharpness(g640))
        dark.append(float(g.mean()))
    if not noise:
        raise ValueError("영상에서 프레임을 읽지 못했어요.")
    say and say(0.6, "깜빡임·흔들림 재는 중")
    bw = 192
    bh = max(2, round(bw * H / W / 2) * 2)
    fl, sk = [], []
    for k in range(3 if dur > 12 else 1):
        st = dur * (k + 0.5) / 3 - 1.5 if dur > 12 else 0.0
        fr = burst(ff, src, max(0.0, st), min(3.0, dur), 12, bw, bh)
        a, b = flicker_shake(fr)
        fl.append(a)
        sk.append(b)
    say and say(0.85, "줄무늬(인터레이스) 확인 중")
    inter = idet(ff, src)
    M = {"noise": round(float(np.median(noise)), 2), "sharp": round(float(np.median(sharp)), 1), "flicker": round(float(np.median(fl)), 2),
         "shake": round(float(np.median(sk)), 3), "interlace": round(inter, 2), "bright": round(float(np.median(dark)), 1)}
    rec = {"deint": inter >= 0.3 or bool(info.get("interlaced_tag") and inter >= 0.1),
           "denoise": "strong" if M["noise"] >= 10 else "medium" if M["noise"] >= 6 else "light" if M["noise"] >= 3.5 else "off",
           "deflicker": M["flicker"] >= 1.2, "stabilize": M["shake"] >= 0.25, "color": M["bright"] < 60,
           "sharpen": M["sharp"] < 60 and M["noise"] < 10, "upscale": 2 if max(W, H) < 1280 else 0, "interp": fps <= 30}
    items = [
        {"key": "deint", "label": "줄무늬(인터레이스)", "value": f"{inter * 100:.0f}% 프레임", "level": _lv(inter, 0.1, 0.3),
         "why": "옛 방송·캠코더 영상에서 움직일 때 빗살 무늬가 보여요."},
        {"key": "denoise", "label": "노이즈(자글거림)", "value": f"{M['noise']:.1f}", "level": _lv(M["noise"], 3.5, 6),
         "why": "어두운 곳·옛 영상의 자글자글한 점. 3.5 아래는 깨끗한 편이에요."},
        {"key": "deflicker", "label": "깜빡임", "value": f"{M['flicker']:.2f}", "level": _lv(M["flicker"], 0.7, 1.2),
         "why": "밝기가 프레임마다 출렁여요(형광등·필름·타임랩스)."},
        {"key": "stabilize", "label": "흔들림", "value": f"{M['shake']:.2f}%", "level": _lv(M["shake"], 0.15, 0.25),
         "why": "손으로 찍어 화면이 떨려요. 보정하면 가장자리가 조금 잘려요."},
        {"key": "color", "label": "밝기", "value": f"{M['bright']:.0f}/255", "level": "warn" if M["bright"] < 60 or M["bright"] > 200 else "ok",
         "why": "너무 어둡거나 밝으면 자동으로 범위를 넓혀요."},
        {"key": "sharpen", "label": "선명도", "value": f"{M['sharp']:.0f}", "level": "warn" if M["sharp"] < 60 else "ok",
         "why": "흐릿하면 살짝 선명하게. 노이즈가 많을 땐 노이즈도 같이 커져요."},
        {"key": "upscale", "label": "해상도", "value": f"{W}×{H}", "level": "bad" if max(W, H) < 960 else "warn" if max(W, H) < 1280 else "ok",
         "why": "AI 업스케일 모델로 2배 등으로 키워요(ComfyUI · 업스케일 모델 필요)."},
        {"key": "interp", "label": "부드러움(초당 프레임)", "value": f"{fps:.0f}fps", "level": "warn" if fps < 24 else "ok",
         "why": "RIFE 로 프레임을 2배로 늘려 움직임을 부드럽게(ComfyUI 확장 필요)."},
        {"key": "audio", "label": "소리", "value": (info.get("acodec") or "있음") if info.get("audio") else "없음", "level": "ok",
         "why": "원래 소리는 다시 인코딩하지 않고(가능하면) 그대로 옮겨요."},
    ]
    say and say(1.0, "진단했어요")
    return {"metrics": M, "items": items, "rec": rec}


def chain(opts, flt, stab=None):
    """고르게 다듬기 필터 줄. stab: None(흔들림 보정 안 함) / 'detect' / 'transform' / 'deshake'."""
    v = []
    if opts.get("deint"):
        v.append("bwdif=mode=send_frame:parity=auto:deint=all" if "bwdif" in flt else "yadif=0:-1:0")
    if opts.get("denoise") in DENOISE:
        v.append(DENOISE[opts["denoise"]])
    if opts.get("deflicker") and "deflicker" in flt:
        v.append("deflicker=size=5:mode=am")
    if opts.get("color") and "normalize" in flt:
        v.append("normalize=smoothing=30:independence=0")
    if stab in ("detect", "transform"):
        v.append("format=yuv420p")                    # vid.stab 은 4:2:0 평면 형식만 받아요
    if stab == "detect":
        v.append("vidstabdetect=shakiness=6:accuracy=12:result=transforms.trf")
        return ",".join(v)
    if stab == "transform":
        v.append(f"vidstabtransform=input=transforms.trf:smoothing={int(opts.get('stab_smooth') or 20)}:zoom=0:optzoom=1:interpol=bicubic")
    elif stab == "deshake":
        v.append("deshake=rx=32:ry=32:edge=mirror")
    if opts.get("sharpen"):
        v.append(SHARPEN)
    v.append("scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p")
    return ",".join(v)


def _ff_progress(cmd, dur, say, cancel, cwd, base, span, label, timeout=None):
    """ffmpeg 를 -progress 로 돌리며 진행률을 알려요. 실패하면 마지막 오류 글로 예외."""
    p = subprocess.Popen([str(c) for c in cmd[:1]] + ["-progress", "pipe:1", "-nostats"] + [str(c) for c in cmd[1:]], cwd=cwd,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", creationflags=NOWIN)
    import threading
    err = []
    th = threading.Thread(target=lambda: err.extend(p.stderr.read().splitlines()[-12:]), daemon=True)
    th.start()
    for ln in p.stdout:
        if ln.startswith("out_time_us=") or ln.startswith("out_time_ms="):
            try:
                t = int(ln.split("=")[1]) / 1e6
            except ValueError:
                continue
            say and say(base + span * min(1.0, t / max(dur, 0.01)), label)
        if cancel and cancel():
            p.kill()
            raise InterruptedError("중단했어요.")
    p.wait()
    th.join(5)
    if p.returncode:
        raise RuntimeError(f"{label} 실패: " + (" / ".join(x for x in err if x.strip())[-300:] or f"코드 {p.returncode}"))


def prepass(ff, src, opts, info, work, seg=0.0, say=None, cancel=None):
    """고르게 다듬기 → work/pre.mp4(소리 없이). seg 초마다 키프레임을 넣어 조각으로 나누기 쉽게 해요. → 쓴 단계 목록"""
    work = Path(work)
    flt = filters(ff)
    dur = float(info.get("dur") or 1)
    stab = None
    used = []
    if opts.get("stabilize"):
        if {"vidstabdetect", "vidstabtransform"} <= flt:
            say and say(0.02, "흔들림 분석 중")
            _ff_progress([ff, "-y", "-v", "error", "-i", src, "-vf", chain(opts, flt, "detect"), "-an", "-f", "null", "-"], dur, say, cancel, work, 0.02, 0.18, "흔들림 분석 중")
            stab = "transform"
        else:
            stab = "deshake"
        used.append("흔들림 보정" + ("" if stab == "transform" else "(간단)"))
    vf = chain(opts, flt, stab)
    kf = ["-force_key_frames", f"expr:gte(t,n_forced*{seg:.3f})"] if seg else []
    _ff_progress([ff, "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-vf", vf, "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "15", *kf, "pre.mp4"],
                 dur, say, cancel, work, 0.2 if stab == "transform" else 0.02, 0.78 if stab == "transform" else 0.96, "고르게 다듬는 중")
    for k, t in (("deint", "줄무늬 없애기"), ("denoise", "노이즈 줄이기"), ("deflicker", "깜빡임 줄이기"), ("color", "밝기 자동"), ("sharpen", "선명하게")):
        if opts.get(k) and opts.get(k) != "off":
            used.append(t)
    return used


def split(ff, pre, seg, folder):
    """pre.mp4 → folder/c000.mp4… (키프레임 기준으로 다시 인코딩 없이)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if not any(folder.glob("c*.mp4")):
        r = _run([ff, "-y", "-v", "error", "-i", pre, "-map", "0:v:0", "-c", "copy", "-f", "segment", "-segment_time", f"{seg:.3f}", "-reset_timestamps", "1",
                  str(folder / "c%03d.mp4")], 3600)
        if r.returncode:
            raise RuntimeError("조각으로 나누지 못했어요: " + (r.stderr or "")[-300:])
    return sorted(folder.glob("c*.mp4"))


def chunk_frames(w, h, model_scale, interp):
    """AI 조각 하나의 프레임 수 — ComfyUI 가 프레임을 한꺼번에 들고 있어서 메모리(약 2.5GB)에 맞춰요."""
    per = 12.0 * w * h * max(1, model_scale) ** 2 * (2 if interp else 1)
    return int(max(8, min(240, 2.5e9 / per)))


def finish(ff, video_parts, src, info, out, work):
    """조각(또는 pre.mp4)을 이어 붙이고 원래 소리를 넣어요 → out."""
    work = Path(work)
    lst = work / "list.txt"
    lst.write_text("".join("file '" + Path(p).resolve().as_posix().replace("'", "'\\''") + "'\n" for p in video_parts), encoding="utf-8")
    ac = (info.get("acodec") or "").lower()
    a = (["-map", "1:a:0?", "-c:a", "copy"] if ac in COPY_AUDIO else ["-map", "1:a:0?", "-c:a", "aac", "-b:a", "192k"]) if info.get("audio") else []
    base = [ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", src, "-map", "0:v:0"]
    r = _run(base + ["-c:v", "copy"] + a + ["-movflags", "+faststart", out], 7200)
    if r.returncode or not Path(out).is_file():
        r = _run(base + ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"] + a + ["-movflags", "+faststart", out], 7200)
        if r.returncode:
            raise RuntimeError("이어 붙이지 못했어요: " + (r.stderr or "")[-300:])


def stream_dur(ff, path, sel="v"):
    """영상(v)·소리(a) 줄기 하나의 실제 길이(초) — 다시 인코딩하지 않고 끝까지 읽어서 재요. 없으면 0."""
    r = _run([ff, "-hide_banner", "-i", str(path), "-map", f"0:{sel}:0", "-c", "copy", "-f", "null", "-"], 1800)
    m = re.findall(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr or "")
    return int(m[-1][0]) * 3600 + int(m[-1][1]) * 60 + float(m[-1][2]) if m and not r.returncode else 0.0


def verify(ff, src_info, out, src=None):
    """소리 보존·길이 확인(영상 줄기·소리 줄기를 따로 재요) → {"ok", "msg", ...}."""
    o = probe2(ff, out)
    sd = stream_dur(ff, src, "v") if src else 0.0
    sd = sd or float(src_info.get("dur") or 0)
    od = stream_dur(ff, out, "v") or float(o.get("dur") or 0)
    tol = max(0.25, sd * 0.01)
    res = {"src_dur": round(sd, 2), "out_dur": round(od, 2), "src_audio": bool(src_info.get("audio")), "out_audio": bool(o.get("audio")),
           "w": o.get("w"), "h": o.get("h"), "fps": o.get("fps")}
    probs = []
    if res["src_audio"] and not res["out_audio"]:
        probs.append("결과에 소리가 없어요")
    if res["src_audio"] and res["out_audio"] and src:
        sa, oa = stream_dur(ff, src, "a"), stream_dur(ff, out, "a")
        res["src_adur"], res["out_adur"] = round(sa, 2), round(oa, 2)
        if sa and abs(sa - oa) > tol:
            probs.append(f"소리 길이가 달라요(원본 {sa:.2f}초 · 결과 {oa:.2f}초)")
    if abs(sd - od) > tol:
        probs.append(f"영상 길이가 달라요(원본 {sd:.2f}초 · 결과 {od:.2f}초)")
    res["ok"] = not probs
    res["msg"] = ("소리·길이 확인: " + ("소리 그대로, " if res["src_audio"] else "원래 소리 없음, ") + f"길이 {sd:.2f}초 → {od:.2f}초") if not probs else "확인 필요: " + ", ".join(probs)
    return res


def compare_image(ff, src, out, t, label_font=None):
    """같은 시점의 원본(왼쪽)·결과(오른쪽) 반반 비교 그림."""
    b = grab(ff, out, t)
    a = grab(ff, src, t)
    if a is None or b is None:
        return None
    if max(b.size) > 1920:
        k = 1920 / max(b.size)
        b = b.resize((round(b.width * k), round(b.height * k)), Image.LANCZOS)
    a = a.resize(b.size, Image.LANCZOS)
    W, H = b.size
    im = Image.new("RGB", (W * 2 + 8, H), (20, 20, 20))
    im.paste(a, (0, 0))
    im.paste(b, (W + 8, 0))
    d = ImageDraw.Draw(im)
    f, kr = label_font or vmix.get_font(max(14, H // 24))
    for x, txt in ((10, "원본" if kr else "Before"), (W + 18, "복원" if kr else "After")):
        d.text((x, 8), txt, fill=(255, 255, 255), font=f, stroke_width=2, stroke_fill=(0, 0, 0))
    return im


def opts_key(src, opts):
    """같은 영상·같은 설정이면 같은 작업 폴더(끊겼을 때 이어서 하기)."""
    import hashlib
    st = Path(src).stat()
    return hashlib.sha1(json.dumps([str(src), st.st_size, int(st.st_mtime), opts], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def model_scale(name):
    m = re.search(r"(?<![0-9])([1-8])x|x([1-8])(?![0-9])", str(name or ""), re.I)
    return int(m.group(1) or m.group(2)) if m else 4


def even(v):
    return max(2, int(round(v / 2)) * 2)

