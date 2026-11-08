# -*- coding: utf-8 -*-
"""사람형 캐릭터 그물망(정점)에서 관절 위치를 어림해요 — numpy 만 써요(Blender 안에서도, 허브 테스트에서도 같은 코드).
좌표: Blender 기준 Z 위, 캐릭터는 -Y 쪽(앞)을 봐요, 캐릭터의 왼쪽 = +X. 바닥 z=0, 가운데 x=y=0 으로 맞춘 정점을 넣어요.
뼈 이름은 Mixamo 와 같아서 Unity·Unreal 의 사람형(Humanoid) 자동 매핑, Mixamo 애니메이션 리타깃에 그대로 써요."""
import numpy as np

BONES = [  # (뼈, 머리 관절, 꼬리 관절, 부모, 이어 붙이기)
    ("Hips", "hips", "spine", None, False),
    ("Spine", "spine", "spine1", "Hips", True),
    ("Spine1", "spine1", "spine2", "Spine", True),
    ("Spine2", "spine2", "neck", "Spine1", True),
    ("Neck", "neck", "head", "Spine2", True),
    ("Head", "head", "headtop", "Neck", True),
]
for _s, _n in (("L", "Left"), ("R", "Right")):
    BONES += [
        (f"{_n}Shoulder", f"clav{_s}", f"arm{_s}", "Spine2", False),
        (f"{_n}Arm", f"arm{_s}", f"elbow{_s}", f"{_n}Shoulder", True),
        (f"{_n}ForeArm", f"elbow{_s}", f"wrist{_s}", f"{_n}Arm", True),
        (f"{_n}Hand", f"wrist{_s}", f"hand{_s}", f"{_n}ForeArm", True),
        (f"{_n}UpLeg", f"upleg{_s}", f"knee{_s}", "Hips", False),
        (f"{_n}Leg", f"knee{_s}", f"ankle{_s}", f"{_n}UpLeg", True),
        (f"{_n}Foot", f"ankle{_s}", f"toe{_s}", f"{_n}Leg", True),
        (f"{_n}ToeBase", f"toe{_s}", f"toetip{_s}", f"{_n}Foot", True),
    ]


def _runs(xs, cell, lo, hi):
    """x 값들을 칸으로 나눠 이어진 덩어리 → [(시작 x, 끝 x, 개수)]. 빈칸이 2칸 이상 이어져야 나눠요(1칸 구멍은 이어 봐요)."""
    if len(xs) == 0:
        return []
    n = max(1, int(np.ceil((hi - lo) / cell)))
    h = np.bincount(np.clip(((np.asarray(xs) - lo) / cell).astype(int), 0, n - 1), minlength=n)
    occ = [i for i in range(n) if h[i] >= max(1, len(xs) * 0.004)]     # 몇 개 안 되는 튄 점은 빈칸으로
    if not occ:
        return []
    out, start, prev = [], occ[0], occ[0]
    for i in occ[1:] + [None]:
        if i is None or i - prev > 2:
            out.append((lo + start * cell, lo + (prev + 1) * cell, int(h[start:prev + 1].sum())))
            start = i
        prev = i if i is not None else prev
    return out


