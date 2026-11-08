"""2.8: Qwen-Image 생성, 효과음(Stable Audio), LTX·VACE·S2V 영상, 사진→3D, 추천 모델 분류·삭제, 메모리·GPU 설정."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17951"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def wait(jid):
    for _ in range(400):
        j = json.load(urllib.request.urlopen(B + "/api/job/" + jid))
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def cls(c): return [v["inputs"] for v in SUBMITTED[-1].values() if v["class_type"] == c]
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
def png():
    b = io.BytesIO(); Image.new("RGB", (300, 200), (10, 120, 200)).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
# 효과음
j = job({"kind": "music", "mengine": "sfx", "tags": "rain on a tin roof"}); assert j["state"] == "error" and "Stable Audio" in j["error"], j
touch("checkpoints/stable_audio_open_1.0.safetensors", "text_encoders/t5_base.safetensors")
j = job({"kind": "music", "mengine": "sfx", "tags": "rain on a tin roof", "sfx_seconds": "60"}); assert j["state"] == "done" and j["images"][0].endswith(".mp3"), j
c = cls("ConditioningStableAudio")[0]; assert c["seconds_total"] == 47.0 and cls("CLIPLoader")[0]["type"] == "stable_audio" and cls("EmptyLatentAudio")[0]["seconds"] == 47.0
assert "stable_audio_open_1.0.safetensors" not in json.load(urllib.request.urlopen(B + "/api/lists"))["checkpoints"]
ok("sound effects: Stable Audio graph, length capped at 47s, model hidden from image list")
# LTX
touch("checkpoints/ltxv-2b-0.9.8-distilled.safetensors", "text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors")
j = job({"kind": "vid", "wan_ver": "ltx", "prompt": "a cat walking", "sec": "3", "fps": "24"}); assert j["state"] == "done" and j["images"][0].endswith(".mp4"), j
assert cls("EmptyLTXVLatentVideo") and cls("SamplerCustom")[0]["cfg"] == 1.0 and (cls("EmptyLTXVLatentVideo")[0]["length"] - 1) % 8 == 0
j = job({"kind": "vid", "wan_ver": "ltx", "prompt": "a cat walking", "image": png()}); assert j["state"] == "done" and cls("LTXVImgToVideo") and not cls("EmptyLTXVLatentVideo")
ok("LTX-Video: text→video and image→video graphs (distilled → CFG 1, frames 8k+1)")
# VACE / S2V
touch("diffusion_models/wan2.1_vace_1.3B_fp16.safetensors", "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "vae/wan_2.1_vae.safetensors")
j = job({"kind": "vid", "wan_ver": "vace", "prompt": "she dances"}); assert j["state"] == "error" and "사진" in j["error"], j
j = job({"kind": "vid", "wan_ver": "vace", "prompt": "she dances", "image": png()}); assert j["state"] == "done", j
assert cls("WanVaceToVideo") and cls("TrimVideoLatent")[0]["trim_amount"][1] == 3 and cls("UNETLoader")[0]["unet_name"].startswith("wan2.1_vace")
touch("diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors")
j = job({"kind": "vid", "wan_ver": "s2v", "prompt": "talking", "image": png(), "audio": "data:audio/wav;base64," + base64.b64encode(b"RIFF" + bytes(4000)).decode()})
assert j["state"] == "error" and "wav2vec2" in j["error"], j
touch("audio_encoders/wav2vec2_large_english_fp16.safetensors")
j = job({"kind": "vid", "wan_ver": "s2v", "prompt": "talking", "image": png(), "audio": "data:audio/wav;base64," + base64.b64encode(b"RIFF" + bytes(4000)).decode(), "sec": "9"})
assert j["state"] == "done", j
assert cls("WanSoundImageToVideo")[0]["length"] <= 77 and cls("LoadAudio")[0]["audio"].endswith(".wav") and "audio" in cls("CreateVideo")[0]
assert "wan2.1_vace_1.3B_fp16.safetensors" not in hub.wan_models() and "wan2.2_s2v_14B_fp8_scaled.safetensors" not in hub.wan_models()
ok("Wan VACE (photo required, reference trimmed) and S2V (audio encoder, ≤77 frames, voice muxed into video)")
# 3D
def png3d():
    im = Image.new("RGBA", (400, 400), (0, 0, 0, 0)); im.paste((200, 60, 60, 255), (100, 60, 300, 360))
    b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
j = job({"kind": "feat", "feature": "img3d", "image": png3d()}); assert j["state"] == "error" and "TRELLIS.2" in j["error"] and j.get("need") == ["trellis2"], j
touch("diffusion_models/trellis_2_int8_convrot.safetensors", "clip_vision/dino_v3_vit_l.safetensors", "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors")
j = job({"kind": "feat", "feature": "img3d", "image": png3d(), "quality": "fast"}); assert j["state"] == "done" and j["images"][0].endswith(".glb"), j
assert cls("DecimateMesh")[0]["target_face_count"] == 20000 and cls("SaveGLB") and not cls("Trellis2UpsampleStage") and cls("UNETLoader")[0]["unet_name"] == "trellis_2_int8_convrot.safetensors"
raw = urllib.request.urlopen(B + j["images"][0]).read(); assert raw[:4] == b"glTF"
L = json.load(urllib.request.urlopen(B + "/api/lists")); assert not any("trellis" in x for x in L["checkpoints"] + L.get("diffusion_models", L.get("unets", [])))
ok("photo → 3D: TRELLIS.2 graph, .glb saved and served")
# 추천 모델 분류·삭제
C = json.load(urllib.request.urlopen(B + "/api/catalog")); cat = {m["id"]: m["cat"] for m in C["image"]}
assert cat["ltx-video"] == cat["wan-s2v"] == cat["wan22-ti2v-5b"] == "video" and cat["stable-audio-open"] == cat["ace-step-15-turbo"] == "audio" and cat["trellis2"] == cat["pixal3d-mv"] == "d3" and cat["qwen-image"] == "image"
C = json.load(urllib.request.urlopen(B + "/api/catalog")); inst = {m["id"]: m["installed"] for m in C["image"]}; assert inst["qwen-image"] and inst["qwen-lightning"]
r = post("/api/catalog/remove", {"id": "qwen-image"}); assert r["ok"] and sorted(r["removed"]) == ["qwen3vl_8b_int8_convrot.safetensors", "qwen_image_2.1_int8_convrot.safetensors", "qwen_image_2.1_vae_bf16.safetensors"], r
assert (M / "loras/qwen_image_2.1_lightning_4step.safetensors").exists()
assert "error" in post("/api/catalog/remove", {"id": "nope"})
ok("catalog grouped into image/video/audio/3D; remove keeps encoder/VAE shared with an installed model")
# 메모리·GPU 설정
assert hub.mem_args() == []
r = post("/api/prefs", {"vram_mode": "low", "reserve_vram": 1.5}); assert "error" in r
r = post("/api/prefs", {"vram_mode": "low", "reserve_vram": 2, "smart_memory": False, "chat_gpu": "cpu"}); assert r["prefs"]["vram_mode"] == "low", r
assert hub.mem_args() == ["--lowvram", "--reserve-vram", "2", "--disable-smart-memory"], hub.mem_args()
ok("memory/GPU limits → ComfyUI launch options, bad values refused")
print("ALL OK")
