# -*- coding: utf-8 -*-
"""소리 복원(ffmpeg 만 씀): 웅웅·윙(험)·딱딱(클릭)·쉬익(노이즈) 줄이기, 음량 맞추기(2단계 loudnorm), 갈래 다시 섞기, 영상에 넣기."""
import json
import re
import subprocess
from pathlib import Path

import vmix

NOWIN = vmix.NOWIN
DENOISE = {"light": "afftdn=nr=8:nf=-50:tn=1", "medium": "afftdn=nr=14:nf=-45:tn=1", "strong": "afftdn=nr=24:nf=-40:tn=1"}
LOUD = {"speech": (-16.0, "말소리·유튜브"), "music": (-14.0, "음악 스트리밍"), "broadcast": (-23.0, "방송 기준"), "off": (None, "안 맞춤")}


def _run(cmd, timeout=3600):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=NOWIN)


def to_wav(ff, src, out, rate=44100, ch=2):
    """아무 소리·영상 파일 → wav(PCM 16bit)."""
    r = _run([ff, "-y", "-v", "error", "-i", src, "-vn", "-map", "0:a:0", "-ac", str(ch), "-ar", str(rate), "-c:a", "pcm_s16le", out])
    if r.returncode or not Path(out).is_file():
        if re.search(r"matches no streams|0:a:0", r.stderr or ""):
            raise RuntimeError("소리를 꺼내지 못했어요: 이 파일에는 소리가 없어요.")
        raise RuntimeError("소리를 꺼내지 못했어요: " + (r.stderr or "").strip().splitlines()[-1][-200:] if (r.stderr or "").strip() else "소리를 꺼내지 못했어요.")


def chain(o):
    """복원 필터 줄(음량 맞추기 빼고)."""
    f = []
    if o.get("rumble"):
        f.append(f"highpass=f={int(o.get('rumble_hz') or 70)}")
    if o.get("hum") in ("50", "60"):
        h = int(o["hum"])
        f += [f"equalizer=f={h * k}:t=q:w={12 if k == 1 else 16}:g=-28" for k in (1, 2, 3, 4)]
    if o.get("declick"):
        f.append("adeclick=w=55:o=75")
    if o.get("denoise") in DENOISE:
        f.append(DENOISE[o["denoise"]])
    return f


def measure(ff, src, pre=None, target=-16.0):
    """loudnorm 1단계 측정 → {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"} (LUFS 등)."""
    af = ",".join((pre or []) + [f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json"])
    r = _run([ff, "-hide_banner", "-nostats", "-i", src, "-vn", "-af", af, "-f", "null", "-"])
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m[-1])
        return {k: float(d[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset") if k in d}
    except (ValueError, KeyError):
        return None


def restore(ff, src, out, o, rate=None, say=None):
    """src → out(wav). → {"steps": [...], "before": LUFS, "after": LUFS}"""
    f = chain(o)
    steps = []
    if o.get("rumble"):
        steps.append("웅웅(저음 잡음) 줄이기")
    if o.get("hum") in ("50", "60"):
        steps.append(f"윙 소리({o['hum']}Hz) 줄이기")
    if o.get("declick"):
        steps.append("딱딱 소리 줄이기")
    if o.get("denoise") in DENOISE:
        steps.append("쉬익 노이즈 줄이기")
    target = LOUD.get(o.get("loud") or "off", LOUD["off"])[0]
    say and say(0.1, "음량 재는 중")
    before = measure(ff, src)
    if target is not None:
        say and say(0.35, "음량 맞추기 준비 중")
        m = measure(ff, src, f, target)
        if m:
            f.append(f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                     f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        else:
            f.append(f"loudnorm=I={target}:TP=-1.5:LRA=11")
        steps.append(f"음량 맞추기({target:.0f} LUFS)")
    if not f:
        raise ValueError("고칠 항목을 하나 이상 골라 주세요.")
    say and say(0.6, "고치는 중")
    ar = ["-ar", str(rate)] if rate else []
    r = _run([ff, "-y", "-v", "error", "-i", src, "-vn", "-map", "0:a:0", "-af", ",".join(f), *ar, "-c:a", "pcm_s16le", out])
    if r.returncode or not Path(out).is_file():
        raise RuntimeError("소리를 고치지 못했어요: " + (r.stderr or "")[-300:])
    say and say(0.9, "결과 음량 재는 중")
    after = measure(ff, out)
    return {"steps": steps, "before": before and round(before["input_i"], 1), "after": after and round(after["input_i"], 1)}


def mix(ff, tracks, out):
    """[(경로, 볼륨 0~2)] → 섞은 wav(넘치지 않게 리미터)."""
    tracks = [(p, float(v)) for p, v in tracks if float(v) > 0.001]
    if not tracks:
        raise ValueError("소리를 켠 갈래가 없어요.")
    cmd = [ff, "-y", "-v", "error"]
    for p, _ in tracks:
        cmd += ["-i", p]
    fc = ";".join(f"[{i}:a]volume={v:.3f}[a{i}]" for i, (_, v) in enumerate(tracks))
    fc += ";" + "".join(f"[a{i}]" for i in range(len(tracks))) + f"amix=inputs={len(tracks)}:normalize=0:duration=longest,alimiter=limit=0.97[m]"
    r = _run(cmd + ["-filter_complex", fc, "-map", "[m]", "-c:a", "pcm_s16le", out])
    if r.returncode or not Path(out).is_file():
        raise RuntimeError("섞지 못했어요: " + (r.stderr or "")[-300:])


def mux(ff, video, audio, out):
    """영상의 소리를 새 소리로 바꿔요(영상은 다시 인코딩하지 않아요)."""
    r = _run([ff, "-y", "-v", "error", "-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-movflags", "+faststart", out])
    if r.returncode or not Path(out).is_file():
        raise RuntimeError("영상에 소리를 넣지 못했어요: " + (r.stderr or "")[-300:])
