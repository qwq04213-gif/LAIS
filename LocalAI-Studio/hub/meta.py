# -*- coding: utf-8 -*-
"""이미지 메타데이터: 읽기(PNG 텍스트·EXIF, A1111/ComfyUI/NovelAI/InvokeAI/캐릭터 카드), 제거, 기록.

표준 라이브러리 + Pillow 만 사용합니다.
"""
import base64
import io
import json
import re
import struct
import zlib

from PIL import Image, ImageOps, PngImagePlugin
from PIL.ExifTags import TAGS

# 큰 ComfyUI 워크플로가 들어 있는 PNG 도 열 수 있게 Pillow 의 텍스트 청크 한도를 올립니다(로컬 도구라 안전).
PngImagePlugin.MAX_TEXT_CHUNK = 64 * 1024 * 1024
PngImagePlugin.MAX_TEXT_MEMORY = 256 * 1024 * 1024

PNG_SIG = b"\x89PNG\r\n\x1a\n"
MAXTXT = 300_000  # 화면으로 보낼 텍스트 한 덩어리의 최대 길이


# ───────────────────────── PNG 청크 ─────────────────────────
def png_chunks(data):
    """(종류, 내용, 원본 바이트) 를 차례로 돌려줍니다. 손상된 파일은 읽을 수 있는 곳까지만."""
    if not data.startswith(PNG_SIG):
        return
    i = 8
    while i + 12 <= len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        t = data[i + 4:i + 8]
        yield t, data[i + 8:i + 8 + n], data[i:i + 12 + n]
        i += 12 + n
        if t == b"IEND":
            return


def _dec(b):
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("latin-1")


def png_texts(data):
    out = {}
    for t, p, _ in png_chunks(data):
        try:
            if t == b"tEXt":
                k, _, v = p.partition(b"\x00")
                out[_dec(k)] = _dec(v)
            elif t == b"zTXt":
                k, _, v = p.partition(b"\x00")
                out[_dec(k)] = _dec(zlib.decompressobj().decompress(v[1:], 1 << 27))
            elif t == b"iTXt":
                k, _, rest = p.partition(b"\x00")
                flag, rest = rest[0], rest[2:]
                _, _, rest = rest.partition(b"\x00")
                _, _, txt = rest.partition(b"\x00")
                out[_dec(k)] = _dec(zlib.decompressobj().decompress(txt, 1 << 27) if flag else txt)
        except Exception:
            pass
    return out


# ───────────────────────── 샘플러 이름 변환 ─────────────────────────
_SAMP = {"euler": "euler", "euler a": "euler_ancestral", "heun": "heun", "dpm2": "dpm_2", "dpm2 a": "dpm_2_ancestral",
         "lms": "lms", "dpm fast": "dpm_fast", "dpm adaptive": "dpm_adaptive", "dpm++ 2s a": "dpmpp_2s_ancestral",
         "dpm++ 2m": "dpmpp_2m", "dpm++ sde": "dpmpp_sde", "dpm++ 2m sde": "dpmpp_2m_sde", "dpm++ 3m sde": "dpmpp_3m_sde",
         "ddim": "ddim", "unipc": "uni_pc", "lcm": "lcm",
         "k_euler": "euler", "k_euler_ancestral": "euler_ancestral", "k_dpmpp_2m": "dpmpp_2m", "k_dpmpp_sde": "dpmpp_sde",
         "k_dpmpp_2s_ancestral": "dpmpp_2s_ancestral"}
_SCH = {"karras": "karras", "exponential": "exponential", "sgm uniform": "sgm_uniform", "simple": "simple",
        "normal": "normal", "beta": "beta", "uniform": "simple", "automatic": None}
