"""4.9 인체 3D(SiTH) — 가짜 엔진으로 흐름 확인(그래픽카드는 모의 GPU — 실제 측정 아님): 약속(본체↔worker), 자세 변환, 사진 준비, 메시 읽기·쓰기·GLB, 메시 검사,
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
assert abs(sum(s[2] for s in K.STAGES) - 1) < 1e-9 and K.overall("preprocess", 0) == 0 and K.overall("export", 1) == 1 and K.MAX_OOM_RETRY == 3 and K.OOM_LADDER == (("chunk", 20000), ("grid", 384), ("grid", 256))
assert K.GENDERS == WR.GENDERS == ("male", "female", "neutral") and K.DEFAULT_OPTS["gender"] == "auto" and K.clean_opts({"gender": "female"})["gender"] == "female" and K.clean_opts({"gender": "남자"})["gender"] == "auto"
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
                     ("lhip", "lkn", (40, 110, 60)), ("lkn", "lan", (40, 110, 60)), ("rhip", "rkn", (40, 110, 60)), ("rkn", "ran", (40, 110, 60))):
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
VR = tmp / "vram.txt"; VR.write_text("900")
os.environ.update(HUMAN3D_FAKE_VRAM=str(VR), HUMAN3D_VRAM_EVERY="0.1", PATH=BASE + "/test/fake_bin" + os.pathsep + os.environ["PATH"])      # 모의 GPU(가짜 nvidia-smi 12GB)
hub._LIVE["t"] = 0; STATE["ollama_loaded"] = ["testmodel:latest"]
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
assert H["gender"] == "auto" and H["gender_used"]["gender"] == "neutral" and H["gender_used"]["applied"] and meta["opts"]["gender"] == "auto" and any("중립" in n and "자동" in n for n in H["notes"]), (H.get("gender_used"), H["notes"])
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

# 7-2) 성별: 고른 성별의 몸 모델로만 맞춤 — 남성 고정 없음, 없는 성별은 다른 성별로 바꾸지 않고 멈춤 (가짜 엔진 — 실제 여성 사진 추론은 미검증)
MODE.write_text("ok")
for g, fn in (("female", "SMPLX_FEMALE.npz"), ("male", "SMPLX_MALE.npz"), ("neutral", "SMPLX_NEUTRAL.npz")):
    j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1, "gender": g}})["id"]); H = j["human3d"]; d = Path(H["dir"])
    gu = json.loads((d / "smplx/gender.json").read_text(encoding="utf-8")); mt = json.loads((d / "job.json").read_text(encoding="utf-8"))
    assert j["state"] == "done" and H["gender"] == g and gu == H["gender_used"] and gu["gender"] == g and gu["model_file"] == fn and gu["applied"] and mt["gender"] == g and mt["gender_used"]["gender"] == g, (g, gu)
    assert mt["opts"]["gender_used"] == g and not any("자동" in n for n in H["notes"]) and get("/api/human3d/job/" + H["id"])["meta"]["gender_used"]["model_file"] == fn
MODE.write_text("no_female"); hub._H3_PF["v"] = None; S2 = get("/api/human3d?deep=1"); assert S2["preflight"]["genders"] == {"male": True, "female": False, "neutral": True} and S2["preflight"]["ready"], S2["preflight"]
assert "SMPLX_FEMALE.npz" in S2["preflight"]["smplx"]["files"] and S2["preflight"]["smplx"]["partial"]
j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"gender": "female"}})["id"]); d = Path(j["human3d"]["dir"])
assert j["state"] == "error" and "여성" in j["error"] and "SMPLX_FEMALE.npz" in j["error"] and "바꿔 쓰지 않아요" in j["error"] and not (d / "smplx").exists() and not (d / "result/human.glb").exists() and hub.GPU_HOLD["who"] is None, j
j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"gender": "male", "back_candidates": 1}})["id"]); assert j["state"] == "done" and j["human3d"]["gender_used"]["gender"] == "male"      # 있는 성별은 그대로 됨
MODE.write_text("no_gender_record"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"gender": "female", "back_candidates": 1}})["id"])
assert j["state"] == "error" and "성별이 적용됐는지 확인할 수 없어" in j["error"] and not (Path(j["human3d"]["dir"]) / "result/human.glb").exists(), j      # 적용 기록이 없으면 결과를 내지 않음
MODE.write_text("ok"); hub._H3_PF["v"] = None
# 실제 SiTH 단계 스크립트(cmd_fit): 공식 fit.py 의 남성 고정을 고른 성별로 바꾸는지 — 가짜 fit 모듈로 확인(torch·SMPL-X 없이)
import subprocess
fk = tmp / "fakesith"; (fk / "data/body_models/smplx").mkdir(parents=True); (fk / "data/body_models/smplx/SMPLX_FEMALE.npz").write_bytes(b"x"); (fk / "data/body_models/smplx/SMPLX_MALE.npz").write_bytes(b"x")
(fk / "fit.py").write_text("""import os, json
SMPL_PATH = 'data/body_models'
class _M:
    def __init__(self, gender): self.gender = gender; self.v_template = type('V', (), {'shape': (10475, 3)})()
