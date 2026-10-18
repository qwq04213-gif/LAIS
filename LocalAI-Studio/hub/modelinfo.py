# -*- coding: utf-8 -*-
"""모델 파일이 어느 계열인지 알아내요. .safetensors 맨 앞의 목록(헤더)만 읽어서 빨라요(모델을 불러오지 않아요).

계열: sd15, sdxl, sd3, flux, chroma, qwen, unknown
all_in_one: 텍스트 인코더·VAE까지 한 파일에 들어 있는 '체크포인트' 형태인지
"""
import json
import struct
from pathlib import Path

FAMILIES = {"sd15": "SD 1.5 계열", "sdxl": "SDXL · Illustrious · Pony · NoobAI", "sd3": "SD3 / SD3.5",
            "flux": "FLUX · Krea", "chroma": "Chroma", "qwen": "Qwen-Image", "unknown": "알 수 없음"}
_CACHE = {}


def read_keys(path, limit=64 * 1024 * 1024):
    """safetensors 헤더의 텐서 이름 목록. 읽을 수 없으면 None."""
    with open(path, "rb") as f:
        head = f.read(8)
        if len(head) < 8:
            return None
        n = struct.unpack("<Q", head)[0]
        if n <= 0 or n > limit:
            return None
        meta = json.loads(f.read(n).decode("utf-8"))
    return [k for k in meta if k != "__metadata__"]


def classify(keys):
    """텐서 이름들로 (계열, 올인원 여부) 판단."""
    ks = keys or []
    has = lambda s: any(s in k for k in ks)
    allin = has("first_stage_model.") or has("text_encoders.") or has("cond_stage_model") or has("conditioner.embedders")
    if has("distilled_guidance_layer"):
        return "chroma", allin
    if has("double_blocks.") and has("single_blocks."):
        return "flux", allin
    if has("joint_blocks."):
        return "sd3", allin
    if has("conditioner.embedders.1") or (has("input_blocks.") and has("label_emb")):
        return "sdxl", True
    if has("input_blocks.") or has("down_blocks."):
        return "sd15", has("cond_stage_model") or has("first_stage_model.")
    if has("transformer_blocks.") and (has("txt_in") or has("txt_norm")) and has("img_in"):
        return "qwen", allin
    return "unknown", allin


def by_name(name):
    n = name.lower()
    for fam, pat in (("chroma", ("chroma",)), ("qwen", ("qwen",)), ("flux", ("flux", "krea")), ("sd3", ("sd3",)),
                     ("sdxl", ("sdxl", "illustrious", "noobai", "pony")), ("sd15", ("sd15", "sd1.5", "v1-5"))):
        if any(p in n for p in pat):
            return fam
    return "unknown"


def detect(path):
    """{'family','all_in_one','how'} — how: header(헤더로 확인) / name(이름으로 추정)."""
    p = Path(path)
    try:
        key = (str(p), p.stat().st_mtime, p.stat().st_size)
    except OSError:
        return {"family": "unknown", "all_in_one": False, "how": "name"}
    if key in _CACHE:
        return _CACHE[key]
    out = None
    if p.suffix.lower() == ".safetensors":
        try:
            fam, allin = classify(read_keys(p))
            if fam != "unknown":
                out = {"family": fam, "all_in_one": allin, "how": "header"}
        except Exception:  # noqa: BLE001
            pass
    if out is None:
        out = {"family": by_name(p.name), "all_in_one": False, "how": "name"}
    _CACHE[key] = out
    return out