_REV = {v: k for k, v in {"Euler": "euler", "Euler a": "euler_ancestral", "Heun": "heun", "LMS": "lms", "DPM++ 2M": "dpmpp_2m",
                          "DPM++ SDE": "dpmpp_sde", "DPM++ 2M SDE": "dpmpp_2m_sde", "DPM++ 3M SDE": "dpmpp_3m_sde",
                          "DPM++ 2S a": "dpmpp_2s_ancestral", "DDIM": "ddim", "UniPC": "uni_pc", "LCM": "lcm"}.items()}


def map_sampler(name, schedule=None):
    """A1111 식 이름 → (ComfyUI sampler, scheduler)."""
    n, sch = (name or "").strip().lower(), None
    for suf, val in _SCH.items():
        if n.endswith(" " + suf):
            n, sch = n[: -len(suf) - 1].strip(), val
            break
    if schedule and schedule.strip().lower() in _SCH:
        sch = _SCH[schedule.strip().lower()] or sch
    return _SAMP.get(n, n.replace(" ", "_") or None), sch


def _num(v, cast=float):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


# ───────────────────────── A1111 / Forge 형식 ─────────────────────────
_PARAM = re.compile(r'\s*(\w[\w \-/]+):\s*("(?:\\.|[^\\"])+"|[^,]*)(?:,|$)')
_LORATAG = re.compile(r"<lora:([^:>]+)(?::(-?[\d.]+))?[^>]*>", re.I)


def parse_a1111(text):
    *lines, last = text.strip().split("\n")
    if len(_PARAM.findall(last)) < 3:
        lines.append(last)
        last = ""
    prompt, neg, done = [], [], False
    for line in lines:
        line = line.strip()
        if line.startswith("Negative prompt:"):
            done, line = True, line[16:].strip()
        (neg if done else prompt).append(line)
    raw = {k: v.strip().strip('"') for k, v in _PARAM.findall(last)}
    prompt = "\n".join(prompt).strip()
    s, sch = map_sampler(raw.get("Sampler"), raw.get("Schedule type"))
    m = re.match(r"^(\d+)x(\d+)$", raw.get("Size", ""))
    return {"prompt": prompt, "negative": "\n".join(neg).strip(), "raw": raw,
            "params": {"steps": _num(raw.get("Steps"), int), "cfg": _num(raw.get("CFG scale")),
                       "seed": _num(raw.get("Seed"), int), "sampler": s, "scheduler": sch,
                       "w": int(m.group(1)) if m else None, "h": int(m.group(2)) if m else None,
                       "clip_skip": _num(raw.get("Clip skip"), int), "denoise": _num(raw.get("Denoising strength")),
                       "model": raw.get("Model"),
                       "loras": [[n, _num(w) if w else 1.0] for n, w in _LORATAG.findall(prompt)]}}


# ───────────────────────── ComfyUI(API 그래프) ─────────────────────────
_TEXTKEYS = ("text", "prompt", "text_g")


def _text_upstream(g, ref):
    queue, seen = [ref], set()
    while queue and len(seen) < 60:
        r = queue.pop(0)
        if not (isinstance(r, list) and len(r) == 2) or str(r[0]) in seen or str(r[0]) not in g:
            continue
        seen.add(str(r[0]))
        ins = g[str(r[0])].get("inputs", {})
        for k in _TEXTKEYS:
            if isinstance(ins.get(k), str):
                return ins[k]
        queue += [v for v in ins.values() if isinstance(v, list)]
    return ""


