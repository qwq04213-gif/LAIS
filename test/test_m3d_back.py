"""3D 뒷면: ① 사진 붙이기가 엔진 원본의 뒷면을 바꾸지 않는지(색·모양), 머리 그물망이 이어져 있는지, 머리·몸 경계에 색 이음새가 없는지,
얇은 곳의 뒷면에 앞 사진이 새지 않는지 ② 뒷면 진단(m3dviews)이 구멍·뒤집힌 면·법선·조각난 그물망·'뒤통수에 얼굴 비침'을 잡는지
③ 3D 만들기에서 '뒷면 진단'을 켜면 단계별 그림·기록이 저장되고 화면에 판정이 나오는지.
둥근 머리 가짜 3D(실제 얼굴 사진 — test_m3d_face49 의 것)와 가짜 ComfyUI·가짜 Blender 로 확인해요. 실제 Pixal3D·Blender 결과는 미검증."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17961"
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import numpy as np
from PIL import Image
import glbscene, photoproj, m3dviews
ok = lambda m: print("PASS", m, flush=True)
src_ = open(BASE + "/test/test_m3d_face49.py", encoding="utf-8").read()
ns = {"__name__": "fx", "BASE": BASE}
exec(src_[src_.index("import io, os, sys"):src_.index("rows = []")].replace('ok(f"photo pasted', 'str(f"photo pasted'), ns)
g_eng, res, photo, box, P, F, UV, N, glb_of, tex_of = (ns[k] for k in ("g_eng", "res", "photo", "box", "P", "F", "UV", "N", "glb_of", "tex_of"))

# 1) 사진 붙이기는 뒷면을 건드리지 않아요 — 뒤에서 본 색·모양이 엔진 원본 그대로
S0, S1 = m3dviews.prepare(g_eng), m3dviews.prepare(res)
ch = m3dviews.compare(S0, S1)
assert ch["back"]["changed"] < 0.005 and ch["back"]["material"] < 1.0 and ch["back"]["clay"] == 0 and ch["back"]["silhouette"] == 1.0, ch["back"]
assert ch["front"]["changed"] > 0.3 and all(v["clay"] == 0 and v["silhouette"] == 1.0 for v in ch.values()), ch
fr = (np.array([0, 1.58, 0]), 0.36)
for yaw in (180, 160, 200):                                # 머리 가까이에서도(정뒤 ±20°)
    a, ma = m3dviews.render(S0, yaw, 384, "material", fr); b, mb = m3dviews.render(S1, yaw, 384, "material", fr)
    d = np.abs(a.astype(float) - b.astype(float)).max(2)[ma & mb]
    assert (d > 24).mean() < 0.01, (yaw, float((d > 24).mean()))
ok(f"photo projection leaves the back exactly as the engine made it (back view: {ch['back']['changed']:.2%} pixels changed, mean colour diff {ch['back']['material']}; shape/shading identical from all six views); the front is the photo")

# 2) 머리 그물망: 정점이 이어져 있고(삼각형마다 따로가 아님), 몸에 안 쓰는 정점이 남지 않고, 삼각형 수는 그대로
x0, x1 = m3dviews.structure(S0), m3dviews.structure(S1)
assert x1["primitives"] == 2 and x1["triangles"] == x0["triangles"] and x1["unwelded_ratio"] < 1.1 and x1["unused_vertices"] == 0, x1
assert x1["split_edges"] < 0.03 * x1["triangles"] and x1["hole_edges"] == x0["hole_edges"] and x1["duplicate_faces"] == 0 and x1["winding_conflicts"] == x0["winding_conflicts"] and x1["normal_flip_area"] == 0.0, (x0, x1)
g_, b_ = glbscene.read(res); hp = g_["meshes"][0]["primitives"][1]
nhv, nhi = g_["accessors"][hp["attributes"]["POSITION"]]["count"], g_["accessors"][hp["indices"]]["count"]
assert nhv < 0.6 * nhi and g_["accessors"][hp["attributes"]["NORMAL"]]["count"] == nhv == g_["accessors"][hp["attributes"]["TEXCOORD_0"]]["count"], (nhv, nhi)
dens = x1["texel_density"]["1"]
assert dens["back"] > 0.8 * x0["texel_density"]["0"]["back"], (dens, x0["texel_density"])      # 뒤통수 텍스처 해상도가 엔진 원본보다 낮아지지 않아요
ok(f"head mesh is welded ({nhv:,} vertices for {nhi // 3:,} triangles, vertices÷positions {x1['unwelded_ratio']}), no unused vertices left in the body, no new holes/duplicates; back-of-head texture density {dens['back']} ≥ engine {x0['texel_density']['0']['back']}")

# 3) 머리 메시와 몸 메시가 만나는 곳: 양쪽 텍스처 색이 같아야 이음새가 안 보여요
sc = photoproj._scene(res, 4096)
(P0, F0, UV0, _, T0, _), (P1, F1, UV1, _, T1, _) = sc[0], sc[1]
k0 = {tuple(np.round(p, 6)): i for i, p in enumerate(P0)}
pr = np.array([(k0[tuple(np.round(p, 6))], j) for j, p in enumerate(P1) if tuple(np.round(p, 6)) in k0])
c0 = photoproj._sample(T0, UV0[pr[:, 0], 0] % 1 * T0.shape[1], UV0[pr[:, 0], 1] * T0.shape[0])
c1 = photoproj._sample(T1, UV1[pr[:, 1], 0] % 1 * T1.shape[1], UV1[pr[:, 1], 1] * T1.shape[0])
sd = np.abs(c0 - c1).max(1)
assert len(pr) > 100 and sd.mean() < 3.5 and np.percentile(sd, 95) < 13, (len(pr), float(sd.mean()), float(np.percentile(sd, 95)))
ok(f"no colour seam where the head mesh meets the body mesh ({len(pr)} shared vertices: mean diff {sd.mean():.1f}, 95% under {np.percentile(sd, 95):.1f} of 255)")

# 4) 얇은 곳(귀·머리카락·옷자락): 뒷면에 앞 사진이 새지 않아요
n = 40
gx, gy = np.meshgrid(np.linspace(-0.3, 0.3, n + 1), np.linspace(0.0, 1.0, n + 1))
i = np.arange(n * n).reshape(n, n); r, c = np.divmod(i, n); a = r * (n + 1) + c
Ff = np.concatenate([np.stack([a, a + 1, a + n + 1], -1).reshape(-1, 3), np.stack([a + 1, a + n + 2, a + n + 1], -1).reshape(-1, 3)])
m_ = (n + 1) ** 2
Pt = np.concatenate([np.c_[gx.ravel(), gy.ravel(), np.full(m_, 0.002)], np.c_[gx.ravel(), gy.ravel(), np.full(m_, -0.002)]])        # 두께 4mm 판(앞면·뒷면)
Ft = np.concatenate([Ff, Ff[:, ::-1] + m_])
Nt = np.concatenate([np.tile([0, 0, 1.0], (m_, 1)), np.tile([0, 0, -1.0], (m_, 1))])
uvg = np.stack([(gx.ravel() + 0.3) / 0.6, 1 - gy.ravel()], 1)
UVt = np.concatenate([uvg * [0.48, 0.96] + [0.01, 0.02], uvg * [0.48, 0.96] + [0.51, 0.02]])
tt = Image.new("RGB", (512, 512), (40, 60, 200)); tt.paste((40, 180, 60), (256, 0, 512, 512))      # 엔진 색: 앞 파랑, 뒤 초록
ns.update(P=Pt, F=Ft, UV=UVt, N=Nt); thin = glb_of(tt); ns.update(P=P, F=F, UV=UV, N=N)
ph = Image.new("RGBA", (600, 1000), (0, 0, 0, 0)); core = Image.new("RGB", (600, 1000), (200, 40, 40))
for yy in range(0, 1000, 80): core.paste((240, 220, 60), (0, yy, 600, yy + 40))
ph.paste(core, (0, 0))
out, inf = photoproj.project(thin, ph, cam_hint=photoproj.PIXAL_CAM)      # 카메라는 +z 쪽(대칭인 판이라 정해 줘요)
assert inf.get("iou", 0) > 0.9, inf
g2, b2 = glbscene.read(out); T2 = np.asarray(photoproj._img_of(g2, b2, 0).convert("RGB")).astype(int)
front, back = T2[60:450, 30:230], T2[60:450, 286:486]
assert np.abs(back - np.array([40, 180, 60])).max() <= 3, np.abs(back - np.array([40, 180, 60])).max()      # 뒷면: 엔진 색 그대로
assert (front[..., 0] > 150).mean() > 0.95, (front[..., 0] > 150).mean()                                    # 앞면: 사진
ok("thin parts (4 mm slab): the front takes the photo, the back side keeps the engine colour — the front photo does not leak through")

# 5) 뒷면 진단이 문제를 잡는지: 구멍 · 뒤집힌 면 · 반대 법선 · 조각난 그물망 · 뒤통수에 얼굴 비침
def variant(**kw):
    ns.update(kw); g = glb_of(kw.pop("tex", None) or tex_of(ns["eng_c"])); ns.update(P=P, F=F, UV=UV, N=N); return m3dviews.prepare(g)
base = m3dviews.structure(S0)
holes = m3dviews.structure(variant(F=F[2000:]))
assert holes["hole_edges"] > base["hole_edges"] + 50
Fflip = F.copy(); Fflip[:len(F) // 4] = Fflip[:len(F) // 4, ::-1]
Sf = variant(F=Fflip); flip = m3dviews.structure(Sf)
assert flip["winding_conflicts"] > 100 and base["winding_conflicts"] == 0 and flip["normal_flip_area"] > 0.05
img, _ = m3dviews.render(Sf, 0, 256, "normal"); img0, _ = m3dviews.render(S0, 0, 256, "normal")
mag = lambda im: int(((im[..., 0] == 255) & (im[..., 1] == 0) & (im[..., 2] == 255)).sum())
assert mag(img) + mag(m3dviews.render(Sf, 180, 256, "normal")[0]) > 300 and mag(img0) == 0
Sn = variant(N=-N); nf = m3dviews.structure(Sn)
assert nf["normal_flip_area"] > 0.95 and m3dviews.render(Sn, 0, 256, "clay")[0].mean() < 0.75 * m3dviews.render(S0, 0, 256, "clay")[0].mean()      # 모양은 같은데 어둡게
soup = np.arange(len(F) * 3).reshape(-1, 3)
Ss = variant(P=P[F].reshape(-1, 3), F=soup, UV=UV[F].reshape(-1, 2), N=N[F].reshape(-1, 3)); so = m3dviews.structure(Ss)
assert so["unwelded_ratio"] > 2.5 and so["split_edges"] > len(F) and so["hole_edges"] == base["hole_edges"]
wimg = m3dviews.render(Ss, 180, 256, "wire")[0]
assert int((np.abs(wimg.astype(int) - np.array(m3dviews.EDGE_COL[1])).max(2) < 8).sum()) > 2000
mir = m3dviews.mirror_score(S0)                              # 이 가짜 엔진 머리는 얼굴이 뒤통수까지 비쳐 칠해져 있어요
plain = np.asarray(tex_of(np.where(ns["Nt"][:, 2:3] < 0, np.array([[90.0, 70, 50]]), ns["eng_c"]))) if False else None
ec = ns["eng_c"].copy(); ec[ns["Nt"][:, 2] < -0.05] = (92, 70, 48)      # 뒤쪽을 머리카락 색 한 가지로 칠한 것
mir2 = m3dviews.mirror_score(variant(tex=tex_of(ec)))
assert mir["head"] > 0.5 and (mir2["head"] or 0) < 0.3, (mir, mir2)
vd = m3dviews.verdict({"stages": {"engine": {"structure": flip, "mirror": mir}}, "changes": {"engine_to_photo": ch}})
kinds = {(v["stage"], v["kind"], v["level"]) for v in vd}
assert ("engine", "mesh", "warn") in kinds and ("engine", "texture", "warn") in kinds and ("engine_to_photo", "none", "ok") in kinds, vd
ok(f"back diagnosis detects holes, flipped faces (magenta in the normal view), inverted normals (dark clay), triangle soup (orange wire), and a face showing through on the back of the head (mirror score {mir['head']} vs {mir2['head']} for a plain back); the verdict names the stage and the kind")

# 6) 3D 만들기에서: 기본 꺼짐 · 켜면 단계별 그림과 기록이 diagnostics 에 · 3D 엔진은 한 번만 · 본 결과는 그대로
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
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True
class Cut:
    def cut(self, img, _): return img.convert("RGBA")
hub.rmbg_engine = lambda k: Cut()
touch("diffusion_models/trellis2_test.safetensors", "clip_vision/dino_v3_L_naf_fp32.safetensors", "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors")
STATE["glb"] = g_eng; hub.M3D_HEAD_MIN = 1024; hub.m3d_face = lambda p_, J: (box, None)
fbl = BASE + "/test/fake_blender.py"; os.chmod(fbl, 0o755); os.environ["BLENDER_EXE"] = fbl
j = job({"kind": "m3d", "op": "prep", "image": url(photo), "kind3": "character", "name": "back"}); assert j["state"] == "done", j
sid = j["m3d"]["id"]; d = hub.M3D_DIR / sid; hub.m3d_defringe(photo).save(d / "view_front.png")
BUILD = {"kind": "m3d", "op": "build", "id": sid, "blender": "", "engine3": "trellis", "keep_hi": "", "capture": "", "seed": 3, "tex": 1024}
assert hub.m3d_opts({}, {})["back_diag"] is False and hub.m3d_opts({"back_diag": "on"}, {})["back_diag"] is True
j0 = job(BUILD); assert j0["state"] == "done" and "back_diag" not in j0["m3d_stats"] and not (path_of(j0["images"][0]).parent / "diagnostics").exists(), j0
n0 = len(SUBMITTED); j = job({**BUILD, "back_diag": "on"}); assert j["state"] == "done", j
assert sum(1 for wf in SUBMITTED[n0:] if any(x["class_type"] == "Trellis2ShapeStage" for x in wf.values())) == 1
assert path_of(j["images"][0]).read_bytes() == path_of(j0["images"][0]).read_bytes()
dg = path_of(j["images"][0]).parent / "diagnostics"
assert sorted(p.name for p in dg.iterdir()) == ["back_compare.png", "back_report.json", "back_views_engine.png", "back_views_photo.png"], sorted(p.name for p in dg.iterdir())
rep = json.loads((dg / "back_report.json").read_text(encoding="utf-8"))
assert set(rep["stages"]) == {"engine", "photo"} and rep["changes"]["engine_to_photo"]["back"]["changed"] < 0.005 and rep["stages"]["photo"]["structure"]["unwelded_ratio"] < 1.1
assert any(v["stage"] == "engine_to_photo" and v["level"] == "ok" for v in rep["verdict"]) and any(v["kind"] == "texture" and "앞면을 뒤집은" in v["text"] for v in rep["verdict"]), rep["verdict"]
sh = Image.open(dg / "back_views_photo.png"); assert sh.width >= 6 * 256 and sh.height >= 5 * 256 and np.asarray(sh.convert("L")).std() > 15
st = j["m3d_stats"]["back_diag"]; assert st["verdict"] == rep["verdict"] and [u.split("/")[-1] for u in j["images"] if "/diagnostics/" in u] == ["back_compare.png"]
jb = job({**BUILD, "back_diag": "on", "blender": "on", "rig": ""}); assert jb["state"] == "done", jb                 # Blender 마무리까지: 세 단계
repb = json.loads((path_of(jb["images"][0]).parent / "diagnostics" / "back_report.json").read_text(encoding="utf-8"))
assert set(repb["stages"]) == {"engine", "photo"} and any("마무리(Blender) 뒤" in e and "건너뛰었어요" in e for e in repb["errors"]), repb.get("errors")      # 가짜 Blender 는 진짜 GLB 를 내놓지 않아요 — 그 단계만 건너뛰고 나머지는 진단
r3, f3 = m3dviews.diagnose({"engine": g_eng, "photo": res, "final": res}, rotate=90)                                 # 세 단계가 다 있을 때(마무리 뒤 = 사진 붙이기 뒤와 같은 3D 로)
assert set(r3["stages"]) == {"engine", "photo", "final"} and r3["changes"]["photo_to_final"]["back"]["changed"] == 0 and r3["stages"]["final"]["yaw_offset"] == 0.0 and "back_views_final.png" in f3
assert any(v["stage"] == "photo_to_final" and v["level"] == "ok" for v in r3["verdict"]) and not r3["errors"]
if os.environ.get("BACK_OUT"):
    Image.open(dg / "back_compare.png").save(os.environ["BACK_OUT"] + "_compare.png"); sh.save(os.environ["BACK_OUT"] + "_views.png")
ok("3D build: back diagnosis is off by default; when on, the engine still runs once, the normal result is byte-identical, and diagnostics/ gets the per-stage sheets (engine / after photo / after Blender), the back comparison and the report with a verdict")

# 7) 화면
from playwright.sync_api import sync_playwright
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1100}); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B); pg.wait_for_selector("#rail nav button[data-v=m3d]"); pg.click("nav button[data-v=m3d]")
    pg.wait_for_function("document.querySelector('#m3-sess') && [...document.querySelector('#m3-sess').options].some(o=>o.value==%r)" % sid)
    pg.select_option("#m3-sess", sid); pg.wait_for_timeout(600)
    assert not pg.is_checked("#m3-backdiag") and pg.locator("#m3-geofit").count() == 0 and "뒷면 진단" in pg.inner_text("label:has(#m3-backdiag)")
    pg.uncheck("#m3-blender"); pg.uncheck("#m3-keephi"); pg.select_option("#m3-engine", "trellis"); pg.select_option("#m3-tex", "1024"); pg.check("#m3-backdiag")
    pg.click("#m3-go"); pg.wait_for_selector("#m3-out .m3-back", timeout=300000)
    txt = pg.inner_text("#m3-out .m3-back")
    assert "뒷면을 바꾸지 않았어요" in txt and "앞면을 뒤집은" in txt and "back_report.json" in txt and "저장한 곳" in txt, txt[:500]
    assert pg.locator("#m3-out .m3-back .m3-sheet img").count() == 1 and pg.locator("#m3-out .m3-back .m3-stat tbody tr").count() == 2 and pg.locator("#m3-out #m3-mv").count() == 1
    b.close()
assert not errs, errs
ok("screen: 'back diagnosis' checkbox is off by default, the failed geometry-fit toggle is gone; after a build the verdict list, the back comparison picture and the save location are shown")
print("ALL OK")
