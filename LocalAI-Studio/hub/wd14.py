"""사진 → Danbooru 태그(WD14 태거, SmilingWolf/wd-vit-tagger-v3, Apache-2.0). onnxruntime 으로 CPU/GPU 어디서든 돌아가요.
LoRA 학습용 캡션(태그형)을 자동으로 달 때 써요."""
import csv
import io
import os
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

HF = os.environ.get("HF_URL", "https://huggingface.co")
REPO = "SmilingWolf/wd-vit-tagger-v3"
FILES = ("model.onnx", "selected_tags.csv")
SIZE_MB = 380
_SESS = {}


def folder(models):
    return Path(models) / "wd14" / REPO.split("/")[1]


def ready(models):
    return all((folder(models) / f).is_file() for f in FILES)


def download(models, say=None):
    d = folder(models)
    d.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        if (d / f).is_file():
            continue
        say and say(f"태그 모델 받는 중: {f} (처음 한 번, 약 {SIZE_MB}MB)")
        tmp = d / (f + ".part")
        with urllib.request.urlopen(f"{HF}/{REPO}/resolve/main/{f}", timeout=600) as r, open(tmp, "wb") as fh:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                fh.write(b)
        tmp.replace(d / f)


def _load(models, factory=None):
    key = str(folder(models))
    if key not in _SESS:
        rows = list(csv.DictReader(io.StringIO((folder(models) / "selected_tags.csv").read_text(encoding="utf-8"))))
        if factory is None:
            import onnxruntime as ort
            prov = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
            factory = lambda p: ort.InferenceSession(str(p), providers=prov)  # noqa: E731
        _SESS[key] = (factory(folder(models) / "model.onnx"), rows)
    return _SESS[key]


def tags(models, img, general=0.35, character=0.85, factory=None, skip=("rating:",)):
    """사진 한 장 → 태그 목록(확률 높은 순). 캐릭터 태그는 더 엄격하게 골라요. rating 태그는 빼요."""
    sess, rows = _load(models, factory)
    inp = sess.get_inputs()[0]
    size = int(inp.shape[1]) if isinstance(inp.shape[1], int) else 448
    im = img.convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    s = max(im.size)
    sq = Image.new("RGB", (s, s), (255, 255, 255))
    sq.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    a = np.asarray(sq.resize((size, size), Image.BICUBIC), dtype=np.float32)[:, :, ::-1]      # BGR
    prob = sess.run(None, {inp.name: a[None]})[0][0]
    out = []
    for r, p in zip(rows, prob):
        cat = str(r.get("category"))
        if cat == "9":
            continue
        if (cat == "4" and p >= character) or (cat != "4" and p >= general):
            name = r["name"]
            if any(name.startswith(x) for x in skip):
                continue
            out.append((float(p), name.replace("_", " ") if len(name) > 3 else name))
    return [n for _, n in sorted(out, reverse=True)]
