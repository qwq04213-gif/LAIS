"""메시 읽기·쓰기: 엔진 원본(OBJ·PLY, 꼭짓점 색) 읽기 → GLB(꼭짓점 색) 저장. numpy 만 써요.
면을 줄이거나 다시 짜지 않아요 — 엔진이 만든 꼭짓점·면을 그대로 옮겨요."""
import json
import struct
from pathlib import Path

import numpy as np


class Mesh:
    """V: (N,3) float32 · F: (M,3) int32 · C: (N,3) uint8 꼭짓점 색(없으면 None) · obs: (N,) 0~1 사진에서 본 정도(없으면 None)"""

    def __init__(self, V, F, C=None, obs=None):
        self.V = np.ascontiguousarray(V, np.float32).reshape(-1, 3)
        self.F = np.ascontiguousarray(F, np.int32).reshape(-1, 3)
        self.C = None if C is None else np.ascontiguousarray(C, np.uint8).reshape(-1, 3)
        self.obs = None if obs is None else np.ascontiguousarray(obs, np.float32).reshape(-1)
        if len(self.F) and (self.F.min() < 0 or self.F.max() >= len(self.V)):
            raise ValueError("면이 없는 꼭짓점을 가리켜요")
        if self.C is not None and len(self.C) != len(self.V):
            raise ValueError("꼭짓점 색 개수가 꼭짓점 수와 달라요")


def _col8(c):
    c = np.asarray(c, np.float32)
    if c.size and c.max() <= 1.0001:
        c = c * 255.0
    return np.clip(np.rint(c), 0, 255).astype(np.uint8)


def read_obj(path):
    """v x y z [r g b] / f a b c (a/b/c 형식도). 삼각형만(사각형은 둘로 나눠요)."""
    vs, cs, fs = [], [], []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                vs.append((float(p[1]), float(p[2]), float(p[3])))
                if len(p) >= 7:
                    cs.append((float(p[4]), float(p[5]), float(p[6])))
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    fs.append((idx[0], idx[k], idx[k + 1]))
    V = np.array(vs, np.float32).reshape(-1, 3)
    F = np.array(fs, np.int64).reshape(-1, 3)
    F = np.where(F < 0, F + len(V), F - 1).astype(np.int32)
    C = _col8(np.array(cs, np.float32)) if len(cs) == len(vs) and vs else None
    return Mesh(V, F, C)


_PLY_T = {"char": "i1", "uchar": "u1", "int8": "i1", "uint8": "u1", "short": "i2", "ushort": "u2", "int16": "i2", "uint16": "u2",
          "int": "i4", "uint": "u4", "int32": "i4", "uint32": "u4", "float": "f4", "float32": "f4", "double": "f8", "float64": "f8"}


def read_ply(path):
    """PLY(binary_little_endian·ascii). 꼭짓점 x y z [red green blue], 면은 삼각형 목록."""
    data = Path(path).read_bytes()
    end = data.find(b"end_header")
    if not data.startswith(b"ply") or end < 0:
        raise ValueError("PLY 파일이 아니에요")
    head = data[:end].decode("ascii", "replace").splitlines()
    body = data[data.find(b"\n", end) + 1:]
    fmt, elems = "ascii", []
    for ln in head:
        p = ln.split()
        if not p:
            continue
        if p[0] == "format":
            fmt = p[1]
        elif p[0] == "element":
            elems.append([p[1], int(p[2]), []])
        elif p[0] == "property" and elems:
            elems[-1][2].append(p[1:])
    V = C = F = None
    if fmt == "ascii":
        rows = body.decode("ascii", "replace").split("\n")
        at = 0
        for name, n, props in elems:
            part = rows[at:at + n]
            at += n
            if name == "vertex":
                a = np.array([r.split() for r in part], np.float64)
                names = [p[-1] for p in props]
                V = a[:, [names.index(k) for k in "xyz"]]
                if all(k in names for k in ("red", "green", "blue")):
                    C = a[:, [names.index(k) for k in ("red", "green", "blue")]].astype(np.uint8)
            elif name == "face":
                F = np.array([r.split()[1:4] for r in part if r.strip()], np.int32)
    else:
        e = "<" if "little" in fmt else ">"
        at = 0
        for name, n, props in elems:
            if name == "vertex":
                dt = np.dtype([(p[-1], e + _PLY_T[p[0]]) for p in props])
                a = np.frombuffer(body, dt, n, at)
                at += dt.itemsize * n
                V = np.stack([a["x"], a["y"], a["z"]], 1)
                if all(k in a.dtype.names for k in ("red", "green", "blue")):
                    C = np.stack([a["red"], a["green"], a["blue"]], 1)
            elif name == "face":
                lp = props[0]                                # list uchar int vertex_indices
                dt = np.dtype([("n", e + _PLY_T[lp[1]]), ("i", e + _PLY_T[lp[2]], (3,))])
                a = np.frombuffer(body, dt, n, at)
                at += dt.itemsize * n
                if n and not (a["n"] == 3).all():
                    raise ValueError("삼각형이 아닌 면이 있어요")
                F = a["i"]
            else:
                raise ValueError("모르는 PLY 요소: " + name)
    if V is None:
        raise ValueError("PLY 에 꼭짓점이 없어요")
    return Mesh(V, F if F is not None else np.zeros((0, 3), np.int32), None if C is None else _col8(C))


