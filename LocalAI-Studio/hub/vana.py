"""영상 분석·재편집(ffmpeg + numpy): 장면 전환 찾기, 대표 장면, 화질 표시(어두움·흐림), 무음 구간, 프레임 뽑기,
고른 구간만 이어 붙이기(무음 빼기 포함), 하이라이트 자동 고르기(점수), 자막 시간 옮기기.

AI(대사 받아쓰기·장면 설명·하이라이트 계획)는 허브가 따로 붙여요. 여기는 계산만 해요.
"""
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

import vmix

NOWIN = vmix.NOWIN
MAX_SHOTS = 240


def _run(cmd, timeout=3600):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=NOWIN)


def scenes(ff, src, dur, thr=0.32, min_len=1.0):
    """장면 전환 시각(초) 목록 → 샷 [(시작, 끝)]. 너무 짧은 샷은 앞 샷에 붙여요."""
    r = _run([ff, "-hide_banner", "-nostats", "-i", src, "-an", "-vf", f"scale=320:-2,select='gt(scene,{thr:.3f})',showinfo", "-f", "null", "-"])
    cuts = sorted({round(float(m.group(1)), 3) for m in re.finditer(r"pts_time:\s*([0-9.]+)", r.stderr or "")})
    edges = [0.0] + [c for c in cuts if 0.2 < c < dur - 0.2] + [dur]
    shots = []
    for a, b in zip(edges, edges[1:]):
        if shots and (b - a < min_len or shots[-1][1] - shots[-1][0] < min_len):
            shots[-1] = (shots[-1][0], b)
        else:
            shots.append((a, b))
    if len(shots) > MAX_SHOTS:                      # 너무 많으면 이웃끼리 합쳐요
        k = -(-len(shots) // MAX_SHOTS)
        shots = [(shots[i][0], shots[min(i + k, len(shots)) - 1][1]) for i in range(0, len(shots), k)]
    return shots or [(0.0, dur)]


def frame(ff, src, t, out, width=480):
    """t 초의 장면 한 장을 jpg 로."""
    r = _run([ff, "-y", "-hide_banner", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", out], 120)
    return r.returncode == 0 and Path(out).is_file()


def quality(img):
    """대표 장면의 밝기(0~255)·선명도(경계 세기). flags: dark(어두움) · blurry(흐림)."""
    g = img.convert("L")
    a = np.asarray(g, dtype=np.float32)
    e = np.asarray(g.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    bright, sharp = float(a.mean()), float(e.var())
    flags = (["dark"] if bright < 45 else []) + (["blurry"] if sharp < 60 else [])
    return {"bright": round(bright, 1), "sharp": round(sharp, 1)}, flags


def silences(ff, src, noise=-35, d=0.6):
    """무음 구간 [(시작, 끝)]."""
    r = _run([ff, "-hide_banner", "-nostats", "-i", src, "-vn", "-af", f"silencedetect=noise={noise}dB:d={d}", "-f", "null", "-"])
    out, s = [], None
    for ln in (r.stderr or "").splitlines():
        m = re.search(r"silence_start:\s*(-?[0-9.]+)", ln)
        if m:
            s = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end:\s*([0-9.]+)", ln)
        if m and s is not None:
            out.append((round(s, 3), round(float(m.group(1)), 3)))
            s = None
    return out


def extract_audio(ff, src, out):
    r = _run([ff, "-y", "-hide_banner", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out])
    return r.returncode == 0 and Path(out).is_file()


def frames(ff, src, fps, width, folder, start=0.0, dur=None):
    """영상 → fps 마다 프레임 png 목록(가로 width)."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-y", "-hide_banner", "-v", "error", "-ss", f"{start:.3f}", "-i", src] + (["-t", f"{dur:.3f}"] if dur else []) + \
          ["-vf", f"fps={fps},scale={width}:-2", str(Path(folder) / "f%05d.png")]
    r = _run(cmd)
    if r.returncode:
        raise RuntimeError("프레임을 뽑지 못했어요: " + (r.stderr or "")[-300:])
    return sorted(Path(folder).glob("f*.png"))


def minus(segs, holes, min_keep=0.3):
    """구간들에서 빈 구간(무음 등)을 빼요."""
    out = []
    for a, b in segs:
        cur = [(a, b)]
        for s, e in holes:
            nxt = []
            for x, y in cur:
                if e <= x or s >= y:
                    nxt.append((x, y))
                    continue
                if s > x:
                    nxt.append((x, s))
                if e < y:
                    nxt.append((e, y))
            cur = nxt
        out += [(round(x, 3), round(y, 3)) for x, y in cur if y - x >= min_keep]
    return out


def cut_concat(ff, src, segs, out, has_audio=True, size=None):
    """src 에서 segs(초)만 순서대로 잘라 한 영상으로(다시 인코딩)."""
    if not segs:
        raise ValueError("남길 구간이 없어요.")
    parts, labels = [], ""
    for k, (a, b) in enumerate(segs):
        sc = f",scale={size[0]}:{size[1]}" if size else ""
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS{sc},format=yuv420p[v{k}]")
        if has_audio:
            parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,aresample=48000[a{k}]")
            labels += f"[v{k}][a{k}]"
        else:
            labels += f"[v{k}]"
    n = len(segs)
    parts.append(labels + f"concat=n={n}:v=1:a={1 if has_audio else 0}" + ("[vc][ac]" if has_audio else "[vc]"))
    cmd = [ff, "-y", "-hide_banner", "-v", "error", "-i", src, "-filter_complex", ";".join(parts), "-map", "[vc]"] + (["-map", "[ac]", "-c:a", "aac", "-b:a", "192k"] if has_audio else []) + \
          ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    r = _run(cmd)
    if r.returncode:
        raise RuntimeError("영상을 자르지 못했어요: " + (r.stderr or "")[-400:])
    return sum(b - a for a, b in segs)


def remap_subs(subs, segs):
    """원본 시간의 자막 [{s,e,text}] → 잘라 붙인 영상의 시간으로."""
    out, base = [], 0.0
    for a, b in segs:
        for c in subs:
            s, e = max(a, c["s"]), min(b, c["e"])
            if e - s >= 0.2:
                out.append({"s": round(base + s - a, 3), "e": round(base + e - a, 3), "text": c["text"]})
        base += b - a
    return out


def auto_pick(shots, target, speech=None):
    """AI 없이 하이라이트 고르기: 대사가 있고 밝고 선명한 샷에 점수를 주고, 목표 길이까지 시간 순으로 담아요.
    shots: [{id,start,end,flags,...}] → [{id,start,end,reason}]"""
    speech = speech or []
    rows = []
    for s in shots:
        L = s["end"] - s["start"]
        talk = sum(max(0.0, min(s["end"], c["e"]) - max(s["start"], c["s"])) for c in speech)
        sc = 1.0 + min(1.0, talk / max(L, 0.1)) * 1.5 - 0.8 * ("dark" in s["flags"]) - 0.6 * ("blurry" in s["flags"]) - 0.3 * (L < 1.2)
        why = ", ".join(x for x in (("대사 있음" if talk > 0.5 else ""), ("밝고 선명함" if not s["flags"] else ""), ) if x) or "전체 흐름 유지"
        rows.append((sc, s, why))
    rows.sort(key=lambda r: -r[0])
    pick, tot = [], 0.0
    for sc, s, why in rows:
        L = s["end"] - s["start"]
        if tot >= target:
            break
        if tot + L > target * 1.15:
            L = max(1.0, target - tot)
            if L < 1.0:
                continue
        pick.append({"id": s["id"], "start": s["start"], "end": round(s["start"] + L, 3), "reason": why})
        tot += L
    return sorted(pick, key=lambda r: r["start"])
