# -*- coding: utf-8 -*-
"""받아쓰기 전용 환경(engine/asr/whisper/venv)에서 실행돼요: python worker.py job.json
job: {audio, model, lang, out, models}. 진행은 'PROGRESS:0.42 글' 줄로 알려요."""
import json
import sys
import wave


def read_wav(path):
    """허브가 미리 뽑아 둔 16kHz 모노 wav 를 ffmpeg 없이 읽어요(whisper.load_audio 는 'ffmpeg' 실행 파일을 찾다가 못 찾으면 실패해요)."""
    import numpy as np
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2 or w.getframerate() != 16000:
            return None
        ch = w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return a.reshape(-1, ch).mean(axis=1) if ch > 1 else a


def main():
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    print("PROGRESS:0.02 받아쓰기 모델을 불러오는 중(처음엔 내려받아요)", flush=True)
    import torch
    import whisper
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = whisper.load_model(job["model"], device=dev, download_root=job["models"])
    print(f"PROGRESS:0.1 받아쓰는 중({'그래픽카드' if dev == 'cuda' else 'CPU — 느려요'})", flush=True)
    audio = None
    try:
        audio = read_wav(job["audio"])
    except (wave.Error, OSError, EOFError):
        audio = None
    if audio is None:
        audio = whisper.load_audio(job["audio"])
    total = max(1.0, len(audio) / 16000)
    segs = []
    res = model.transcribe(audio, language=job.get("lang") or None, fp16=dev == "cuda", verbose=None, condition_on_previous_text=False)
    for s in res.get("segments", []):
        t = (s.get("text") or "").strip()
        if t:
            segs.append({"s": round(float(s["start"]), 2), "e": round(float(s["end"]), 2), "text": t})
            print(f"PROGRESS:{min(0.98, 0.1 + 0.88 * float(s['end']) / total):.3f} 받아쓰는 중 {int(s['end'])}/{int(total)}초", flush=True)
    json.dump(segs, open(job["out"], "w", encoding="utf-8"), ensure_ascii=False)
    print("PROGRESS:1 끝", flush=True)


if __name__ == "__main__":
    main()
