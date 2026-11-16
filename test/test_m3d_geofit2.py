"""얼굴 3D 형상 보정(실험) 둘째 시험 — 남성 얼굴 사진, 얼굴 정렬을 켠 경우(본 결과 = C), 결과 화면(A·B·C 나란히).
여성 사진 전체 흐름은 test_m3d_geofit.py. 가짜 3D(geofix.py)·가짜 ComfyUI + 진짜 랜드마크(MediaPipe). 실제 Pixal3D·GPU 결과는 미검증.
남성 사진(미국 정부 공식 초상, 퍼블릭 도메인)은 처음 한 번 인터넷에서 받아요 — 못 받으면 이 시험은 실패해요(남성 검증을 했다고 할 수 없으니까요)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, hashlib, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17960"
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

fx = geofix.build("male", res=(150, 110), ts=1024)
assert fx, "남성 얼굴 사진을 받지 못했어요(인터넷 필요) — 남성 얼굴은 검증하지 못했어요"
PHOTO, FB = fx["photo"], fx["box"]
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True
class Cut:
    def cut(self, img, _): return img.convert("RGBA")
hub.rmbg_engine = lambda k: Cut()
touch("diffusion_models/trellis2_test.safetensors", "diffusion_models/pixal3d_int8_convrot.safetensors", "clip_vision/dino_v3_L_naf_fp32.safetensors",
      "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors", "geometry_estimation/moge_2_vitl_normal_fp16.safetensors",
      "detection/mediapipe_face_fp32.safetensors")
hub.caps(force=True)
STATE["glb"] = fx["engine"]
hub.M3D_HEAD_MIN = 1024
hub.m3d_face = lambda photo, J: (FB, None)
def lm_fn(src, sets):
    xy = geofix.points(src)
    return [geofix.draw_lines(src, grp, xy=xy) for grp in sets]
STATE["lm_fn"] = lm_fn
j = job({"kind": "m3d", "op": "prep", "image": url(PHOTO), "kind3": "character", "name": "geofit_m"}); assert j["state"] == "done", j
sid = j["m3d"]["id"]; d = hub.M3D_DIR / sid
hub.m3d_defringe(PHOTO).save(d / "view_front.png")
def engines(n0): return sum(1 for wf in SUBMITTED[n0:] if any(x["class_type"] == "Trellis2ShapeStage" for x in wf.values()))
BUILD = {"kind": "m3d", "op": "build", "id": sid, "blender": "", "engine3": "trellis", "keep_hi": "", "capture": "", "seed": 7, "tex": 1024}
def diag(j): return path_of(j["images"][0]).parent / "diagnostics"

# 1) 남성 얼굴 + 얼굴 정렬 켬: 본 결과 = C(얼굴 정렬 + 형상 보정), 사진 붙이기는 A·B·C 세 번뿐
n0 = len(SUBMITTED); j = job({**BUILD, "face_geometry_fit": "on", "align": "on"}); assert j["state"] == "done", j
assert engines(n0) == 1
dg = diag(j); S_ = json.loads((dg / "face_geometry_fit_summary.json").read_text(encoding="utf-8"))
A, Bg, C = ((dg / f).read_bytes() for f in ("face_A_baseline.glb", "face_B_texture_align.glb", "face_C_geometry_fit.glb"))
main = path_of(j["images"][0]).read_bytes()
fC = S_["fits"]["C"]
assert S_["status"] == "applied" and S_["result"]["used"] == "C" and S_["result"]["geometry_fit_applied"] and list(S_["fits"]) == ["C"] and fC["accepted"], (S_["result"], fC.get("reason"))
assert main == C and main != Bg and S_["shared"]["align_option"] is True and S_["variants"]["B"]["face_align"]["requested"] is True
eb, ea, mc, pc = fC["landmark_error_before"], fC["landmark_error_after"], fC["mesh_check"], fC["position_changed"]
assert ea["mean"] < 0.6 * eb["mean"] and mc["outside_moved"] == 0 and mc["flipped_triangles"] == 0 and mc["degenerate_added"] == 0 and mc["seam_torn"] == 0 and fC["mesh_consistency"]["ok"]
assert 300 < pc["changed_vertices"] < 0.25 * pc["vertices"] and pc["same_layout"] and pc["max_move_rel"] <= 0.45
ok(f"male face, align on: main result is C; {pc['changed_vertices']:,} face vertices moved (mean {pc['mean_move_rel']} × eye distance), landmark error {eb['mean']} → {ea['mean']} (eyes {eb['eyes']} → {ea['eyes']}, nose {eb['nose']} → {ea['nose']}, lips {eb['lips']} → {ea['lips']}), mesh checks pass")

# 2) 정답 3D 와 비교(남성)
eng = (d / "engine_last.glb").read_bytes()
res = {}
for deg in (0, 45, -45, 90, -90):
    t, zt = geofix.view(fx["true"], deg); e, ze = geofix.view(eng, deg); b, zb = geofix.view(Bg, deg); c, zc = geofix.view(C, deg)
    m = np.isfinite(zt) & np.isfinite(zb) & np.isfinite(zc) & np.isfinite(ze)
    yy = np.mgrid[0:640, 0:640][0]
    face = m & (np.abs(yy - 320) < 0.095 * 640 / 0.30)
    with np.errstate(invalid="ignore"):
        wrong = face & (np.abs(ze - zt) > 0.0015)
        res[deg] = (float(np.abs(zb - zt)[wrong].mean() * 1000), float(np.abs(zc - zt)[wrong].mean() * 1000), float(np.abs(zb - zt)[face].mean() * 1000), float(np.abs(zc - zt)[face].mean() * 1000),
                    float(np.abs(b - t)[face].mean()), float(np.abs(c - t)[face].mean()), int(wrong.sum()))
    print(f"   {deg:4d}°: depth error where the engine was wrong B {res[deg][0]:.2f} → C {res[deg][1]:.2f} mm | whole face B {res[deg][2]:.2f} → C {res[deg][3]:.2f} mm | colour vs truth B {res[deg][4]:.2f} → C {res[deg][5]:.2f}", flush=True)
for deg in (0, 45, -45):
    # 색 차이: 정면은 A·B·C 모두 같은 사진이 보이는 방향이라 표본 오차만 있어요(3% 까지), 좌우 45°는 나빠지면 안 돼요
    assert res[deg][6] > 500 and res[deg][1] < 0.75 * res[deg][0] and res[deg][3] < res[deg][2] and res[deg][5] <= res[deg][4] * (1.03 if deg == 0 else 1.005), (deg, res[deg])
for deg in (90, -90):
    assert res[deg][3] <= res[deg][2] * 1.05 and res[deg][5] <= res[deg][4] * 1.02, (deg, res[deg])
if os.environ.get("GEOFIT_OUT"):
    Image.open(dg / "face_geometry_fit_views.png").save(os.environ["GEOFIT_OUT"] + "_views.png"); Image.open(dg / "face_geometry_fit_landmarks.png").save(os.environ["GEOFIT_OUT"] + "_lm.png")
ok("male face against the true head: relief closer to the truth from the front and ±45°, side views not degraded")

# 3) 화면: 체크칸 기본 꺼짐 · 켜고 만들면 A·B·C 세 3D 가 나란히 · 방향 버튼이 셋을 함께 돌려요
from playwright.sync_api import sync_playwright
errs, sent = [], []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1700, "height": 1200}); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("request", lambda r: sent.append(r.post_data) if r.url.endswith("/api/job") and r.method == "POST" else None)
    pg.goto(B); pg.wait_for_selector("#rail nav button[data-v=m3d]"); pg.click("nav button[data-v=m3d]")
    pg.wait_for_function("document.querySelector('#m3-sess') && [...document.querySelector('#m3-sess').options].some(o=>o.value==%r)" % sid)
    pg.select_option("#m3-sess", sid); pg.wait_for_timeout(600)
    assert not pg.is_checked("#m3-geofit") and not pg.is_checked("#m3-align") and not pg.is_checked("#m3-faceab") and "얼굴 3D 형상 보정 (실험)" in pg.inner_text("label:has(#m3-geofit)")
    pg.uncheck("#m3-blender"); pg.uncheck("#m3-keephi"); pg.select_option("#m3-engine", "trellis"); pg.select_option("#m3-tex", "1024"); pg.check("#m3-geofit"); pg.check("#m3-align")
    pg.click("#m3-go"); pg.wait_for_selector("#m3-out .m3-geo", timeout=400000)
    body = json.loads([s for s in sent if s and '"build"' in s][-1]); assert body["face_geometry_fit"] is True and body["align"] is True and body["face_ab"] is False, body
    assert pg.locator("#m3-out .m3-geo .m3-abmv").count() == 3 and pg.locator("#m3-out #m3-mv").count() == 1 and pg.locator("#m3-out .m3-ab").count() == 1
    caps_ = pg.eval_on_selector_all("#m3-out .m3-geo .m3-abfig figcaption b", "els=>els.map(e=>e.textContent)")
    assert caps_ == ["A: 기존 사진 투영", "B: 얼굴 정렬", "C: 얼굴 정렬 + 3D 형상 보정"], caps_
    srcs = pg.eval_on_selector_all("#m3-out .m3-geo .m3-abmv", "els=>els.map(e=>e.getAttribute('src').split('/').pop())")
    assert srcs == ["face_A_baseline.glb", "face_B_texture_align.glb", "face_C_geometry_fit.glb"], srcs
    assert "diagnostics" not in pg.get_attribute("#m3-mv", "src") and pg.locator("#m3-out .m3-files a[href*=diagnostics]").count() == 0
    orb = lambda: pg.eval_on_selector_all("#m3-out .m3-geo .m3-abmv", "els=>els.map(e=>[e.getAttribute('camera-orbit'),e.getAttribute('camera-target')])")
    o0 = orb(); assert o0[0] == o0[1] == o0[2] and o0[0][0].startswith("0deg") and o0[0][1].endswith("m"), o0
    for label, yaw in (("왼쪽 45°", "45deg"), ("오른쪽 45°", "-45deg"), ("왼쪽 옆", "90deg"), ("오른쪽 옆", "-90deg"), ("정면", "0deg")):
        pg.click(f"#m3-out .m3-geo .m3-abbar button:text-is('{label}')"); o = orb(); assert o[0] == o[1] == o[2] and o[0][0].startswith(yaw + " "), (label, o)
    pg.click("#m3-out .m3-geo [data-abnear]"); o = orb(); assert o[0][1] == "auto auto auto" and pg.inner_text("#m3-out .m3-geo [data-abnear]") == "얼굴 가까이", o
    txt = pg.inner_text("#m3-out .m3-geo")
    assert "위의 결과에 적용했어요" in txt and "합격" in txt and "저장한 곳" in txt and "face_geometry_fit_summary.json" in txt and "옮긴 정점" in txt, txt[:400]
    assert pg.locator("#m3-out .m3-geo .m3-sheet img").count() == 1 and pg.locator("#m3-out .m3-geo .m3-stat tbody tr").count() == 1
    assert "형상 보정" in pg.inner_text("#m3-out .m3-photo.ok >> nth=0")
    if os.environ.get("GEOFIT_OUT"):
        pg.evaluate("document.querySelector('#m3-out .m3-geo').scrollIntoView()"); pg.screenshot(path=os.environ["GEOFIT_OUT"] + "_ui.png")
    pg.click("#m3-out .m3-geo .m3-abfig button[data-m3view]"); pg.wait_for_selector("#lb:not([hidden])", timeout=5000)
    b.close()
assert not errs, errs
ok("screen: experimental checkbox off by default and separate from the align option; after a build A/B/C are side by side with names, view buttons turn all three together, the check table and save location are shown")
geofix.close()
print("ALL OK")
