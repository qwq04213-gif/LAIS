# -*- coding: utf-8 -*-
"""음성 모델 엔진 안(전용 파이썬)에서 실행되는 스크립트예요. 허브가 이 파일을 엔진 폴더로 복사해 돌려요.
사용: python tts_worker.py <engine> <job.json> <out.wav>
job.json: {"text","language","speaker","ref","speed","exaggeration"}  — 글은 파일로 받아서 따옴표 문제가 없어요."""
import json
import os
import sys


def say(msg):
    print("PROGRESS:" + msg, flush=True)


def device():
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def run_xtts(job, out):
    from TTS.api import TTS
    dev = device()
    say("XTTS 모델 불러오는 중" + ("" if dev == "cuda" else " (그래픽카드를 못 찾아 CPU로 해요 — 느려요)"))
    t = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to(dev)
    try:
        spk = list(t.speakers or [])
        if spk:
            with open(os.path.join(os.path.dirname(out), "speakers.json"), "w", encoding="utf-8") as f:
                json.dump(spk, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        spk = []
    kw = {}
    if job.get("ref"):
        kw["speaker_wav"] = job["ref"]
    else:
        kw["speaker"] = job.get("speaker") or (spk[0] if spk else "Claribel Dervla")
    say("음성 만드는 중")
    t.tts_to_file(text=job["text"], language=job.get("language") or "ko", file_path=out, split_sentences=True, speed=float(job.get("speed") or 1.0), **kw)


def run_chatterbox(job, out):
    import torchaudio as ta
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    dev = device()
    say("Chatterbox 모델 불러오는 중" + ("" if dev == "cuda" else " (그래픽카드를 못 찾아 CPU로 해요 — 느려요)"))
    m = ChatterboxMultilingualTTS.from_pretrained(device=dev)
    say("음성 만드는 중")
    kw = {"audio_prompt_path": job["ref"]} if job.get("ref") else {}
    wav = m.generate(job["text"], language_id=job.get("language") or "ko", exaggeration=float(job.get("exaggeration") or 0.5), **kw)
    ta.save(out, wav, m.sr)


def run_kokoro(job, out):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    voice = job.get("speaker") or "af_heart"
    lang = "b" if voice.startswith("b") else "a"
    say("Kokoro 모델 불러오는 중")
    p = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    say("음성 만드는 중")
    parts = [np.asarray(a) for _gs, _ps, a in p(job["text"], voice=voice, speed=float(job.get("speed") or 1.0)) if a is not None]
    if not parts:
        raise RuntimeError("소리가 만들어지지 않았어요.")
    sf.write(out, np.concatenate(parts), 24000)


QWEN_LANG = {"ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese", "de": "German", "fr": "French", "ru": "Russian", "pt": "Portuguese", "es": "Spanish", "it": "Italian"}
QWEN_EMO = {"calm": "Speak in a calm, gentle tone.", "rich": "Speak expressively with rich emotion."}


def split_text(text, limit=220):
    """긴 글은 문장 단위로 잘라 차례로 읽어요(한 번에 너무 길면 뒤가 뭉개질 수 있어요)."""
    import re
    parts, cur = [], ""
    for s in re.split(r"(?<=[.!?。！？\n])\s+", text.strip()):
        if not s:
            continue
        if cur and len(cur) + len(s) > limit:
            parts.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        parts.append(cur)
    return parts or [text]


def run_qwen3(job, out):
    import inspect
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    dev = device()
    clone = bool(job.get("ref"))
    repo = "Qwen/Qwen3-TTS-12Hz-1.7B-" + ("Base" if clone else "CustomVoice")
    say("Qwen3-TTS 모델 불러오는 중" + (" (처음에는 모델을 내려받아요)" if True else "") + ("" if dev == "cuda" else " (그래픽카드를 못 찾아 CPU로 해요 — 아주 느려요)"))
    kw = dict(device_map="cuda:0" if dev == "cuda" else "cpu", dtype=torch.bfloat16 if dev == "cuda" and torch.cuda.is_bf16_supported() else (torch.float16 if dev == "cuda" else torch.float32))
    try:
        m = Qwen3TTSModel.from_pretrained(repo, attn_implementation="sdpa", **kw)
    except (TypeError, ValueError):
        m = Qwen3TTSModel.from_pretrained(repo, **kw)
    lang = QWEN_LANG.get(job.get("language") or "ko", "Korean")
    pieces = split_text(job["text"])
    wavs, sr = [], 24000
    for i, t in enumerate(pieces, 1):
        say(f"음성 만드는 중 ({i}/{len(pieces)})")
        if clone:
            ref_text = (job.get("ref_text") or "").strip()
            if ref_text:
                w, sr = m.generate_voice_clone(text=t, language=lang, ref_audio=job["ref"], ref_text=ref_text)
            else:
                ps = inspect.signature(m.generate_voice_clone).parameters
                if "x_vector_only_mode" not in ps:
                    raise RuntimeError("이 버전의 Qwen3-TTS 는 목소리 따라 하기에 '샘플에서 말한 내용'이 꼭 필요해요. 칸을 채워 주세요.")
                w, sr = m.generate_voice_clone(text=t, language=lang, ref_audio=job["ref"], x_vector_only_mode=True)
        else:
            extra = {}
            ins = QWEN_EMO.get(job.get("emotion") or "")
            if ins and "instruct" in inspect.signature(m.generate_custom_voice).parameters:
                extra["instruct"] = ins
            w, sr = m.generate_custom_voice(text=t, language=lang, speaker=job.get("speaker") or "Sohee", **extra)
        a = np.asarray(w[0], dtype=np.float32).reshape(-1)
        wavs += [a, np.zeros(int(sr * 0.25), dtype=np.float32)]
    sf.write(out, np.concatenate(wavs[:-1] if len(wavs) > 1 else wavs), sr)


def main():
    eng, jp, out = sys.argv[1:4]
    with open(jp, "r", encoding="utf-8") as f:
        job = json.load(f)
    {"qwen3": run_qwen3, "xtts": run_xtts, "chatterbox": run_chatterbox, "kokoro": run_kokoro}[eng](job, out)
    if not os.path.exists(out) or os.path.getsize(out) < 100:
        raise RuntimeError("음성 파일이 만들어지지 않았어요.")
    say("끝")


if __name__ == "__main__":
    main()
