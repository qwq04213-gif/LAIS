"""3.15: 영상 복원 — 진단(노이즈·해상도·소리), ffmpeg 다듬기·원래 소리·확인·비교 그림, AI 조각(업스케일·RIFE) 그래프·이어서 하기·길이 확인, 검사."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, subprocess, urllib.request, urllib.parse
from pathlib import Path
os.environ["TEST_HUB_PORT"] = "17981"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def job2(o, t=300):
    jid = post("/api/job", o)["id"]
    for _ in range(t * 10):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
    raise AssertionError("timeout")
def nodes(g, c): return [n["inputs"] for n in g.values() if n["class_type"] == c]
FF = "ffmpeg"
vd = hub.OUT / "영상"; vd.mkdir(parents=True, exist_ok=True)
src = vd / "old.mp4"
subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:r=24:d=12", "-f", "lavfi", "-i", "sine=f=440:d=12",
                "-vf", "noise=alls=45:allf=t", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)], check=True)
url = "/out/" + urllib.parse.quote("영상") + "/old.mp4"
# 1) 진단
j = job2({"kind": "vrestore", "op": "analyze", "video": url}); assert j["state"] == "done", j
R = j["report"]; keys = [x["key"] for x in R["items"]]
assert {"deint", "denoise", "deflicker", "stabilize", "upscale", "interp", "audio"} <= set(keys)
assert R["metrics"]["noise"] > 3.5 and R["rec"]["denoise"] != "off", R["metrics"]
assert R["rec"]["upscale"] == 2 and R["rec"]["interp"] and R["meta"]["audio"] and R["meta"]["w"] == 320, R
assert not R["rec"]["deint"] and R["metrics"]["interlace"] < 0.3
ok(f"diagnosis: noise {R['metrics']['noise']}, low resolution → upscale 2x, 24fps → interp, audio kept")
# 2) ffmpeg 만으로 다듬기
assert job2({"kind": "vrestore", "op": "run", "video": url})["error"].startswith("고칠 항목")
j = job2({"kind": "vrestore", "op": "run", "video": url, "deint": True, "denoise": "medium", "deflicker": True, "color": True, "stabilize": True, "sharpen": True})
assert j["state"] == "done", j
mp4 = [u for u in j["images"] if u.endswith(".mp4")]; png = [u for u in j["images"] if u.endswith(".png")]
assert len(mp4) == 1 and len(png) == 1 and "/영상 복원/" in urllib.parse.unquote(mp4[0]), j["images"]
V = j["verify"]; assert V["ok"] and V["src_audio"] and V["out_audio"] and abs(V["out_dur"] - 12) < 0.3, V
assert "소리 그대로" in j["msg"] and "흔들림 보정" in j["msg"] and "노이즈 줄이기" in j["msg"], j["msg"]
outf = hub.OUT / "영상 복원" / urllib.parse.unquote(mp4[0]).split("/")[-1]
meta = json.loads(Path(str(outf) + ".json").read_text(encoding="utf-8")); assert meta["kind"] == "vrestore" and meta["verify"]["ok"]
cmp = Image.open(hub.OUT / "영상 복원" / urllib.parse.unquote(png[0]).split("/")[-1]); assert cmp.size == (320 * 2 + 8, 240)
assert not list(hub.VR_WORK.glob("*/pre.mp4")), "work folder removed after success"
assert any("old.mp4" in x["name"] or x["url"] == mp4[0] for x in get("/api/vmix/list")["videos"])
ok("ffmpeg pass: deinterlace/denoise/deflicker/brightness/vidstab/sharpen, original audio kept & verified, comparison image, own folder")
# 3) AI 조각: 업스케일 + RIFE
(hub.MODELS / "upscale_models").mkdir(parents=True, exist_ok=True); (hub.MODELS / "upscale_models" / "RealESRGAN_x4plus.pth").write_bytes(b"x")
chunk = TMP / "chunk.mp4"
subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x480:r=48:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(chunk)], check=True)
STATE["mp4"] = chunk.read_bytes()
n0 = len(SUBMITTED)
calls = {"n": 0}; real = hub.run_wf
def flaky(wf, J, raw=False):
    calls["n"] += 1
    if calls["n"] == 2: raise RuntimeError("CUDA out of memory (테스트)")
    return real(wf, J, raw)
hub.run_wf = flaky
P = {"kind": "vrestore", "op": "run", "video": url, "denoise": "light", "upscale": "2", "interp": True}
j = job2(P); assert j["state"] == "error" and "이어서" in j["error"], j
work = next(hub.VR_WORK.glob("*/done"))
assert len(list(work.glob("o*.mp4"))) == 1 and len(list((work.parent / "chunks").glob("c*.mp4"))) >= 2
hub.run_wf = real
j = job2(P); assert j["state"] == "done", j
assert any("이어서" in w for w in j.get("warn", [])), j.get("warn")
g = SUBMITTED[-1]
assert nodes(g, "UpscaleModelLoader")[0]["model_name"] == "RealESRGAN_x4plus.pth"
sc = nodes(g, "ImageScale")[0]; assert (sc["width"], sc["height"]) == (640, 480), sc
assert nodes(g, "RIFE VFI")[0]["multiplier"] == 2 and nodes(g, "CreateVideo")[0]["fps"] == 48
assert not nodes(g, "LoadAudio") and len(SUBMITTED) - n0 >= 3
V = j["verify"]; assert V["out_audio"] and not V["ok"] and "길이" in V["msg"], V      # 가짜 조각(1초)이라 길이가 달라 확인에서 걸려야 해요
assert any("확인 필요" in w for w in j["warn"])
assert not list((hub.COMFY / "input").glob("hub_*.mp4"))
ok("AI chunks: upscale model → ImageScale to 2x → RIFE x2 per chunk, resume skips finished chunks, length check catches mismatch")
# 4) 검사
STATE["missing"].add("RIFE VFI"); hub.caps(force=True)
j = job2({"kind": "vrestore", "op": "run", "video": url, "interp": True}); assert j["state"] == "error" and "ComfyUI-Frame-Interpolation" in j["error"]
STATE["missing"].clear(); hub.caps(force=True)
for f in (hub.MODELS / "upscale_models").iterdir(): f.unlink()
j = job2({"kind": "vrestore", "op": "run", "video": url, "upscale": "2"}); assert j["state"] == "error" and "업스케일 모델이 없" in j["error"] and j.get("need") == ["esrgan"], j
j = job2({"kind": "vrestore", "op": "run", "video": "/out/영상/nope.mp4", "denoise": "light"}); assert j["state"] == "error" and "찾을 수 없" in j["error"]
assert hub.vrestore.chunk_frames(1920, 1080, 4, True) == 8 and hub.vrestore.chunk_frames(320, 240, 2, False) == 240
assert hub.vrestore.model_scale("4x-UltraSharp.pth") == 4 and hub.vrestore.model_scale("RealESRGAN_x2plus.pth") == 2
ok("checks: missing RIFE extension, missing upscale model → download offer, bad file, chunk sizing")
print("ALL OK")
