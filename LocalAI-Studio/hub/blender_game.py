# -*- coding: utf-8 -*-
"""Blender 안에서 도는 마무리 스크립트(허브가 'blender -b --python 이파일 -- {json}' 으로 실행해요).
GLB 하나 → 크기·바닥 기준점·앞 방향 맞추기 → LOD(면 줄인 판) → GLB·FBX·OBJ·.blend + 텍스처 → result.json
Blender 4.5 LTS 기준. 실패하면 'HUBERR:이유' 를 찍고 코드 3 으로 끝나요."""
import json
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig_fit  # noqa: E402  (numpy 만 쓰는 관절 어림 — 허브 테스트와 같은 코드)


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return json.loads(a[0]) if a else {}


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights):
        for d in list(coll):
            if d.users == 0:
                coll.remove(d)


def select_only(objs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def selftest(folder):
    clear()
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    path = os.path.join(folder, "check.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=False)
    with open(os.path.join(folder, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": os.path.isfile(path), "blender": bpy.app.version_string}, f)


def bake_world(objs):
    """부모·변환을 정점에 굳혀서, 물체마다 원점=세상 원점·변환 없음 상태로 만들어요."""
    for o in objs:
        mw = o.matrix_world.copy()
        o.parent = None
        if o.data.users > 1:
            o.data = o.data.copy()
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)


def bounds(objs):
    lo, hi = Vector((1e18, 1e18, 1e18)), Vector((-1e18, -1e18, -1e18))
    for o in objs:
        for v in o.data.vertices:
            for i in range(3):
                lo[i] = min(lo[i], v.co[i])
                hi[i] = max(hi[i], v.co[i])
    return lo, hi


def tri_count(objs):
    return sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs), sum(len(o.data.vertices) for o in objs)


def lod_copy(objs, ratio, name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    out = []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        n = o.copy()
        n.data = o.data.copy()
        n.name = f"{o.name}_{name}"
        coll.objects.link(n)
        arms = [(md.name, md.object) for md in n.modifiers if md.type == "ARMATURE"]
        for md in [md for md in n.modifiers if md.type == "ARMATURE"]:      # 자세가 굳지 않게 뼈대는 잠시 빼요
            n.modifiers.remove(md)
        m = n.modifiers.new("hub_decimate", "DECIMATE")
        m.decimate_type = "COLLAPSE"
        m.ratio = max(0.01, min(1.0, ratio))
        m.use_collapse_triangulate = True
        dg.update()
        ev = n.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        n.modifiers.clear()
        old = n.data
        n.data = me
        if old.users == 0:
            bpy.data.meshes.remove(old)
        for mname, aobj in arms:                                       # 가중치(정점 그룹)는 면을 줄여도 남아요 → 뼈대 다시 연결
            md = n.modifiers.new(mname, "ARMATURE")
            md.object = aobj
        out.append(n)
    return out


def safe(s):
    return re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", s).strip("_") or "model"


def join(objs, name):
    if len(objs) == 1:
        return objs[0]
    select_only(objs)
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    return o


def rig(mesh, name):
    """사람형 뼈대(Mixamo 이름) → 자동 가중치(뼈 열 확산) → 못 받은 정점은 가장 가까운 뼈로."""
    import numpy as np
    n = len(mesh.data.vertices)
    co = np.empty(n * 3)
    mesh.data.vertices.foreach_get("co", co)
    fit = rig_fit.fit(co.reshape(-1, 3))
    J = {k: Vector(v) for k, v in fit["joints"].items()}
    H = fit["height"]
    data = bpy.data.armatures.new(f"{name}_Armature")
    arm = bpy.data.objects.new("Armature", data)
    bpy.context.scene.collection.objects.link(arm)
    select_only([arm])
    bpy.ops.object.mode_set(mode="EDIT")
    eb = data.edit_bones
    for bn, a, b, parent, conn in rig_fit.BONES:
        e = eb.new(bn)
        e.head, e.tail = J[a], J[b]
        if (e.tail - e.head).length < 1e-3 * H:
            e.tail = e.head + Vector((0, 0, 0.02 * H))
        if parent:
            e.parent = eb[parent]
            e.use_connect = conn and (eb[parent].tail - e.head).length < 1e-6
    bpy.ops.object.mode_set(mode="OBJECT")
    select_only([mesh, arm])
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    # 자동 가중치가 못 준 정점(뼈 열 확산 실패)은 가장 가까운 뼈로
    names = [b[0] for b in rig_fit.BONES]
    vgs = {g.index: g.name for g in mesh.vertex_groups}
    bare = [v.index for v in mesh.data.vertices if sum(g.weight for g in v.groups if g.group in vgs) <= 1e-6]
    if bare:
        segs = [(tuple(data.bones[b].head_local), tuple(data.bones[b].tail_local)) for b in names]
        pts = np.array([tuple(mesh.data.vertices[i].co) for i in bare])
        near = rig_fit.nearest_bone(pts, segs)
        for bi in set(near.tolist()):
            g = mesh.vertex_groups.get(names[bi]) or mesh.vertex_groups.new(name=names[bi])
            g.add([bare[k] for k in range(len(bare)) if near[k] == bi], 1.0, "REPLACE")
    if not any(m.type == "ARMATURE" for m in mesh.modifiers):
        md = mesh.modifiers.new("Armature", "ARMATURE")
        md.object = arm
    return arm, {"bones": len(names), "pose": fit["pose"], "legs": fit["legs"], "warn": fit["warn"], "fixed": len(bare)}


def preview_motion(arm, frames=60):
    """확인용 짧은 움직임(팔 들기·고개 끄덕임)을 넣어요. 뼈대 자세 공간 → 뼈 자기 공간으로 바꿔 줘요."""
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = 1, frames
    arm.animation_data_create()
    arm.animation_data.action = bpy.data.actions.new("확인용_움직임")
    moves = {"LeftArm": ("Y", -40), "RightArm": ("Y", 40), "LeftForeArm": ("Y", -20), "RightForeArm": ("Y", 20), "Head": ("X", 12), "Spine1": ("Z", 8)}
    for bn, (ax, deg) in moves.items():
        pb = arm.pose.bones.get(bn)
        if not pb:
            continue
        pb.rotation_mode = "QUATERNION"
        rest = arm.data.bones[bn].matrix_local.to_quaternion()
        for f, k in ((1, 0.0), (frames // 2, 1.0), (frames, 0.0)):
            q = Quaternion(Vector({"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[ax]), math.radians(deg) * k)
            pb.rotation_quaternion = rest.inverted() @ q @ rest
            pb.keyframe_insert("rotation_quaternion", frame=f)
    scn.frame_set(1)


def main(j):
    if j.get("selftest"):
        selftest(j["selftest"])
        return
    out, name = j["out"], safe(j.get("name") or "model")
    os.makedirs(out, exist_ok=True)
    clear()
    bpy.ops.import_scene.gltf(filepath=j["glb"])
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not objs:
        raise RuntimeError("GLB 안에 그물망(메시)이 없어요.")
    for o in [o for o in bpy.context.scene.objects if o.type != "MESH"]:      # 빈 부모·카메라·조명은 지워요
        bpy.data.objects.remove(o, do_unlink=True)
    bake_world(objs)
    # 앞 방향 돌리기(위쪽 축 기준, 90도 단위) → 바닥 가운데를 원점으로 → 키(m) 맞추기
    rot = float(j.get("rotate") or 0)
    if rot:
        R = Matrix.Rotation(math.radians(rot), 4, "Z")
        for o in objs:
            o.data.transform(R)
    lo, hi = bounds(objs)
    size = hi - lo
    h = float(j.get("height") or 0)
    s = h / size.z if h > 0 and size.z > 1e-9 else 1.0
    M = Matrix.Scale(s, 4) @ Matrix.Translation(Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
    for o in objs:
        o.data.transform(M)
        o.data.update()
    for i, o in enumerate(objs):
        o.name = name if len(objs) == 1 else f"{name}_{i}"
    lo, hi = bounds(objs)
    arm, rinfo = None, None
    if j.get("rig"):
        mesh = join(objs, name)
        objs = [mesh]
        arm, rinfo = rig(mesh, name)
    # 텍스처는 .blend 옆 textures/ 로 풀어 둬요(FBX·OBJ 가 파일로 가져가게)
    blend = os.path.join(out, f"{name}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    try:
        bpy.ops.file.unpack_all(method="WRITE_LOCAL")
    except RuntimeError:
        pass
    ratios = [r for r in (j.get("lods") or [1.0]) if 0 < float(r) <= 1.0] or [1.0]
    fmts = set(j.get("formats") or ["glb", "fbx"])
    levels = []
    for i, r in enumerate(ratios):
        group = objs if i == 0 and r >= 0.999 else lod_copy(objs, float(r), f"LOD{i}")
        tris, verts = tri_count(group)
        tag = f"{name}_LOD{i}"
        rec = {"lod": i, "ratio": round(float(r), 3), "tris": tris, "verts": verts}
        select_only(group + ([arm] if arm else []))
        if "glb" in fmts:
            p = os.path.join(out, tag + ".glb")
            bpy.ops.export_scene.gltf(filepath=p, export_format="GLB", use_selection=True, export_animations=False)
            rec["glb"] = os.path.basename(p)
        if "fbx" in fmts:
            p = os.path.join(out, tag + ".fbx")
            bpy.ops.export_scene.fbx(filepath=p, use_selection=True, path_mode="COPY", embed_textures=True, axis_forward="-Z", axis_up="Y",
                                     apply_scale_options="FBX_SCALE_UNITS", mesh_smooth_type="FACE", add_leaf_bones=False, bake_anim=False)
            rec["fbx"] = os.path.basename(p)
        if "obj" in fmts:
            p = os.path.join(out, tag + ".obj")
            bpy.ops.wm.obj_export(filepath=p, export_selected_objects=True, export_materials=True, path_mode="COPY",
                                  forward_axis="NEGATIVE_Z", up_axis="Y")
            rec["obj"] = os.path.basename(p)
        levels.append(rec)
    if arm:                                            # 화면에서 돌려 볼 확인용 움직임(게임용 파일에는 안 넣어요)
        preview_motion(arm)
        select_only(objs + [arm])
        p = os.path.join(out, f"{name}_rig_preview.glb")
        bpy.ops.export_scene.gltf(filepath=p, export_format="GLB", use_selection=True, export_animations=True)
        rinfo["preview"] = os.path.basename(p)
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    tex_dir = os.path.join(out, "textures")
    res = {"ok": True, "blender": bpy.app.version_string, "name": name, "lods": levels, "blend": os.path.basename(blend),
           "size_m": [round(hi.x - lo.x, 4), round(hi.y - lo.y, 4), round(hi.z - lo.z, 4)], "scale": round(s, 6),
           "textures": sorted(os.listdir(tex_dir)) if os.path.isdir(tex_dir) else [], **({"rig": rinfo} if rinfo else {})}
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 윈도우에서도 한글 오류가 깨지지 않게
    except Exception:  # noqa: BLE001
        pass
    J = {}
    try:
        J = args()
        main(J)
    except Exception as e:  # noqa: BLE001
        msg = (str(e) or type(e).__name__).replace("\n", " ")[:400]
        print("HUBERR:" + msg, flush=True)
        d = J.get("out") or J.get("selftest")
        if d and os.path.isdir(d):
            try:
                with open(os.path.join(d, "error.txt"), "w", encoding="utf-8") as f:
                    f.write(msg)
            except OSError:
                pass
        sys.exit(3)