def comfy_norm(g):
    nodes = [n for n in g.values() if isinstance(n, dict)]
    ks = [n for n in nodes if n.get("class_type") in ("KSampler", "KSamplerAdvanced")]
    ks.sort(key=lambda n: 0 if _num(n["inputs"].get("denoise", 1.0)) in (1, 1.0, None) else 1)
    p = {}
    out = {"prompt": "", "negative": "", "params": p}
    if ks:
        i = ks[0]["inputs"]
        out["prompt"] = _text_upstream(g, i.get("positive"))
        out["negative"] = _text_upstream(g, i.get("negative"))
        p.update(steps=_num(i.get("steps"), int), cfg=_num(i.get("cfg")), sampler=i.get("sampler_name"),
                 scheduler=i.get("scheduler"), denoise=_num(i.get("denoise")),
                 seed=_num(i.get("seed", i.get("noise_seed")), int))
    for n in nodes:
        i, c = n.get("inputs", {}), n.get("class_type", "")
        if c in ("EmptyLatentImage", "EmptySD3LatentImage") and "w" not in p:
            p["w"], p["h"] = _num(i.get("width"), int), _num(i.get("height"), int)
        if c == "CheckpointLoaderSimple" and "model" not in p:
            p["model"] = i.get("ckpt_name")
        if c == "UNETLoader" and "model" not in p:
            p["model"] = i.get("unet_name")
        if c == "CLIPSetLastLayer" and _num(i.get("stop_at_clip_layer"), int):
            p["clip_skip"] = -_num(i.get("stop_at_clip_layer"), int)
        if isinstance(i.get("lora_name"), str):
            p.setdefault("loras", []).append([i["lora_name"], _num(i.get("strength_model"))])
    return out


# ───────────────────────── 캐릭터 카드(SillyTavern 등) ─────────────────────────
def parse_card(raw_b64):
    d = json.loads(base64.b64decode(raw_b64 + "=" * (-len(raw_b64) % 4)).decode("utf-8", "replace"))
    d = d.get("data", d) if isinstance(d, dict) else {}
    keys = ("name", "description", "personality", "scenario", "first_mes", "mes_example", "system_prompt",
            "post_history_instructions", "creator_notes")
    card = {k: str(d.get(k) or "")[:20000] for k in keys}
    card["alternate_greetings"] = [str(x)[:5000] for x in (d.get("alternate_greetings") or [])][:10]
    card["tags"] = [str(x) for x in (d.get("tags") or [])][:30]
    return card


# ───────────────────────── EXIF ─────────────────────────
def _usercomment(b):
    if isinstance(b, str):
        return b
    head, body = bytes(b[:8]), bytes(b[8:])
    if head.startswith(b"UNICODE"):
        s = body.decode("utf-16-be", "replace")
        if s.count("\x00") > len(s) // 4 or not re.search(r"[A-Za-z가-힣]", s):
            s = body.decode("utf-16-le", "replace")
        return s.strip("\x00")
    return body.decode("utf-8", "replace").strip("\x00")


