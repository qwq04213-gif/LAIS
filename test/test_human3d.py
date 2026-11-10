"""4.9 인체 3D(SiTH) — 가짜 엔진으로 흐름 확인: 약속(본체↔worker), 자세 변환, 사진 준비, 메시 읽기·쓰기·GLB, 메시 검사,
사진 화소 붙이기(앞면만), worker 실행·단계·진행·VRAM, 메모리 부족 재시도(최대 2번)·진단, 중단, 결과 폴더, 파일 주소 보안, 기존 3D 유지, 빌드 포함.
※ 실제 SiTH·그래픽카드는 쓰지 않아요(그 부분은 미검증)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, socket, urllib.request, urllib.error, tempfile
os.environ["TEST_HUB_PORT"] = "17951"
sys.path.insert(0, BASE + "/test")
from mocks import *
import numpy as np
from PIL import ImageDraw
sys.path.insert(0, BASE + "/LocalAI-Studio/engine/human3d")
from human3d import contracts as K, preprocess as PRE, export as X, mesh_qa as Q, texture_project as T, manager as MG, preflight as PF
from worker import runtime as WR
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid, t=120):
    for _ in range(t * 10):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
    raise AssertionError("timeout " + str(j))

# 1) 약속: 본체와 worker 가 같은 값을 쓰는지
assert (K.API_VERSION, K.HOST, K.PORT) == (WR.API_VERSION, WR.HOST, WR.PORT) and K.WORKER_STAGES == WR.WORKER_STAGES and K.HOST == "127.0.0.1"
assert abs(sum(s[2] for s in K.STAGES) - 1) < 1e-9 and K.overall("preprocess", 0) == 0 and K.overall("export", 1) == 1 and K.MAX_OOM_RETRY == 2
o = K.clean_opts({"grid": 999, "back_candidates": 99, "provider": "evil", "chunk": 1}); assert o["grid"] == 512 and o["back_candidates"] == 8 and o["provider"] == "sith" and o["chunk"] == 5000
ok("contracts shared by hub and worker; options clamped")

# 2) 자세: COCO-WholeBody 133 → OpenPose BODY_25 + 손 + 얼굴 70
k = np.zeros((133, 3)); k[:, 0] = np.arange(133); k[:, 1] = np.arange(133) * 2; k[:, 2] = 0.9
op = PRE.wholebody_to_openpose(k)["people"][0]; b = np.array(op["pose_keypoints_2d"]).reshape(25, 3)
assert b[4, 0] == 10 and b[7, 0] == 9 and b[11, 0] == 16 and b[14, 0] == 15 and b[1, 0] == 5.5 and b[8, 0] == 11.5 and b[19, 0] == 17 and b[24, 0] == 22
assert len(op["face_keypoints_2d"]) == 210 and len(op["hand_left_keypoints_2d"]) == 63 and op["hand_left_keypoints_2d"][0] == 91 and op["hand_right_keypoints_2d"][0] == 112
f = np.array(op["face_keypoints_2d"]).reshape(70, 3); assert abs(f[68, 0] - (23 + np.arange(36, 42)).mean()) < 1e-6
ok("pose adapter: wholebody-133 → OpenPose JSON (neck/mid-hip computed, pupils from eye ring)")

# 시험 그림: 투명 배경 위의 사람 모양(팔다리를 벌린 자세) + 관절점(원본 화소 좌표)
W, Hh = 800, 1200
J2 = {"nose": (400, 150), "lsh": (490, 300), "rsh": (310, 300), "lel": (600, 420), "rel": (200, 420), "lwr": (690, 540), "rwr": (110, 540),
      "lhip": (450, 620), "rhip": (350, 620), "lkn": (480, 850), "rkn": (320, 850), "lan": (500, 1080), "ran": (300, 1080)}
def person(drop=None):
    im = Image.new("RGBA", (W, Hh), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((330, 60, 470, 240), fill=(224, 172, 140, 255)); d.rectangle((370, 230, 430, 300), fill=(224, 172, 140, 255))
    d.rectangle((300, 280, 500, 640), fill=(180, 40, 40, 255))
    for a, b_, c in (("lsh", "lel", (180, 40, 40)), ("lel", "lwr", (224, 172, 140)), ("rsh", "rel", (180, 40, 40)), ("rel", "rwr", (224, 172, 140)),
                     ("lhip", "lkn", (40, 60, 150)), ("lkn", "lan", (40, 60, 150)), ("rhip", "rkn", (40, 60, 150)), ("rkn", "ran", (40, 60, 150))):
        d.line([J2[a], J2[b_]], fill=c + (255,), width=62); d.ellipse((J2[b_][0] - 31, J2[b_][1] - 31, J2[b_][0] + 31, J2[b_][1] + 31), fill=c + (255,))
    for x in (300, 500): d.ellipse((x - 45, 1070, x + 45, 1130), fill=(30, 30, 30, 255))
    for i in range(0, 200, 20): d.line([(300 + i, 300), (300 + i, 620)], fill=(250, 220, 60, 255), width=6)      # 옷 무늬(사진 화소가 붙었는지 보려고)
    return im
def kp133():
    k = np.zeros((133, 3)); k[:, 2] = 0.9
    for i, n in {0: "nose", 5: "lsh", 6: "rsh", 7: "lel", 8: "rel", 9: "lwr", 10: "rwr", 11: "lhip", 12: "rhip", 13: "lkn", 14: "rkn", 15: "lan", 16: "ran"}.items(): k[i, :2] = J2[n]
    for i, (dx, dy) in {1: (25, -15), 2: (-25, -15), 3: (55, 0), 4: (-55, 0)}.items(): k[i, :2] = (400 + dx, 150 + dy)
    for base, an in ((17, "lan"), (20, "ran")):
        x, y = J2[an]; k[base, :2] = (x + 20, y + 40); k[base + 1, :2] = (x + 35, y + 35); k[base + 2, :2] = (x - 20, y + 30)
    th = np.linspace(0, 2 * np.pi, 68, endpoint=False); k[23:91, 0] = 400 + 50 * np.cos(th); k[23:91, 1] = 150 + 65 * np.sin(th)
    for s, wr in ((91, "lwr"), (112, "rwr")):
        k[s:s + 21, 0] = J2[wr][0] + np.linspace(-20, 20, 21); k[s:s + 21, 1] = J2[wr][1] + np.linspace(-20, 20, 21)
    return k
def url(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

# 3) 사진 준비: 전신이 잘리지 않게 가운데 정렬
P0 = person(); sq, fr = PRE.square_input(P0); bx = PRE.person_box(sq.getchannel("A"))
assert sq.size == (1024, 1024) and bx[0] > 20 and bx[2] < 1004 and bx[1] > 50 and bx[3] < 980 and 0.80 < (bx[3] - bx[1]) / 1024 <= 0.86
x0, y0 = J2["nose"]; assert sq.getpixel((round(x0 * fr["scale"] + fr["ox"]), round(y0 * fr["scale_y"] + fr["oy"])))[3] == 255
wide = Image.new("RGBA", (1600, 600), (0, 0, 0, 0)); wide.paste((200, 0, 0, 255), (0, 100, 1600, 500)); s2, _ = PRE.square_input(wide); b2 = PRE.person_box(s2.getchannel("A")); assert b2[0] >= 40 and b2[2] <= 984
assert PRE.body_checks(P0)[0]["level"] == "ok" and any(c["id"] == "cut" for c in PRE.body_checks(wide)) and PRE.body_checks(Image.new("RGBA", (64, 64), (0, 0, 0, 0)))[0]["level"] == "bad"
ok("preprocess: square 1024 input keeps the whole body with margins; cut-off / empty photos flagged")

# 4) 메시 검사(위상): 조각·구멍·뒤집힘 — 작은 조각을 지우지 않고 세기만
def box(c, s):
    V = (np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float) * np.array(s) / 2 + np.array(c)).astype(np.float32)
    return V, np.array([(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)], np.int32)
V1, F1 = box((0, 0, 0), (.5, 1, .3)); V2, F2 = box((.6, 0, 0), (.1, .1, .1))
t = Q.topology(np.concatenate([V1, V2]), np.concatenate([F1, F2 + 8])); assert t["components"] == 2 and t["watertight"] and not t["inverted"] and t["faces"] == 24
t = Q.topology(V1, F1[:-2]); assert t["holes"] == 1 and t["big_holes"] == 1 and t["boundary_edges"] == 4 and not t["watertight"]
assert Q.topology(V1, F1[:, ::-1])["inverted"] and Q.topology(V1, np.concatenate([F1, [[0, 0, 1]]]).astype(np.int32))["degenerate_faces"] == 1
m = X.Mesh(V1, F1, np.full((8, 3), 9, np.uint8)); tmp = Path(tempfile.mkdtemp()); X.write_ply(tmp / "a.ply", m); r = X.read_ply(tmp / "a.ply"); assert (r.V == m.V).all() and (r.F == m.F).all() and (r.C == 9).all()
(tmp / "a.obj").write_text("v 0 0 0 1 0 0\nv 1 0 0 0 1 0\nv 0 1 0 0 0 1\nf 1/1/1 2/2/2 3/3/3\n"); r = X.read_obj(tmp / "a.obj"); assert r.F.tolist() == [[0, 1, 2]] and r.C.tolist()[0] == [255, 0, 0]
n = X.write_glb(tmp / "a.glb", X.Mesh(V1, F1, np.full((8, 3), 9, np.uint8), np.ones(8))); g = X.read_glb_json(tmp / "a.glb")
at = g["meshes"][0]["primitives"][0]["attributes"]; assert set(at) == {"POSITION", "NORMAL", "COLOR_0", "_OBSERVED"} and g["accessors"][at["POSITION"]]["count"] == 8 and (tmp / "a.glb").stat().st_size == n
ok("mesh QA topology (pieces counted not deleted, holes, inversion, degenerate) · OBJ/PLY read · GLB with vertex colors + observed map")

# 5) 본체: 준비 안 됨(리눅스·WSL 없음) → 안내, 기존 3D 는 그대로
S = get("/api/human3d"); assert S["preflight"]["ready"] is False and S["preflight"]["stage"] == "wsl" and len(S["stages"]) == 10 and S["install"]["state"] == "idle"
assert "items" in get("/api/m3d") and hasattr(hub, "do_m3d") and hasattr(hub, "photoproj") and hub.KIND_NAME["m3d"] == "3D 만들기"
j = wait(post("/api/job", {"kind": "human3d", "image": url(P0)})["id"]); assert j["state"] == "error" and "준비가 안 됐어요" in j["error"], j
d0 = Path(j["human3d"]["dir"]); assert (d0 / "input/original.png").is_file() and (d0 / "images/000.png").is_file() and json.loads((d0 / "job.json").read_text(encoding="utf-8"))["state"] == "error"
ok("not ready → clear Korean guidance, inputs kept; the existing 3D (m3d) is untouched")

# 6) 가짜 엔진으로 끝까지
MODE = tmp / "mode.txt"; KP = tmp / "kp.json"; KP.write_text(json.dumps(kp133().tolist())); MODE.write_text("ok")
WPORT = 17990 + SLOT * 1000
os.environ.update(HUMAN3D_WORKER_CMD=f"{sys.executable} -m worker.app --provider fake_human3d:FakeProvider --home {tmp}", HUMAN3D_FAKE_MODE=str(MODE), HUMAN3D_FAKE_KP=str(KP),
                  PYTHONPATH=BASE + "/test" + os.pathsep + os.environ.get("PYTHONPATH", ""))
MG.STATE["port"] = WPORT
S = get("/api/human3d?deep=1"); assert S["preflight"]["ready"] and S["preflight"]["stage"] == "ok" and S["preflight"]["verified"] is False, S["preflight"]
h = MG.running(WPORT); assert h and h["api"] == 1
s = socket.socket(); s.settimeout(1)
try:
    ext = socket.gethostbyname(socket.gethostname())
    if not ext.startswith("127."): assert s.connect_ex((ext, WPORT)) != 0, "worker 가 바깥 주소에서도 열려 있어요"
finally: s.close()
j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 2}})["id"]); assert j["state"] == "done", j
H = j["human3d"]; d = Path(H["dir"]); assert d.parent == hub.OUT / "3D-human" and H["glb"] and j["images"] == [H["glb"]] and j["progress"] == 1.0
need = ["input/original.png", "input/original.bin", "input/mask.png", "input/rgba.png", "input/frame.json", "images/000.png", "images/000_keypoints.json", "smplx/000_smplx.obj", "smplx/debug/000.json",
        "back_images/000_000.png", "back_images/all_images/000_001.png", "back_images/pick.json", "meshes/000_reco.ply", "meshes/000_reco.obj", "result/texture_front.png", "result/mesh_qa.json",
        "result/human.glb", "result/view_front.png", "result/view_q45.png", "result/view_side.png", "result/view_back.png", "job.log", "hub.log", "job.json"]
assert not [f for f in need if not (d / f).is_file()], [f for f in need if not (d / f).is_file()]
assert (d / "input/original.bin").read_bytes() == base64.b64decode(url(P0).split(",")[1]) and Image.open(d / "input/original.png").size == (W, Hh)
meta = json.loads((d / "job.json").read_text(encoding="utf-8")); assert meta["state"] == "done" and meta["versions"]["engine"] == "fake" and meta["provider_verified"] is False and meta["opts"]["back_candidates"] == 2
assert [s["id"] for s in meta["stages"]] == ["keypoints", "smplx_init", "smplx_fit", "back", "geometry", "texture"] and all(s["state"] == "done" and "sec" in s for s in meta["stages"]) and "vram_peak_mb" in meta
assert [s["id"] for s in H["stages"]] == [s["id"] for s in meta["stages"]] and H["stages"][3]["vram_proc_mb"] == 5000 and set(H["views"]) >= {"front", "q45", "side", "back", "observed"}
qa = json.loads((d / "result/mesh_qa.json").read_text(encoding="utf-8")); assert qa["pass"] and qa["silhouette"]["iou"] > 0.93 and qa["topology"]["components"] == 1 and not qa["topology"]["inverted"], qa["problems"]
assert all(e["known"] and e["cover"] > 0.8 for e in qa["parts"].values()) and len(qa["parts"]) == 12 and qa["face"]["ok"] and qa["neck"]["ok"] and qa["neck"]["connected"] and qa["legs_gap"]["filled"] < 0.2, qa["parts"]
assert qa["glb"]["remesh"] is False and qa["glb"]["decimate"] is False and qa["glb"]["vertices"] == qa["topology"]["vertices"]
# 사진 화소 붙이기: 앞면은 사진 색(옷 빨강·노란 줄), 뒷면은 엔진 색 그대로
eng = X.read_ply(d / "meshes/000_reco.ply"); assert set(map(tuple, eng.C.tolist())) == {(110, 110, 110), (60, 80, 160)}
g = X.read_glb_json(d / "result/human.glb"); assert {"COLOR_0", "_OBSERVED", "NORMAL"} <= set(g["meshes"][0]["primitives"][0]["attributes"]) and g["accessors"][0]["count"] == len(eng.V)
fv = np.asarray(Image.open(d / "result/view_front.png").convert("RGB")).astype(int); bv = np.asarray(Image.open(d / "result/view_back.png").convert("RGB")).astype(int)
red = lambda a: ((a[..., 0] > a[..., 2] * 1.6) & (a[..., 0] > 80)).mean(); blue = lambda a: ((a[..., 2] > a[..., 0] * 1.5) & (a[..., 2] > 60)).mean()
assert red(fv) > 0.03 and blue(fv) < 0.002 and blue(bv) > 0.08 and red(bv) < 0.002, (red(fv), blue(fv), blue(bv), red(bv))
assert qa["projection"]["source"] == "original" and 0.25 < qa["projection"]["observed_ratio"] < 0.6
V = get("/api/human3d/job/" + H["id"]); assert V["glb"] and V["qa"]["pass"] and V["pick"]["picked"] == 0 and V["views"]["side"] and any(x["id"] == H["id"] and x["glb"] for x in get("/api/human3d")["jobs"])
assert urllib.request.urlopen(B + V["glb"]).read()[:4] == b"glTF"
for bad in (f"/human3d/file/{H['id']}/..%2F..%2Fsettings.json", f"/human3d/file/{H['id']}/../../settings.json", "/human3d/file/nope/job.json", f"/human3d/file/{H['id']}/hub.py"):
    try: urllib.request.urlopen(B + bad); raise AssertionError(bad)
    except urllib.error.HTTPError as e: assert e.code == 404
ok("fake engine end-to-end: all stage files kept in outputs/3D-human/<id>, GLB with photo pixels only on the visible front, QA passes, 4 views, meta with versions/VRAM")

# 7) 팔이 빠진 메시 → 검사가 부위와 단계를 짚음(지우거나 고치지 않음)
MODE.write_text("drop_arm"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); assert j["state"] == "done" and "문제" in j["msg"], j
ids = {p["id"]: p for p in j["human3d"]["qa"]["problems"]}; assert not j["human3d"]["qa"]["pass"] and "missing_l_forearm" in ids and "missing_l_hand" in ids and "missing_r_forearm" not in ids, ids.keys()
assert ids["missing_l_forearm"]["stage"] == "geometry" and "형태 복원에서 빠졌어요" in ids["missing_l_forearm"]["text"]
MODE.write_text("two_pieces"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); q2 = j["human3d"]["qa"]
assert j["state"] == "done" and q2["topology"]["components"] == 2 and any(p["id"] == "pieces" for p in q2["problems"])
assert X.read_glb_json(Path(j["human3d"]["dir"]) / "result/human.glb")["accessors"][0]["count"] == q2["topology"]["vertices"]      # 작은 조각도 GLB 에 그대로
ok("missing limb is named with the stage that lost it; separate pieces are reported and kept")

# 8) 메모리 부족: 설정을 낮춰 다시(최대 2번) → 그래도 안 되면 진단 보고서, 중간 결과 보존
MODE.write_text("oom_once"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); H = j["human3d"]
assert j["state"] == "done" and H["retries"] == 1 and any("2만" in n for n in H["notes"]) and H["grid"] == 512, H
MODE.write_text("oom_always"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); H = j["human3d"]; d = Path(H["dir"])
assert j["state"] == "error" and "형태 복원" in j["error"] and "메모리" in j["error"] and "diagnosis.json" in j["error"] and H["retries"] == 2, j
dg = json.loads((d / "diagnosis.json").read_text(encoding="utf-8")); assert dg["failed_stage"] == "geometry" and dg["code"] == "oom" and len(dg["tried"]) == 2 and dg["opts"]["grid"] == 384 and dg["suggestions"] and "out of memory" in dg["last_output"]
assert (d / "back_images/000_000.png").is_file() and (d / "smplx/000_smplx.obj").is_file() and not (d / "result/human.glb").exists() and json.loads((d / "job.json").read_text(encoding="utf-8"))["state"] == "error"
assert get("/api/human3d/job/" + H["id"])["diagnosis"]["code"] == "oom"
ok("OOM: one retry with smaller chunks succeeds; persistent OOM stops after 2 retries with diagnosis.json and all intermediate files kept")

# 9) 중단
MODE.write_text("slow"); r = post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 4}})
for _ in range(100):
    time.sleep(0.2); jj = get("/api/job/" + r["id"])
    if (jj.get("human3d") or {}).get("stage") == "back": break
post("/api/job/cancel", {"id": r["id"]}); j = wait(r["id"]); assert j["state"] == "cancelled" and (Path(j["human3d"]["dir"]) / "smplx/000_smplx.obj").is_file(), j
assert json.loads((Path(j["human3d"]["dir"]) / "job.json").read_text(encoding="utf-8"))["state"] == "cancelled" and MG.running(WPORT)["busy"] is None
MODE.write_text("ok"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); assert j["state"] == "done"
ok("cancel stops the worker job, keeps intermediate files, and the next job runs")

# 10) 실제 SiTH 어댑터: 메모리 부족 때 낮추는 순서, 저메모리 격자 순서, 없는 환경에서의 점검
from worker.providers.sith import SithProvider
sp = SithProvider({"home": str(tmp / "nohome"), "python": sys.executable})
class JB: opts = {"grid": 512, "chunk": 50000, "back_candidates": 4}
a = [sp.on_oom(JB, "geometry") for _ in range(4)]; assert "2만" in a[0] and "384" in a[1] and "256" in a[2] and a[3] is None and JB.opts["grid"] == 256
b = [sp.on_oom(JB, "back") for _ in range(3)]; assert JB.opts["offload"] and JB.opts["back_candidates"] == 1 and b[2] is None and sp.on_oom(JB, "smplx_fit") is None
pf = sp.preflight(); ids = {c["id"]: c for c in pf["checks"]}; assert not pf["ready"] and not ids["smplx"]["ok"] and "smpl-x.is.tue.mpg.de" in ids["smplx"]["fix"] and not ids["code"]["ok"] and sp.verified is False
import itertools
lin = np.linspace(-1, 1, 5); assert np.allclose(np.concatenate([p for _, p in WR.grid_chunks(5, 7)]), np.array(list(itertools.product(lin, lin, lin)), np.float32))
assert WR.is_oom("torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate") and not WR.is_oom("ValueError: bad shape")
assert MG.wsl_path(r"D:\AI\LAIS\outputs\3D-human\x") == "/mnt/d/AI/LAIS/outputs/3D-human/x"
src = (Path(BASE) / "LocalAI-Studio/engine/human3d/worker/providers/sith_stages.py").read_text(encoding="utf-8")
assert "_repair_mesh(" not in src.replace("(_repair_mesh)", "") and "inference_mode" in src and "grid_chunks" in src and "enable_model_cpu_offload" in src and "num_images_per_prompt=1" in src
ok("SiTH adapter: OOM step-down order (chunk → 384 → 256, back: offload → 1 candidate), CPU-side grid chunks in SiTH order, SMPL-X guidance without bypass")

# 11) 빌드: worker 코드는 업데이트에 들어가고, engine 의 다른 것(모델·가상환경)은 안 들어감
sys.path.insert(0, BASE + "/release-tools"); import build_update as BU
tree = tmp / "tree"; (tree / "engine/human3d/worker").mkdir(parents=True); (tree / "engine/human3d/worker/app.py").write_text("x"); (tree / "engine/human3d/models").mkdir(); (tree / "engine/human3d/models/big.pth").write_text("x")
(tree / "engine/ComfyUI").mkdir(); (tree / "engine/ComfyUI/main.py").write_text("x"); (tree / "hub").mkdir(); (tree / "hub/a.py").write_text("x"); (tree / "outputs").mkdir(); (tree / "outputs/o.png").write_text("x")
assert sorted(BU.collect(tree)) == ["engine/human3d/worker/app.py", "hub/a.py"]
real = BU.collect(Path(BASE) / "LocalAI-Studio"); assert "engine/human3d/worker/providers/sith.py" in real and "engine/human3d/scripts/install_wsl.sh" in real and "hub/human3d/mesh_qa.py" in real and "hub/server/27_m3d.py" in real
assert b"\r" not in real["engine/human3d/scripts/install_wsl.sh"] and b"\r" not in real["engine/human3d/scripts/install_models.sh"]
ok("build: worker code ships in the update; models / venv / other engine folders never do")
MG.stop(WPORT)
print("ALL OK")
