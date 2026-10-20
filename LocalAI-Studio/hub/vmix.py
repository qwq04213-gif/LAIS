# -*- coding: utf-8 -*-
"""영상에 소리(음성·음악)와 자막 넣기. ffmpeg 를 한 번 불러서 합쳐요.
- 자막은 글자 그림(PNG)을 만들어 영상 위에 겹쳐서 넣어요(글꼴·libass 에 기대지 않아요).
- ffmpeg 는 스튜디오 폴더(engine/ffmpeg) → PATH → 내장 파이썬의 imageio-ffmpeg 순서로 찾아요."""
import os
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NOWIN = 0x08000000 if os.name == "nt" else 0
MAX_CUES = 200
MAX_MIN = 30                                        # 영상 길이 제한(분) — 너무 긴 건 오래 걸려요
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v")
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac")
FONT_CANDS = [
    r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\NanumGothicBold.ttf", r"C:\Windows\Fonts\NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


class Cancelled(Exception):
    pass


# ─────────────────────────── ffmpeg 찾기 · 읽기 ───────────────────────────
def find_ffmpeg(py=None, root=None):
    """ffmpeg 실행 파일 경로 (없으면 None)."""
    cands = []
    if root:
        for sub in ("engine/ffmpeg", "engine/ffmpeg/bin", "ffmpeg", "ffmpeg/bin"):
            for n in ("ffmpeg.exe", "ffmpeg"):
                cands.append(Path(root) / sub / n)
    for c in cands:
        if c.is_file():
            return str(c)
    w = shutil.which("ffmpeg")
    if w:
        return w
    if py and Path(py).exists():
        try:
            r = subprocess.run([str(py), "-s", "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"], capture_output=True, text=True,
                               timeout=60, creationflags=NOWIN)
            out = [x for x in (r.stdout or "").strip().splitlines() if x.strip()]
            if r.returncode == 0 and out and Path(out[-1]).is_file():
                return out[-1].strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def ff_version(ff):
    try:
        r = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, text=True, timeout=30, creationflags=NOWIN)
        m = re.search(r"version\D*(\d+)\.(\d+)", r.stdout or "")
        return (int(m.group(1)), int(m.group(2))) if m else (4, 2)
    except (OSError, subprocess.SubprocessError):
        return (4, 2)


