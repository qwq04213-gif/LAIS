"""얼굴 정렬 A/B 비교(진단): 3D 엔진은 한 번만 돌리고, 그 원본 하나에서 A(얼굴 정렬 끔)·B(켬)를 각각 따로 만들어
결과 폴더의 diagnostics 폴더에 저장해요. 평소 결과는 그대로, 얼굴 찾기·확대는 한 번만, 한쪽이 실패해도 나머지는 남아요.
가짜 3D(실제 얼굴 사진을 입힌 머리 + 몸, 사진은 머리를 돌리고 기울여 찍음)와 가짜 ComfyUI 로 흐름만 확인해요 — 실제 Pixal3D·GPU 결과는 미검증."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, hashlib, urllib.request, urllib.parse, urllib.error
os.environ["TEST_HUB_PORT"] = "17958"
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import numpy as np
import glbscene, photoproj
from PIL import Image, ImageFilter
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid):
    for _ in range(3000):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
def url(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def path_of(u): return hub.OUT / urllib.parse.unquote(u[len("/out/"):])
sha = lambda b: hashlib.sha256(b).hexdigest()

# 가짜 3D·사진: test_m3d_align 의 머리(실제 얼굴 사진) + 몸
src = open(BASE + "/test/test_m3d_align.py", encoding="utf-8").read()
ns = {"BASE": BASE}; exec(src[src.index("import io, sys"):src.index("P, UV, F, N = mesh()")], ns)
P, UV, F, N = ns["mesh"](); S, K = ns["S"], ns["K"]
nm = Image.new("RGB", (512, 512), (128, 128, 255)); orm = Image.new("RGB", (512, 512), (150, 230, 0))
ENGINE = ns["glb_of"](P, UV, F, N, [ns["bake"](P, UV, F, 512).filter(ImageFilter.GaussianBlur(2)), nm, orm])
hd = P[:, 1] > 1.42; c0 = np.array([0, 1.5, 0]); a1, a2 = np.radians(20), np.radians(8)
R = np.array([[np.cos(a2), -np.sin(a2), 0], [np.sin(a2), np.cos(a2), 0], [0, 0, 1]]) @ np.array([[np.cos(a1), 0, np.sin(a1)], [0, 1, 0], [-np.sin(a1), 0, np.cos(a1)]])
Pr = P.copy(); Pr[hd] = (P[hd] - c0) @ R.T + c0
PHOTO = ns["shoot"](Pr, F, P)                                # 머리를 20° 돌리고 8° 기울인 사진
FB = (int(S / 2 - 0.1 * K), int(S / 2 - 0.87 * K), int(S / 2 + 0.1 * K), int(S / 2 - 0.65 * K))

hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True
class Cut:
    def cut(self, img, _): return img.convert("RGBA")
hub.rmbg_engine = lambda k: Cut()
touch("diffusion_models/trellis2_test.safetensors", "diffusion_models/pixal3d_int8_convrot.safetensors", "clip_vision/dino_v3_L_naf_fp32.safetensors",
      "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors", "geometry_estimation/moge_2_vitl_normal_fp16.safetensors")
assert all(hub.trellis_files(False).values()), hub.trellis_files(False)
STATE["glb"] = ENGINE
j = job({"kind": "m3d", "op": "prep", "image": url(PHOTO), "kind3": "character", "name": "abtest"}); assert j["state"] == "done", j
sid = j["m3d"]["id"]; d = hub.M3D_DIR / sid
hub.m3d_defringe(PHOTO).save(d / "view_front.png")           # 앞 사진을 그대로(얼굴 상자 좌표가 맞게)

# 지켜보기: 얼굴 준비 횟수, 사진 붙이기 호출(어떤 원본·정렬 값으로), 3D 엔진 실행 횟수
CALLS = {"face": 0, "proj": [], "fail": None}
def fake_face(photo, J):
    CALLS["face"] += 1
    return FB, None
hub.m3d_face = fake_face
real_project = photoproj.project
def spy(glb, photo, face=None, **kw):
    CALLS["proj"].append({"sha": sha(glb), "align": kw.get("align"), "head": kw.get("head"), "face": face, "photo": photo.size, "head_size": kw.get("head_size"), "dist_e": kw.get("dist_e"), "cam_hint": kw.get("cam_hint")})
    if CALLS["fail"] is not None and kw.get("align") == CALLS["fail"] and len(CALLS["proj"]) > 1:
        raise RuntimeError("일부러 낸 오류")
    return real_project(glb, photo, face, **kw)
hub.photoproj.project = spy
def engines(n0): return sum(1 for wf in SUBMITTED[n0:] if any(x["class_type"] == "Trellis2ShapeStage" for x in wf.values()))
BUILD = {"kind": "m3d", "op": "build", "id": sid, "blender": "", "engine3": "trellis", "keep_hi": "", "capture": "", "seed": 7, "tex": 2048}
def diag_dirs(j): return sorted(p.name for p in path_of(j["images"][0]).parent.iterdir() if p.is_dir())

# 1) 기본값: 꺼져 있어요 — 진단 폴더도, 기록도 없어요
assert hub.m3d_opts({}, {"kind": "character"})["face_ab"] is False and hub.m3d_opts({"face_ab": "on"}, {})["face_ab"] is True and hub.m3d_opts({}, {})["align"] is False
n0 = len(SUBMITTED); j0 = job(BUILD); assert j0["state"] == "done", j0
main0 = path_of(j0["images"][0]).read_bytes()
assert "face_ab" not in j0["m3d_stats"] and diag_dirs(j0) == [] and not any("diagnostics" in u for u in j0["images"]) and engines(n0) == 1
assert len(CALLS["proj"]) == 1 and CALLS["proj"][0]["align"] is False and CALLS["face"] == 1
ok("option is off by default: a normal build makes no diagnostics folder and projects the photo once")

# 2) 켜면: 엔진 한 번 · 얼굴 준비 한 번 · 같은 원본에서 A(끔)·B(켬) · 평소 결과는 그대로
CALLS.update(face=0, proj=[]); n0 = len(SUBMITTED)
j = job({**BUILD, "face_ab": "on"}); assert j["state"] == "done", j
assert engines(n0) == 1, engines(n0)
ok("3D engine ran exactly once with the A/B option on")
eng = (d / "engine_last.glb").read_bytes()
pc = CALLS["proj"]
assert CALLS["face"] == 1 and len(pc) == 3 and [c["align"] for c in pc] == [False, False, True], (CALLS["face"], [c["align"] for c in pc])
assert {c["sha"] for c in pc} == {sha(eng)}, "A·B 가 엔진 원본이 아닌 것에서 시작했어요"
assert all(c["head"] == FB and c["photo"] == pc[0]["photo"] and c["head_size"] == pc[0]["head_size"] and c["dist_e"] == pc[0]["dist_e"] and c["cam_hint"] == pc[0]["cam_hint"] and c["face"] is pc[0]["face"] for c in pc)
ok("face box/enlargement prepared once and reused; main, A and B all start from the same engine mesh with the same camera/texture settings — only align differs (False, True)")
main = path_of(j["images"][0]); assert main.parent.name != "diagnostics" and main.read_bytes() == main0
ok("the normal result is byte-identical to a build without the option")
dg = main.parent / "diagnostics"
names = sorted(p.name for p in dg.iterdir())
assert names == ["face_ab_summary.json", "face_ab_views.png", "face_align_off.glb", "face_align_off.json", "face_align_on.glb", "face_align_on.json"], names
A, Bg = (dg / "face_align_off.glb").read_bytes(), (dg / "face_align_on.glb").read_bytes()
ja, jb, js = (json.loads((dg / n).read_text(encoding="utf-8")) for n in ("face_align_off.json", "face_align_on.json", "face_ab_summary.json"))
assert ja["align"] is False and jb["align"] is True and ja["engine"] == jb["engine"] == "TRELLIS.2" and ja["label"].startswith("A:") and jb["label"].startswith("B:")
for r in (ja, jb):
    assert r["camera"] and r["camera_dist"] is not None and r["iou"] > 0.9 and r["ncc"] is not None and r["head_texture"] and r["head_texture_size"] == 2048 and r["errors"] == [] and r["file"], r
fa = jb["face_align"]
assert ja["face_align"]["applied"] is False and ja["face_align"]["ncc_before"] is None and fa["requested"] and fa["applied"] and fa["ncc_after"] > fa["ncc_before"] + 0.08 and abs(fa["rotation_deg"]) > 3 and fa["shift"] is not None and len(fa["scale"]) == 2, (ja["face_align"], fa)
assert js["shared"]["source_mesh"]["sha256"] == sha(eng) and js["shared"]["face_box"] == [float(v) for v in FB] and js["shared"]["engine_match"]["face"] < 0.5 and js["same_result"] is False and "휘어" in js["verdict"]
assert js["files"] == {"off": "face_align_off.glb", "on": "face_align_on.glb", "views": "face_ab_views.png"} and js["focus"] and "log" not in js["runs"]["on"]
assert A != Bg and sha(A) == ja["sha256"] and sha(Bg) == jb["sha256"]
ok(f"diagnostics/: 2 GLBs + 3 JSONs + face close-up sheet; JSON has engine, align, camera, distance, IoU, NCC, face NCC {fa['ncc_before']} → {fa['ncc_after']}, rotation {fa['rotation_deg']}°, shift, scale, head texture, errors/warnings")
def geo(gl):
    g, b = glbscene.read(gl)
    return [(photoproj._acc(g, b, pr["attributes"]["POSITION"]).tobytes(), photoproj._acc(g, b, pr["attributes"]["TEXCOORD_0"]).tobytes(), photoproj._acc(g, b, pr["indices"]).tobytes()) for pr in g["meshes"][0]["primitives"]]
assert geo(A) == geo(Bg) and len(geo(A)) == 2
ok("A and B have identical geometry and UVs (body + head part) — only the textures differ")
sheet = Image.open(dg / "face_ab_views.png"); assert sheet.width > 5 * 300 and sheet.height > 2 * 300 and np.asarray(sheet.convert("L")).std() > 10
fo = photoproj.head_focus(Bg); assert fo and 1.4 < fo[0][1] < 1.7 and fo[1] < 0.4, fo
st = j["m3d_stats"]["face_ab"]; assert st["runs"]["on"]["face_align"]["applied"] and j["m3d_stats"]["diag_dir"].endswith("/diagnostics") and j["m3d_stats"]["diag_dir"].startswith("outputs/")
du = [u for u in j["images"] if "/diagnostics/" in u]
assert sorted(u.split("/")[-1] for u in du) == ["face_ab_views.png", "face_align_off.glb", "face_align_on.glb"] and j["images"][0] not in du
assert urllib.request.urlopen(B + du[0]).read() in (A, Bg, (dg / "face_ab_views.png").read_bytes())
for bad in ("/out/3D/" + urllib.parse.quote(main.parent.name) + "/secret/face_align_off.glb", "/out/3D/" + urllib.parse.quote(main.parent.name) + "/diagnostics/..%2F..%2Fx.glb"):
    try:
        body = urllib.request.urlopen(B + bad).read(); assert body not in (A, Bg)
    except urllib.error.HTTPError:
        pass
ok("results are served for the viewer from the job's diagnostics folder only; the job reports where they were saved")

# 3) 한쪽이 실패해도: 다른 쪽과 평소 결과는 남아요
for fail, good, lost in ((True, "off", "on"), (False, "on", "off")):
    CALLS.update(face=0, proj=[], fail=fail)
    j = job({**BUILD, "face_ab": "on"}); assert j["state"] == "done", j
    main = path_of(j["images"][0]); dg = main.parent / "diagnostics"
    assert main.read_bytes() == main0 and (dg / f"face_align_{good}.glb").is_file() and not (dg / f"face_align_{lost}.glb").exists()
    jl = json.loads((dg / f"face_align_{lost}.json").read_text(encoding="utf-8")); js = json.loads((dg / "face_ab_summary.json").read_text(encoding="utf-8"))
    assert jl["errors"] and "일부러 낸 오류" in jl["errors"][0] and jl["file"] is None and list(js["files"]) [:1] == [good] and "만들지 못한" in js["verdict"]
CALLS["fail"] = None
ok("if A or B fails, the other one and the normal result are still saved, and the failure is written to its JSON")

# 4) 얼굴을 못 찾으면: A/B 는 만들지 않고 이유만 남겨요(3D 는 평소대로)
hub.m3d_face = lambda photo, J: (None, None)
CALLS.update(proj=[]); j = job({**BUILD, "face_ab": "on"}); assert j["state"] == "done", j
dg = path_of(j["images"][0]).parent / "diagnostics"
assert sorted(p.name for p in dg.iterdir()) == ["face_ab_summary.json"] and len(CALLS["proj"]) == 1 and any("A/B" in w for w in j["warn"]), (j.get("warn"), CALLS["proj"])
assert "얼굴을 찾지 못했어요" in json.loads((dg / "face_ab_summary.json").read_text(encoding="utf-8"))["errors"][0]
hub.m3d_face = fake_face
ok("no face found: no A/B models, the reason is saved and shown, the 3D itself is made as usual")

# 5) 덮어쓰지 않기: 같은 결과 폴더에 진단 폴더가 이미 있으면 새 이름으로
jn = hub.job_dir_name; hub.job_dir_name = lambda stamp, label="": "20200101-000000-abcd-fixed"
j1 = job({**BUILD, "face_ab": "on"}); f1 = path_of(j1["images"][0]).parent / "diagnostics" / "face_align_on.glb"; b1, t1 = f1.read_bytes(), f1.stat().st_mtime_ns
j2 = job({**BUILD, "face_ab": "on"}); hub.job_dir_name = jn
assert diag_dirs(j2) == ["diagnostics", "diagnostics_2"] and f1.read_bytes() == b1 and f1.stat().st_mtime_ns == t1 and j2["m3d_stats"]["diag_dir"].endswith("/diagnostics_2")
assert any("/diagnostics_2/face_align_on.glb" in u for u in j2["images"]) and urllib.request.urlopen(B + next(u for u in j2["images"] if u.endswith("/diagnostics_2/face_align_off.glb"))).status == 200
ok("an existing diagnostics folder is never overwritten — the next run goes to diagnostics_2")

# 6) 단계별 비교(E·F)와 함께 켜도 A/B 는 한 번만, 갤러리에는 섞이지 않아요
CALLS.update(face=0, proj=[]); n0 = len(SUBMITTED)
j = job({**BUILD, "face_ab": "on", "engine3": "pixal", "compare": "on"}); assert j["state"] == "done", j
ab_calls = [c for c in CALLS["proj"] if c["align"]]
assert len(ab_calls) == 1 and CALLS["face"] == 2 and len([u for u in j["images"] if u.endswith("face_align_on.glb")]) == 1, (len(ab_calls), CALLS["face"])
# (얼굴 찾기 2번 = 본 제작 1번 + 비교용 TRELLIS.2(F) 가 자기 결과에 쓰려고 1번 — 예전부터 그랬어요. A·B 는 본 제작 것을 같이 써요)
assert not [f for f in hub.out_files(hub.OUT / "3D") if "diagnostics" in str(f)]
ok("with the stage comparison on too, A/B is still made once (extra comparison engines do not repeat it); diagnostics files stay out of the gallery list")

# 7) 화면: 체크칸은 기본 꺼짐 · 켜고 만들면 A/B 두 3D 가 나란히 · 방향 버튼이 두 3D 를 함께 돌려요
from playwright.sync_api import sync_playwright
errs, sent = [], []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1100}); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("request", lambda r: sent.append(r.post_data) if r.url.endswith("/api/job") and r.method == "POST" else None)
    pg.goto(B); pg.wait_for_selector("#rail nav button[data-v=m3d]"); pg.click("nav button[data-v=m3d]")
    pg.wait_for_function("document.querySelector('#m3-sess') && [...document.querySelector('#m3-sess').options].some(o=>o.value==%r)" % sid)
    pg.select_option("#m3-sess", sid); pg.wait_for_function("window.M3 ? !!M3.S : true"); pg.wait_for_timeout(500)
    assert not pg.is_checked("#m3-faceab") and not pg.is_checked("#m3-align") and "얼굴 정렬 A/B 비교" in pg.inner_text("label:has(#m3-faceab)")
    pg.evaluate("document.querySelector('#m3-faceab').closest('fieldset').scrollIntoView()")
    pg.uncheck("#m3-blender"); pg.uncheck("#m3-keephi"); pg.select_option("#m3-engine", "trellis"); pg.check("#m3-faceab")
    pg.click("#m3-go"); pg.wait_for_selector("#m3-out .m3-ab", timeout=180000)
    body = json.loads([s for s in sent if s and '"build"' in s][-1]); assert body["face_ab"] is True and body["align"] is False, body
    assert pg.locator("#m3-out .m3-abmv").count() == 2 and pg.locator("#m3-out #m3-mv").count() == 1
    caps_ = pg.eval_on_selector_all("#m3-out .m3-abfig figcaption b", "els=>els.map(e=>e.textContent)"); assert caps_ == ["A: 기존 사진 투영", "B: 얼굴 정렬 적용"], caps_
    srcs = pg.eval_on_selector_all("#m3-out .m3-abmv", "els=>els.map(e=>e.getAttribute('src'))"); assert srcs[0].endswith("/diagnostics/face_align_off.glb") and srcs[1].endswith("/diagnostics/face_align_on.glb"), srcs
    assert "diagnostics" not in pg.get_attribute("#m3-mv", "src") and pg.locator("#m3-out .m3-files a[href*=diagnostics]").count() == 0
    orb = lambda: pg.eval_on_selector_all("#m3-out .m3-abmv", "els=>els.map(e=>[e.getAttribute('camera-orbit'),e.getAttribute('camera-target')])")
    o0 = orb(); assert o0[0] == o0[1] and o0[0][0].startswith("0deg") and o0[0][1].endswith("m"), o0          # 처음: 정면, 얼굴 가까이
    for label, yaw in (("왼쪽 45°", "45deg"), ("오른쪽 45°", "-45deg"), ("왼쪽 옆", "90deg"), ("오른쪽 옆", "-90deg"), ("정면", "0deg")):
        pg.click(f"#m3-out .m3-abbar button:text-is('{label}')"); o = orb(); assert o[0] == o[1] and o[0][0].startswith(yaw + " "), (label, o)
    pg.click("#m3-abnear"); o = orb(); assert o[0][1] == "auto auto auto" and pg.inner_text("#m3-abnear") == "얼굴 가까이", o
    txt = pg.inner_text("#m3-out .m3-ab")
    assert "휘었어요" in txt and "저장한 곳" in txt and "diagnostics" in txt and "face_ab_summary.json" in txt and pg.locator("#m3-out .m3-ab .m3-sheet img").count() == 1 and pg.locator("#m3-out .m3-ab .m3-stat tbody tr").count() == 2
    pg.click("#m3-out .m3-abfig button[data-m3view]"); pg.wait_for_selector("#lb:not([hidden])", timeout=5000)
    b.close()
assert not errs, errs
ok("screen: checkbox off by default; after a build A and B are shown side by side with their names, view buttons (front / 45° / side) turn both together, numbers table and save location are shown, each opens in the big viewer")
print("ALL OK")
