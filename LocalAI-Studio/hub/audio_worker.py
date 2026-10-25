# -*- coding: utf-8 -*-
"""소리 분리 일꾼(engine/demucs 전용 파이썬에서 돌아요). job.json: {"wav","model","two","out"}
진행은 'PROGRESS:0.42 글', 끝나면 'DONE:[{"stem","file"}]', 오류는 'ERR:글' 로 알려요.
소리 읽고 쓰기는 soundfile 로 해서 ffmpeg·torchaudio 저장 기능이 필요 없어요(허브가 미리 44.1kHz wav 로 바꿔 줘요)."""
import json
import sys
import types


def say(pc, msg):
    print(f"PROGRESS:{pc:.3f} {msg}", flush=True)


def main():
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    try:
        import lameenc  # noqa: F401
    except Exception:  # mp3 저장용이라 없어도 돼요
        sys.modules["lameenc"] = types.ModuleType("lameenc")
    import numpy as np
    import soundfile as sf
    import torch
    from demucs import apply as A
    from demucs.pretrained import get_model
    from pathlib import Path

    say(0.02, "분리 모델 불러오는 중(처음엔 내려받아요)")
    model = get_model(job["model"])
    model.eval()
    data, sr = sf.read(job["wav"], dtype="float32", always_2d=True)
    if sr != model.samplerate:
        print(f"ERR:소리 빠르기({sr}Hz)가 모델({model.samplerate}Hz)과 달라요.", flush=True)
        sys.exit(2)
    wav = torch.from_numpy(np.ascontiguousarray(data.T))
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    wav = wav[:2]
    ref = wav.mean(0)
    m, s = ref.mean(), ref.std() + 1e-8
    x = (wav - m) / s
    state = {"k": 0}

    class Prog:
        def __init__(self, it, **_):
            self.it = list(it)

        def __iter__(self):
            state["k"] += 1
            n = len(self.it)
            for i, v in enumerate(self.it):
                yield v
                say(0.05 + 0.85 * (i + 1) / max(1, n), f"나누는 중 {i + 1}/{n}" + (f" (모델 {state['k']})" if job["model"] == "htdemucs_ft" else ""))

    A.tqdm = types.SimpleNamespace(tqdm=Prog)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    say(0.05, "나누는 중" + (" (그래픽카드)" if dev == "cuda" else " (CPU — 오래 걸려요)"))

    def run(device):
        with torch.no_grad():
            return A.apply_model(model, x[None], device=device, shifts=1, split=True, overlap=0.25, progress=True, num_workers=0)[0]
    try:
        out = run(dev)
    except RuntimeError as e:
        if dev != "cuda" or "out of memory" not in str(e).lower():
            raise
        torch.cuda.empty_cache()
        say(0.05, "그래픽카드 메모리가 부족해 CPU 로 다시 해요(오래 걸려요)")
        out = run("cpu")
    out = out * s + m
    names = list(model.sources)
    res = {n: out[i] for i, n in enumerate(names)}
    if job.get("two") == "vocals" and "vocals" in res:
        res = {"vocals": res["vocals"], "no_vocals": sum(v for k, v in res.items() if k != "vocals")}
    say(0.95, "저장하는 중")
    od = Path(job["out"])
    done = []
    for n, t in res.items():
        a = t.cpu().numpy().T
        peak = float(np.abs(a).max() or 1.0)
        if peak > 0.999:
            a = a / peak * 0.999
        f = f"{n}.wav"
        sf.write(str(od / f), a, sr, subtype="PCM_16")
        done.append({"stem": n, "file": f})
    print("DONE:" + json.dumps(done), flush=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"ERR:{type(e).__name__}: {e}", flush=True)
        sys.exit(1)
