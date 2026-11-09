"""4.0: 3D 만들기 — 사진 점검·작업 폴더, 방향 칸(내 사진·비우기), 여러 방향 그림(Qwen 편집), TRELLIS.2/Pixal3D 그래프,
없는 모델·노드 안내, Blender 마무리(가짜 blender 로 LOD·묶음 zip), Blender 실패 시 GLB 만 저장, wf_fit, 따옴표 글자 지키기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, zipfile, urllib.request, urllib.error, py_compile
os.environ["TEST_HUB_PORT"] = "17991"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid):
    for _ in range(400):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def core(j): return [u for u in j["images"] if not any(t in urllib.parse.unquote(u) for t in ("-4방향.png", "-원본고밀도.glb", "-비교표.png"))]   # 3D 본 결과(캡처·원본 메시 빼고)
def cls(c): return [v["inputs"] for v in SUBMITTED[-1].values() if v["class_type"] == c]
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
def rgba(box=(100, 60, 300, 360), size=(400, 400), col=(200, 60, 60)):
    im = Image.new("RGBA", size, (0, 0, 0, 0)); im.paste(col + (255,), box)
    b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
py_compile.compile(BASE + "/LocalAI-Studio/hub/blender_game.py", doraise=True)
# 배경 모델이 없으면: 받기 시작 + 안내
hub.rmbg_install = lambda p: {"ok": True}
opaque = png_url(Image.new("RGB", (300, 300), (10, 120, 200)))
j = job({"kind": "m3d", "op": "prep", "image": opaque}); assert j["state"] == "error" and "배경" in j["error"] and "받기 시작" in j["error"], j
ok("prep: no background model → starts the download and explains")
class FakeCut:
    def cut(self, img, _):
        a = Image.new("L", img.size, 0); w, h = img.size; a.paste(255, (w // 4, h // 6, w * 3 // 4, h * 5 // 6))
        o = img.convert("RGBA"); o.putalpha(a); return o
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True; hub.rmbg_engine = lambda k: FakeCut()
# 사진 점검
n0 = len(SUBMITTED)
j = job({"kind": "m3d", "op": "prep", "image": rgba(), "kind3": "character", "name": "기사 캐릭터!"}); assert j["state"] == "done", j
S = j["m3d"]; assert S["kind"] == "character" and S["name"] == "기사_캐릭터" and S["checks"][0]["level"] in ("ok", "warn") and S["slots"]["front"] and not S["slots"]["left"], S
assert len(SUBMITTED) == n0 and S["ready"] == {"trellis": False, "multiview": False, "pixal": False} and not j["images"]
sid = S["id"]; assert (hub.M3D_DIR / sid / "orig.png").is_file()
im = Image.open(io.BytesIO(urllib.request.urlopen(B + S["slots"]["front"]).read())); assert im.mode == "RGBA"
for bad in ("/m3d/" + sid + "/meta.json", "/m3d/" + sid + "/..%2Fmeta.json", "/m3d/zzz/orig.png"):
    try: urllib.request.urlopen(B + bad); assert False, bad
    except urllib.error.HTTPError as e: assert e.code == 404, (bad, e.code)
assert get("/api/m3d")["items"][0]["id"] == sid and get("/api/m3d/" + sid)["id"] == sid and req("/api/m3d/nothexid0000")[0] == 404
ok("prep: cut-out saved in its own work folder (no ComfyUI, no output file), list/open, only view files served")
cut_edge = hub.m3d_analyze(Image.open(io.BytesIO(base64.b64decode(rgba((0, 50, 250, 350)).split(",")[1]))))[0]
assert cut_edge[0]["level"] == "bad" and "가장자리" in cut_edge[0]["text"]
small = hub.m3d_analyze(Image.open(io.BytesIO(base64.b64decode(rgba((180, 180, 230, 230)).split(",")[1]))))[0]
assert any("작게" in c["text"] for c in small) and any("px" in c["text"] for c in small)
two = Image.new("RGBA", (400, 400), (0, 0, 0, 0)); two.paste((9, 9, 9, 255), (40, 100, 160, 300)); two.paste((9, 9, 9, 255), (240, 100, 360, 300))
assert any("2개" in c["text"] for c in hub.m3d_analyze(two)[0]) and hub.m3d_analyze(Image.new("RGBA", (64, 64)))[0][0]["level"] == "bad"
ok("analysis: cut at the edge, small, multiple pieces, nothing found")
# 방향 칸
r = post("/api/m3d/slot", {"id": sid, "side": "left", "image": rgba(col=(10, 200, 10))}); assert r["slots"]["left"], r
assert post("/api/m3d/slot", {"id": sid, "side": "front", "clear": 1})["error"] and post("/api/m3d/slot", {"id": sid, "side": "top", "image": rgba()})["error"]
r = post("/api/m3d/slot", {"id": sid, "side": "left", "clear": 1}); assert not r["slots"]["left"]
r = post("/api/m3d/slot", {"id": sid, "side": "front", "image": rgba((0, 50, 250, 350))}); assert r["checks"][0]["level"] == "bad"
post("/api/m3d/slot", {"id": sid, "side": "front", "image": rgba()})
ok("slots: my own photo (background removed), clear, front can't be cleared, replacing front re-checks")
# 여러 방향 그림(Qwen-Image 2.1 편집)
j = job({"kind": "m3d", "op": "views", "id": sid, "sides": ["left", "back"], "fast": "on"}); assert j["state"] == "done", j
assert j["m3d"]["slots"]["left"] and j["m3d"]["slots"]["back"] and not j["m3d"]["slots"]["right"]
assert len(j["images"]) == 2 and all("/3D/" in u and u.endswith(".png") for u in j["images"])          # 4.3: 방향 그림도 결과 폴더(3D)에 남아요
txt = " ".join(str(v["inputs"].get("prompt", "")) + str(v["inputs"].get("text", "")) for v in SUBMITTED[-1].values())
assert "back" in txt and "white background" in txt, txt[:300]
assert any("lightning" in str(v["inputs"].get("lora_name", "")).lower() for v in SUBMITTED[-1].values())
assert Image.open(hub.M3D_DIR / sid / "view_back.png").mode == "RGBA"
ok("views: Qwen 2.1 edit per side (fast = Lightning), cut out, stored in slots")
# 3D 만들기 — 모델 없음 → need
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": False}); assert j["state"] == "error" and "TRELLIS.2" in j["error"] and j["need"] == ["trellis2"], j
touch("diffusion_models/trellis_2_int8_convrot.safetensors", "diffusion_models/trellis_2_fp16.safetensors", "clip_vision/dino_v3_vit_l.safetensors",
      "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors")
assert hub.m3d_ready() == {"trellis": True, "multiview": False, "pixal": False}
# 한 장(방향 그림은 골랐지만 Pixal3D 없음 → 경고하고 앞 사진만)
j = job({"kind": "m3d", "op": "build", "id": sid, "sides": ["left", "back"], "res": "1024", "faces": "50000", "tex": "4096", "blender": False, "seed": 7})
assert j["state"] == "done" and len(core(j)) == 1 and j["images"][0].endswith(".glb") and "/3D/" in j["images"][0], j
assert any(urllib.parse.unquote(u).endswith("-4방향.png") for u in j["images"]) and any(urllib.parse.unquote(u).endswith("-원본고밀도.glb") for u in j["images"]), j["images"]   # 4.7: 4방향 캡처·원본 고밀도 메시
assert any("Pixal3D" in w for w in j["warn"]) and not any("Blender" in w for w in j["warn"]), j["warn"]
assert cls("UNETLoader")[0]["unet_name"] == "trellis_2_int8_convrot.safetensors" and cls("Trellis2Conditioning") and not cls("Pixal3DMultiViewConditioning")
assert [x["seed"] for x in cls("KSampler")] == [7, 8, 9, 10] and cls("Trellis2UpsampleStage")[0]["target_resolution"] == 1024
assert cls("DecimateMesh")[0]["target_face_count"] == 50000 and cls("BakeTextureFromVoxel")[0]["texture_size"] == 4096 and cls("RemeshMesh")[0]["resolution"] == 768
assert sorted(x["filename_prefix"] for x in cls("SaveGLB")) == ["3d/hub3d", "3d/hub3d_hi"] and len(cls("LoadImage")) == 1 and cls("VAELoader")[0]["vae_name"].startswith("trellis_2_shape")
assert urllib.request.urlopen(B + j["images"][0]).read()[:4] == b"glTF"
# 4.1: 공식 예시와 같은 샘플링 — 구조/모양 단계는 앞쪽에만 cfg(CFGOverride)·RescaleCFG, 구조는 shift 5, 모양 512 는 20단계, 닫힌 몸체(solid)로 다시 짜기
co = sorted((x["start_percent"], x["cfg"]) for x in cls("CFGOverride")); assert co == [(0.667, 1.0), (0.769, 1.0)], co
assert sorted(x["multiplier"] for x in cls("RescaleCFG")) == [0.5, 0.7] and [x["shift"] for x in cls("ModelSamplingSD3")] == [5.0]
ks = sorted(cls("KSampler"), key=lambda x: x["seed"]); assert [(x["steps"], x["cfg"], x["scheduler"]) for x in ks] == [(12, 7.5, "normal"), (20, 7.5, "normal"), (12, 7.5, "simple"), (12, 1.0, "normal")], ks
node = lambda ref: SUBMITTED[-1][ref[0]]["class_type"]
assert [node(x["model"]) for x in ks] == ["ModelSamplingSD3", "RescaleCFG", "RescaleCFG", "UNETLoader"]
rm = cls("RemeshMesh")[0]; assert rm["sign_mode"] == "solid" and rm["sign_mode.fill"] == 20.0 and rm["smooth_iters"] == 20 and not any("drop_inverted" in k for k in rm), rm
assert (lambda b: abs(max(b[2] - b[0], b[3] - b[1]) - 1024 / 1.0) <= 3)(Image.open(hub.M3D_DIR / sid / "engine_input_front.png").convert("L").point(lambda v: 255 if v > 8 else 0).getbbox()) and node(cls("BakeNormalMapFromMesh")[0]["high_poly"]) == "RemeshMesh"
assert node(cls("Trellis2TextureStage")[0]["positive"]) == "Trellis2UpsampleStage" and len(cls("MeshSmoothNormals")) == 2
side = json.loads(next((hub.OUT / "3D").rglob("*.glb.json")).read_text(encoding="utf-8")); assert side["engine"] == "TRELLIS.2" and side["views"] == ["front"]
ok("build (single view): TRELLIS.2 graph — seeds, upsample to 1024, remesh, faces, texture size; Pixal3D fallback warned; saved in 3D/")
# 빠르게(512) + 다시 짜기 끔 → 올려 그리기·다시 짜기 없음, 이상한 값은 기본값
j = job({"kind": "m3d", "op": "build", "id": sid, "res": "512", "remesh": False, "faces": "123", "tex": "9999", "blender": False}); assert j["state"] == "done", j
assert not cls("Trellis2UpsampleStage") and not cls("RemeshMesh") and cls("DecimateMesh")[0]["target_face_count"] == hub.M3D_KIND[hub.m3d_meta(sid)["kind"]]["faces"] and cls("UnwrapMesh")[0]["resolution"] == 2048
ok("build options: 512 skips upsample, remesh off, invalid faces/tex fall back")
# Pixal3D 멀티뷰
touch("diffusion_models/pixal3d_multiview_int8_convrot.safetensors", "clip_vision/dino_v3_L_naf_fp32.safetensors")
for s_ in ("left", "back"): Image.open(hub.M3D_DIR / sid / "view_front.png").save(hub.M3D_DIR / sid / f"view_{s_}.png")   # 4.8: 같은 인물·옷(색)이어야 멀티뷰에 써요
j = job({"kind": "m3d", "op": "build", "id": sid, "sides": ["left", "back", "right"], "blender": False}); assert j["state"] == "done" and not [w for w in j.get("warn", []) if "업스케일로 키워" not in w], j
pc = cls("Pixal3DMultiViewConditioning"); assert pc and set(pc[0]) >= {"front", "left", "back"} and "right" not in pc[0] and len(cls("LoadImage")) == 3
assert not cls("ImageCropToMask") and all(node(pc[0][k]) == "LoadImage" for k in ("front", "left", "back"))     # 허브가 같은 배율로 맞춰 넣어요
assert cls("UNETLoader")[0]["unet_name"].startswith("pixal3d") and cls("CLIPVisionLoader")[0]["clip_name"] == "dino_v3_L_naf_fp32.safetensors"
ok("build (multi-view): Pixal3D with front + the views that exist (empty right skipped)")
# 노드 없음
STATE["missing"].add("Trellis2ShapeStage"); hub._CAPS["t"] = 0
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": False}); assert j["state"] == "error" and "Trellis2ShapeStage" in j["error"] and "update" in j["error"], j
STATE["missing"].discard("Trellis2ShapeStage"); hub._CAPS["t"] = 0
ok("missing ComfyUI 3D nodes → tells to update ComfyUI")
# Blender 없음 → 경고하고 GLB 만
assert get("/api/blender")["installed"] is False and "error" in post("/api/blender/check", {})
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": True}); assert j["state"] == "done" and len(core(j)) == 1 and any("Blender 가 없어" in w for w in j["warn"]), j
r = post("/api/blender/install", {}); assert "윈도우" in r.get("error", ""), r
ok("no Blender → GLB only with a hint; auto install is Windows-only")
# 가짜 Blender 로 마무리
fb = BASE + "/test/fake_blender.py"; os.chmod(fb, 0o755); os.environ["BLENDER_EXE"] = fb
st = get("/api/blender"); assert st["installed"] and st["version"] == "4.5.15" and post("/api/blender/check", {})["ok"]
j = job({"kind": "m3d", "op": "build", "id": sid, "sides": [], "blender": "on", "height": "1.8", "rotate": "450", "lods": True, "fmt_glb": True, "fmt_fbx": True, "fmt_obj": True})
assert j["state"] == "done" and not [w for w in j.get("warn", []) if "업스케일로 키워" not in w], j
glb, z = j["images"][:2]; assert glb.endswith(".glb") and z.endswith(".zip") and "-m3d-" in z
assert urllib.request.urlopen(B + glb).read().endswith(b"LOD0")
names = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(B + z).read())).namelist()
assert {"기사_캐릭터_LOD0.glb", "기사_캐릭터_LOD1.fbx", "기사_캐릭터_LOD2.obj", "기사_캐릭터.blend", "textures/base.png"} <= set(names) and "result.json" not in names, names
s = j["m3d_stats"]; assert [x["ratio"] for x in s["lods"]] == [1.0, 0.5, 0.2] and s["size_m"][2] == 1.8 and s["lods"][1]["tris"] == 10000
assert "LOD 3단계" in j["msg"] and not list((hub.M3D_DIR / sid).glob("build_*")) and not list((hub.M3D_DIR / sid).glob("*.zip"))
info = json.loads((Path(str(hub.out_path(z[5:])) + ".json")).read_text(encoding="utf-8")); assert info["pack"] and info["blender"] == "4.5.15"
ok("Blender finish: LOD 1/0.5/0.2, GLB+FBX+OBJ+.blend+textures in a zip, LOD0 shown, stats, temp folder cleaned")
j = job({"kind": "m3d", "op": "build", "id": sid, "lods": "", "fmt_fbx": "", "rotate": "90"}); assert j["state"] == "done", j
assert len(j["m3d_stats"]["lods"]) == 1 and j["m3d_stats"]["size_m"][2] == 1.7      # 캐릭터 기본 키 1.7m
assert hub.m3d_opts({"rotate": "450"}, {})["rotate"] == 90 and hub.m3d_opts({"fmt_glb": "", "fmt_fbx": ""}, {})["formats"] == ["glb"]
ok("Blender options: no LODs, glb only, default height by kind, rotation snapped to 90°")
open("/tmp/claude-0/fail_bl", "w").close(); os.environ["FAKE_BLENDER_FAIL"] = "/tmp/claude-0/fail_bl"
j = job({"kind": "m3d", "op": "build", "id": sid}); assert j["state"] == "done" and len(core(j)) == 1 and j["images"][0].endswith(".glb"), j
assert any("Blender 마무리 실패" in w and "메시" in w for w in j["warn"]) and "lods" not in (j.get("m3d_stats") or {}), j
os.remove("/tmp/claude-0/fail_bl")
ok("Blender failure → reason shown, ComfyUI GLB still saved")
# 이미지 기능 메뉴 '사진 → 3D 모델'(한 번에, Blender 없이)
j = job({"kind": "feat", "feature": "img3d", "image": rgba(), "quality": "high", "faces": "5000"}); assert j["state"] == "done" and len(j["images"]) == 1 and j["images"][0].endswith(".glb") and "-m3d-" in j["images"][0], j
assert cls("Trellis2UpsampleStage")[0]["target_resolution"] == 1536 and cls("DecimateMesh")[0]["target_face_count"] == 5000 and not [w for w in j.get("warn", []) if "업스케일로 키워" not in w]
ok("feature menu photo → 3D: one-shot TRELLIS.2, no Blender")
# 지우기
r = post("/api/m3d/delete", {"id": sid}); assert all(x["id"] != sid for x in r["items"]) and not (hub.M3D_DIR / sid).exists()
assert list(hub.out_files(hub.OUT / "3D", {".glb"}))
ok("delete work folder; made 3D files stay")
# wf_fit
real = hub.caps
hub.caps = lambda *a, **k: {"nodes": ["A"], "info": {"A": {"input": {"required": {"x": ["INT", {"default": 3}], "y": ["INT", {"default": 5}], "img": ["IMAGE"]}, "optional": {"o": ["INT", {}]}}}}}
g = hub.wf_fit({"1": {"class_type": "A", "inputs": {"x": 1, "zz": 2, "o": 4}}, "2": {"class_type": "Unknown", "inputs": {"q": 1}}})
hub.caps = real
assert g["1"]["inputs"] == {"x": 1, "o": 4, "y": 5} and g["2"]["inputs"] == {"q": 1}, g
DC = {"options": [{"key": "udf", "inputs": {"required": {"qef": ["BOOLEAN", {"default": False}]}, "optional": {"drop_enclosed_components": ["BOOLEAN", {"default": False}]}}},
                  {"key": "solid", "inputs": {"required": {"fill": ["FLOAT", {"default": 20.0}]}}}], "default": "udf"}
hub.caps = lambda *a, **k: {"nodes": ["R"], "info": {"R": {"input": {"required": {"mesh": ["MESH"], "sign_mode": ["COMFY_DYNAMICCOMBO_V3", DC]}}}}}
g = hub.wf_fit({"1": {"class_type": "R", "inputs": {"mesh": ["2", 0]}}, "2": {"class_type": "R", "inputs": {"mesh": ["1", 0], "sign_mode": "solid", "sign_mode.fill": 5}}})
hub.caps = real
assert g["1"]["inputs"] == {"mesh": ["2", 0], "sign_mode": "udf", "sign_mode.qef": False, "sign_mode.drop_enclosed_components": False}, g["1"]
assert g["2"]["inputs"] == {"mesh": ["1", 0], "sign_mode": "solid", "sign_mode.fill": 5}, g["2"]
ok("wf_fit: drops unknown inputs, fills missing required defaults, fills DynamicCombo children (parent.child), leaves unknown nodes alone")
# 4.1.1: 예전 ComfyUI — RemeshMesh 선택지에 solid 가 없으면 ComfyUI 가 칸을 통째로 빼서 'missing sign_mode' 로 멈췄어요 → udf + 안쪽 껍질 지우기로 바꿔요
OLD = {"options": [{"key": "udf", "inputs": {"optional": {"qef": ["BOOLEAN", {"default": False}], "drop_inverted_components": ["BOOLEAN", {"default": False}],
                                                       "drop_enclosed_components": ["BOOLEAN", {"default": False}]}}},
                   {"key": "sdf", "inputs": {"required": {"qef": ["BOOLEAN", {"default": True}]}}}], "default": "udf"}
RM = {"input": {"required": {"mesh": ["MESH"], "resolution": ["INT", {"default": 512}], "sign_mode": ["COMFY_DYNAMICCOMBO_V3", OLD]},
                "optional": {"band": ["FLOAT", {}], "project_back": ["FLOAT", {}], "fix_poles": ["BOOLEAN", {}], "smooth_iters": ["INT", {}],
                             "drop_small_components": ["FLOAT", {}], "precluster_max_verts": ["INT", {}]}}}
q0 = {"files": {"model": "m", "dino": "d", "svae": "s", "tvae": "t"}, "views": {"front": "f.png"}, "seed": 1, "steps": (12, 20, 12, 12), "cfg": (7.5, 7.5, 1.0),
      "res": 1024, "remesh": 768, "faces": 20000, "tex": 2048}
notes = []
hub.caps = lambda *a, **k: {"nodes": ["RemeshMesh"], "info": {"RemeshMesh": RM}}
g = hub.wf_fit(hub.flows.wf_trellis(q0), notes)
hub.caps = real
rm = next(v["inputs"] for v in g.values() if v["class_type"] == "RemeshMesh")
assert rm["sign_mode"] == "udf" and rm["sign_mode.drop_inverted_components"] is False and rm["sign_mode.drop_enclosed_components"] is True and "sign_mode.fill" not in rm and rm["sign_mode.qef"] is False, rm
assert notes == ["RemeshMesh.sign_mode: solid → udf"] and not any("_alt" in v for v in g.values())
g = hub.wf_fit(hub.flows.wf_trellis(q0))                                           # 설명이 없는 노드여도 '_alt' 는 빠져요(그대로 보내면 ComfyUI 가 거부)
assert not any("_alt" in v for v in g.values()) and next(v["inputs"] for v in g.values() if v["class_type"] == "RemeshMesh")["sign_mode"] == "solid"
NEW = {"options": OLD["options"] + [{"key": "solid", "inputs": {"required": {"fill": ["FLOAT", {"default": 20.0}]}, "optional": {"qef": ["BOOLEAN", {"default": False}]}}}], "default": "udf"}
notes = []; hub.caps = lambda *a, **k: {"nodes": ["RemeshMesh"], "info": {"RemeshMesh": {"input": {**RM["input"], "required": {**RM["input"]["required"], "sign_mode": ["COMFY_DYNAMICCOMBO_V3", NEW]}}}}}
g = hub.wf_fit(hub.flows.wf_trellis(q0), notes); hub.caps = real
rm = next(v["inputs"] for v in g.values() if v["class_type"] == "RemeshMesh"); assert rm["sign_mode"] == "solid" and rm["sign_mode.fill"] == 20.0 and not notes, rm
assert "sign_mode.drop_inverted_components" not in rm
ok("wf_fit: an option this ComfyUI doesn't know (solid) falls back to udf + drop inner shell, stray children removed, '_alt' never sent")
# 따옴표 글자 지키기
seen = []
def tr(t, style): seen.append(t); return t.replace("간판", "a sign that says").replace("고양이", "a cat")
real_tr = hub.translate; hub.translate = tr
assert hub.translate_keep_quotes("간판 '오늘 영업'", "") == 'a sign that says "오늘 영업"' and "오늘 영업" not in seen[-1]
assert hub.translate_keep_quotes('고양이 "HELLO"', "") == 'a cat "HELLO"'
assert hub.translate_keep_quotes('a sign "안녕"', "") == 'a sign "안녕"'       # 따옴표 밖에 한글이 없으면 그대로
hub.translate = lambda t, s: "a cat"
assert hub.translate_keep_quotes('고양이 "야옹"', "") == 'a cat, with the text "야옹"'
hub.translate = real_tr
ok("translation keeps quoted text as-is (and re-adds it if the translator drops it)")
print("ALL OK")
