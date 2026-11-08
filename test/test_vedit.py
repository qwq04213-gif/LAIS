"""영상 편집: 이어 붙이기·자르기(진짜 ffmpeg, ComfyUI 안 씀), AI로 이어 그리기(VACE 그래프 확인 + 원본 뒤에 붙이기)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, subprocess, urllib.request
os.environ["TEST_HUB_PORT"] = "17955"
sys.path.insert(0, BASE + "/test")
from mocks import *
import vmix
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def job(o):
    jid = post("/api/job", o)["id"]
    for _ in range(900):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
V = hub.OUT / "영상"; V.mkdir(parents=True, exist_ok=True)
mkv = lambda name, src, dur, extra=(): subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"{src}:rate=24:duration={dur}", *extra, str(V / name)], check=True)
mkv("a.mp4", "testsrc=size=640x360", 2); mkv("b.mp4", "testsrc2=size=480x480", 3)
ff = vmix.find_ffmpeg(); dur = lambda u: vmix.probe(ff, hub.out_path(u[5:]))["dur"]
n0 = len(SUBMITTED)
j = job({"kind": "vedit", "op": "concat", "files": ["/out/영상/a.mp4", "/out/영상/b.mp4"]}); assert j["state"] == "done", j
assert abs(dur(j["images"][0]) - 5.0) < 0.2 and vmix.probe(ff, hub.out_path(j["images"][0][5:]))["w"] == 640
j = job({"kind": "vedit", "op": "concat", "files": ["/out/영상/a.mp4", "/out/영상/b.mp4"], "fade": "0.5"}); assert abs(dur(j["images"][0]) - 4.5) < 0.2
assert job({"kind": "vedit", "op": "concat", "files": ["/out/영상/a.mp4"]})["state"] == "error"
ok("join two videos (sizes matched to the first, optional crossfade); one video refused")
j = job({"kind": "vedit", "op": "trim", "file": "/out/영상/b.mp4", "start": "0.5", "end": "2"}); assert j["state"] == "done" and abs(dur(j["images"][0]) - 1.5) < 0.15, j
assert "짧아요" in job({"kind": "vedit", "op": "trim", "file": "/out/영상/b.mp4", "start": "2", "end": "2"})["error"] and len(SUBMITTED) == n0
ok("trim keeps the chosen range; empty range refused; neither job touches ComfyUI")
j = job({"kind": "vedit", "op": "extend", "file": "/out/영상/a.mp4"}); assert j["state"] == "error" and "VACE" in j["error"], j
for f in ("diffusion_models/wan2.1_vace_1.3B_fp16.safetensors", "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "vae/wan_2.1_vae.safetensors"):
    (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
GEN = hub.ROOT / "gen_fake.mp4"; subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=848x480:rate=16:duration=4.06", str(GEN)], check=True)
real = hub.run_wf; seen = {}
def fake(wf, J, raw=False):
    validate(wf); seen["wf"] = wf; return [("gen.mp4", GEN.read_bytes())]
hub.run_wf = fake
j = job({"kind": "vedit", "op": "extend", "file": "/out/영상/a.mp4", "sec": "3", "prompt": "the camera keeps panning"}); hub.run_wf = real; assert j["state"] == "done", j
c = {n["class_type"]: n["inputs"] for n in seen["wf"].values()}; v = c["WanVaceToVideo"]
assert v["length"] == 65 and v["width"] == 848 and isinstance(v["control_video"], list) and isinstance(v["control_masks"], list) and c["ImageToMask"]["channel"] == "red"
d = dur(j["images"][0]); assert 2 + 3 - 0.3 < d < 2 + 3.2, d
assert vmix.probe(ff, hub.out_path(j["images"][0][5:]))["w"] == 640
ok(f"AI continuation: VACE graph with control video + mask, original + new part joined ({d:.1f}s, original size)")
print("ALL OK")
