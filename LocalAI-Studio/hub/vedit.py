"""영상 편집(ffmpeg): 여러 영상 이어 붙이기, 구간 자르기, AI 이어 그리기용 입력 만들기.

ComfyUI 없이 ffmpeg 만 써요. 입력 확인(길이·크기·소리)은 vmix.probe 를 그대로 써요.
"""
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image

import vmix

NOWIN = vmix.NOWIN


def _run(cmd, timeout=1800):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=NOWIN)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 처리에 실패했어요: " + (r.stderr or "").strip()[-400:])
    return r


def even(n):
    return max(2, int(round(n / 2)) * 2)


def concat(ff, files, out, fade=0.0, size=None, fps=None):
    """files 를 순서대로 한 영상으로. 크기·초당 장면 수는 첫 영상(또는 size·fps)에 맞추고, 소리가 없는 영상은 무음으로 채워요.
    fade>0 이면 영상 사이를 그 시간만큼 겹쳐 부드럽게 넘겨요. 돌려주는 값: 전체 길이(초)"""
    if len(files) < 2:
        raise ValueError("이어 붙일 영상을 두 개 이상 골라 주세요.")
    infos = [vmix.probe(ff, f) for f in files]
    for f, i in zip(files, infos):
        if not i.get("video") or not i.get("dur"):
            raise ValueError(f"영상으로 읽을 수 없는 파일이에요: {Path(f).name}")
    W, H = size or (even(infos[0]["w"]), even(infos[0]["h"]))
    F = fps or min(60.0, max(8.0, float(infos[0].get("fps") or 24)))
    cmd, parts = [ff, "-y", "-hide_banner", "-v", "error"], []
    for f in files:
        cmd += ["-i", f]
    for k, i in enumerate(infos):
        parts.append(f"[{k}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
                     f"setsar=1,fps={F:g},format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v{k}]")
        if i.get("audio"):
            parts.append(f"[{k}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{k}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={i['dur']:.3f},aformat=sample_fmts=fltp[a{k}]")
    n = len(files)
    fade = max(0.0, min(float(fade or 0), min(i["dur"] for i in infos) / 2 - 0.05))
    if fade > 0:
        vprev, aprev, off = "v0", "a0", 0.0
        for k in range(1, n):
            off += infos[k - 1]["dur"] - fade
            parts.append(f"[{vprev}][v{k}]xfade=transition=fade:duration={fade:.3f}:offset={off:.3f}[vx{k}]")
            parts.append(f"[{aprev}][a{k}]acrossfade=d={fade:.3f}[ax{k}]")
            vprev, aprev = f"vx{k}", f"ax{k}"
        vout, aout = vprev, aprev
        total = sum(i["dur"] for i in infos) - fade * (n - 1)
    else:
        parts.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
        vout, aout = "vc", "ac"
        total = sum(i["dur"] for i in infos)
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{vout}]", "-map", f"[{aout}]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    _run(cmd)
    return total


def trim(ff, src, out, start, end):
    """src 의 start~end(초) 구간만 남겨요(정확한 위치에서 자르려고 다시 인코딩해요). 돌려주는 값: 남은 길이(초)"""
    info = vmix.probe(ff, src)
    dur = float(info.get("dur") or 0)
    if not info.get("video") or dur <= 0:
        raise ValueError("영상으로 읽을 수 없는 파일이에요.")
    s, e = max(0.0, float(start or 0)), min(dur, float(end if end not in (None, "") else dur))
    if e - s < 0.1:
        raise ValueError(f"남길 구간이 너무 짧아요. 시작은 끝보다 앞이어야 하고, 이 영상은 {dur:.1f}초예요.")
    cmd = [ff, "-y", "-hide_banner", "-v", "error", "-ss", f"{s:.3f}", "-i", src, "-t", f"{e - s:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
    cmd += (["-c:a", "aac", "-b:a", "192k"] if info.get("audio") else ["-an"]) + ["-movflags", "+faststart", out]
    _run(cmd)
    return e - s


def extend_inputs(ff, src, work, ctx=16, new=48, fps=16, area=832 * 480):
    """AI 이어 그리기(Wan VACE)에 넣을 '조절 영상'과 '가림 영상'을 만들어요.
    앞 ctx 장면 = 원본의 마지막 장면들(그대로 두기), 뒤 new 장면 = 회색(새로 그리기). 가림 영상은 둘을 검정/흰색으로 표시해요.
    돌려주는 값: dict(control, mask, w, h, length, ctx, fps, src_info)"""
    info = vmix.probe(ff, src)
    if not info.get("video") or not info.get("dur"):
        raise ValueError("영상으로 읽을 수 없는 파일이에요.")
    k = (area / max(1, info["w"] * info["h"])) ** 0.5
    w, h = (max(256, min(1280, int(round(x * k / 16)) * 16)) for x in (info["w"], info["h"]))
    length = 4 * math.ceil((ctx + new - 1) / 4) + 1              # Wan 은 4k+1 장면
    fr = Path(work) / "frames"
    shutil.rmtree(fr, ignore_errors=True)
    fr.mkdir(parents=True, exist_ok=True)
    back = ctx / fps + 0.6
    _run([ff, "-y", "-hide_banner", "-v", "error", "-sseof", f"-{back:.2f}", "-i", src,
          "-vf", f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}", str(fr / "%04d.png")])
    got = sorted(fr.glob("*.png"))
    if not got:
        raise RuntimeError("원본 영상의 마지막 장면을 읽지 못했어요.")
    last = got[-ctx:]
    while len(last) < ctx:                                      # 너무 짧은 영상: 첫 장면을 앞에 채워요
        last.insert(0, last[0])
    cdir, mdir = Path(work) / "ctl", Path(work) / "msk"
    for d in (cdir, mdir):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    gray, black, white = Image.new("RGB", (w, h), (128, 128, 128)), Image.new("RGB", (w, h), 0), Image.new("RGB", (w, h), (255, 255, 255))
    for i in range(length):
        (Image.open(last[i]).convert("RGB") if i < ctx else gray).save(cdir / f"{i:04d}.png")
        (black if i < ctx else white).save(mdir / f"{i:04d}.png")
    ctl, msk = Path(work) / "control.mp4", Path(work) / "mask.mp4"
    for d, o in ((cdir, ctl), (mdir, msk)):
        _run([ff, "-y", "-hide_banner", "-v", "error", "-framerate", str(fps), "-i", str(d / "%04d.png"),
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "8", "-pix_fmt", "yuv420p", o])
    return dict(control=ctl, mask=msk, w=w, h=h, length=length, ctx=ctx, fps=fps, src_info=info)