def probe(ff, path):
    """{dur, w, h, fps, video, audio} — ffmpeg -i 의 안내 글에서 읽어요."""
    r = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True, errors="replace", timeout=60, creationflags=NOWIN)
    t = r.stderr or ""
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", t)
    out = {"dur": (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else 0.0, "w": 0, "h": 0, "fps": 24.0, "video": False, "audio": False}
    for ln in t.splitlines():
        if "Video:" in ln and "attached pic" not in ln and not out["video"]:
            out["video"] = True
            s = re.search(r",\s*(\d{2,5})x(\d{2,5})[\s,\[]", ln)
            if s:
                out["w"], out["h"] = int(s.group(1)), int(s.group(2))
            f = re.search(r"(\d+(?:\.\d+)?)\s*fps", ln)
            if f:
                out["fps"] = float(f.group(1))
        elif "Audio:" in ln:
            out["audio"] = True
    return out


# ─────────────────────────── 자막 글 읽기 ───────────────────────────
_T = r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?"
CUE_ARROW = re.compile(r"^\s*" + _T + r"\s*(?:-->|~|–|—|-)\s*" + _T + r"\s*(.*)$")


def _secs(h, m, s, ms):
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + (float("0." + ms) if ms else 0.0)


def _clean(t):
    t = re.sub(r"\{\\[^}]*\}", "", t)
    t = re.sub(r"</?[a-zA-Z][^>]*>", "", t)
    return t.strip()


def parse_subs(text, start=0.0, end=None):
    """자막 글 → [{s, e, text}].
    시간이 적힌 글(SRT, '0:01 ~ 0:03 문장')은 그대로, 시간이 없는 글은 줄(긴 줄은 문장)마다 start~end 사이에 글자 수대로 나눠요."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    timed, untimed, cur = [], [], None
    for ln in lines:
        s = ln.strip().lstrip("\ufeff")
        m = CUE_ARROW.match(s) if s else None
        if m:
            g = m.groups()
            cur = {"s": _secs(*g[0:4]), "e": _secs(*g[4:8]), "text": [_clean(g[8])] if _clean(g[8]) else []}
            timed.append(cur)
            continue
        if not s:
            cur = None
            continue
        if cur is not None:
            cur["text"].append(_clean(s))
            continue
        if timed and re.fullmatch(r"\d+", s):             # SRT 번호 줄
            continue
        if not timed:
            untimed.append(_clean(s))
    if timed:
        cues = [{"s": c["s"], "e": c["e"], "text": "\n".join(x for x in c["text"] if x)} for c in timed]
        return [c for c in cues if c["text"] and c["e"] > c["s"]][:MAX_CUES]
    items = []
    for ln in untimed:
        if not ln:
            continue
        parts = [x.strip() for x in re.split(r"(?<=[.!?。！？…])\s+", ln)] if len(ln) > 40 else [ln]
        items += [x for x in parts if x]
    if not items:
        return []
    end = start + 3.0 * len(items) if end is None else end
    total = max(0.5, end - start)
    w = [len(re.sub(r"\s", "", t)) + 6 for t in items]
    t0, cues = start, []
    for t, k in zip(items, w):
        d = total * k / sum(w)
        cues.append({"s": t0, "e": t0 + d, "text": t})
        t0 += d
    return cues[:MAX_CUES]


def srt_time(t):
    t = max(0.0, t)
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def to_srt(cues):
    return "".join(f"{i}\n{srt_time(c['s'])} --> {srt_time(c['e'])}\n{c['text']}\n\n" for i, c in enumerate(cues, 1))


# ─────────────────────────── 자막 그림 ───────────────────────────
def get_font(size, path=""):
    """(글꼴, 한글 글꼴인지)"""
    for c in ([path] if path else []) + FONT_CANDS:
        try:
            if c and Path(c).is_file():
                return ImageFont.truetype(c, size), True
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size), False
    except TypeError:
        return ImageFont.load_default(), False


def _rgb(c, d=(255, 255, 255)):
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(c or ""))
    return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if m else d


def wrap(draw, text, font, maxw):
    out = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split(" "):
            t = (cur + " " + w) if cur else w
            if draw.textlength(t, font=font) <= maxw:
                cur = t
                continue
            if cur:
                out.append(cur)
                cur = ""
            if draw.textlength(w, font=font) <= maxw:
                cur = w
            else:
                piece = ""
                for ch in w:
                    if draw.textlength(piece + ch, font=font) <= maxw:
                        piece += ch
                    else:
                        out.append(piece)
                        piece = ch
                cur = piece
        out.append(cur)
    return [x for x in out if x] or [""]


def render_cue(text, W, H, st, path):
    """자막 한 칸을 W 너비의 투명 PNG 로 그려요. 돌려주는 값: (y 위치, 한글 글꼴을 썼는지)"""
    size = max(14, int(H * float(st.get("size", 5.5)) / 100))
    font, kor = get_font(size, st.get("font", ""))
    probe_im = Image.new("RGBA", (8, 8))
    d0 = ImageDraw.Draw(probe_im)
    lines = wrap(d0, text, font, W * 0.88)
    sw = max(2, size // 11) if st.get("outline", True) else 0
    lh = int(size * 1.28)
    pad = int(size * 0.45) if st.get("bg") else sw + 2
    bh = lh * len(lines) + pad * 2
    im = Image.new("RGBA", (W, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    widths = [d.textlength(x, font=font) for x in lines]
    if st.get("bg"):
        bw = max(widths) + pad * 2
        d.rounded_rectangle((int((W - bw) / 2), 0, int((W + bw) / 2), bh - 1), radius=int(size * 0.3), fill=(0, 0, 0, 150))
    col = _rgb(st.get("color"))
    for i, (x, w) in enumerate(zip(lines, widths)):
        d.text(((W - w) / 2, pad + i * lh + (lh - size) / 2 - size * 0.08), x, font=font, fill=col + (255,),
               stroke_width=sw, stroke_fill=(0, 0, 0, 255))
    pos = st.get("pos", "bottom")
    margin = int(H * 0.05)
    y = margin if pos == "top" else (H - bh) // 2 if pos == "middle" else H - bh - margin
    im.save(path, "PNG")
    return max(0, y), kor


# ─────────────────────────── 합치기 ───────────────────────────
def make(ff, job, work, say=None, cancel=None):
    """job: video, audio(없으면 None), amode('replace'|'mix'), vol, ovol, delay, fit('video'|'audio'), fade, subs(글), size, pos, color, outline, bg, font
    돌려주는 값: {out(경로), srt(글), dur, warn[]}"""
    say = say or (lambda m, p=None: None)
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    warn = []
    vi = probe(ff, job["video"])
    if not vi["video"] or vi["dur"] <= 0:
        raise ValueError("영상을 읽지 못했어요. 다른 영상으로 해 보세요.")
    if vi["dur"] > MAX_MIN * 60:
        raise ValueError(f"영상이 너무 길어요({int(vi['dur'] // 60)}분). {MAX_MIN}분 이하로 해 주세요.")
    vdur = vi["dur"]
    W, H = vi["w"] - vi["w"] % 2, vi["h"] - vi["h"] % 2
    ai = None
    delay = max(0.0, min(float(job.get("delay") or 0), 600))
    if job.get("audio"):
        ai = probe(ff, job["audio"])
        if not ai["audio"] or ai["dur"] <= 0:
            raise ValueError("소리 파일을 읽지 못했어요. wav · mp3 · m4a · ogg · flac 파일로 해 보세요.")
    out_len = vdur
    if ai and job.get("fit") == "audio":
        out_len = max(vdur, delay + ai["dur"])
    ver = ff_version(ff)
    # 자막
    cues = []
    text = (job.get("subs") or "").strip()
    if text:
        t0, t1 = (delay, min(out_len, delay + ai["dur"])) if ai else (0.0, vdur)
        if t1 - t0 < 0.5:
            t0, t1 = 0.0, out_len
        cues = parse_subs(text, t0, t1)
        cues = [dict(c, s=max(0.0, c["s"]), e=min(out_len, c["e"])) for c in cues if c["s"] < out_len]
        cues = [c for c in cues if c["e"] > c["s"] + 0.05]
        if not cues:
            warn.append("자막 글에서 넣을 줄을 찾지 못했어요. (시간이 적힌 줄이 영상 길이를 벗어났을 수 있어요)")
    st = {k: job.get(k) for k in ("size", "pos", "color", "outline", "bg", "font")}
    if st["size"] is None:
        st["size"] = 5.5
    inputs = ["-i", str(job["video"])]
    vsteps = []
    if out_len > vdur + 0.05:
        vsteps.append(f"tpad=stop_mode=clone:stop_duration={out_len - vdur:.3f}")
    vsteps.append("scale=%d:%d" % (W, H))
    parts = ["[0:v]" + ",".join(vsteps) + "[v0]"]
    n_in = 1
    if ai:
        inputs += ["-i", str(job["audio"])]
        n_in += 1
    kor_ok = True
    for i, c in enumerate(cues):
        png = work / f"cue{i}.png"
        y, kor = render_cue(c["text"], W, H, st, png)
        kor_ok = kor_ok and kor
        inputs += ["-i", str(png)]
        parts.append(f"[v{i}][{n_in}:v]overlay=0:{y}:enable='between(t,{c['s']:.3f},{c['e']:.3f})'[v{i + 1}]")
        n_in += 1
    if cues and not kor_ok and re.search(r"[\u3131-\uD7A3]", text):
        warn.append("한글 글꼴을 찾지 못해 자막 글자가 네모로 보일 수 있어요. 윈도우의 맑은 고딕이 있으면 자동으로 써요.")
    parts.append(f"[v{len(cues)}]format=yuv420p[vout]")
    # 소리
    has_a = None
    vol, ovol = max(0.0, min(float(job.get("vol", 1)), 3)), max(0.0, min(float(job.get("ovol", 1)), 3))
    fmt = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    labels = []
    if ai:
        ms = int(delay * 1000)
        parts.append(f"[1:a]{fmt}" + (f",adelay={ms}|{ms}" if ms > 0 else "") + f",volume={vol:.3f}[an]")
        labels.append("an")
        if vi["audio"] and job.get("amode") == "mix":
            parts.append(f"[0:a]{fmt},volume={ovol:.3f}[ao]")
            labels.insert(0, "ao")
    elif vi["audio"]:
        parts.append(f"[0:a]{fmt},volume={ovol:.3f}[ao]")
        labels.append("ao")
    if labels:
        if len(labels) == 2:
            nrm = ":normalize=0" if ver >= (4, 4) else ""
            parts.append("[" + "][".join(labels) + f"]amix=inputs=2:duration=longest:dropout_transition=0{nrm}" + ("" if ver >= (4, 4) else ",volume=2") + "[am]")
            last = "am"
        else:
            last = labels[0]
        tail = f"[{last}]atrim=end={out_len:.3f}"
        if job.get("fade", True) and ai and delay + ai["dur"] > out_len + 0.05:
            tail += f",afade=t=out:st={max(0.0, out_len - 0.6):.3f}:d=0.6"
        parts.append(tail + ",apad[aout]")
        has_a = "aout"
    graph = ";".join(parts)
    cmd = [ff, "-hide_banner", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1"] + inputs
    if len(graph) > 8000:
        gp = work / "graph.txt"
        gp.write_text(graph, encoding="utf-8")
        cmd += ["-filter_complex_script", str(gp)]
    else:
        cmd += ["-filter_complex", graph]
    cmd += ["-map", "[vout]"] + (["-map", "[aout]"] if has_a else ["-an"])
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
    if has_a:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    outp = work / "out.mp4"
    cmd += ["-t", f"{out_len:.3f}", "-movflags", "+faststart", str(outp)]
    errf = work / "ffmpeg.err"
    with open(errf, "wb") as ef:
        pr = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=ef, text=True, errors="replace", creationflags=NOWIN)
        try:
            for ln in pr.stdout:
                if cancel and cancel():
                    pr.kill()
                    raise Cancelled("중단했어요.")
                m = re.match(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)", ln.strip())
                if m:
                    t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                    say("영상에 소리·자막을 합치는 중…", min(0.99, t / max(out_len, 0.1)))
            pr.wait()
        finally:
            if pr.poll() is None:
                pr.kill()
    if pr.returncode != 0 or not outp.is_file():
        tail = errf.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
        raise RuntimeError("ffmpeg 로 합치지 못했어요: " + " / ".join(tail)[-500:])
    return {"out": outp, "srt": to_srt(cues) if cues else "", "dur": out_len, "warn": warn, "cues": len(cues)}
