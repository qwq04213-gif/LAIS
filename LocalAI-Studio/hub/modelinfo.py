# -*- coding: utf-8 -*-
"""모델 파일이 어느 계열인지 알아내요. .safetensors 맨 앞의 목록(헤더)만 읽어서 빨라요(모델을 불러오지 않아요).

계열: sd15, sdxl, sd3, flux, chroma, qwen, hidream, lumina, unknown
all_in_one: 텍스트 인코더·VAE까지 한 파일에 들어 있는 '체크포인트' 형태인지
"""
import json
import re
import struct
from pathlib import Path

_CACHE = {}


def read_header(path, limit=64 * 1024 * 1024):
    """safetensors 맨 앞의 목록(헤더) 전체(dict). 읽을 수 없으면 None."""
    with open(path, "rb") as f:
        head = f.read(8)
        if len(head) < 8:
            return None
        n = struct.unpack("<Q", head)[0]
        if n <= 0 or n > limit:
            return None
        return json.loads(f.read(n).decode("utf-8"))


def read_keys(path, limit=64 * 1024 * 1024):
    """safetensors 헤더의 텐서 이름 목록. 읽을 수 없으면 None."""
    meta = read_header(path, limit)
    return None if meta is None else [k for k in meta if k != "__metadata__"]


def classify(keys):
    """텐서 이름들로 (계열, 올인원 여부) 판단."""
    ks = keys or []
    has = lambda s: any(s in k for k in ks)
    allin = has("first_stage_model.") or has("text_encoders.") or has("cond_stage_model") or has("conditioner.embedders")
    if has("distilled_guidance_layer"):
        return "chroma", allin
    if has("double_stream_blocks.") and has("single_stream_blocks."):
        return "hidream", allin
    if has("noise_refiner.") and has("context_refiner."):
        return "lumina", allin
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
    for fam, pat in (("krea2", ("krea2", "krea-2", "krea_2")), ("chroma", ("chroma",)), ("qwen", ("qwen",)), ("flux", ("flux", "krea")), ("sd3", ("sd3", "sd_3")), ("hidream", ("hidream",)), ("lumina", ("lumina",)),
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
    if by_name(p.name) == "krea2":     # Krea 2 는 FLUX 와 구조가 달라서 이름을 먼저 믿어요
        out = {"family": "krea2", "all_in_one": False, "how": "name"}
    elif p.suffix.lower() == ".safetensors":
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


# ───────────────────────── LoRA 가 어느 모델용인지 ─────────────────────────
def classify_lora(meta, name=""):
    """LoRA 헤더(메타정보 + 텐서 이름·모양)로 계열 추정: sd15 / sdxl / flux / qwen / krea2 / unknown. 못 정하면 이름으로, 그래도 모르면 unknown."""
    if by_name(name) == "krea2":
        return "krea2"
    md = (meta or {}).get("__metadata__") or {}
    keys = [k for k in (meta or {}) if k != "__metadata__"]
    base = " ".join(str(md.get(k, "")) for k in ("ss_base_model_version", "modelspec.architecture", "ss_sd_model_name")).lower()
    if "sdxl" in base or "xl-v1" in base or "illustrious" in base or "pony" in base or "noob" in base:
        return "sdxl"
    if "flux" in base:
        return "flux"
    if "qwen" in base:
        return "qwen"
    if "sd_v1" in base or "stable-diffusion-v1" in base or "sd15" in base:
        return "sd15"
    has = lambda s: any(s in k for k in keys)
    if has("single_blocks") or has("single_transformer_blocks") or has("double_blocks"):
        return "flux"
    if has("lora_te2") or has("text_encoder_2") or has("conditioner.embedders.1"):
        return "sdxl"
    if has("img_mod") or (has("img_mlp") and has("txt_mlp")):
        return "qwen"
    dims = set()
    for k in keys:
        if "attn2" in k and ("to_k" in k or "to_v" in k) and ("lora_down" in k or "lora_A" in k):
            sh = (meta[k] or {}).get("shape") or []
            if sh:
                dims.add(sh[-1])
    if 2048 in dims:
        return "sdxl"
    if 768 in dims:
        return "sd15"
    if has("lora_te_") and not has("lora_te2"):
        return "sd15"
    fam = by_name(name)
    return fam if fam in ("sd15", "sdxl", "flux", "qwen", "chroma") else "unknown"


def lora_family(path):
    """{'family','how'} — 파일이 바뀌지 않으면 캐시를 써요."""
    p = Path(path)
    try:
        key = ("lora", str(p), p.stat().st_mtime, p.stat().st_size)
    except OSError:
        return {"family": "unknown", "how": "name"}
    if key in _CACHE:
        return _CACHE[key]
    out = None
    if p.suffix.lower() == ".safetensors":
        try:
            fam = classify_lora(read_header(p), p.name)
            out = {"family": fam, "how": "header" if fam != "unknown" else "name"}
        except Exception:  # noqa: BLE001
            out = None
    if out is None:
        fam = by_name(p.name)
        out = {"family": fam if fam in ("sd15", "sdxl", "flux", "qwen", "chroma", "krea2") else "unknown", "how": "name"}
    _CACHE[key] = out
    return out


# ───────────────────────── LoRA 정보 카드 ─────────────────────────
def _json(v):
    try:
        return json.loads(v) if isinstance(v, str) else v
    except ValueError:
        return None


def lora_card(path):
    """LoRA 파일 안에 적힌 학습 정보를 사람이 읽을 수 있게 정리해요(트리거 단어, 기반 모델, 크기 등). 파일이 같으면 캐시."""
    p = Path(path)
    st = p.stat()
    key = ("card", str(p), st.st_mtime, st.st_size)
    if key in _CACHE:
        return _CACHE[key]
    card = {"name": p.name, "size_mb": round(st.st_size / 1048576, 1), "family": lora_family(p)["family"],
            "title": "", "base": "", "trigger": [], "tags": [], "dim": None, "alpha": None, "images": None, "epochs": None, "description": ""}
    try:
        meta = read_header(p) if p.suffix.lower() == ".safetensors" else None
    except Exception:  # noqa: BLE001
        meta = None
    md = (meta or {}).get("__metadata__") or {}
    g = lambda *ks: next((str(md[k]).strip() for k in ks if md.get(k) not in (None, "")), "")
    card["title"] = g("modelspec.title", "ss_output_name")
    card["base"] = g("ss_sd_model_name", "ss_base_model_version", "modelspec.architecture")
    card["description"] = g("modelspec.description")[:300]
    card["dim"], card["alpha"] = g("ss_network_dim") or None, g("ss_network_alpha") or None
    card["images"], card["epochs"] = g("ss_num_train_images") or None, g("ss_epoch", "ss_num_epochs") or None
    trig = g("modelspec.trigger_phrase", "trigger_words", "ss_trigger_words")
    if trig:
        t = _json(trig)
        card["trigger"] = [str(x).strip() for x in (t if isinstance(t, list) else trig.split(",")) if str(x).strip()][:12]
    freq = _json(md.get("ss_tag_frequency")) if md.get("ss_tag_frequency") else None
    if isinstance(freq, dict):        # {데이터셋: {태그: 횟수}} → 가장 자주 쓰인 태그
        tot = {}
        for d in freq.values():
            if isinstance(d, dict):
                for tag, n in d.items():
                    try:
                        tot[tag.strip()] = tot.get(tag.strip(), 0) + int(n)
                    except (TypeError, ValueError):
                        pass
        card["tags"] = [t for t, _ in sorted(tot.items(), key=lambda kv: -kv[1])[:14] if t]
    card["kind_auto"] = guess_kind(card)
    _CACHE[key] = card
    return card


KINDS = ("character", "style", "background", "other")
_KIND_RX = {
    "character": r"character|char[_\- ]|cosplay|\boc\b|캐릭터|캐릭",
    "style": r"style|art ?style|artist|lineart|line[ _-]?art|watercolor|oil ?paint|sketch|pixel|aesthetic|screencap|ghibli|cyberpunk|illustration|painting|manga|comic|3d ?render|film ?grain|vintage|retro|flat ?color|画风|风格|스타일|화풍",
    "background": r"background|backdrop|scenery|landscape|cityscape|\bcity\b|street|\broom\b|interior|bedroom|forest|mountain|ocean|beach|\bsky\b|building|architecture|environment|\bbg\b|배경|풍경",
    "other": r"slider|detail|lightning|turbo|\blcm\b|hyper|speed|refiner|enhance|quality|contrast|lighting|\bpose\b|outfit|clothes|clothing|dress|uniform|costume|concept|expression|\bhands?\b|fix|tweak|의상|포즈|디테일",
}
_CHAR_TAG = re.compile(r"(hair|eyes)$|^(1girl|1boy|solo|2girls|2boys)$|ponytail|twintails|ahoge|bangs|breasts|school uniform", re.I)


def guess_kind(card):
    """LoRA 가 캐릭터용인지 / 스타일 / 배경·풍경 / 기타인지 파일 정보와 이름으로 짐작해요(틀릴 수 있어서 화면에서 직접 고칠 수 있어요)."""
    tags = [t.lower() for t in card.get("tags", [])]
    if any(t in tags[:10] for t in ("no humans", "scenery", "landscape", "cityscape")):
        return "background"
    text = " ".join([card.get("name", ""), card.get("title", ""), card.get("description", ""), " ".join(card.get("trigger", []))]).lower()
    for k in ("character", "style", "background", "other"):
        if re.search(_KIND_RX[k], text):
            return k
    if sum(1 for t in tags[:15] if _CHAR_TAG.search(t)) >= 3:
        return "character"
    return "unknown"
