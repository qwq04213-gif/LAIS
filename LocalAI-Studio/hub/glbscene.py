# -*- coding: utf-8 -*-
"""GLB 여러 개 → 한 장면 GLB (Blender 없이, 파이썬만). 3D 장면 전체 만들기에서 물체별 GLB 를 제자리에 놓아 합쳐요.
각 파일의 장면을 새 부모 노드 아래에 두고, 부모 노드의 크기·위치로 '바닥 가운데'가 정해진 자리에 오게 해요.
좌표: 넣는 위치(pos)는 Blender 기준(x 오른쪽, y 앞쪽=카메라에서 멀어짐, z 위) — glTF(y 위)로 바꿔 넣어요."""
import json
import math
import struct

import numpy as np

JSON_T, BIN_T = 0x4E4F534A, 0x004E4942
ARRAYS = ("buffers", "bufferViews", "accessors", "images", "samplers", "textures", "materials", "meshes", "nodes", "skins",
          "cameras", "animations")


def read(data):
    """GLB 바이트 → (json dict, bin bytes)"""
    if data[:4] != b"glTF" or len(data) < 20:
        raise ValueError("GLB 파일이 아니에요.")
    _, _, total = struct.unpack_from("<4sII", data, 0)
    pos, g, b = 12, None, b""
    while pos + 8 <= min(total, len(data)):
        ln, typ = struct.unpack_from("<II", data, pos)
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == JSON_T:
            g = json.loads(chunk.decode("utf-8"))
        elif typ == BIN_T and not b:
            b = bytes(chunk)
        pos += 8 + ln
    if g is None:
        raise ValueError("GLB 안에 JSON 이 없어요.")
    return g, b


def write(g, b):
    js = json.dumps(g, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    js += b" " * (-len(js) % 4)
    b = bytes(b) + b"\0" * (-len(b) % 4)
    out = struct.pack("<II", len(js), JSON_T) + js + (struct.pack("<II", len(b), BIN_T) + b if b else b"")
    return struct.pack("<4sII", b"glTF", 2, 12 + len(out)) + out


def _mat(n):
    if "matrix" in n:
        return np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.array(n.get("translation", [0, 0, 0]), dtype=np.float64)
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = np.array(n.get("scale", [1, 1, 1]), dtype=np.float64)
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


def bounds(g):
    """장면의 세계 좌표 상자(glTF, y 위) — POSITION 의 min/max 모서리를 노드 변환으로 옮겨서 구해요. → (lo, hi) 또는 None"""
    nodes, acc, meshes = g.get("nodes") or [], g.get("accessors") or [], g.get("meshes") or []
    roots = (g.get("scenes") or [{}])[g.get("scene", 0)].get("nodes") if g.get("scenes") else list(range(len(nodes)))
    pts = []

    def walk(i, parent, depth=0):
        if depth > 64 or i >= len(nodes):
            return
        n = nodes[i]
        m = parent @ _mat(n)
        if "mesh" in n and n["mesh"] < len(meshes):
            for pr in meshes[n["mesh"]].get("primitives") or []:
                a = acc[pr.get("attributes", {}).get("POSITION", -1)] if 0 <= pr.get("attributes", {}).get("POSITION", -1) < len(acc) else None
                if not a or "min" not in a or "max" not in a:
                    continue
                lo, hi = a["min"], a["max"]
                for c in range(8):
                    p = np.array([hi[0] if c & 1 else lo[0], hi[1] if c & 2 else lo[1], hi[2] if c & 4 else lo[2], 1.0])
                    pts.append((m @ p)[:3])
        for ch in n.get("children") or []:
            walk(ch, m, depth + 1)
    for r in roots or []:
        walk(r, np.eye(4))
    if not pts:
        return None
    P = np.array(pts)
    return P.min(axis=0), P.max(axis=0)


def _shift_tex(o, off):
    """재질 안의 텍스처 참조({index: n, texCoord..})를 모두 옮겨요(확장 안의 것도)."""
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, dict) and "index" in v and isinstance(v["index"], int) and (k.endswith("Texture") or "texCoord" in v):
                v["index"] += off
            _shift_tex(v, off)
    elif isinstance(o, list):
        for v in o:
            _shift_tex(v, off)


