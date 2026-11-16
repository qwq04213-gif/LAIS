"""얼굴 3D 형상 보정(실험) — 여성 얼굴 사진으로 전체 흐름: 3D 엔진은 한 번만, 같은 원본에서 A(기존 투영)·B(얼굴 정렬)·C(얼굴 정렬 + 형상 보정),
C 에서 얼굴 정점이 실제로 옮겨졌는지(얼굴 밖은 그대로), 정답 3D 에 가까워졌는지(앞·좌우 45°·옆), 실패·불합격이면 기존 결과로 돌아가는지.
가짜 3D(정답이 있는 머리 — geofix.py)와 가짜 ComfyUI 로 돌리고, 얼굴 랜드마크만 진짜(MediaPipe)예요. 실제 Pixal3D·GPU 결과는 미검증.
필요: pip install mediapipe scipy scikit-image, libEGL, 인터넷(랜드마크 모델을 처음 한 번 받아요)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, hashlib, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17959"
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import numpy as np
from PIL import Image
import glbscene, photoproj, facegeo, geofix
ok = lambda m: print("PASS", m, flush=True)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid):
    for _ in range(5000):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
def url(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def path_of(u): return hub.OUT / urllib.parse.unquote(u[len("/out/"):])
sha = lambda b: hashlib.sha256(b).hexdigest()

fx = geofix.build("female", res=(150, 110), ts=1024)
assert fx, "얼굴 사진·랜드마크 모델을 준비하지 못했어요(mediapipe · 인터넷 필요)"
PHOTO, FB = fx["photo"], fx["box"]
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True
class Cut:
    def cut(self, img, _): return img.convert("RGBA")
hub.rmbg_engine = lambda k: Cut()
touch("diffusion_models/trellis2_test.safetensors", "diffusion_models/pixal3d_int8_convrot.safetensors", "clip_vision/dino_v3_L_naf_fp32.safetensors",
      "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors", "geometry_estimation/moge_2_vitl_normal_fp16.safetensors",
      "detection/mediapipe_face_fp32.safetensors")
hub.caps(force=True)
assert hub.m3d_lm_ready()
STATE["glb"] = fx["engine"]
hub.M3D_HEAD_MIN = 1024                                   # 시험 환경(CPU)에서 빨리 끝나게
hub.m3d_face = lambda photo, J: (FB, None)                # 얼굴 상자는 정해 둔 것(얼굴 찾기 자체는 다른 시험에서)
LM = {"fail_from": None, "n": 0}
def lm_fn(src, sets):                                     # ComfyUI 의 랜드마크 그리기 노드 흉내: 진짜 MediaPipe 로 찾아 같은 색 선으로
    LM["n"] += 1
    if LM["fail_from"] is not None and LM["n"] >= LM["fail_from"]:
        return [Image.new("RGB", src.size, 0) for _ in sets]
    xy = geofix.points(src)
    return [geofix.draw_lines(src, grp, xy=xy) for grp in sets]
STATE["lm_fn"] = lm_fn
j = job({"kind": "m3d", "op": "prep", "image": url(PHOTO), "kind3": "character", "name": "geofit"}); assert j["state"] == "done", j
sid = j["m3d"]["id"]; d = hub.M3D_DIR / sid
hub.m3d_defringe(PHOTO).save(d / "view_front.png")
def engines(n0): return sum(1 for wf in SUBMITTED[n0:] if any(x["class_type"] == "Trellis2ShapeStage" for x in wf.values()))
def lm_runs(n0): return sum(1 for wf in SUBMITTED[n0:] if any(x["class_type"] == "MediaPipeFaceMeshVisualize" for x in wf.values()))
BUILD = {"kind": "m3d", "op": "build", "id": sid, "blender": "", "engine3": "trellis", "keep_hi": "", "capture": "", "seed": 7, "tex": 1024}
def diag(j): return path_of(j["images"][0]).parent / "diagnostics"
def prims(gl):
    g, b = glbscene.read(gl)
    return [(photoproj._acc(g, b, pr["attributes"]["POSITION"]), photoproj._acc(g, b, pr["indices"]).astype(int).reshape(-1, 3)) for pr in g["meshes"][0]["primitives"]]
def posset(gl): return {r.tobytes() for P, F in prims(gl) for r in P.astype(np.float32)}

# 1) 기본값: 꺼져 있어요 — 평소 결과 그대로, 랜드마크도 찾지 않아요
assert hub.m3d_opts({}, {"kind": "character"})["face_geometry_fit"] is False and hub.m3d_opts({"face_geometry_fit": "on"}, {})["face_geometry_fit"] is True
assert hub.m3d_opts({"face_geometry_fit": "on"}, {})["align"] is False and hub.m3d_opts({"align": "on"}, {})["face_geometry_fit"] is False      # 얼굴 정렬과 따로 켜고 꺼요
n0 = len(SUBMITTED); j0 = job(BUILD); assert j0["state"] == "done", j0
main0 = path_of(j0["images"][0]).read_bytes()
assert "face_geo" not in j0["m3d_stats"] and not diag(j0).exists() and engines(n0) == 1 and lm_runs(n0) == 0
ok("option is off by default and independent of the align option: a normal build is untouched (no landmark runs, no diagnostics)")

# 2) 켜면: 엔진 한 번, A·B·C 와 요약, 본 결과는 형상 보정한 것
n0 = len(SUBMITTED); j = job({**BUILD, "face_geometry_fit": "on"}); assert j["state"] == "done", j
assert engines(n0) == 1, engines(n0)
dg = diag(j); names = sorted(p.name for p in dg.iterdir())
assert names == ["face_A_baseline.glb", "face_B_texture_align.glb", "face_C_geometry_fit.glb", "face_geometry_fit_landmarks.png", "face_geometry_fit_summary.json", "face_geometry_fit_views.png"], names
S_ = json.loads((dg / "face_geometry_fit_summary.json").read_text(encoding="utf-8"))
A, Bg, C = ((dg / f).read_bytes() for f in ("face_A_baseline.glb", "face_B_texture_align.glb", "face_C_geometry_fit.glb"))
main = path_of(j["images"][0]).read_bytes()
eng = (d / "engine_last.glb").read_bytes()
assert A == main0, "A(기존 투영)가 옵션을 끈 결과와 달라요"
assert S_["shared"]["source_mesh"]["sha256"] == sha(eng) and S_["shared"]["engine"] == "TRELLIS.2" and S_["shared"]["camera"] and S_["shared"]["face_box"]
V = S_["variants"]
assert [V[k]["align"] for k in "ABC"] == [False, True, True] and [V[k]["geometry_fit"] for k in "ABC"] == [False, False, True] and all(V[k]["iou"] > 0.9 and V[k]["ncc"] is not None and V[k]["head_texture"] for k in "ABC")
assert V["A"]["sha256"] == sha(A) and V["B"]["sha256"] == sha(Bg) and V["C"]["sha256"] == sha(C) and V["C"]["accepted"] is True
ok("3D engine ran once; diagnostics has A/B/C models, the summary, close-up views and the landmark picture; A is byte-identical to the normal result")
fC, fD = S_["fits"]["C"], S_["fits"]["D"]
assert S_["status"] == "applied" and S_["result"] == {**S_["result"], "used": "D", "geometry_fit_applied": True, "fallback_reason": None} and fD["accepted"] and fC["accepted"], S_["result"]
assert main != main0, "본 결과가 옵션을 끈 결과와 같아요"
assert "형상 보정" in j["m3d_stats"]["photo"]["text"] and j["m3d_stats"]["photo"]["geofit"] is True, j["m3d_stats"]["photo"]
assert (main == C) == (not V["B"]["face_align"]["applied"])      # 얼굴 정렬이 실제로 휘지 않았다면 C(정렬 + 보정)와 본 결과(보정만)는 같아요
ok("align option off + geometry fit on: the main result is 'plain projection + geometry fit' (recorded as D), C (align + fit) is saved for comparison")

# 3) 실제로 정점이 옮겨졌는지 — A·B 는 엔진 원본과 정점 자리가 같고, C 만 얼굴에서 달라요
pe, pa, pb, pc = posset(eng), posset(A), posset(Bg), posset(C)
assert pa == pe and pb == pe, "A·B 의 정점 자리가 엔진 원본과 달라요"
gone = np.array([np.frombuffer(r, np.float32) for r in pe - pc])
assert 500 < len(gone) < 0.25 * len(pe), len(gone)
px, py = geofix.px_of(gone.astype(np.float64))
fw, fh = FB[2] - FB[0], FB[3] - FB[1]
inside = (px > FB[0] - 0.2 * fw) & (px < FB[2] + 0.2 * fw) & (py > FB[1] - 0.05 * fh) & (py < FB[3] + 0.3 * fh) & (gone[:, 2] > 0)
assert inside.all(), f"얼굴 밖 정점이 움직였어요: {int((~inside).sum())}개"
P_e = prims(eng)[0][0]
torso = P_e[fx["nhead"]:].astype(np.float32); back = P_e[:fx["nhead"]][P_e[:fx["nhead"], 2] < -0.02].astype(np.float32); top = P_e[:fx["nhead"]][P_e[:fx["nhead"], 1] > fx["hc"][1] + 0.9 * fx["A"][1]].astype(np.float32)
for part in (torso, back, top):
    assert len(part) > 50 and all(r.tobytes() in pc for r in part)
pcg = fC["position_changed"]; mc = fC["mesh_check"]
assert pcg["vertices"] == len(P_e) and pcg["triangles"] == len(prims(eng)[0][1]) and pcg["same_layout"] and 500 < pcg["changed_vertices"] < 0.25 * pcg["vertices"]
assert 0.005 < pcg["mean_move_rel"] < 0.2 and pcg["max_move_rel"] <= 0.45 and mc == {**mc, "valid": True, "outside_moved": 0, "flipped_triangles": 0, "degenerate_added": 0, "seam_torn": 0} and mc["normal_turn_max"] < 40
assert fC["mesh_hash"]["before"] == sha(eng) and fC["mesh_hash"]["after"] != sha(eng) and fC["mesh_consistency"]["ok"] and fC["mesh_consistency"]["missing"] == 0
p1 = fC["passes"][0]["mesh"]
assert p1["hash"]["position_before"] != p1["hash"]["position_after"] and p1["vertices"] == pcg["vertices"] and p1["triangles"] == pcg["triangles"] and p1["degenerate_after"] == p1["degenerate_before"]
tri = lambda gl: sum(len(F) for _, F in prims(gl))
assert tri(A) == tri(Bg) == tri(C) == len(prims(eng)[0][1]) and len(prims(C)) == 2
ok(f"C really moved {pcg['changed_vertices']:,} of {pcg['vertices']:,} vertices (mean {pcg['mean_move_rel']} / max {pcg['max_move_rel']} × eye distance), all inside the face; hair top, back of head and body are bit-identical; A and B keep the engine positions; no flipped/degenerate triangles; head + body triangles match the fitted mesh exactly")

# 4) 랜드마크 오차(모양 vs 붙인 그림) — NCC·IoU 와 따로 기록, 보정 뒤 줄어야 해요
eb, ea = fC["landmark_error_before"], fC["landmark_error_after"]
assert eb["n"] >= 30 and ea["mean"] < 0.5 * eb["mean"] and all(g in eb for g in ("eyes", "nose", "lips", "outline")), (eb, ea)
assert S_["photo_landmarks"]["ok"] and S_["photo_landmarks"]["score"] == 0.93 and S_["photo_landmarks"]["points"] >= 40 and fC["front_vs_photo_after"]["mean"] < 0.03
assert fC["refine_before"]["nose"]["used"] in (True, False) and "seconds" in S_["timing"] and "note" in S_["memory"]
ok(f"landmark error between 3D shape and pasted photo: {eb['mean']} → {ea['mean']} × eye distance (eyes {eb['eyes']} → {ea['eyes']}, nose {eb['nose']} → {ea['nose']}, lips {eb['lips']} → {ea['lips']}); front view still matches the photo ({fC['front_vs_photo_after']['mean']})")

# 5) 정답 3D 와 비교: 앞·좌우 45°·옆에서 — 굴곡(코·눈·입)이 진짜 자리에 가까워지고, 옆에서 본 그림이 나빠지지 않아야 해요
res = {}
for deg in (0, 45, -45, 90, -90):
    t, zt = geofix.view(fx["true"], deg); e, ze = geofix.view(eng, deg); b, zb = geofix.view(Bg, deg); c, zc = geofix.view(C, deg)
    m = np.isfinite(zt) & np.isfinite(zb) & np.isfinite(zc) & np.isfinite(ze)
    yy = np.mgrid[0:640, 0:640][0]
    face = m & (np.abs(yy - 320) < 0.095 * 640 / 0.30)
    with np.errstate(invalid="ignore"):
        wrong = face & (np.abs(ze - zt) > 0.0015)          # 엔진 모양이 틀렸던 곳(1.5mm 넘게)
        res[deg] = (float(np.abs(zb - zt)[wrong].mean() * 1000), float(np.abs(zc - zt)[wrong].mean() * 1000), float(np.abs(zb - zt)[face].mean() * 1000), float(np.abs(zc - zt)[face].mean() * 1000),
                    float(np.abs(b - t)[face].mean()), float(np.abs(c - t)[face].mean()), int(wrong.sum()))
    print(f"   {deg:4d}°: depth error where the engine was wrong B {res[deg][0]:.2f} → C {res[deg][1]:.2f} mm | whole face B {res[deg][2]:.2f} → C {res[deg][3]:.2f} mm | colour vs truth B {res[deg][4]:.2f} → C {res[deg][5]:.2f}", flush=True)
for deg in (0, 45, -45):
    # 색 차이: 정면은 A·B·C 모두 같은 사진이 보이는 방향이라 표본 오차만 있어요(3% 까지), 좌우 45°는 나빠지면 안 돼요
    assert res[deg][6] > 500 and res[deg][1] < 0.75 * res[deg][0] and res[deg][3] < res[deg][2] and res[deg][5] <= res[deg][4] * (1.03 if deg == 0 else 1.005), (deg, res[deg])
for deg in (90, -90):
    assert res[deg][3] <= res[deg][2] * 1.05 and res[deg][5] <= res[deg][4] * 1.02, (deg, res[deg])
ok("against the true head: from the front and ±45° the facial relief is closer to where it really is and the rendered face is no worse; side views (±90°) are not degraded")
sheet = Image.open(dg / "face_geometry_fit_views.png"); lmk = Image.open(dg / "face_geometry_fit_landmarks.png")
assert sheet.width > 5 * 300 and sheet.height > 3 * 300 and lmk.width >= 3 * 400 and np.asarray(sheet.convert("L")).std() > 10
st = j["m3d_stats"]["face_geo"]; du = sorted(u.split("/")[-1] for u in j["images"] if "/diagnostics/" in u)
assert du == ["face_A_baseline.glb", "face_B_texture_align.glb", "face_C_geometry_fit.glb", "face_geometry_fit_views.png"] and st["result"]["used"] == "D" and st["focus"] and "_glb" not in st
assert urllib.request.urlopen(B + next(u for u in j["images"] if u.endswith("face_C_geometry_fit.glb"))).read() == C
if os.environ.get("GEOFIT_OUT"):
    sheet.save(os.environ["GEOFIT_OUT"] + "_views.png"); lmk.save(os.environ["GEOFIT_OUT"] + "_lm.png")
ok("close-up sheet (A/B/C × front, ±45°, sides) and landmark picture are saved; the result screen gets the three models and the summary")

# 6) 랜드마크를 못 찾으면: 기존 결과로 돌아가고 이유를 남겨요
for fail_from, word, has_c in ((1, "원본 사진에서 얼굴 랜드마크를 찾지 못했어요", False), (3, "3D 엔진이 칠한 얼굴에서 랜드마크를 찾지 못했어요", False)):
    LM.update(fail_from=fail_from, n=0)
    jf = job({**BUILD, "face_geometry_fit": "on"}); assert jf["state"] == "done", jf
    sf = json.loads((diag(jf) / "face_geometry_fit_summary.json").read_text(encoding="utf-8"))
    assert path_of(jf["images"][0]).read_bytes() == main0 and sf["status"] == "fallback" and sf["result"]["used"] == "A" and not sf["result"]["geometry_fit_applied"]
    reasons = [sf["result"]["fallback_reason"] or ""] + [f.get("reason") or "" for f in sf["fits"].values()]      # 본 결과의 이유 + 보정별 이유
    assert sf["result"]["fallback_reason"] and any(word in r for r in reasons), (sf["result"], reasons)
    assert any("형상 보정" in w and "기존 결과" in w for w in jf["warn"]) and (diag(jf) / "face_A_baseline.glb").read_bytes() == main0 and (diag(jf) / "face_B_texture_align.glb").is_file()
    assert (diag(jf) / "face_C_geometry_fit.glb").exists() == has_c and sf["variants"]["C"]["file"] is None
LM.update(fail_from=None, n=0)
ok("landmarks not found (in the photo, or on the engine's face): the normal result is used unchanged, the reason is in the summary and shown as a warning, A and B are still saved")

# 7) 검사에서 불합격이면(효과가 작음): 기존 결과를 쓰고, C 는 '불합격'으로 남겨요 · 노드가 없으면 건너뛰어요
keep = facegeo.MIN_GAIN; facegeo.MIN_GAIN = 0.0
jr = job({**BUILD, "face_geometry_fit": "on"}); facegeo.MIN_GAIN = keep; assert jr["state"] == "done", jr
sr = json.loads((diag(jr) / "face_geometry_fit_summary.json").read_text(encoding="utf-8"))
assert path_of(jr["images"][0]).read_bytes() == main0 and sr["status"] == "fallback" and "보정 효과가 작아요" in sr["result"]["fallback_reason"] and sr["fits"]["D"]["accepted"] is False
assert not (diag(jr) / "face_C_geometry_fit.glb").exists() and sr["variants"]["C"]["file"] is None and sr["variants"]["C"]["accepted"] is False and "보정 효과가 작아요" in sr["variants"]["C"]["reason"]
assert sr["fits"]["C"]["passes"] and sr["fits"]["C"]["landmark_error_before"] if "landmark_error_before" in sr["fits"]["C"] else sr["fits"]["C"]["before"]      # 잰 값은 남아 있어요
STATE["missing"].add("MediaPipeFaceMeshVisualize"); hub.caps(force=True)
jm = job({**BUILD, "face_geometry_fit": "on"}); STATE["missing"].discard("MediaPipeFaceMeshVisualize"); hub.caps(force=True); assert jm["state"] == "done", jm
sm = json.loads((diag(jm) / "face_geometry_fit_summary.json").read_text(encoding="utf-8"))
assert path_of(jm["images"][0]).read_bytes() == main0 and sm["status"] == "skipped" and "MediaPipeFaceMeshVisualize" in sm["result"]["fallback_reason"] and sorted(p.name for p in diag(jm).iterdir()) == ["face_geometry_fit_summary.json"]
ok("quality gate: a fit that does not pass is not used (normal result kept, C not produced, measurements and the reason recorded); an old ComfyUI without the landmark node is skipped with a clear reason")
geofix.close()
print("ALL OK")
