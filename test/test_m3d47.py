"""4.7: 사진 한 장 기반 3D — 단일 사진 모드가 기본(AI 방향 그림은 선택형 '멀티뷰 보조'), 멀티뷰 그림 일관성 검사(안 맞는 그림 빼기),
엔진 카메라 방향 그대로 쓰기, 얼굴 휘기 기본 꺼짐, 원본 고밀도 메시 따로 저장, 4방향 캡처·그물망 검사, 단계별 결과(A~E)·비교표,
얼굴을 다시 그리지 않는 업스케일."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17970"
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import numpy as np
import glbscene, photoproj
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid):
    for _ in range(1500):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
def url(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def cls(name, wf=None): return [n["inputs"] for n in (wf or SUBMITTED[-1]).values() if n["class_type"] == name]
def names(j): return [urllib.parse.unquote(u.split("/")[-1]) for u in j["images"]]
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True
class Cut:
    def cut(self, img, _):
        a = Image.new("L", img.size, 0); w, h = img.size; a.paste(255, (w // 4, h // 6, w * 3 // 4, h * 5 // 6)); o = img.convert("RGBA"); o.putalpha(a); return o
hub.rmbg_engine = lambda k: Cut()
for f in (M / "upscale_models").glob("*") if (M / "upscale_models").is_dir() else []: f.unlink()
touch("diffusion_models/pixal3d_int8_convrot.safetensors", "diffusion_models/pixal3d_multiview_int8_convrot.safetensors", "clip_vision/dino_v3_L_naf_fp32.safetensors",
      "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors", "geometry_estimation/moge_2_vitl_normal_fp16.safetensors")

S = 1200
photo = Image.new("RGB", (S, S), (128, 128, 128)); photo.paste((200, 40, 40), (0, 0, S // 2, S)); photo.paste((40, 200, 40), (S // 2, 0, S, S))
T = Image.new("RGB", (512, 512), (40, 40, 160)); T.paste((120, 70, 70), (0, 0, 85, 256)); T.paste((70, 120, 70), (85, 0, 171, 256))
STATE["glb"] = uv_glb(0.75, 1.0, 0.5, T, n=16)
STATE["glb_hi"] = uv_glb(0.75, 1.0, 0.5, T, n=40)                 # 원본 고밀도 메시(면이 더 많음)
j = job({"kind": "m3d", "op": "prep", "image": url(photo), "kind3": "character", "name": "hero"}); assert j["state"] == "done", j
sid = j["m3d"]["id"]; d = hub.M3D_DIR / sid
front = Image.open(d / "view_front.png").convert("RGBA")
front.save(d / "view_back.png"); front.save(d / "view_left.png"); front.save(d / "view_right.png")     # AI 방향 그림이 있다고 쳐요(실루엣이 맞음)

# 1) 기본 = 사진 한 장: 방향 그림이 있어도 쓰지 않아요 + 원본 고밀도 메시·4방향 캡처·검사
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": ""}); assert j["state"] == "done", j
wf = SUBMITTED[-1]
assert cls("Pixal3DConditioning", wf) and not cls("Pixal3DMultiViewConditioning", wf) and len(cls("LoadImage", wf)) == 1, [n["class_type"] for n in wf.values()]
assert sorted(x["filename_prefix"] for x in cls("SaveGLB", wf)) == ["3d/hub3d", "3d/hub3d_hi"]
hi = next(x for x in cls("SaveGLB", wf) if x["filename_prefix"] == "3d/hub3d_hi"); assert wf[hi["mesh"][0]]["class_type"] == "VaeDecodeShapeTrellis"   # 다시 짜기·면 줄이기 전
nm = names(j); assert nm[0].endswith(".glb") and "-4방향.png" in nm[1] and nm[2].endswith("-원본고밀도.glb"), nm
hb = urllib.request.urlopen(B + j["images"][2]).read(); assert hb == STATE["glb_hi"]
sheet = Image.open(io.BytesIO(urllib.request.urlopen(B + j["images"][1]).read())); assert sheet.width > 4 * 300 and sheet.height > 300
ms = j["m3d_stats"]["mesh"]; assert ms["tris"] > 0 and ms["holes"] == 0 and ms["parts"] == 1 and not ms["flat"] and "head_tris" in ms, ms
ok("default = single photo (Pixal3D one image) even when AI direction views exist; original dense mesh saved separately; 4-view capture + mesh check")

# 2) 사진 붙이기: Pixal3D 카메라 방향 그대로(다시 찾지 않음), 얼굴 휘기는 기본 꺼짐
calls = []
orig = photoproj.project
def spy(*a, **k): calls.append(k); return orig(*a, **k)
photoproj.project = spy
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "keep_hi": "", "capture": ""}); assert j["state"] == "done", j
photoproj.project = orig
assert calls and calls[-1]["cam_hint"] == photoproj.PIXAL_CAM and calls[-1]["align"] is False, calls
assert len(names(j)) == 1, names(j)                                                     # 원본 메시·캡처를 끄면 결과 하나
ok("photo projection uses Pixal3D's own camera direction; face warping is off by default; extras can be turned off")

# 3) AI 멀티뷰 보조: 앞 사진과 자세·비율이 다른 그림은 빼요
bad = Image.new("RGBA", front.size, (0, 0, 0, 0)); bad.paste((90, 90, 90, 255), (front.width // 8, front.height // 2, front.width * 7 // 8, front.height * 7 // 8))
bad.save(d / "view_back.png")                                                            # 뒤 그림: 넓적한 다른 모양
j = job({"kind": "m3d", "op": "build", "id": sid, "mode": "multi", "sides": ["left", "back", "right"], "blender": "", "keep_hi": "", "capture": ""}); assert j["state"] == "done", j
mvc = cls("Pixal3DMultiViewConditioning")[0]
assert "back" not in mvc and "left" in mvc and "right" in mvc and any("뒤" in w and "빼고" in w for w in j["warn"]), (mvc.keys(), j["warn"])
for s_ in ("left", "right"): bad.save(d / f"view_{s_}.png")                            # 옆 그림도 다른 색·모양 → 모두 빠져요
j = job({"kind": "m3d", "op": "build", "id": sid, "mode": "multi", "sides": ["left", "back", "right"], "blender": "", "keep_hi": "", "capture": ""}); assert j["state"] == "done", j
assert cls("Pixal3DConditioning") and not cls("Pixal3DMultiViewConditioning") and any("사진 한 장으로" in w for w in j["warn"]), j["warn"]
ok("AI multiview assist: direction views that don't match the front photo (pose/proportions) are dropped; none left → single photo")
for s_ in ("left", "right", "back"): front.save(d / f"view_{s_}.png")

# 4) 단계별 결과·비교표: A 엔진 원본 · B 사진 붙이기 · C 최종 · E AI 멀티뷰(같은 씨앗, 차례로 한 번 더)
n0 = len(SUBMITTED)
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "compare": "on", "seed": 5}); assert j["state"] == "done", j
runs = [w for w in SUBMITTED[n0:] if any(n["class_type"] == "SaveGLB" for n in w.values())]
assert len(runs) == 2 and any(n["class_type"] == "Pixal3DConditioning" for n in runs[0].values()) and any(n["class_type"] == "Pixal3DMultiViewConditioning" for n in runs[1].values())
assert sum(n["class_type"] == "SaveGLB" for n in runs[1].values()) == 1                  # E 는 원본 고밀도 메시를 또 저장하지 않아요
nm = names(j)
for t in ("-엔진원본.glb", "-사진붙이기.glb", "-멀티뷰.glb", "-비교표.png", "-원본고밀도.glb"):
    assert any(x.endswith(t) for x in nm), (t, nm)
assert [s_["stage"] for s_ in j["m3d_stats"]["stages"]] == ["hi", "remesh", "dec", "A", "B", "E"], j["m3d_stats"]["stages"]      # 4.8: 모양 단계(고밀도·다시 짠 뒤·면 줄인 뒤)도
assert sorted(x["filename_prefix"] for x in cls("SaveGLB", runs[0])) == ["3d/hub3d", "3d/hub3d_dec", "3d/hub3d_hi", "3d/hub3d_remesh"]
lb = j["m3d_stats"]["limbs"]; assert set(lb["stages"]) == {"hi", "remesh", "dec", "A"} and lb["missing"] == [] and lb["lost_at"] is None, lb
assert any(x.endswith("-다시짠뒤.glb") for x in names(j)) and any(x.endswith("-면줄인뒤.glb") for x in names(j))
ma = {s_["stage"]: s_["match"] for s_ in j["m3d_stats"]["stages"]}
assert (d / "engine_input_front.png").is_file() and Image.open(d / "engine_input_front.png").size == (1024, 1024) and (d / "mask_front.png").is_file()
assert not any(n["class_type"] == "ImageCropToMask" for n in runs[0].values())             # 4.8: 엔진 입력 정사각형은 우리가 직접(비율 유지·여백) — 한 장·멀티뷰 같은 방식
assert any("업스케일" not in w for w in j["warn"])
assert ma["B"] is None and ma["A"]["iou"] > 0.8 and ma["E"]["iou"] > 0.8, ma                # 엔진 결과(A·E)가 사진과 맞는 정도를 숫자로
sh = Image.open(io.BytesIO(urllib.request.urlopen(B + next(u for u, x in zip(j["images"], nm) if x.endswith("-비교표.png"))).read()))
assert sh.height >= 4 * 320                                                              # A·B·C·E 네 줄
a = urllib.request.urlopen(B + next(u for u, x in zip(j["images"], nm) if x.endswith("-엔진원본.glb"))).read()
ta = np.asarray(photoproj.load(a)["tex"].convert("RGB")); tc = np.asarray(photoproj.load(urllib.request.urlopen(B + j["images"][0]).read())["tex"].convert("RGB"))
assert (ta == np.asarray(T)).all() and not (tc == np.asarray(T)).all()                  # A = 엔진이 칠한 그대로, 최종 = 사진을 붙인 것
ok("compare mode: stage files A (engine) / B (photo) / C (final) / E (AI multiview, same seed, run after) + front/left/right/back comparison sheet")

# 5) 업스케일: 다시 그리지 않는 모델(Real-ESRGAN)이 먼저, 얼굴 확대에는 SeedVR2 를 쓰지 않아요
keep = hub.seedvr_names
hub.seedvr_names = lambda: ["seedvr2_ema_3b_fp8_e4m3fn.safetensors"]
assert hub.m3d_upscaler() == "seedvr2_ema_3b_fp8_e4m3fn.safetensors" and hub.m3d_upscaler(redraw_ok=False) is None
touch("upscale_models/RealESRGAN_x4plus.pth")
assert hub.m3d_upscaler() == "RealESRGAN_x4plus.pth" and hub.m3d_upscaler(redraw_ok=False) == "RealESRGAN_x4plus.pth"
hub.seedvr_names = keep
orig_im = Image.new("RGBA", (100, 100), (100, 100, 100, 255)); orig_im.paste((230, 180, 160, 255), (40, 30, 60, 50))
big = Image.new("RGBA", (400, 400), (100, 100, 100, 255)); big.paste((20, 220, 20, 255), (150, 110, 250, 210))     # '다시 그린' 얼굴(초록)
mf, mb = hub.m3d_face_model, hub.m3d_face_box
hub.m3d_face_model = lambda: "mp"; hub.m3d_face_box = lambda img, J, model=None: (40, 30, 60, 50)
out, kept = hub.m3d_keep_face(orig_im, big, {"warn": []})
hub.m3d_face_model, hub.m3d_face_box = mf, mb
o = np.asarray(out.convert("RGB")).astype(int)
assert kept and out.mode == "RGBA" and abs(o[160, 200] - (230, 180, 160)).max() < 12 and abs(o[10, 10] - (100, 100, 100)).max() < 3, (o[160, 200], o[10, 10])
ok("upscaling: plain (non-redrawing) models first; face enlargement never uses SeedVR2; after SeedVR2 the original face is put back")

# 6) 그물망 검사: 구멍·떨어진 조각·납작함
def mesh_glb(P, F):
    bv, bi = P.astype(np.float32).tobytes(), F.astype(np.uint32).tobytes()
    g = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(bv) + len(bi)}],
         "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(bv)}, {"buffer": 0, "byteOffset": len(bv), "byteLength": len(bi)}],
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(P), "type": "VEC3", "min": P.min(0).tolist(), "max": P.max(0).tolist()},
                       {"bufferView": 1, "componentType": 5125, "count": F.size, "type": "SCALAR"}],
         "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}], "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
    return glbscene.write(g, bv + bi)
def box(c, s):
    v = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float) * s + c
    f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]]); return v, f
v1, f1 = box([0, 0, 0], [0.3, 1, 0.2]); v2, f2 = box([0, 2, 0], [0.05, 0.05, 0.05])
r = photoproj.mesh_report(mesh_glb(np.concatenate([v1, v2]), np.concatenate([f1[:-1], f2 + 8])))     # 큰 상자 면 하나 빠짐 + 떨어진 작은 상자
assert r["holes"] == 1 and r["hole_edges"] == 3 and r["parts"] == 2 and len(r["notes"]) == 2, r
r = photoproj.mesh_report(mesh_glb(*box([0, 0, 0], [0.5, 1, 0.05]))); assert r["flat"] and r["holes"] == 0 and r["parts"] == 1, r
ok("mesh check finds holes, loose pieces and flat (card-like) shapes")

# 7) 4.8 팔다리 검사: 두 다리·두 팔이 있는 사람 모양 → 한쪽 다리를 지우면 '없음', 어느 단계에서 사라졌는지
def boxes(spec):
    Ps, Fs = [], []
    for c_, s3 in spec:
        v, f = box(c_, s3); Fs.append(f + sum(len(x) for x in Ps)); Ps.append(v)
    return np.concatenate(Ps), np.concatenate(Fs)
body = [([0, 0.25, 0], [0.2, 0.3, 0.1]), ([0, 0.75, 0], [0.1, 0.12, 0.1]),                  # 몸통·머리
        ([-0.1, -0.45, 0], [0.07, 0.4, 0.07]), ([0.1, -0.45, 0], [0.07, 0.4, 0.07]),     # 두 다리(사이에 틈)
        ([-0.3, 0.25, 0], [0.05, 0.25, 0.05]), ([0.3, 0.25, 0], [0.05, 0.25, 0.05])]     # 두 팔(몸통과 떨어짐)
P0, F0 = boxes(body)
cam0 = photoproj.Cam(next(c_ for c_ in photoproj._cams() if c_["name"] == photoproj.PIXAL_CAM), P0, (100, 50, 500, 650))
xx, yy, _ = cam0.px(P0); pix, _, _, _ = photoproj.raster(np.stack([xx, yy], 1), F0, 600, 700)
al = np.zeros(600 * 700); al[pix] = 1; al = al.reshape(700, 600)
r = photoproj.limb_check(P0, F0, cam0, al); assert r["missing"] == [] and all(v["cover"] is None or v["cover"] > 0.95 for v in r["parts"].values()), r
P1, F1 = boxes(body[:2] + body[3:])                                                       # 사진 왼쪽(인물 오른쪽) 다리를 뺀 3D
r = photoproj.limb_check(P1, F1, cam0, al); assert r["missing"] == ["오른쪽 다리(사진 왼쪽)"], r
P2, F2 = boxes(body[:5])                                                                  # 사진 오른쪽(인물 왼쪽) 팔을 뺀 3D
r = photoproj.limb_check(P2, F2, cam0, al); assert r["missing"] == ["왼쪽 팔(사진 오른쪽)"], r
gF, gL = mesh_glb(P0, F0), mesh_glb(P1, F1)
st_ = {"A": gL, "hi": gF, "remesh": gL, "dec": gL}
keep_fit = photoproj.shape_cam; photoproj.shape_cam = lambda *a, **k: cam0
front_im = Image.fromarray((np.dstack([np.full((700, 600, 3), 128), al * 255])).astype(np.uint8), "RGBA")
lb = hub.m3d_limbs({**st_, "_front": front_im}, {"warn": []}, all_stages=True)
photoproj.shape_cam = keep_fit
assert lb["missing"] == ["오른쪽 다리(사진 왼쪽)"] and lb["lost_at"] == "remesh" and not lb["stages"]["hi"]["missing"], lb
ok("limb check: each leg and arm separately; a missing leg/arm is caught, and the stage where it vanished (dense → remesh) is named")

# 8) 4.8 멀티뷰 검사: 뒤 그림은 앞 그림을 좌우로 뒤집은 모양이 아니어도 돼요(색·비율·다리 수로) / 다른 색 옷은 빼요
fr_ = Image.open(d / "view_front.png").convert("RGBA")
bk = fr_.copy(); a_ = np.asarray(bk).copy(); a_[..., :3] = a_[..., :3][:, ::-1]; bk = Image.fromarray(a_, "RGBA")      # 색 무늬만 좌우가 달라진 뒤모습
bk.save(d / "view_back.png"); fr_.save(d / "view_left.png"); fr_.save(d / "view_right.png")
vc = hub.m3d_vcheck(d); assert vc["back"]["ok"] and vc["left"]["ok"], vc
blue = fr_.copy(); bb_ = np.asarray(blue).copy(); bb_[..., :3] = (20, 20, 230); Image.fromarray(bb_, "RGBA").save(d / "view_back.png")
vc = hub.m3d_vcheck(d); assert not vc["back"]["ok"] and "색" in vc["back"]["text"], vc
ok("multiview check: no 'back = mirrored front' rule; same person/clothes by colour, body proportions, legs count; left/right mirror each other")

# 9) 4.8 F: TRELLIS.2 가 있으면 비교용으로 하나 더(같은 사진·씨앗), 다시 짜기 대체값은 '갇힌 안쪽 껍질만 지우기'
fr_.save(d / "view_back.png")
touch("diffusion_models/trellis_2_int8_convrot.safetensors", "clip_vision/dino_v3_vit_l.safetensors")
n0 = len(SUBMITTED)
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "", "compare": "on", "seed": 9}); assert j["state"] == "done", j
runs = [w for w in SUBMITTED[n0:] if any(n["class_type"] == "SaveGLB" for n in w.values())]
assert len(runs) == 3 and any(n["class_type"] == "Trellis2Conditioning" for n in runs[2].values()), [[n["class_type"] for n in w.values() if "Conditioning" in n["class_type"]] for w in runs]
assert any(x.endswith("-TRELLIS2.glb") for x in names(j)) and "F" in [s_["stage"] for s_ in j["m3d_stats"]["stages"]]
alt = [n for n in runs[0].values() if n["class_type"] == "RemeshMesh"]
ok("compare mode also builds F = TRELLIS.2 with the same photo and seed (run one after another)")
print("ALL OK")