def merge(items):
    """items: [{"glb": bytes, "name": str, "pos": [x, y, z](Blender 좌표, 바닥 가운데), "height": m}] → (GLB bytes, 정보 목록)"""
    G = {"asset": {"version": "2.0", "generator": "LocalAI Studio scene"}, "scene": 0, "scenes": [{"name": "Scene", "nodes": []}]}
    for k in ARRAYS:
        G[k] = []
    B = bytearray()
    used, req = set(), set()
    info = []
    for it in items:
        g, b = read(it["glb"])
        box = bounds(g)
        off = {k: len(G[k]) for k in ARRAYS}
        boff = len(B)
        B += b
        B += b"\0" * (-len(B) % 4)
        for bv in g.get("bufferViews") or []:
            bv = dict(bv)
            bv["buffer"] = 0
            bv["byteOffset"] = bv.get("byteOffset", 0) + boff
            G["bufferViews"].append(bv)
        for a in g.get("accessors") or []:
            a = json.loads(json.dumps(a))
            if "bufferView" in a:
                a["bufferView"] += off["bufferViews"]
            for part in ("indices", "values"):
                if "sparse" in a and "bufferView" in a["sparse"].get(part, {}):
                    a["sparse"][part]["bufferView"] += off["bufferViews"]
            G["accessors"].append(a)
        for im in g.get("images") or []:
            im = dict(im)
            if "bufferView" in im:
                im["bufferView"] += off["bufferViews"]
            G["images"].append(im)
        G["samplers"] += [dict(s) for s in g.get("samplers") or []]
        for t in g.get("textures") or []:
            t = json.loads(json.dumps(t))
            if "sampler" in t:
                t["sampler"] += off["samplers"]
            if "source" in t:
                t["source"] += off["images"]
            for ext in (t.get("extensions") or {}).values():
                if isinstance(ext, dict) and "source" in ext:
                    ext["source"] += off["images"]
            G["textures"].append(t)
        for m in g.get("materials") or []:
            m = json.loads(json.dumps(m))
            _shift_tex(m, off["textures"])
            G["materials"].append(m)
        for me in g.get("meshes") or []:
            me = json.loads(json.dumps(me))
            for pr in me.get("primitives") or []:
                pr["attributes"] = {k: v + off["accessors"] for k, v in pr.get("attributes", {}).items()}
                if "indices" in pr:
                    pr["indices"] += off["accessors"]
                if "material" in pr:
                    pr["material"] += off["materials"]
                if "targets" in pr:
                    pr["targets"] = [{k: v + off["accessors"] for k, v in t.items()} for t in pr["targets"]]
            G["meshes"].append(me)
        G["cameras"] += [dict(c) for c in g.get("cameras") or []]
        for n in g.get("nodes") or []:
            n = json.loads(json.dumps(n))
            for k, a in (("mesh", "meshes"), ("skin", "skins"), ("camera", "cameras")):
                if k in n:
                    n[k] += off[a]
            if "children" in n:
                n["children"] = [c + off["nodes"] for c in n["children"]]
            G["nodes"].append(n)
        for s in g.get("skins") or []:
            s = json.loads(json.dumps(s))
            if "inverseBindMatrices" in s:
                s["inverseBindMatrices"] += off["accessors"]
            s["joints"] = [j + off["nodes"] for j in s.get("joints") or []]
            if "skeleton" in s:
                s["skeleton"] += off["nodes"]
            G["skins"].append(s)
        for an in g.get("animations") or []:
            an = json.loads(json.dumps(an))
            for sm in an.get("samplers") or []:
                sm["input"] += off["accessors"]
                sm["output"] += off["accessors"]
            for ch in an.get("channels") or []:
                if "node" in ch.get("target", {}):
                    ch["target"]["node"] += off["nodes"]
            G["animations"].append(an)
        used |= set(g.get("extensionsUsed") or [])
        req |= set(g.get("extensionsRequired") or [])
        sc = g.get("scenes") or []
        roots = sc[g.get("scene", 0)].get("nodes", []) if sc else [i for i in range(len(g.get("nodes") or []))
                                                                   if not any(i in (n.get("children") or []) for n in g["nodes"])]
        # 크기·자리: 물체의 바닥 가운데 → pos, 키 → height
        x, y, z = (float(v) for v in it.get("pos", (0, 0, 0)))
        tgt = np.array([x, z, -y])                    # Blender(z 위) → glTF(y 위)
        s = 1.0
        if box is not None:
            lo, hi = box
            h = float(hi[1] - lo[1])
            if it.get("height") and h > 1e-9:
                s = float(it["height"]) / h
            base = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
            t = tgt - s * base
            size = ((hi - lo) * s).tolist()
        else:
            t, size = tgt, [0, 0, 0]
        G["nodes"].append({"name": str(it.get("name") or f"object_{len(info) + 1}"), "children": [r + off["nodes"] for r in roots],
                           "translation": [round(float(v), 6) for v in t], "scale": [round(s, 6)] * 3})
        G["scenes"][0]["nodes"].append(len(G["nodes"]) - 1)
        info.append({"name": G["nodes"][-1]["name"], "scale": round(s, 6), "size_m": [round(size[0], 3), round(size[2], 3), round(size[1], 3)],
                     "tris": sum(_tris(g, p) for me in g.get("meshes") or [] for p in me.get("primitives") or [])})
    if B:
        G["buffers"] = [{"byteLength": len(B)}]
    for k in ARRAYS:
        if not G[k]:
            del G[k]
    if used:
        G["extensionsUsed"] = sorted(used)
    if req:
        G["extensionsRequired"] = sorted(req)
    return write(G, B), info


