"""테스트용 가짜 사람 그물망(정점 구름): 키 1.8, -Y 를 보고, 왼쪽 = +X. pose: T / A / down / robe"""
import numpy as np

def box(rng, c, s, n):
    return rng.uniform(-0.5, 0.5, (n, 3)) * np.array(s) + np.array(c)

def seg(rng, a, b, r, n):
    a, b = np.array(a, float), np.array(b, float); t = rng.uniform(0, 1, (n, 1))
    return a + t * (b - a) + rng.normal(0, r / 2, (n, 3))

def person(pose="T", seed=0):
    rng = np.random.default_rng(seed); P = []
    P.append(box(rng, (0, 0, 1.15), (0.36, 0.2, 0.55), 4000))        # 몸통 0.875~1.425
    P.append(box(rng, (0, 0, 1.47), (0.1, 0.1, 0.08), 300))          # 목
    P.append(box(rng, (0, -0.01, 1.64), (0.2, 0.22, 0.3), 1500))     # 머리 1.49~1.79
    if pose == "robe":
        P.append(box(rng, (0, 0, 0.45), (0.5, 0.3, 0.86), 5000))
    else:
        for sx in (1, -1):
            P.append(seg(rng, (sx * 0.12, 0, 0.88), (sx * 0.12, -0.01, 0.5), 0.05, 1500))
            P.append(seg(rng, (sx * 0.12, -0.01, 0.5), (sx * 0.12, 0, 0.08), 0.045, 1500))
            P.append(box(rng, (sx * 0.12, -0.06, 0.04), (0.1, 0.26, 0.08), 600))
    for sx in (1, -1):
        sh = np.array([sx * 0.2, 0, 1.4])
        d = {"T": (sx, 0, 0), "A": (sx * 0.75, 0, -0.66), "down": (sx * 0.12, 0, -1)}[("T" if pose == "robe" else pose)]
        tip = sh + np.array(d) / np.linalg.norm(d) * 0.78
        P.append(seg(rng, sh, tip, 0.06, 2000))
    return np.concatenate(P)