def _fmt(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")[:200] if len(v) < 200 and v.isascii() else f"<{len(v)} bytes>"
    if hasattr(v, "numerator"):
        try:
            return f"{float(v):.6g}"
        except Exception:
            return str(v)
    if isinstance(v, (tuple, list)):
        return ", ".join(_fmt(x) for x in v[:12])
    return str(v)[:300]


def _dms(v, ref):
    try:
        d, m, s = (float(x) for x in v)
        r = d + m / 60 + s / 3600
        return -r if str(ref).upper().startswith(("S", "W")) else r
    except Exception:
        return None


def exif_info(im):
    """(행 목록, GPS 또는 None, UserComment 텍스트)"""
    try:
        ex = im.getexif()
    except Exception:
        return [], None, ""
    rows, uc, tags = [], "", dict(ex)
    try:
        tags.update(ex.get_ifd(0x8769))
    except Exception:
        pass
    for k, v in tags.items():
        if k in (0x927C, 0x8769, 0x8825, 0xA005, 0x0201, 0x0202, 0x02BC):
            continue
        if k == 0x9286:
            uc = _usercomment(v)
            rows.append(["UserComment", uc[:300] + ("…" if len(uc) > 300 else "")])
            continue
        rows.append([TAGS.get(k, f"0x{k:04x}"), _fmt(v)])
    gps = None
    try:
        g = ex.get_ifd(0x8825)
        if g.get(2) and g.get(4):
            lat, lon = _dms(g[2], g.get(1, "N")), _dms(g[4], g.get(3, "E"))
            if lat is not None and lon is not None:
                gps = {"lat": round(lat, 6), "lon": round(lon, 6)}
    except Exception:
        pass
    return rows, gps, uc


# ───────────────────────── 종합 읽기 ─────────────────────────
def read(data):
    try:
        im = Image.open(io.BytesIO(data))
    except Exception:
        if not data.startswith(PNG_SIG):
            raise
        im = None  # Pillow 가 못 여는 PNG 라도 직접 파싱한 텍스트·크기는 보여 줍니다
    if im is None:
        w, h = struct.unpack(">II", data[16:24])
        fmt, f = "PNG", {"format": "PNG", "w": w, "h": h, "mode": "?", "bytes": len(data), "frames": 1, "icc": False}
        rows, gps, uc = [], None, ""
    else:
        fmt = im.format
        f = {"format": fmt, "w": im.width, "h": im.height, "mode": im.mode, "bytes": len(data),
             "frames": getattr(im, "n_frames", 1), "icc": bool(im.info.get("icc_profile"))}
        if im.info.get("dpi"):
            try:
                f["dpi"] = [round(float(x)) for x in im.info["dpi"]]
            except Exception:
                pass
        rows, gps, uc = exif_info(im)
    texts = png_texts(data) if fmt == "PNG" else {}
    out = {"file": f, "kind": "none", "gen": None, "comfy": None, "card": None, "text": {}, "exif": rows, "gps": gps}

    if "chara" in texts or "ccv3" in texts:
        try:
            out["card"], out["kind"] = parse_card(texts.get("ccv3") or texts["chara"]), "card"
        except Exception:
            pass
    params = texts.get("parameters") or (uc if re.search(r"Steps:\s*\d+", uc or "") else "")
    if params and not params.lstrip().startswith("{"):
        out["gen"], out["kind"] = parse_a1111(params), "a1111"
    try:
        g = json.loads(texts["prompt"]) if "prompt" in texts else None
        if isinstance(g, dict) and any(isinstance(v, dict) and "class_type" in v for v in g.values()):
            out["comfy"] = g
            if not out["gen"]:
                out["gen"], out["kind"] = comfy_norm(g), "comfyui"
    except ValueError:
        pass
    if texts.get("Software") == "NovelAI" and "Comment" in texts:
        try:
            c = json.loads(texts["Comment"])
            s, _ = map_sampler(c.get("sampler"))
            out["gen"] = {"prompt": c.get("prompt", ""), "negative": c.get("uc", ""), "raw": {},
                          "params": {"steps": c.get("steps"), "cfg": c.get("scale"), "seed": c.get("seed"), "sampler": s,
                                     "scheduler": None, "w": c.get("width"), "h": c.get("height"), "model": "NovelAI"}}
            out["kind"] = "novelai"
        except ValueError:
            pass
    if "invokeai_metadata" in texts:
        try:
            c = json.loads(texts["invokeai_metadata"])
            m = c.get("model")
            out["gen"] = {"prompt": c.get("positive_prompt", ""), "negative": c.get("negative_prompt", ""), "raw": {},
                          "params": {"steps": c.get("steps"), "cfg": c.get("cfg_scale"), "seed": c.get("seed"),
                                     "sampler": c.get("scheduler"), "scheduler": None, "w": c.get("width"),
                                     "h": c.get("height"), "model": m.get("name") if isinstance(m, dict) else m}}
            out["kind"] = "invoke"
        except ValueError:
            pass
    if "hub" in texts:
        out["kind"] = "hub"
    out["text"] = {k: v[:MAXTXT] for k, v in texts.items() if k not in ("chara", "ccv3")}
    out["text_truncated"] = [k for k, v in texts.items() if len(v) > MAXTXT]
    return out


# ───────────────────────── 메타데이터 제거 ─────────────────────────
_PNG_KEEP = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"pHYs",
             b"acTL", b"fcTL", b"fdAT", b"bKGD", b"cICP"}