def read_mesh(path):
    path = Path(path)
    return read_ply(path) if path.suffix.lower() == ".ply" else read_obj(path)


def write_ply(path, m):
    props = [("x", "<f4"), ("y", "<f4"), ("z", "<f4")] + ([("red", "u1"), ("green", "u1"), ("blue", "u1")] if m.C is not None else [])
    a = np.zeros(len(m.V), np.dtype(props))
    a["x"], a["y"], a["z"] = m.V[:, 0], m.V[:, 1], m.V[:, 2]
    if m.C is not None:
        a["red"], a["green"], a["blue"] = m.C[:, 0], m.C[:, 1], m.C[:, 2]
    f = np.zeros(len(m.F), np.dtype([("n", "u1"), ("i", "<i4", (3,))]))
    f["n"], f["i"] = 3, m.F
    head = ["ply", "format binary_little_endian 1.0", f"element vertex {len(m.V)}", "property float x", "property float y", "property float z"]
    if m.C is not None:
        head += ["property uchar red", "property uchar green", "property uchar blue"]
    head += [f"element face {len(m.F)}", "property list uchar int vertex_indices", "end_header"]
    Path(path).write_bytes(("\n".join(head) + "\n").encode("ascii") + a.tobytes() + f.tobytes())


def vertex_normals(V, F):
    """면 넓이로 가중한 꼭짓점 노멀(길이 1)."""
    n = np.zeros((len(V), 3), np.float64)
    if len(F):
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]).astype(np.float64)
        for k in range(3):
            np.add.at(n, F[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    return (n / np.where(ln > 1e-20, ln, 1.0)).astype(np.float32)


def write_glb(path, m, name="human", extras=None):
    """GLB 2.0 — POSITION · NORMAL · COLOR_0(꼭짓점 색) · (있으면) _OBSERVED(사진에서 본 정도 0~1).
    좌표는 엔진 그대로(y 위, +z 가 앞 = glTF 기본과 같아요)."""
    V, F = m.V, m.F
    N = vertex_normals(V, F)
    chunks, views, accs = [], [], []

    def add(arr, target, ctype, typ, norm=False, mm=False):
        b = arr.tobytes()
        off = sum(len(c) for c in chunks)
        chunks.append(b + b"\0" * (-len(b) % 4))
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(b), **({"target": target} if target else {})})
        a = {"bufferView": len(views) - 1, "componentType": ctype, "count": len(arr), "type": typ}
        if norm:
            a["normalized"] = True
        if mm:
            a["min"], a["max"] = arr.min(0).tolist(), arr.max(0).tolist()
        accs.append(a)
        return len(accs) - 1

    att = {"POSITION": add(V.astype("<f4"), 34962, 5126, "VEC3", mm=True), "NORMAL": add(N.astype("<f4"), 34962, 5126, "VEC3")}
    if m.C is not None:
        rgba = np.concatenate([m.C, np.full((len(V), 1), 255, np.uint8)], 1)
        att["COLOR_0"] = add(rgba, 34962, 5121, "VEC4", norm=True)
    if m.obs is not None:
        att["_OBSERVED"] = add(m.obs.astype("<f4").reshape(-1, 1), 34962, 5126, "SCALAR")
    idx = add(F.astype("<u4").reshape(-1, 1), 34963, 5125, "SCALAR")
    blob = b"".join(chunks)
    g = {"asset": {"version": "2.0", "generator": "LAIS human3d"}, "scene": 0, "scenes": [{"nodes": [0]}],
         "nodes": [{"mesh": 0, "name": name}],
         "materials": [{"name": name, "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.9}, "doubleSided": True}],
         "meshes": [{"name": name, "primitives": [{"attributes": att, "indices": idx, "material": 0, "mode": 4}]}],
         "buffers": [{"byteLength": len(blob)}], "bufferViews": views, "accessors": accs}
    if extras:
        g["extras"] = extras
    js = json.dumps(g, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(blob)) + struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(blob), b"BIN\0") + blob
    Path(path).write_bytes(out)
    return len(out)


def read_glb_json(path):
    d = Path(path).read_bytes()
    if d[:4] != b"glTF":
        raise ValueError("GLB 파일이 아니에요")
    n = struct.unpack("<I", d[12:16])[0]
    return json.loads(d[20:20 + n].decode("utf-8"))