def _tris(g, p):
    acc = g.get("accessors") or []
    if p.get("mode", 4) != 4:
        return 0
    if "indices" in p and p["indices"] < len(acc):
        return acc[p["indices"]].get("count", 0) // 3
    pos = p.get("attributes", {}).get("POSITION")
    return acc[pos].get("count", 0) // 3 if pos is not None and pos < len(acc) else 0


def layout(size, depth, objs, fov=50.0):
    """사진 한 장에서 물체 자리 어림(AI 깊이 + 사진 속 위치·크기). 상대값이에요.
    size: (W, H), depth: (H, W) 0~1(1 = 가까움), objs: [(n, box(x0, y0, x1, y1), mask bool(H, W))]
    → [{"n", "pos": [x, y, z](Blender, 바닥 가운데), "height", "dist", "near"}] — 가장 낮은 물체의 바닥이 z=0"""
    W, H = size
    t = math.tan(math.radians(fov / 2))
    vt = t * H / max(W, 1)
    out = []
    for n, box, mk in objs:
        near = float(np.median(depth[mk])) if mk is not None and mk.any() else 0.5
        dist = 2.0 + 8.0 * (1.0 - near)                 # 가까움 2m ~ 멀리 10m
        x0, y0, x1, y1 = box
        cx = ((x0 + x1 + 1) / 2 / W - 0.5) * 2 * dist * t
        h = max(0.05, (y1 - y0 + 1) / H * 2 * dist * vt)
        zb = (0.5 - (y1 + 1) / H) * 2 * dist * vt
        out.append({"n": n, "pos": [round(cx, 4), round(dist, 4), round(zb, 4)], "height": round(h, 4), "dist": round(dist, 3), "near": round(near, 3)})
    if out:
        g = min(o["pos"][2] for o in out)
        for o in out:
            o["pos"][2] = round(o["pos"][2] - g, 4)
    return out