def _strip_jpeg(data):
    out, i = [data[:2]], 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        m = data[i + 1]
        if m == 0xDA:
            out.append(data[i:])
            return b"".join(out)
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            out.append(data[i:i + 2])
            i += 2
            continue
        n = struct.unpack(">H", data[i + 2:i + 4])[0]
        if not (m in (0xE1, 0xED, 0xFE) or 0xE3 <= m <= 0xEC or m == 0xEF):  # EXIF/XMP/IPTC/주석 제거, JFIF·ICC·Adobe 유지
            out.append(data[i:i + 2 + n])
        i += 2 + n
    out.append(data[i:])
    return b"".join(out)


def strip(data):
    """(바이트, 확장자, 안내문). PNG·JPEG 는 화질 손실 없이 메타데이터 청크/세그먼트만 제거합니다."""
    if data.startswith(PNG_SIG):
        return PNG_SIG + b"".join(r for t, _, r in png_chunks(data) if t in _PNG_KEEP), "png", "화질 손실 없이 텍스트·EXIF 청크를 제거했어요."
    if data[:2] == b"\xff\xd8":
        im = Image.open(io.BytesIO(data))
        if (im.getexif().get(0x0112) or 1) != 1:  # 방향 정보가 있으면 EXIF 만 지우면 사진이 돌아가 버림 → 다시 인코딩
            b = io.BytesIO()
            ImageOps.exif_transpose(im).convert("RGB").save(b, "JPEG", quality=95, subsampling=0)
            return b.getvalue(), "jpg", "회전 정보가 있어 방향을 반영해 JPEG 를 다시 인코딩했어요(품질 95)."
        return _strip_jpeg(data), "jpg", "화질 손실 없이 EXIF/XMP/GPS 를 제거했어요."
    im = Image.open(io.BytesIO(data))
    b = io.BytesIO()
    if im.format == "WEBP":
        ImageOps.exif_transpose(im).save(b, "WEBP", lossless=True)
        return b.getvalue(), "webp", "WebP 를 무손실로 다시 저장하며 메타데이터를 제거했어요."
    ImageOps.exif_transpose(im).convert("RGBA" if "A" in im.getbands() else "RGB").save(b, "PNG")
    return b.getvalue(), "png", "PNG 로 변환하며 메타데이터를 제거했어요."


# ───────────────────────── 결과 이미지에 기록 ─────────────────────────
def a1111_text(i):
    """i: prompt, negative, steps, cfg, sampler, scheduler, seed, w, h, model, clip_skip, loras, extra(dict)"""
    prompt = i["prompt"] + "".join(f" <lora:{n}:{w}>" for n, w in i.get("loras", []))
    parts = [f"Steps: {i['steps']}", f"Sampler: {_REV.get(i['sampler'], i['sampler'])}"]
    if i.get("scheduler"):
        parts.append(f"Schedule type: {str(i['scheduler']).replace('_', ' ').title()}")
    parts += [f"CFG scale: {i['cfg']}", f"Seed: {i['seed']}", f"Size: {i['w']}x{i['h']}", f"Model: {i.get('model', '')}"]
    if i.get("clip_skip"):
        parts.append(f"Clip skip: {i['clip_skip']}")
    parts += [f"{k}: {v}" for k, v in (i.get("extra") or {}).items()]
    parts.append("Version: LocalAI Studio")
    return f"{prompt}\nNegative prompt: {i.get('negative', '')}\n{', '.join(parts)}"


def pnginfo(i, graph=None):
    pi = PngImagePlugin.PngInfo()
    if i.get("sampler"):
        pi.add_text("parameters", a1111_text(i))
    pi.add_text("hub", json.dumps({k: v for k, v in i.items()}, ensure_ascii=False))
    if graph:
        pi.add_text("prompt", json.dumps(graph, ensure_ascii=False))
    return pi
