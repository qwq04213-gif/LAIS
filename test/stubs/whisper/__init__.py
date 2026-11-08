def load_audio(p):
    raise FileNotFoundError(2, "지정된 파일을 찾을 수 없습니다", "ffmpeg")
class _M:
    def transcribe(self, audio, **k):
        assert len(audio) > 1000
        return {"segments": [{"start": 0.0, "end": len(audio) / 16000, "text": " 안녕하세요 "}]}
def load_model(*a, **k): return _M()
