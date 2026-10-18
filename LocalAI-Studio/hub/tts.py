# -*- coding: utf-8 -*-
"""글을 소리로 바꿔요(ComfyUI 없이). 두 가지 방법:
  sapi : 윈도우에 들어 있는 음성(System.Speech). 인터넷 없이 내 PC 안에서만 동작해요.
  edge : Edge 읽어 주기(edge-tts). 목소리가 자연스럽지만 글이 마이크로소프트 서버로 전송돼요(인터넷 필요).
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NO_WIN = 0x08000000 if os.name == "nt" else 0
MAX_CHARS = 5000

SAPI_PS = r"""param([string]$Op,[string]$TextFile,[string]$Out,[string]$Voice,[int]$Rate,[int]$Volume)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($Op -eq 'list') {
  foreach ($v in $s.GetInstalledVoices()) { if ($v.Enabled) { Write-Output ($v.VoiceInfo.Name + '|' + $v.VoiceInfo.Culture.Name) } }
  exit 0
}
if ($Voice) { $s.SelectVoice($Voice) }
$s.Rate = $Rate
$s.Volume = $Volume
$s.SetOutputToWaveFile($Out)
$s.Speak([System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8))
$s.Dispose()
"""

# Edge 목소리: 자주 쓰는 것만 직접 적어 뒀어요(목록을 받으려고 인터넷에 접속하지 않도록)
EDGE_VOICES = [
    ("ko-KR-SunHiNeural", "한국어 여성 · 선히"), ("ko-KR-InJoonNeural", "한국어 남성 · 인준"), ("ko-KR-HyunsuMultilingualNeural", "한국어 남성 · 현수(다국어)"),
    ("en-US-AriaNeural", "영어(미국) 여성 · Aria"), ("en-US-GuyNeural", "영어(미국) 남성 · Guy"), ("en-GB-SoniaNeural", "영어(영국) 여성 · Sonia"),
    ("ja-JP-NanamiNeural", "일본어 여성 · Nanami"), ("ja-JP-KeitaNeural", "일본어 남성 · Keita"),
    ("zh-CN-XiaoxiaoNeural", "중국어 여성 · Xiaoxiao"), ("es-ES-ElviraNeural", "스페인어 여성 · Elvira"), ("fr-FR-DeniseNeural", "프랑스어 여성 · Denise"),
    ("de-DE-KatjaNeural", "독일어 여성 · Katja"),
]
_VOICE_CACHE = {"t": 0, "v": None}


def edge_ready():
    return importlib.util.find_spec("edge_tts") is not None


def _ps_script(cache_dir):
    d = Path(cache_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "sapi.ps1"
    if not p.exists() or p.read_text(encoding="utf-8") != SAPI_PS:
        p.write_text(SAPI_PS, encoding="utf-8-sig")        # 윈도우 파워셸이 한글을 올바르게 읽도록 BOM 포함
    return p


def _ps(args, cache_dir, run=subprocess.run, timeout=300):
    return run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(_ps_script(cache_dir))] + args,
               capture_output=True, timeout=timeout, creationflags=NO_WIN)


def sapi_voices(cache_dir, run=subprocess.run, force=False, is_windows=None):
    """[(이름, 언어코드)] — 윈도우가 아니거나 못 읽으면 빈 목록."""
    if (os.name == "nt") if is_windows is None else is_windows:
        if not force and _VOICE_CACHE["v"] is not None and time.time() - _VOICE_CACHE["t"] < 60:
            return _VOICE_CACHE["v"]
        try:
            r = _ps(["-Op", "list"], cache_dir, run, 60)
            txt = (r.stdout or b"").decode("utf-8", "replace")
            out = [tuple(x.strip().split("|", 1)) for x in txt.splitlines() if "|" in x]
        except Exception:  # noqa: BLE001
            out = []
        _VOICE_CACHE.update(t=time.time(), v=out)
        return out
    return []


def speak_sapi(text, voice, rate, volume, cache_dir, run=subprocess.run):
    """윈도우 내장 음성으로 읽은 wav 바이트."""
    with tempfile.TemporaryDirectory(dir=str(Path(cache_dir))) as td:
        tf, out = Path(td) / "t.txt", Path(td) / "o.wav"
        tf.write_text(text, encoding="utf-8")
        r = _ps(["-Op", "speak", "-TextFile", str(tf), "-Out", str(out), "-Voice", voice or "", "-Rate", str(int(rate)), "-Volume", str(int(volume))], cache_dir, run)
        if r.returncode != 0 or not out.exists() or out.stat().st_size < 100:
            err = ((r.stderr or b"").decode("utf-8", "replace") or (r.stdout or b"").decode("utf-8", "replace")).strip()[-300:]
            raise RuntimeError("윈도우 음성으로 읽지 못했어요." + (f" ({err})" if err else ""))
        return out.read_bytes()


def speak_edge(text, voice, rate_pct, volume_pct, pitch_hz, cache_dir, run=subprocess.run, py=None):
    """Edge 읽어 주기로 읽은 mp3 바이트."""
    if not edge_ready():
        raise RuntimeError("Edge 읽어 주기 부품(edge-tts)이 아직 없어요. 화면의 [부품 설치] 버튼을 눌러 주세요.")
    with tempfile.TemporaryDirectory(dir=str(Path(cache_dir))) as td:
        tf, out = Path(td) / "t.txt", Path(td) / "o.mp3"
        tf.write_text(text, encoding="utf-8")
        cmd = [py or sys.executable, "-m", "edge_tts", "--voice", voice, f"--rate={int(rate_pct):+d}%", f"--volume={int(volume_pct):+d}%", f"--pitch={int(pitch_hz):+d}Hz",
               "--file", str(tf), "--write-media", str(out)]
        r = run(cmd, capture_output=True, timeout=300, creationflags=NO_WIN)
        if r.returncode != 0 or not out.exists() or out.stat().st_size < 100:
            err = (r.stderr or b"").decode("utf-8", "replace").strip()[-300:]
            raise RuntimeError("Edge 읽어 주기에 실패했어요. 인터넷 연결을 확인해 주세요." + (f" ({err})" if err else ""))
        return out.read_bytes()


def install_edge(run=subprocess.run, py=None):
    r = run([py or sys.executable, "-m", "pip", "install", "edge-tts", "--no-warn-script-location"], capture_output=True, timeout=600, creationflags=NO_WIN)
    importlib.invalidate_caches()
    return r.returncode == 0 and edge_ready(), ((r.stderr or b"").decode("utf-8", "replace") + (r.stdout or b"").decode("utf-8", "replace"))[-400:]
