"""4.1: 3D 품질·리깅 — 관절 어림(rig_fit, 가짜 사람 정점), 방향 그림 점검(실루엣)·같은 배율 맞추기, 방향 문장,
T자 자세 바꾸기·되돌리기, 뼈대 넣기(가짜 blender) → 뼈대 정보·움직임 미리보기."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request
os.environ["TEST_HUB_PORT"] = "17995"
sys.path.insert(0, BASE + "/test"); sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
from mocks import *
import numpy as np
import rig_fit, humanoid
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def wait(jid):
    for _ in range(400):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def job(o): return wait(post("/api/job", o)["id"])
def touch(*fs):
    for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x")
def url(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

# 1) 관절 어림 — 자세별
for pose, want in (("T", "T"), ("A", "A"), ("down", "down")):
    f = rig_fit.fit(humanoid.person(pose)); J = {k: np.array(v) for k, v in f["joints"].items()}
    assert f["pose"] == want and f["legs"], (pose, f["pose"], f["warn"])
    assert J["handL"][0] > 0.25 and J["handR"][0] < -0.25 or pose == "down", (pose, J["handL"])
    assert 0.75 < J["hips"][2] < 1.0 and 1.45 < J["neck"][2] < 1.6 and J["headtop"][2] > 1.75, (pose, J["hips"], J["neck"])
    assert J["kneeL"][0] > 0 > J["kneeR"][0] and J["ankleL"][2] < 0.15 and J["toetipL"][1] < J["ankleL"][1]
    assert ("T자" in " ".join(f["warn"])) == (pose == "down")
f = rig_fit.fit(humanoid.person("robe")); assert not f["legs"] and any("다리" in w for w in f["warn"])
names = [b[0] for b in rig_fit.BONES]; assert len(names) == len(set(names)) == 22 and {"Hips", "LeftArm", "RightUpLeg", "Head", "LeftToeBase"} <= set(names)
assert all(p is None or p in names for _, _, _, p, _ in rig_fit.BONES)
P = np.array([[0.3, 0, 1.4], [0, 0, 0.1]]); segs = [((0.2, 0, 1.4), (0.9, 0, 1.4)), ((0, 0, 0), (0, 0, 0.5))]
assert rig_fit.nearest_bone(P, segs).tolist() == [0, 1]
ok("rig_fit: T / A / arms-down poses, robe (no legs) warns, Mixamo bone names unique with valid parents, nearest bone")

# 2) 방향 문장: 왼쪽 = 얼굴이 그림 왼쪽, 오른쪽 = 그림 오른쪽, 뒤 = 얼굴 안 보임 (4.0 의 서로 어긋난 문장이 없어야 해요)
E = hub.M3D_SIDE_EN
assert "LEFT edge" in E["left"] and "RIGHT edge" in E["right"] and "NOT visible" in E["back"]
assert "subject's right" not in E["left"] and "subject's left" not in E["right"]
ok("side prompts follow the Pixal3D orbit (left view faces image-left, right view faces image-right)")

# 3) 실루엣 점검·같은 배율
def fig(w=400, h=400, parts=()):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for b in parts: im.paste((200, 90, 60, 255), b)
    return im
person_ = [(170, 40, 230, 100), (150, 100, 250, 260), (250, 110, 330, 130), (160, 260, 195, 380), (205, 260, 240, 380)]   # 오른손만 든 사람(좌우 비대칭)
mirror = lambda parts, w=400: [(w - b[2], b[1], w - b[0], b[3]) for b in parts]
side = [(180, 40, 220, 100), (170, 100, 230, 260), (175, 260, 225, 380), (150, 360, 225, 380)]      # 옆모습: 발끝이 한쪽으로
d = TMP / "vchk"; d.mkdir(exist_ok=True)
def put(**kw):
    for f in d.glob("view_*.png"): f.unlink()
    for k, parts in kw.items(): fig(parts=parts).save(d / f"view_{k}.png")
put(front=person_, back=mirror(person_), left=side, right=mirror(side))
c = hub.m3d_vcheck(d); assert c["back"]["ok"] and c["left"]["ok"] and c["right"]["ok"], c
put(front=person_, back=[(60, 150, 340, 260)], left=side, right=side)            # 뒤: 엉뚱한 모양 · 왼쪽=오른쪽(뒤집히지 않음)
c = hub.m3d_vcheck(d); assert not c["back"]["ok"] and not c["left"]["ok"] and not c["right"]["ok"] and "뒤바뀌" in c["left"]["text"], c
put(front=person_); assert hub.m3d_vcheck(d) == {}
car_front = fig(parts=[(150, 150, 250, 250)]); car_side = fig(parts=[(20, 150, 380, 250)])
fr = hub.m3d_frame({"front": car_front, "left": car_side})
hs = {k: (lambda bb: (bb[2] - bb[0], bb[3] - bb[1]))(np.asarray(v.convert("L")).nonzero() and Image.fromarray((np.asarray(v.convert("L")) > 10).astype("uint8") * 255).getbbox()) for k, v in fr.items()}
assert fr["front"].size == (1024, 1024) and fr["front"].mode == "RGB" and abs(hs["front"][1] - hs["left"][1]) <= 2, hs     # 같은 키(배율)
assert abs(hs["left"][0] - 1024 / 1.1) <= 3 and hs["front"][0] < hs["left"][0] / 3, hs                                     # 가장 넓은 방향이 틀의 1/1.1
assert fr["front"].getpixel((5, 5)) == (0, 0, 0)
ok("view check: back must mirror the front, left/right must mirror each other; multiview framing keeps one scale for all sides")

# 4) 작업 흐름: 사진 → 방향 그림(점검 결과 포함) → T자 자세 → 되돌리기 → 뼈대 넣기
hub.bgremove.have_ort = lambda: True; hub.bgremove.installed = lambda *a: True
class Cut:
    def cut(self, img, _):
        a = Image.new("L", img.size, 0); w, h = img.size
        for x0, y0, x1, y1 in person_: a.paste(255, (x0 * w // 400, y0 * h // 400, x1 * w // 400, y1 * h // 400))
        o = img.convert("RGBA"); o.putalpha(a); return o
hub.rmbg_engine = lambda k: Cut()
j = job({"kind": "m3d", "op": "prep", "image": url(Image.new("RGB", (400, 400), (30, 90, 160))), "kind3": "character", "name": "hero"}); assert j["state"] == "done", j
sid = j["m3d"]["id"]; dd = hub.M3D_DIR / sid
j = job({"kind": "m3d", "op": "views", "id": sid, "sides": ["back"]}); assert j["state"] == "done", j
assert "back" in j["m3d"]["vcheck"] and not j["m3d"]["vcheck"]["back"]["ok"] and "뒤" in j["msg"] and "체크를 풀어" in j["msg"], (j["m3d"]["vcheck"], j["msg"])   # 가짜 편집은 뒤집지 않아 '안 맞음'
txt = " ".join(str(v["inputs"].get("prompt", "")) + str(v["inputs"].get("text", "")) for v in SUBMITTED[-1].values()); assert "same pose" in txt and "NOT visible" in txt, txt[:400]
before = (dd / "view_front.png").read_bytes()
j = job({"kind": "m3d", "op": "tpose", "id": sid}); assert j["state"] == "done" and j["m3d"]["front_orig"] and "방향 그림" in j["msg"], j
txt = " ".join(str(v["inputs"].get("prompt", "")) + str(v["inputs"].get("text", "")) for v in SUBMITTED[-1].values()); assert "T-pose" in txt, txt[:300]
assert (dd / "view_front_orig.png").read_bytes() == before and urllib.request.urlopen(B + f"/m3d/{sid}/view_front_orig.png").status == 200
j = job({"kind": "m3d", "op": "tpose", "id": sid}); assert (dd / "view_front_orig.png").read_bytes() == before        # 두 번 눌러도 처음 원본은 그대로
r = post("/api/m3d/slot", {"id": sid, "side": "front", "restore": 1}); assert not r["front_orig"] and (dd / "view_front.png").read_bytes() == before
assert "error" in post("/api/m3d/slot", {"id": sid, "side": "front", "restore": 1}) and "error" in post("/api/m3d/slot", {"id": sid, "side": "left", "restore": 1})
ok("views report a silhouette check; T-pose keeps the original once, restore brings it back (and only once)")

touch("diffusion_models/trellis_2_int8_convrot.safetensors", "clip_vision/dino_v3_L_naf_fp32.safetensors",
      "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors")
assert hub.trellis_files()["dino"] == "dino_v3_L_naf_fp32.safetensors"                 # TRELLIS.2 전용 인코더가 없으면 Pixal3D 것도 써요(공식 예시와 같음)
fb = BASE + "/test/fake_blender.py"; os.chmod(fb, 0o755); os.environ["BLENDER_EXE"] = fb
assert hub.m3d_opts({}, {"kind": "character"})["rig"] and not hub.m3d_opts({}, {"kind": "object"})["rig"] and not hub.m3d_opts({"rig": ""}, {"kind": "character"})["rig"]
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "on", "rig": True, "height": "1.8"}); assert j["state"] == "done" and not j.get("warn"), j
rg = j["m3d_stats"]["rig"]; assert rg["bones"] == 22 and rg["pose"] == "T" and rg["legs"] and rg["fixed"] == 12, rg
assert rg["preview"].startswith(f"/m3d/{sid}/rig_preview.glb") and urllib.request.urlopen(B + rg["preview"]).read().endswith(b"RIGPREVIEW")
z = [u for u in j["images"] if u.endswith(".zip")][0]
info = json.loads((hub.OUT / "3D" / (z.rsplit("/", 1)[1] + ".json")).read_text(encoding="utf-8")); assert info["rig"] == {"bones": 22, "pose": "T", "legs": True}, info
import zipfile; names = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(B + z).read())).namelist(); assert not any("rig_preview" in n for n in names), names
os.environ["FAKE_BLENDER_POSE"] = "down"
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "on", "rig": True}); assert j["state"] == "done" and any("T자" in w for w in j["warn"]), j
j = job({"kind": "m3d", "op": "build", "id": sid, "blender": "on", "rig": ""}); assert j["state"] == "done" and "rig" not in j["m3d_stats"], j
ok("rig build: bones/pose/fix count shown, motion preview served from the work folder only, arms-down warns, rig off → no rig")
print("ALL OK")
