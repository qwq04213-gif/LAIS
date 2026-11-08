#!/usr/bin/env python3
"""테스트용 가짜 blender: 허브가 넘기는 인자(-b ... --python blender_game.py -- {json})를 확인하고 결과 묶음을 흉내 내요.
FAKE_BLENDER_FAIL 파일이 있으면 HUBERR 로 실패해요."""
import json, os, sys
a = sys.argv
assert a[1] == "-b" and "--factory-startup" in a and "--python-exit-code" in a and a[a.index("--python") + 1].endswith("blender_game.py"), a
j = json.loads(a[a.index("--") + 1])
if os.path.exists(os.environ.get("FAKE_BLENDER_FAIL", "/nonexistent")):
    out = j.get("out")
    if out:
        os.makedirs(out, exist_ok=True); open(os.path.join(out, "error.txt"), "w", encoding="utf-8").write("GLB 안에 그물망(메시)이 없어요.")
    print("HUBERR:GLB 안에 그물망(메시)이 없어요.", flush=True); sys.exit(3)
if j.get("selftest"):
    json.dump({"ok": True, "blender": "4.5.15"}, open(os.path.join(j["selftest"], "result.json"), "w")); sys.exit(0)
out, name = j["out"], j["name"]
assert open(j["glb"], "rb").read(4) == b"glTF"
os.makedirs(os.path.join(out, "textures"), exist_ok=True)
open(os.path.join(out, "textures", "base.png"), "wb").write(b"png")
open(os.path.join(out, name + ".blend"), "wb").write(b"BLENDER")
lods = []
for i, r in enumerate(j["lods"]):
    rec = {"lod": i, "ratio": r, "tris": int(20000 * r), "verts": int(10000 * r)}
    for f in j["formats"]:
        fn = f"{name}_LOD{i}.{f}"; open(os.path.join(out, fn), "wb").write(b"glTF\x02\x00\x00\x00LOD" + str(i).encode() if f == "glb" else f.encode()); rec[f] = fn
    lods.append(rec)
h = float(j.get("height") or 0)
json.dump({"ok": True, "blender": "4.5.15", "name": name, "lods": lods, "blend": name + ".blend", "size_m": [0.6, 0.4, h or 1.0],
           "scale": 1.0, "textures": ["base.png"], "args": j}, open(os.path.join(out, "result.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("fake blender done")