def fit(v):
    """v: (N, 3) 정점. → {"joints": {이름: [x, y, z]}, "pose": "T"|"A"|"down", "warn": [...], "legs": bool}"""
    v = np.asarray(v, dtype=np.float64)
    if v.ndim != 2 or v.shape[0] < 50:
        raise ValueError("정점이 너무 적어요.")
    H = float(v[:, 2].max() - v[:, 2].min())
    if H <= 1e-6:
        raise ValueError("높이가 없는 그물망이에요.")
    v = v - np.array([0.0, 0.0, v[:, 2].min()])
    xlo, xhi = float(v[:, 0].min()), float(v[:, 0].max())
    cell = H / 90
    warn = []

    def band(z0, z1):
        return v[(v[:, 2] >= z0) & (v[:, 2] < z1)]

    def runs_at(z, t=0.012):
        b = band(z - t * H, z + t * H)
        return b, _runs(b[:, 0], cell, xlo, xhi)

    # 1) 다리: 아래에서 위로 올라가며, 가운데(x=0) 양쪽에 덩어리가 나뉘어 있는 동안이 다리
    crotch, legs_ok = None, False
    for z in np.arange(0.06, 0.62, 0.01) * H:
        _, rs = runs_at(z)
        mid = [r for r in rs if r[0] < 0 < r[1]]
        left = [r for r in rs if r[0] >= 0]
        right = [r for r in rs if r[1] <= 0]
        if mid or not left or not right:
            if z > 0.2 * H and legs_ok:
                crotch = z
                break
            if z > 0.2 * H:
                break
            continue
        legs_ok = True
    if crotch is None or not (0.3 * H <= crotch <= 0.6 * H):
        crotch = 0.47 * H
        warn.append("다리가 붙어 있거나(치마·로브 등) 잘 나뉘지 않아 다리 뼈대를 대략 넣었어요.")
        legs_ok = False

    def leg_center(z, side):
        b, rs = runs_at(z, 0.02)
        rs = [r for r in rs if (r[0] >= 0 if side > 0 else r[1] <= 0)]
        if not rs or not legs_ok:
            return None
        r = min(rs, key=lambda r: abs((r[0] + r[1]) / 2))           # 가운데에 가장 가까운 덩어리(팔이 아닌 다리)
        m = b[(b[:, 0] >= r[0]) & (b[:, 0] <= r[1])]
        return m.mean(axis=0) if len(m) else None

    def torso(z):
        b, rs = runs_at(z, 0.015)
        r = next((r for r in rs if r[0] <= 0 <= r[1]), None)
        if r is None:
            return np.array([0.0, float(np.median(v[:, 1])), z]), 0.08 * H
        m = b[(b[:, 0] >= r[0]) & (b[:, 0] <= r[1])]
        c = m.mean(axis=0) if len(m) else np.array([0.0, 0.0, z])
        return np.array([0.0, c[1], z]), max(0.03 * H, min(abs(r[0]), abs(r[1])))

    up = H - crotch
    zs = {"hips": crotch + 0.05 * up, "neck": crotch + 0.67 * up, "head": crotch + 0.75 * up, "shoulder": crotch + 0.64 * up}
    J = {}
    J["hips"], _ = torso(zs["hips"])
    for i, k in enumerate(("spine", "spine1", "spine2")):
        J[k], _ = torso(zs["hips"] + (zs["neck"] - zs["hips"]) * (0.22 + 0.26 * i))
    J["neck"], _ = torso(zs["neck"])
    J["head"], _ = torso(zs["head"])
    J["headtop"] = np.array([0.0, J["head"][1], H])
    _, half = torso(crotch + 0.40 * up)                                # 가슴 아래 높이 몸통 반폭(T자 팔 높이는 피해요)

    # 2) 팔: 위쪽 몸에서 x 가 가장 큰(작은) 점 = 손끝
    upper = v[(v[:, 2] > crotch) & (v[:, 2] < zs["head"])]
    tips = {}
    for s, sg in (("L", 1), ("R", -1)):
        side = upper[upper[:, 0] * sg > half * 1.15]
        tips[s] = side[np.argmax(side[:, 0] * sg)] if len(side) else None
    # 자세: 어깨에서 손끝까지가 수평에서 얼마나 내려갔는지(두 팔 평균)
    angs = []
    for s, sg in (("L", 1), ("R", -1)):
        t = tips[s]
        if t is not None:
            dx, dz = abs(t[0]) - half, zs["shoulder"] - t[2]
            angs.append(np.degrees(np.arctan2(dz, max(dx, 1e-6))) if dx > 0.05 * H else 90.0)
    ang = float(np.mean(angs)) if angs else 90.0
    pose = "T" if ang < 25 else "A" if ang < 62 else "down"
    if pose == "down":
        warn.append("팔이 몸에 붙어 있어 팔·몸통 가중치가 섞일 수 있어요. 3D 만들기의 [T자 자세로 바꾸기]로 다시 만들면 잘 맞아요.")
    sz = zs["shoulder"]
    if pose == "T":                                                    # T자면 팔 높이 = 어깨 높이로 보정
        arm_pts = upper[np.abs(upper[:, 0]) > half * 1.6]
        if len(arm_pts):
            sz = float(np.clip(np.median(arm_pts[:, 2]), zs["shoulder"] - 0.06 * H, zs["shoulder"] + 0.06 * H))
    for s, sg in (("L", 1), ("R", -1)):
        c, _ = torso(sz)
        arm = np.array([sg * half * 0.95, c[1], sz])
        J[f"clav{s}"] = np.array([sg * 0.025 * H, c[1], sz + 0.005 * H])
        J[f"arm{s}"] = arm
        tip = tips[s]
        if tip is None or pose == "down" and abs(tip[0]) < half * 1.3:
            tip = arm + np.array([sg * 0.06 * H, 0.0, -0.40 * H])         # 팔을 못 찾으면 옆으로 내린 팔로 어림
        wrist = arm + (tip - arm) * 0.78
        J[f"elbow{s}"] = arm + (wrist - arm) * 0.55 + np.array([0.0, 0.012 * H, 0.0])
        J[f"wrist{s}"] = wrist
        J[f"hand{s}"] = tip

    # 3) 다리 관절
    for s, sg in (("L", 1), ("R", -1)):
        def at(z, dx):
            c = leg_center(z, sg)
            return np.array([sg * dx * H, J["hips"][1], z]) if c is None else np.array([c[0], c[1], z])
        J[f"upleg{s}"] = at(crotch - 0.02 * H, 0.09)
        J[f"upleg{s}"][2] = zs["hips"] - 0.02 * H
        knee = at(crotch * 0.56, 0.085)
        J[f"knee{s}"] = knee + np.array([0.0, -0.012 * H, 0.0])
        ankle = at(max(crotch * 0.11, 0.035 * H), 0.085)
        J[f"ankle{s}"] = ankle
        foot = v[(v[:, 2] < 0.06 * H) & (v[:, 0] * sg > 0)]
        if legs_ok and len(foot):
            near = foot[np.abs(foot[:, 0] - ankle[0]) < 0.08 * H]
            foot = near if len(near) else foot
            tipp = foot[np.argmin(foot[:, 1])]                         # 가장 앞(-Y) 점 = 발끝
            toetip = np.array([ankle[0], tipp[1], 0.015 * H])
        else:
            toetip = np.array([ankle[0], ankle[1] - 0.12 * H, 0.015 * H])
        if toetip[1] > ankle[1] - 0.04 * H:
            toetip[1] = ankle[1] - 0.08 * H
        J[f"toe{s}"] = ankle + (toetip - ankle) * 0.65
        J[f"toe{s}"][2] = 0.02 * H
        J[f"toetip{s}"] = toetip
    return {"joints": {k: [round(float(x), 6) for x in p] for k, p in J.items()}, "pose": pose, "warn": warn, "legs": legs_ok,
            "height": H}


def nearest_bone(points, segs):
    """각 점에서 가장 가까운 뼈(선분) 번호. points (N,3), segs [(머리, 꼬리)]"""
    P = np.asarray(points, dtype=np.float64)
    best, bi = np.full(len(P), np.inf), np.zeros(len(P), dtype=int)
    for i, (a, b) in enumerate(segs):
        a, b = np.asarray(a, float), np.asarray(b, float)
        ab = b - a
        t = np.clip(((P - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
        d = np.linalg.norm(P - (a + t[:, None] * ab), axis=1)
        m = d < best
        best[m], bi[m] = d[m], i
    return bi