def SMPLX(model_path=None, gender=None, **kw): return _M(gender)
def main(args):
    m = SMPLX(model_path=os.path.join(SMPL_PATH, 'smplx'), gender='male', use_pca=False)      # 공식 코드처럼 남성 고정
    os.makedirs(args.output_path, exist_ok=True)
    json.dump({'made_with': m.gender, 'debug': args.debug, 'opt_betas': args.opt_betas, 'opt_orient': args.opt_orient, 'size': args.size}, open(os.path.join(args.output_path, 'made.json'), 'w'))
""")
def run_fit(g, extra=""):
    jd = Path(tempfile.mkdtemp()); (jd / "images").mkdir()
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([BASE + "/LocalAI-Studio/engine/human3d", BASE + "/LocalAI-Studio/hub", str(fk)]))
    r = subprocess.run([sys.executable, "-m", "worker.providers.sith_stages", "fit", "--job", str(jd), "--gender", g], cwd=fk, env=env, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr, jd
rc, out, jd = run_fit("female"); made = json.loads((jd / "smplx/made.json").read_text()); gj = json.loads((jd / "smplx/gender.json").read_text(encoding="utf-8"))
assert rc == 0 and made == {"made_with": "female", "debug": True, "opt_betas": True, "opt_orient": True, "size": 1024} and gj["gender"] == "female" and gj["upstream_default"] == "male" and gj["applied"] and gj["vertices"] == 10475, (out, made, gj)
rc, out, jd = run_fit("neutral"); assert rc != 0 and "@@ERROR no_smplx" in out and "SMPLX_NEUTRAL.npz" in out and "바꿔 쓰지 않아요" in out and not (jd / "smplx").exists(), out      # 없는 성별 → 남성으로 대신하지 않고 멈춤
rc, out, jd = run_fit("woman"); assert rc != 0 and "모르는 성별" in out
st_src = (Path(BASE) / "LocalAI-Studio/engine/human3d/worker/providers/sith_stages.py").read_text(encoding="utf-8"); pv_src = (Path(BASE) / "LocalAI-Studio/engine/human3d/worker/providers/sith.py").read_text(encoding="utf-8")
assert 'kw["gender"] = g' in st_src and '"fit.py", "-i"' not in pv_src and '"fit", "--gender", g' in pv_src      # 공식 fit.py 를 직접 돌리던(남성 고정) 경로는 없어짐
ok("gender: chosen SMPL-X model is really applied (female/male/neutral), auto = neutral never male, missing gender file stops instead of substituting, no result without an 'applied' record")

# 8) 메모리 부족: 한 단계씩 낮춰 다시(점 수 2만 → 격자 384 → 격자 256), 같은 설정은 두 번 안 돌림, 시도마다 격자·점 수·VRAM 기록
MODE.write_text("oom_once"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); H = j["human3d"]
assert j["state"] == "done" and H["retries"] == 1 and any("2만" in n for n in H["notes"]) and H["grid"] == 512 and H["chunk"] == 20000 and not H["low_detail"], H
ga = [a for a in H["attempts"] if a["stage"] == "geometry"]; assert [(a["grid"], a["chunk"], a["result"]) for a in ga] == [(512, 50000, "oom"), (512, 20000, "ok")], ga
assert ga[0]["vram_peak_mb"] >= 11000 and ga[0]["failed_stage"] == "geometry" and 9000 < ga[1]["vram_peak_mb"] < ga[0]["vram_peak_mb"], ga      # 모의 GPU 값(실제 측정 아님)
MODE.write_text("oom_above_256"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); H = j["human3d"]; d = Path(H["dir"])
assert j["state"] == "done" and H["retries"] == 3 and H["grid"] == 256 and H["low_detail"] and "512 → 256" in H["low_detail_text"] and "덜 세밀" in j["msg"] and "격자 256" in j["msg"], j
ga = [a for a in H["attempts"] if a["stage"] == "geometry"]; assert [(a["grid"], a["chunk"], a["result"]) for a in ga] == [(512, 50000, "oom"), (512, 20000, "oom"), (384, 20000, "oom"), (256, 20000, "ok")], ga
assert len({(a["grid"], a["chunk"]) for a in ga}) == 4 and all(a["vram_peak_mb"] > 5000 for a in ga)
meta = json.loads((d / "job.json").read_text(encoding="utf-8")); assert meta["final_grid"] == 256 and meta["requested_grid"] == 512 and meta["low_detail"] and len(meta["attempts"]) >= 4 and meta["retries"] == 3
assert (d / "result/human.glb").is_file() and get("/api/human3d/job/" + H["id"])["meta"]["low_detail_text"]
MODE.write_text("oom_always"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); H = j["human3d"]; d = Path(H["dir"])
assert j["state"] == "error" and "형태 복원" in j["error"] and "메모리" in j["error"] and "diagnosis.json" in j["error"] and H["retries"] == 3, j
dg = json.loads((d / "diagnosis.json").read_text(encoding="utf-8")); assert dg["failed_stage"] == "geometry" and dg["code"] == "oom" and len(dg["tried"]) == 4 and dg["opts"]["grid"] == 256 and dg["opts"]["chunk"] == 20000 and "out of memory" in dg["last_output"]
ga = [a for a in dg["attempts"] if a["stage"] == "geometry"]; assert [(a["grid"], a["chunk"]) for a in ga] == [(512, 50000), (512, 20000), (384, 20000), (256, 20000)] and all(a["result"] == "oom" and a["vram_peak_mb"] for a in ga), ga
assert dg["tried"][-1]["next"] is None and any("256" in x and "어려워요" in x for x in dg["suggestions"]) and dg["vram"]["total_mb"] == 12288
assert (d / "back_images/000_000.png").is_file() and (d / "smplx/000_smplx.obj").is_file() and not (d / "result/human.glb").exists() and json.loads((d / "job.json").read_text(encoding="utf-8"))["state"] == "error"
assert get("/api/human3d/job/" + H["id"])["diagnosis"]["code"] == "oom"
ok("OOM ladder really reaches 256 (512/50k → 512/20k → 384 → 256), no setting repeated, per-attempt grid/chunk/VRAM logged (mock GPU); lower grid flagged as less detailed; stops with diagnosis after 256")

# 9) 중단
MODE.write_text("slow"); r = post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 4}})
for _ in range(100):
    time.sleep(0.2); jj = get("/api/job/" + r["id"])
    if (jj.get("human3d") or {}).get("stage") == "back": break
post("/api/job/cancel", {"id": r["id"]}); j = wait(r["id"]); assert j["state"] == "cancelled" and (Path(j["human3d"]["dir"]) / "smplx/000_smplx.obj").is_file(), j
assert json.loads((Path(j["human3d"]["dir"]) / "job.json").read_text(encoding="utf-8"))["state"] == "cancelled" and MG.running(WPORT)["busy"] is None
MODE.write_text("ok"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); assert j["state"] == "done"
ok("cancel stops the worker job, keeps intermediate files, and the next job runs")

# 9-2) 그래픽카드 혼자 쓰기: 인체 3D 가 도는 동안 대화(Ollama)가 모델을 올리지 못하고, 끝나면(완료·중단·실패) 반드시 풀림
def chat():
    raw = urllib.request.urlopen(urllib.request.Request(B + "/api/chat", json.dumps({"model": "testmodel:latest", "messages": [{"role": "user", "content": "안녕"}]}).encode(), {"Content-Type": "application/json"})).read().decode()
    rows = [json.loads(l) for l in raw.splitlines() if l.strip()]
    return "".join((r.get("message") or {}).get("content", "") for r in rows) + "".join("error:" + r["error"] for r in rows if r.get("error"))
assert hub.GPU_HOLD["who"] is None and "안녕" in chat() and len(STATE["chatreq"]) == 1                       # 평소 대화는 그대로
STATE["ollama_loaded"] = ["testmodel:latest"]; n_gen = len(GEN); MODE.write_text("slow"); r = post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 4}})
for _ in range(150):
    time.sleep(0.1)
    if (get("/api/job/" + r["id"]).get("human3d") or {}).get("stage") == "back": break
assert hub.GPU_HOLD["who"] == "human3d" and hub.GPU_HOLD["owner"] == r["id"] and get("/api/human3d")["gpu_hold"]["who"] == "human3d" and get("/api/job/" + r["id"])["human3d"]["gpu_hold"] is True
assert STATE["ollama_loaded"] == [] and any(g.get("keep_alive") == 0 and g.get("model") == "testmodel:latest" for g in GEN[n_gen:]), GEN[n_gen:]      # 시작할 때 Ollama 모델을 실제로 내림
c = chat(); assert "인체 3D" in c and "혼자" in c and "error" in c and len(STATE["chatreq"]) == 1, c                 # 대화 요청은 한국어 안내만 받고 Ollama 에 가지 않음
n_g2 = len(GEN); assert hub.translate("빨간 재킷", "tags") == "빨간 재킷" and len(GEN) == n_g2                       # 번역도 모델을 올리지 않음(원문 그대로)
try: hub.llm_http("/api/chat", {"model": "m", "messages": []}); raise AssertionError("llm_http 가 막히지 않았어요")
except hub.GpuBusy as e: assert "인체 3D" in str(e)
try: hub.claim("chat"); raise AssertionError("claim 이 막히지 않았어요")
except hub.GpuBusy: pass
STATE["vision"] = ["testmodel:latest"]; de = post("/api/describe", {"image": url(P0.convert("RGB")), "model": "testmodel:latest"}); assert "인체 3D" in de.get("error", ""), de
assert hub.llm_http("/api/chat", {"model": "m", "stream": False, "messages": [], "options": {"num_gpu": 0}})["message"]      # CPU 로만 도는 대화는 그래픽카드를 안 쓰니 허용
assert STATE["ollama_loaded"] == []
post("/api/job/cancel", {"id": r["id"]}); j = wait(r["id"]); assert j["state"] == "cancelled" and hub.GPU_HOLD["who"] is None and hub.STATE["last"] is None and j["human3d"]["gpu_hold"] is False
assert "안녕" in chat() and len(STATE["chatreq"]) == 2                                                               # 풀린 뒤 대화가 다시 됨
MODE.write_text("oom_always"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); assert j["state"] == "error" and hub.GPU_HOLD["who"] is None     # 실패해도 풀림
MODE.write_text("ok"); j = wait(post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}})["id"]); assert j["state"] == "done" and hub.GPU_HOLD["who"] is None            # 완료 뒤 풀림
real_submit = hub.H3Client.submit
def boom(self, *a): raise RuntimeError("뜻밖의 오류")
hub.H3Client.submit = boom; j = wait(post("/api/job", {"kind": "human3d", "image": url(P0)})["id"]); hub.H3Client.submit = real_submit
assert j["state"] == "error" and "뜻밖의 오류" in j["error"] and hub.GPU_HOLD["who"] is None and hub.LLM_USERS["n"] == 0     # 뜻밖의 예외에도 점유가 남지 않음(finally)
# 답을 만들고 있는 대화가 있으면 그게 끝난 뒤에 시작
import threading; rel = {}
def talk():
    with hub.llm_use(): time.sleep(2.0); rel["t"] = time.time()
threading.Thread(target=talk).start(); time.sleep(0.2); assert hub.LLM_USERS["n"] == 1
r = post("/api/job", {"kind": "human3d", "image": url(P0), "opts": {"back_candidates": 1}}); seen = False
for _ in range(60):
    time.sleep(0.1); jj = get("/api/job/" + r["id"]); seen = seen or "대화가 끝나기를 기다리는 중" in (jj.get("msg") or "")
    if "t" in rel: break
    assert not (jj.get("human3d") or {}).get("stages"), "대화가 끝나기 전에 worker 가 시작됐어요"
j = wait(r["id"]); hl = (Path(j["human3d"]["dir"]) / "hub.log").read_text(encoding="utf-8")
assert seen and j["state"] == "done" and "그래픽카드 혼자 쓰기 시작" in hl and (Path(j["human3d"]["dir"]) / "job.log").stat().st_mtime >= rel["t"] - 0.01 and hub.GPU_HOLD["who"] is None
# 대화가 끝나지 않으면 기다리다 멈추고 점유를 풀어요 · 이미 점유 중이면 두 번째 점유는 거절
hub.LLM_USERS["n"] = 1
try: hub.gpu_exclusive_begin("human3d", "인체 3D", wait=0.6); raise AssertionError("기다리지 않았어요")
except RuntimeError as e: assert "끝나지 않아" in str(e) and hub.GPU_HOLD["who"] is None
hub.LLM_USERS["n"] = 0; hub.gpu_exclusive_begin("human3d", "인체 3D", owner="a")
try: hub.gpu_exclusive_begin("human3d", "인체 3D", owner="b"); raise AssertionError
except hub.GpuBusy: pass
hub.gpu_exclusive_end("human3d", "b"); assert hub.GPU_HOLD["who"] == "human3d"; hub.gpu_exclusive_end("human3d", "a"); assert hub.GPU_HOLD["who"] is None
ok("GPU exclusivity: Ollama unloaded at start, chat/translate/describe refused in Korean while running (CPU-only chat allowed), waits for a running chat, released on done / cancel / error / unexpected exception")

# 10) 실제 SiTH 어댑터: 메모리 부족 때 낮추는 순서, 저메모리 격자 순서, 없는 환경에서의 점검
from worker.providers.sith import SithProvider
sp = SithProvider({"home": str(tmp / "nohome"), "python": sys.executable})
class JB: opts = {"grid": 512, "chunk": 50000, "back_candidates": 4}
a = [sp.on_oom(JB, "geometry") for _ in range(4)]; assert "2만" in a[0] and "384" in a[1] and "256" in a[2] and a[3] is None and JB.opts["grid"] == 256 and JB.opts["chunk"] == 20000 and len(a) - 1 == K.MAX_OOM_RETRY
b = [sp.on_oom(JB, "back") for _ in range(3)]; assert JB.opts["offload"] and JB.opts["back_candidates"] == 1 and b[2] is None and sp.on_oom(JB, "smplx_fit") is None
pf = sp.preflight(); ids = {c["id"]: c for c in pf["checks"]}; assert not pf["ready"] and not ids["smplx"]["ok"] and "smpl-x.is.tue.mpg.de" in ids["smplx"]["fix"] and "남성·여성·중립 모두" in ids["smplx"]["fix"] and pf["genders"] == {"male": False, "female": False, "neutral": False} and not ids["code"]["ok"] and sp.verified is False
import itertools
lin = np.linspace(-1, 1, 5); assert np.allclose(np.concatenate([p for _, p in WR.grid_chunks(5, 7)]), np.array(list(itertools.product(lin, lin, lin)), np.float32))
assert WR.is_oom("torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate") and not WR.is_oom("ValueError: bad shape")
assert MG.wsl_path(r"D:\AI\LAIS\outputs\3D-human\x") == "/mnt/d/AI/LAIS/outputs/3D-human/x"
src = (Path(BASE) / "LocalAI-Studio/engine/human3d/worker/providers/sith_stages.py").read_text(encoding="utf-8")
assert "_repair_mesh(" not in src.replace("(_repair_mesh)", "") and "inference_mode" in src and "grid_chunks" in src and "enable_model_cpu_offload" in src and "num_images_per_prompt=1" in src
ok("SiTH adapter: OOM step-down order (chunk → 384 → 256, back: offload → 1 candidate), CPU-side grid chunks in SiTH order, SMPL-X guidance without bypass")

# 10-2) 설치 스크립트: CUDA 컴파일러가 먼저, 없으면 nvdiffrast 를 시작하지 않음 · 그리기 검사 실패면 '완료'가 아님 (가짜 명령으로 순서만 확인 — 실제 설치 아님)
import subprocess, stat
SH = Path(BASE) / "LocalAI-Studio/engine/human3d/scripts/install_wsl.sh"
def run_install(nvcc, nvcheck, apt="none", build="ok", steps="cuda nvdiffrast", envcheck="ok"):
    h = Path(tempfile.mkdtemp()); stub = h / "stub"; stub.mkdir(); log = h / "calls.log"; cuda = h / "cudahome"
    def mk(name, body):
        f = stub / name; f.write_text("#!/usr/bin/env bash\n" + body); f.chmod(f.stat().st_mode | stat.S_IEXEC)
    mk("pip", f'echo "pip $*" >> {log}\ncase "$*" in show*) exit 1 ;; *nvdiffrast*) [ "{build}" = ok ] || exit 1; touch {h}/built ;; *nvidia-cuda-nvcc*) exit 1 ;; *--force-reinstall*pins.txt*) touch {h}/repaired ;; esac\nexit 0\n')
    mk("python", f'echo "python $*" >> {log}\ncase "$*" in *worker.nvcheck*) if [ "{nvcheck}" = ok ] && [ -f {h}/built ]; then echo \'@@NVCHECK {{"ok": true, "text": "ok"}}\'; exit 0; else '
                 f'echo \'@@NVCHECK {{"ok": false, "kind": "runtime", "text": "그리기를 실패했어요(CUDA 실행 문제).", "fix": "드라이버를 올려 주세요."}}\'; exit 2; fi ;; '
                 f'*worker.envcheck*) if [ "{envcheck}" = ok ] || {{ [ "{envcheck}" = repair ] && [ -f {h}/repaired ]; }}; then echo \'@@ENVCHECK {{"ok": true, "text": "부품 16개를 모두 불러왔어요(numpy 1.24.1)."}}\'; exit 0; else '
                 f'echo "[안 됨] kaolin: ValueError: numpy.dtype size changed  ← scipy"; echo \'@@ENVCHECK {{"ok": false, "abi": true, "text": "부품끼리 판이 안 맞아요: kaolin 을(를) 불러오지 못해요. 문제가 난 곳: scipy."}}\'; exit 2; fi ;; '
                 f'*json.loads*) exec python3 "$@" ;; esac\nexit 0\n')
    for n in ("wget", "dpkg", "sudo"): mk(n, f'echo "{n} $*" >> {log}\nexit {0 if apt == "ok" else 1}\n')
    mk("apt-get", f'echo "apt-get $*" >> {log}\n' + (f'case "$*" in *cuda-compiler*) mkdir -p {cuda}/bin {cuda}/include; printf \'#!/bin/sh\\necho "Cuda compilation tools, release 12.1, V12.1.105"\\n\' > {cuda}/bin/nvcc; chmod +x {cuda}/bin/nvcc; touch {cuda}/include/cuda_runtime.h ;; esac\nexit 0\n' if apt == "ok" else "exit 1\n"))
    if nvcc in ("ok", "old"):
        (cuda / "bin").mkdir(parents=True); (cuda / "include").mkdir(); (cuda / "include/cuda_runtime.h").write_text("")
        f = cuda / "bin/nvcc"; f.write_text('#!/bin/sh\necho "Cuda compilation tools, release %s, V0"\n' % ("12.1" if nvcc == "ok" else "11.8")); f.chmod(0o755)
    env = dict(os.environ, HUMAN3D_HOME=str(h / "home"), HUMAN3D_INSTALL_STEPS=steps, HUMAN3D_TEST_BIN=str(stub), CUDA_HOME=str(cuda), HOME=str(h))
    r = subprocess.run(["bash", str(SH)], capture_output=True, text=True, env=env, timeout=60)
    return r.returncode, r.stdout + r.stderr, (log.read_text() if log.exists() else ""), h
rc, out, calls, h = run_install("ok", "ok")
assert rc == 0 and "@@DONE" in out and "@@FAIL" not in out and "release 12.1" in out, out
nv = [l for l in calls.splitlines() if "nvdiffrast" in l and l.startswith("pip")]; assert len(nv) == 1 and "--no-build-isolation" in nv[0] and "git+https://github.com/NVlabs/nvdiffrast" in nv[0], calls
assert calls.index("setuptools, wheel, ninja") < calls.index("pip install -q --force-reinstall") < calls.rindex("worker.nvcheck") and out.index("CUDA 12.1 컴파일러 준비") < out.index("nvdiffrast 설치")
envsh = (h / "home/env.sh").read_text(); assert "CUDA_HOME=" in envsh and "/bin:$PATH" in envsh and "LD_LIBRARY_PATH" in envsh
for nvcc in ("none", "old"):                                   # 컴파일러가 없거나 12.1 이 아니고, 받지도 못하면 → 멈춤, nvdiffrast 는 시작도 안 함
    rc, out, calls, _ = run_install(nvcc, "ok")
    assert rc == 1 and "@@DONE" not in out and "@@FAIL" in out and "nvcc" in out and "cuda-toolkit-12-1" in out and "nvdiffrast 설치" not in out and "NVlabs/nvdiffrast" not in calls, (nvcc, out, calls)
rc, out, calls, _ = run_install("none", "ok", apt="ok")         # 없으면 NVIDIA 저장소에서 받아서 진행
assert rc == 0 and "@@DONE" in out and "cuda-compiler-12-1" in calls and calls.index("cuda-compiler-12-1") < calls.index("NVlabs/nvdiffrast"), (out, calls)
rc, out, calls, _ = run_install("ok", "fail")                   # 설치는 됐지만 실제 그리기 검사 실패 → 완료로 표시하지 않음
assert rc == 1 and "@@DONE" not in out and "실제로 그리는 검사에 실패" in out and "CUDA 실행 문제" in out and "드라이버" in out, out
rc, out, calls, _ = run_install("ok", "fail", build="fail")     # 컴파일 실패 → 한 번 더 시도 뒤 멈춤
assert rc == 1 and "@@DONE" not in out and "컴파일하지 못했어요" in out and calls.count("NVlabs/nvdiffrast") == 2, (out, calls)
txt = SH.read_text(encoding="utf-8"); assert txt.index("want torch") < txt.index("if want cuda") < txt.index("if want nvdiffrast") and "STEPS=" in txt and "gpu base sith venv torch cuda parts nvdiffrast pose" in txt
ok("installer (stubbed commands): torch → CUDA 12.1 nvcc → nvdiffrast with --no-build-isolation → real raster check; no compiler ⇒ nvdiffrast never starts; failed check ⇒ not marked done")

# 10-2b) 부품 판 고정 + 마지막 '실제로 불러와 보는' 검사 (실제 PC 에서 kaolin 이 numpy 판 문제로 안 불러와졌던 것)
pins = (SH.parent / "pins.txt").read_text(encoding="utf-8"); assert "numpy==1.24.1" in pins and "scipy==" in pins and "opencv-python==" in pins and "onnxruntime==" in pins
assert "onnxruntime-gpu" not in txt.replace("# 자세 검출은", "") or "pip install -q onnxruntime-gpu" not in txt
assert "PIP_CONSTRAINT" in txt and txt.index("PIP_CONSTRAINT") < txt.index("want torch") and "want check" in txt and txt.rindex("@@DONE") > txt.index("want check")
rc, out, calls, h = run_install("ok", "ok", steps="check"); assert rc == 0 and "@@DONE" in out and "모두 불러왔어요" in out and (h / "home/pins.txt").read_text(encoding="utf-8") == pins, out
rc, out, calls, h = run_install("ok", "ok", steps="check", envcheck="repair")      # 처음엔 안 불러와짐 → 고정한 판으로 다시 깔고 → 통과
assert rc == 0 and "@@DONE" in out and "고정한 판으로 다시 깔고" in out and "--force-reinstall --no-deps -r" in calls and calls.count("worker.envcheck") >= 2, (out, calls)
rc, out, calls, h = run_install("ok", "ok", steps="check", envcheck="fail")        # 다시 깔아도 안 되면 → 완료로 표시하지 않음
assert rc == 1 and "@@DONE" not in out and "부품을 불러오는 검사에 실패" in out and "판이 안 맞아요" in out and "캡처" in out, out
rc, out, calls, h = run_install("ok", "ok", steps="parts"); assert rc == 0 and calls.index("-r " + str(h / "home/pins.txt")) < calls.index("kaolin==0.15.0") < calls.index("diffusers==0.24.0"), calls
from worker import envcheck as EC
tb = 'Traceback\n  File "/root/lais-human3d/venv/lib/python3.10/site-packages/kaolin/__init__.py", line 1, in <module>\n  File "/root/lais-human3d/venv/lib/python3.10/site-packages/scipy/ndimage/_ni.py", line 3\nValueError: x'
assert EC.culprit_of(tb) == "scipy" and EC.ABI_RX.search("numpy.dtype size changed, may indicate binary incompatibility. Expected 96 from C header, got 88 from PyObject") and not EC.ABI_RX.search("No module named 'x'")
r = EC.check((("json", "json", "json"), ("nope", "no_such_module_xyz", "없는 부품"))); assert r["ok"] is False and r["failed"] == ["nope"] and r["modules"]["json"]["ok"] and "없는 부품" in r["text"] and r["fix"] and r["modules"]["nope"]["trace"]
sys.path.insert(0, BASE + "/release-tools"); import apply_update as AU, build_update as BU2
assert AU.safe_rel("engine/human3d/scripts/pins.txt") and "engine/human3d/scripts/pins.txt" in BU2.collect(Path(BASE) / "LocalAI-Studio")
ok("pinned package set shipped and enforced (PIP_CONSTRAINT), final import check with one repair attempt; a still-broken environment is not marked done and names the culprit")

# 10-3) 사전 검사: nvdiffrast 를 실제로 돌려 보고 '설치 문제 / CUDA 실행 문제'를 구분, 전체 메모리와 쓸 수 있는 메모리를 따로 표시
from worker import nvcheck as NV
assert NV.check()["ok"] is False and NV.check()["kind"] in ("no_torch", "not_installed")          # 이 시험 환경에는 torch·nvdiffrast 가 없어요
assert NV.classify("import_pkg", ImportError("x"))[0] == "not_installed" and NV.classify("import_torch_ext", ImportError("No module named '_nvdiffrast_c'"))[0] == "build"
assert NV.classify("context", RuntimeError("CUDA error: unknown error"))[0] == "runtime" and NV.classify("raster", RuntimeError("Could not find nvcc"))[0] == "build"
src = Path(NV.__file__).read_text(encoding="utf-8"); assert "import nvdiffrast.torch as dr" in src and "RasterizeCudaContext(device=\"cuda\")" in src and "dr.rasterize(" in src
def pf_with(nv, free=11000):
    sp2 = SithProvider({"home": str(tmp / "nohome"), "python": sys.executable})
    sp2._probe = (time.time(), {"python": "3.10", "torch": "2.1.0", "cuda": True, "gpu": "Mock", "vram_mb": 12288, "free_mb": free, "fp16": True, "bf16": True, "cuda_version": "12.1",
                               "kaolin": "0.15", "diffusers": "0.24", "smplx": "ok", "rtmlib": "ok", "nv": nv})
    return sp2.preflight()
ok_nv = {"ok": True, "kind": "ok", "text": "nvdiffrast 0.4.0 — 그래픽카드에서 삼각형 그리기 확인(1310화소)", "pixels": 1310}
c = {x["id"]: x for x in pf_with(ok_nv)["checks"]}; assert c["nvdiffrast"]["ok"] and "삼각형" in c["nvdiffrast"]["text"] and "mod_nvdiffrast" not in c
assert "전체 메모리 12.0GB" in c["vram"]["text"] and "실제로 쓸 수 있는 메모리 10.7GB" in c["vram_free"]["text"] and "1.3GB 사용 중" in c["vram_free"]["text"] and c["vram_free"]["ok"] and "보장하지 않아요" in c["vram_note"]["text"]
c = {x["id"]: x for x in pf_with({"ok": False, "kind": "build", "text": "CUDA 확장을 불러오지 못했어요.", "fix": NV.FIX_INSTALL}, free=5000)["checks"]}
assert not c["nvdiffrast"]["ok"] and c["nvdiffrast"]["text"].startswith("[설치 문제]") and "설치 시작" in c["nvdiffrast"]["fix"] and not c["vram_free"]["ok"] and "닫으면" in c["vram_free"]["fix"]
r2 = pf_with({"ok": False, "kind": "runtime", "text": "그리기를 실패했어요.", "fix": NV.FIX_RUNTIME}); c = {x["id"]: x for x in r2["checks"]}
assert c["nvdiffrast"]["text"].startswith("[CUDA 실행 문제]") and "wsl --shutdown" in c["nvdiffrast"]["fix"] and r2["ready"] is False and r2["nvdiffrast"]["kind"] == "runtime"
sp3 = SithProvider({"home": str(tmp / "nohome"), "python": sys.executable})
sp3._probe = (time.time(), {"python": "3.10", "torch": "2.1.0", "cuda": True, "gpu": "Mock", "vram_mb": 12288, "free_mb": 9700, "kaolin": None, "kaolin_error": "ValueError: numpy.dtype size changed, may indicate binary incompatibility. Expected 96 from C header, got 88 from PyObject",
                             "kaolin_abi": True, "kaolin_culprit": "scipy", "kaolin_trace": "File .../scipy/ndimage/x.py", "diffusers": "0.24", "smplx": "ok", "rtmlib": "ok", "nv": ok_nv, "env": {"ok": False, "failed": ["kaolin", "h5py"], "abi": True}, "h5py_error": "boom"})
c = {x["id"]: x for x in sp3.preflight()["checks"]}
assert not c["mod_kaolin"]["ok"] and "판이 안 맞아요" in c["mod_kaolin"]["text"] and "scipy" in c["mod_kaolin"]["text"] and "설치 시작" in c["mod_kaolin"]["fix"] and "Expected 96" in c["mod_kaolin"]["detail"] and c["mod_kaolin"]["trace"]
assert not c["mod_others"]["ok"] and "h5py" in c["mod_others"]["text"] and "SMPL-X 몸 모델: 없음" in c["smplx"]["text"]
ok("preflight: nvdiffrast is actually exercised (context + tiny raster), install vs CUDA-runtime problems told apart, total vs usable VRAM shown separately")

# 11) 빌드: worker 코드는 업데이트에 들어가고, engine 의 다른 것(모델·가상환경)은 안 들어감
sys.path.insert(0, BASE + "/release-tools"); import build_update as BU
tree = tmp / "tree"; (tree / "engine/human3d/worker").mkdir(parents=True); (tree / "engine/human3d/worker/app.py").write_text("x"); (tree / "engine/human3d/models").mkdir(); (tree / "engine/human3d/models/big.pth").write_text("x")
(tree / "engine/ComfyUI").mkdir(); (tree / "engine/ComfyUI/main.py").write_text("x"); (tree / "hub").mkdir(); (tree / "hub/a.py").write_text("x"); (tree / "outputs").mkdir(); (tree / "outputs/o.png").write_text("x")
assert sorted(BU.collect(tree)) == ["engine/human3d/worker/app.py", "hub/a.py"]
real = BU.collect(Path(BASE) / "LocalAI-Studio"); assert "engine/human3d/worker/providers/sith.py" in real and "engine/human3d/scripts/install_wsl.sh" in real and "hub/human3d/mesh_qa.py" in real and "hub/server/27_m3d.py" in real
assert b"\r" not in real["engine/human3d/scripts/install_wsl.sh"] and b"\r" not in real["engine/human3d/scripts/install_models.sh"]
ok("build: worker code ships in the update; models / venv / other engine folders never do")
# 12) LAIS 를 업데이트했는데 예전 코드의 worker 가 떠 있으면 → 알아채고 다시 띄움(실제 PC 에서 4.9 worker 가 4.9.1 뒤에도 남아 있었어요)
h1 = MG.running(WPORT); assert h1["code"] == MG.code_hash() == WR.code_hash(BASE + "/LocalAI-Studio/engine/human3d/worker") and MG.start(hub.ROOT, WPORT)["pid"] == h1["pid"]      # 같으면 그대로
real_hash = MG.code_hash; MG.code_hash = lambda: "changed"; h2 = MG.start(hub.ROOT, WPORT); MG.code_hash = real_hash
assert h2 and h2["pid"] != h1["pid"] and h2["code"] == real_hash(), (h1, h2)
ok("stale worker (old code still running after an update) is detected by a code fingerprint and restarted")
MG.stop(WPORT)
print("ALL OK")
