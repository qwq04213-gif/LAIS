"""메시 품질 검사(인체 전용, 독립 검사기). 메시를 고치지 않고 '재기만' 해요 — 작은 조각(손가락·머리카락)을 지우지 않아요.

검사: 꼭짓점·면 수, 떨어진 조각, 열린 가장자리·구멍, 면 방향·노멀, 퇴화 삼각형,
      앞 실루엣과 사진의 겹침, 팔·다리 누락, 손·발이 몸에 붙었는지, 얼굴 크기·위치, 목과 몸의 연결,
      앞·45도·옆·뒤 그림.
문제마다 '어느 단계에서 생겼는지'(stage)와 까닭을 적어요."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from . import contracts as K
from . import texture_project as T

SIL = 512            # 실루엣 비교 크기
MISSING = 0.6        # 사진 속 부위를 3D 가 이 비율 미만으로 덮으면 '없음'
CONF = 0.2           # 관절점 점수가 이보다 낮으면 그 부위는 판단하지 않아요

# 부위: (이름, 화면 말, BODY_25 관절 a, b, 종류)
LIMBS = (("l_upper_arm", "왼팔 위", 5, 6, "arm"), ("l_forearm", "왼팔 아래", 6, 7, "arm"), ("r_upper_arm", "오른팔 위", 2, 3, "arm"), ("r_forearm", "오른팔 아래", 3, 4, "arm"),
         ("l_thigh", "왼다리 위", 12, 13, "leg"), ("l_shin", "왼다리 아래", 13, 14, "leg"), ("r_thigh", "오른다리 위", 9, 10, "leg"), ("r_shin", "오른다리 아래", 10, 11, "leg"))


def components(F, n):
    """꼭짓점마다 조각 번호(0…). 면으로 이어진 꼭짓점은 같은 번호."""
    lab = np.arange(n, dtype=np.int64)
    if len(F):
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]]], 0).astype(np.int64)
        try:
            from scipy.sparse import coo_matrix
            from scipy.sparse.csgraph import connected_components
            g = coo_matrix((np.ones(len(e), np.int8), (e[:, 0], e[:, 1])), shape=(n, n))
            return connected_components(g, directed=False)[1].astype(np.int64)
        except ImportError:
            pass
        for _ in range(10000):
            m = np.minimum(lab[e[:, 0]], lab[e[:, 1]])
            new = lab.copy()
            np.minimum.at(new, lab[e[:, 0]], m)
            np.minimum.at(new, lab[e[:, 1]], m)
            np.minimum.at(new, e[:, 0], m)
            np.minimum.at(new, e[:, 1], m)
            while True:
                nn = new[new]
                if (nn == new).all():
                    break
                new = nn
            if (new == lab).all():
                break
            lab = new
    return np.unique(lab, return_inverse=True)[1].astype(np.int64)


def topology(V, F):
    """조각·열린 가장자리·구멍·겹친 변·퇴화 삼각형·면 방향."""
    n = len(V)
    out = {"vertices": int(n), "faces": int(len(F))}
    if not len(F):
        return {**out, "empty": True}
    lab = components(F, n)
    used = np.zeros(n, bool)
    used[F.reshape(-1)] = True
    flab = lab[F[:, 0]]
    ncomp = int(lab[used].max()) + 1 if used.any() else 0
    P = V.astype(np.float64)
    cr = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    area = np.linalg.norm(cr, axis=1) / 2
    vol6 = np.einsum("ij,ij->i", P[F[:, 0]], np.cross(P[F[:, 1]], P[F[:, 2]]))
    ids, inv = np.unique(flab, return_inverse=True)
    c_area = np.bincount(inv, area)
    c_vol = np.bincount(inv, vol6) / 6
    c_faces = np.bincount(inv)
    c_ymin = np.full(len(ids), np.inf)
    c_ymax = np.full(len(ids), -np.inf)
    fy = P[F, 1]
    np.minimum.at(c_ymin, inv, fy.min(1))
    np.maximum.at(c_ymax, inv, fy.max(1))
    y0, y1 = float(P[used, 1].min()), float(P[used, 1].max())
    hgt = max(1e-9, y1 - y0)
    order = np.argsort(-c_area)
    total = max(1e-12, c_area.sum())
    comps = [{"faces": int(c_faces[i]), "area_ratio": round(float(c_area[i] / total), 5), "y_from": round(float((c_ymin[i] - y0) / hgt), 3),
              "y_to": round(float((c_ymax[i] - y0) / hgt), 3), "inverted": bool(c_vol[i] < 0)} for i in order[:12]]
    # 변: 한 번만 쓰인 변 = 열린 가장자리, 3번 이상 = 겹친 변, 같은 방향으로 두 번 = 이웃 면의 방향이 서로 반대
    de = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 0).astype(np.int64)
    key = np.minimum(de[:, 0], de[:, 1]) * n + np.maximum(de[:, 0], de[:, 1])
    uk, uinv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    bmask = cnt[uinv] == 1
    bedges = de[bmask]
    dkey = de[:, 0] * n + de[:, 1]
    same_dir = int(len(dkey) - len(np.unique(dkey)))
    holes = []
    if len(bedges):
        bl = components(bedges[:, [0, 1, 1]].astype(np.int32), n)
        bid, binv = np.unique(bl[bedges[:, 0]], return_inverse=True)
        elen = np.linalg.norm(P[bedges[:, 0]] - P[bedges[:, 1]], axis=1)
        per = np.bincount(binv, elen)
        cy = np.bincount(binv, P[bedges[:, 0], 1]) / np.bincount(binv)
        for i in np.argsort(-per)[:12]:
            holes.append({"perimeter_ratio": round(float(per[i] / hgt), 4), "edges": int((binv == i).sum()), "y": round(float((cy[i] - y0) / hgt), 3)})
    dup = (F[:, 0] == F[:, 1]) | (F[:, 1] == F[:, 2]) | (F[:, 0] == F[:, 2])
    nrm = np.zeros((n, 3))
    for k in range(3):
        np.add.at(nrm, F[:, k], cr)
    zero_n = int((np.linalg.norm(nrm[used], axis=1) < 1e-20).sum())
    out.update({"components": ncomp, "component_list": comps, "largest_area_ratio": comps[0]["area_ratio"] if comps else 0.0,
                "boundary_edges": int(bmask.sum()), "holes": len(np.unique(bl[bedges[:, 0]])) if len(bedges) else 0, "hole_list": holes,
                "big_holes": int(sum(1 for h in holes if h["perimeter_ratio"] > 0.05)),
                "nonmanifold_edges": int((cnt > 2).sum()), "degenerate_faces": int((dup | (area < 1e-14)).sum()),
                "flipped_pairs": same_dir, "inverted": bool(c_vol[order[0]] < 0), "inverted_components": int((c_vol < 0).sum()),
                "zero_normals": zero_n, "unused_vertices": int((~used).sum()), "watertight": bool(bmask.sum() == 0 and (cnt > 2).sum() == 0),
                "bbox": [[round(float(v), 4) for v in P[used].min(0)], [round(float(v), 4) for v in P[used].max(0)]]})
    return out


def _capsule(shape, a, b, r):
    """선분 a-b 둘레 r 화소 안인 곳(불 마스크)."""
    h, w = shape
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    d = np.array([b[0] - a[0], b[1] - a[1]], np.float32)
    L2 = max(1e-6, float(d @ d))
    t = np.clip(((xx - a[0]) * d[0] + (yy - a[1]) * d[1]) / L2, 0, 1)
    return (xx - a[0] - t * d[0]) ** 2 + (yy - a[1] - t * d[1]) ** 2 <= r * r


def _cover(region, sil):
    n = int(region.sum())
    return (None, 0) if n < 12 else (round(float((region & sil).sum() / n), 3), n)


def body_parts(photo_mask, sil, pose, smpl_sil=None):
    """사진 속 부위(관절점 기준)를 3D 실루엣이 덮는 비율. photo_mask·sil: (S,S) 불. pose: preprocess.load_openpose 결과(좌표는 1024 기준)."""
    S = photo_mask.shape[0]
    k = S / 1024.0
    B = pose["body"].copy()
    B[:, :2] *= k
    ok = lambda i: B[i, 2] >= CONF
    sh = float(np.linalg.norm(B[2, :2] - B[5, :2])) if ok(2) and ok(5) else S * 0.18
    parts = {}

    def put(name, ko, region, kind, known=True):
        if not known:
            parts[name] = {"ko": ko, "kind": kind, "known": False}
            return
        c, n = _cover(region & photo_mask, sil)
        ring = region & ~photo_mask
        extra = round(float((ring & sil).sum() / max(1, ring.sum())), 3) if ring.sum() >= 12 else 0.0
        e = {"ko": ko, "kind": kind, "known": c is not None, "cover": c, "px": n, "extra": extra, "missing": c is not None and c < MISSING}
        if smpl_sil is not None and c is not None:
            e["smplx_cover"] = _cover(region & photo_mask, smpl_sil)[0]
        parts[name] = e

    for name, ko, a, b, kind in LIMBS:
        put(name, ko, _capsule((S, S), B[a, :2], B[b, :2], sh * (0.16 if kind == "arm" else 0.22)) if ok(a) and ok(b) else None, kind, ok(a) and ok(b))
    for side, ko, wr, el, hk in (("l", "왼손", 7, 6, "lhand"), ("r", "오른손", 4, 3, "rhand")):
        H = pose[hk]
        good = H[:, 2] >= CONF
        if good.sum() >= 6:
            c = H[good, :2].mean(0) * k
            rad = max(sh * 0.14, float(np.linalg.norm(H[good, :2] * k - c, axis=1).max()))
            reg, known = _capsule((S, S), c, c, rad * 1.15), True
        elif ok(wr) and ok(el):
            d = B[wr, :2] - B[el, :2]
            reg, known = _capsule((S, S), B[wr, :2], B[wr, :2] + d * 0.35, sh * 0.16), True
        else:
            reg, known = None, False
        put(side + "_hand", ko, reg, "hand", known)
    for side, ko, an, toe, heel in (("l", "왼발", 14, 19, 21), ("r", "오른발", 11, 22, 24)):
        if ok(an):
            b = B[toe, :2] if ok(toe) else B[an, :2] + np.array([0, sh * 0.25])
            a = B[heel, :2] if ok(heel) else B[an, :2]
            put(side + "_foot", ko, _capsule((S, S), a, b, sh * 0.2), "foot")
        else:
            put(side + "_foot", ko, None, "foot", False)
    return parts


def legs_merged(photo_mask, sil, pose):
    """사진에서는 두 다리 사이가 비어 있는데 3D 에서는 메워졌는지(다리·발이 붙음). None = 판단 못 함."""
    S = photo_mask.shape[0]
    B = pose["body"].copy()
    B[:, :2] *= S / 1024.0
    if min(B[i, 2] for i in (10, 11, 13, 14)) < CONF:
        return None
    reg = _capsule((S, S), (B[10, :2] + B[13, :2]) / 2, (B[11, :2] + B[14, :2]) / 2, max(2.0, abs(B[11, 0] - B[14, 0]) * 0.18))
    gap = reg & ~photo_mask
    if gap.sum() < 30 or gap.sum() < reg.sum() * 0.5:
        return None                                    # 사진에서도 다리가 붙어 있어요(긴 치마 등)
    return {"gap_px": int(gap.sum()), "filled": round(float((gap & sil).sum() / gap.sum()), 3)}


def face_check(photo_mask, sil, pose, obs_img=None):
    S = photo_mask.shape[0]
    f = pose["face"]
    g = f[:, 2] >= CONF
    if g.sum() < 20:
        return {"known": False}
    p = f[g, :2] * (S / 1024.0)
    x0, y0, x1, y1 = p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()
    box = np.zeros((S, S), bool)
    box[max(0, int(y0)):int(y1) + 1, max(0, int(x0)):int(x1) + 1] = True
    cov = _cover(box & photo_mask, sil)[0]
    rows = lambda m: np.where(m.any(1))[0]
    pr, sr = rows(photo_mask), rows(sil)
    body_h = float(pr.max() - pr.min() + 1) if len(pr) else S
    out = {"known": True, "box": [round(float(v) / S, 4) for v in (x0, y0, x1, y1)], "height_ratio": round(float((y1 - y0) / body_h), 4),
           "cover": cov, "head_top_diff": round(float((sr.min() - pr.min()) / body_h), 4) if len(pr) and len(sr) else None}
    if obs_img is not None and box.any():
        out["photo_ratio"] = round(float(obs_img[box & sil].mean()) if (box & sil).any() else 0.0, 3)
    out["ok"] = bool(cov is not None and cov >= 0.9 and (out["head_top_diff"] is None or abs(out["head_top_diff"]) < 0.04))
    return out


def neck_check(V, F, photo_mask, sil, pose, lab=None):
    """목 높이에서 실루엣 폭(사진 대비)과, 머리와 몸통이 한 조각으로 이어졌는지."""
    S = photo_mask.shape[0]
    B = pose["body"]
    if B[1, 2] < CONF or B[0, 2] < CONF:
        return {"known": False}
    yn = (B[1, 1] * 0.7 + B[0, 1] * 0.3) * (S / 1024.0)
    r = int(np.clip(round(yn), 0, S - 1))
    pw, sw = int(photo_mask[r].sum()), int(sil[r].sum())
    out = {"known": True, "y": round(r / S, 4), "photo_width": pw, "mesh_width": sw, "width_ratio": round(sw / pw, 3) if pw else None}
    y3 = 1 - 2 * yn / S                                 # 목 높이의 3D y
    lab = components(F, len(V)) if lab is None else lab
    head, torso = V[:, 1] > y3 + 0.02, (V[:, 1] < y3 - 0.02) & (V[:, 1] > y3 - 0.5)
    if head.sum() > 10 and torso.sum() > 10:
        hc = np.bincount(lab[head]).argmax()
        out["connected"] = bool(hc == np.bincount(lab[torso]).argmax())
        out["head_in_main"] = round(float((lab[head] == hc).mean()), 3)
    else:
        out["connected"] = None
    out["ok"] = bool(out.get("connected") is not False and (out["width_ratio"] is None or out["width_ratio"] > 0.5))
    return out


def renders(mesh, out_dir, size=768, tint=None):
    """앞·45도·옆·뒤 그림을 저장하고 {이름: 파일 이름} 을 돌려줘요."""
    from .export import vertex_normals
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    N = vertex_normals(mesh.V, mesh.F)
    files = {}
    for vid, _, yaw in K.VIEWS:
        T.render(mesh.V, mesh.F, mesh.C, size, yaw=-yaw, N=N).save(out_dir / f"view_{vid}.png")      # 카메라가 오른쪽으로 돌면 물체는 반대로 돌아요
        files[vid] = f"view_{vid}.png"
    if tint is not None:
        T.render(mesh.V, mesh.F, mesh.C, size, N=N, tint=tint).save(out_dir / "view_front_observed.png")
        files["observed"] = "view_front_observed.png"
    return files


def inspect(mesh, square_rgba=None, pose=None, smplx=None, obs=None):
    """전체 검사. 돌려주는 값: 보고서(dict) — report['problems'] 가 비면 통과."""
    V, F = mesh.V, mesh.F
    rep = {"version": 1, "topology": topology(V, F), "problems": []}
    top = rep["topology"]
    P = rep["problems"]

    def bad(pid, level, text, stage, **kw):
        P.append({"id": pid, "level": level, "text": text, "stage": stage, "stage_ko": K.STAGE_KO.get(stage, stage), **kw})

    if top.get("empty"):
        bad("empty", "bad", "메시에 면이 하나도 없어요.", "geometry")
        rep["pass"] = False
        return rep
    if top["components"] > 1:
        small = [c for c in top["component_list"][1:] if c["area_ratio"] > 0.002]
        bad("pieces", "warn" if small else "info", f"떨어진 조각이 {top['components']}개예요(가장 큰 조각이 겉넓이의 {top['largest_area_ratio'] * 100:.1f}%). 조각은 지우지 않고 그대로 뒀어요.", "geometry")
    if top["big_holes"]:
        ys = ", ".join(f"키의 {h['y'] * 100:.0f}% 높이" for h in top["hole_list"][:4] if h["perimeter_ratio"] > 0.05)
        bad("holes", "warn", f"큰 구멍이 {top['big_holes']}개 있어요({ys}).", "geometry")
    elif top["boundary_edges"]:
        bad("open", "info", f"열린 가장자리가 {top['boundary_edges']}개 있어요(작은 틈).", "geometry")
    if top["inverted"]:
        bad("inverted", "warn", "면 방향이 뒤집혀 있어요(안팎이 바뀜). 게임 엔진에서 안쪽이 보일 수 있어요.", "geometry")
    if top["flipped_pairs"] > max(20, top["faces"] * 0.002):
        bad("winding", "warn", f"이웃한 면끼리 방향이 서로 반대인 곳이 {top['flipped_pairs']}곳 있어요.", "geometry")
    if top["degenerate_faces"] > max(10, top["faces"] * 0.001):
        bad("degenerate", "info", f"넓이가 0 인 면이 {top['degenerate_faces']}개 있어요.", "geometry")
    if top["zero_normals"]:
        bad("normals", "info", f"노멀을 정할 수 없는 꼭짓점이 {top['zero_normals']}개 있어요.", "geometry")

    if square_rgba is not None:
        photo = np.asarray(square_rgba.getchannel("A").resize((SIL, SIL), Image.BILINEAR)) > 127
        sil = T.silhouette(V, F, SIL)
        inter, union = (photo & sil).sum(), (photo | sil).sum()
        rep["silhouette"] = {"iou": round(float(inter / max(1, union)), 4), "photo_px": int(photo.sum()), "mesh_px": int(sil.sum()),
                             "missing_ratio": round(float((photo & ~sil).sum() / max(1, photo.sum())), 4), "extra_ratio": round(float((sil & ~photo).sum() / max(1, photo.sum())), 4)}
        if rep["silhouette"]["iou"] < 0.85:
            bad("silhouette", "bad" if rep["silhouette"]["iou"] < 0.7 else "warn", f"앞에서 본 윤곽이 사진과 {rep['silhouette']['iou'] * 100:.0f}% 만 겹쳐요(정상 90% 이상).", "geometry")
        if pose is not None:
            ssil = T.silhouette(smplx.V, smplx.F, SIL) if smplx is not None else None
            if ssil is not None:
                rep["smplx_silhouette_iou"] = round(float((photo & ssil).sum() / max(1, (photo | ssil).sum())), 4)
            parts = body_parts(photo, sil, pose, ssil)
            rep["parts"] = parts
            for name, e in parts.items():
                if e.get("missing"):
                    from_fit = e.get("smplx_cover") is not None and e["smplx_cover"] < MISSING
                    bad("missing_" + name, "bad", f"{e['ko']}이(가) 3D 에 거의 없어요(사진 속 그 부위의 {e['cover'] * 100:.0f}% 만 덮음)." +
                        (" 몸 맞추기(SMPL-X)에서 이미 그 부위가 사진과 어긋났어요." if from_fit else " 몸 맞추기는 맞았는데 형태 복원에서 빠졌어요."),
                        "smplx_fit" if from_fit else "geometry", part=name)
                elif e.get("known") and e["kind"] == "hand" and e.get("extra", 0) > 0.45:
                    bad("fused_" + name, "warn", f"{e['ko']}이(가) 몸이나 다른 부위와 붙어 보여요(사진에서 비어 있는 손 둘레의 {e['extra'] * 100:.0f}% 가 3D 로 메워짐).", "geometry", part=name)
            lm = legs_merged(photo, sil, pose)
            rep["legs_gap"] = lm
            if lm and lm["filled"] > 0.5:
                bad("legs_merged", "warn", f"사진에서는 두 다리 사이가 비어 있는데 3D 에서는 {lm['filled'] * 100:.0f}% 가 메워졌어요(다리·발이 붙음).", "geometry")
            obs_img = None
            if obs is not None:
                zb = T.zbuffer(V, F, SIL)
                obs_img = np.zeros((SIL, SIL), np.float32)
                hit = zb["face"] >= 0
                obs_img[hit] = (obs[F[zb["face"][hit]]] * zb["bary"][hit]).sum(1)
            rep["face"] = face_check(photo, sil, pose, obs_img)
            if rep["face"].get("known") and not rep["face"]["ok"]:
                bad("face", "warn", "얼굴 자리의 3D 가 사진과 어긋나요(머리 높이나 얼굴 범위가 달라요).", "geometry")
            rep["neck"] = neck_check(V, F, photo, sil, pose)
            if rep["neck"].get("known") and not rep["neck"]["ok"]:
                bad("neck", "bad" if rep["neck"].get("connected") is False else "warn",
                    "머리와 몸통이 떨어져 있어요." if rep["neck"].get("connected") is False else "목 부분이 사진보다 많이 가늘어요.", "geometry")
    rep["pass"] = not any(p["level"] == "bad" for p in P)
    rep["warnings"] = sum(1 for p in P if p["level"] == "warn")
    return rep


def save(report, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
