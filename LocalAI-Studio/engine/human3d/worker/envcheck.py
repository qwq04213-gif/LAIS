"""설치한 부품을 '실제로 불러와 보는' 검사 — 깔려 있다는 것만으로는 통과시키지 않아요.
설치 스크립트의 마지막 단계와 사전 검사가 함께 써요.   python -m worker.envcheck   →  "@@ENVCHECK {json}" 한 줄, 모두 되면 종료 코드 0.

부품마다 따로 시도하고, 실패하면 오류 글 끝부분과 '어느 꾸러미의 파일에서 났는지'(culprit)를 남겨요.
"numpy.dtype size changed … Expected 96 … got 88" 는 numpy 2 용으로 만든 부품이 numpy 1.x 와 섞였다는 뜻이라 따로 표시해요(abi)."""
import importlib
import json
import re
import sys
import traceback

# (검사 이름, 불러올 모듈, 화면에 보일 이름)
MODULES = (("numpy", "numpy", "numpy"), ("scipy", "scipy.ndimage", "scipy"), ("torch", "torch", "PyTorch"), ("kaolin", "kaolin", "kaolin"),
           ("diffusers", "diffusers", "diffusers"), ("transformers", "transformers", "transformers"), ("smplx", "smplx", "smplx"),
           ("trimesh", "trimesh", "trimesh"), ("cv2", "cv2", "opencv"), ("skimage", "skimage.measure", "scikit-image"), ("h5py", "h5py", "h5py"),
           ("tinyobjloader", "tinyobjloader", "tinyobjloader"), ("yaml", "yaml", "pyyaml"), ("onnxruntime", "onnxruntime", "onnxruntime"),
           ("rtmlib", "rtmlib", "자세 검출기(rtmlib)"), ("accelerate", "accelerate", "accelerate"))
ABI_RX = re.compile(r"numpy\.(dtype|ndarray|ufunc|flatiter|broadcast) size changed|compiled using NumPy 1\.x cannot be run in NumPy 2|numpy\.core\.multiarray failed to import|_ARRAY_API not found", re.I)
FIX = "인체 3D 화면에서 [설치 시작]을 다시 눌러 주세요(부품 판을 다시 맞춰요)."


def culprit_of(tb_text):
    """오류가 난 파일 경로에서 꾸러미 이름을 뽑아요(…/site-packages/<꾸러미>/…). 가장 안쪽(마지막) 것."""
    hit = None
    for m in re.finditer(r'File "([^"]+)"', tb_text):
        parts = m.group(1).replace("\\", "/").split("/")
        for key in ("site-packages", "dist-packages"):
            if key in parts and parts.index(key) + 1 < len(parts):
                hit = parts[parts.index(key) + 1].split(".")[0]
    return hit


def try_import(mod):
    try:
        m = importlib.import_module(mod)
        top = sys.modules.get(mod.split(".")[0], m)
        return {"ok": True, "version": str(getattr(top, "__version__", "ok"))}
    except BaseException as e:  # noqa: BLE001
        tb = traceback.format_exc()
        msg = f"{e.__class__.__name__}: {e}"
        return {"ok": False, "error": msg[:400], "abi": bool(ABI_RX.search(msg)), "culprit": culprit_of(tb), "trace": tb[-1500:]}


def check(mods=MODULES):
    out = {"ok": True, "modules": {}, "failed": [], "abi": False, "culprits": []}
    for key, mod, ko in mods:
        r = try_import(mod)
        r["name"] = ko
        out["modules"][key] = r
        if not r["ok"]:
            out["ok"] = False
            out["failed"].append(key)
            out["abi"] = out["abi"] or r.get("abi", False)
            if r.get("culprit") and r["culprit"] not in out["culprits"]:
                out["culprits"].append(r["culprit"])
    try:
        import numpy
        out["numpy"] = numpy.__version__
    except Exception:  # noqa: BLE001
        out["numpy"] = None
    if not out["ok"]:
        names = ", ".join(out["modules"][k]["name"] for k in out["failed"])
        if out["abi"]:
            out["text"] = f"부품끼리 판이 안 맞아요(numpy {out['numpy']} 와 맞지 않는 부품이 섞였어요): {names} 을(를) 불러오지 못해요." + (f" 문제가 난 곳: {', '.join(out['culprits'])}." if out["culprits"] else "")
        else:
            out["text"] = f"불러오지 못하는 부품이 있어요: {names}."
        out["fix"] = FIX
    else:
        out["text"] = f"부품 {len(mods)}개를 모두 불러왔어요(numpy {out['numpy']})."
    return out


def main():
    r = check()
    for k in r["failed"]:
        m = r["modules"][k]
        print(f"[안 됨] {m['name']}: {m['error']}" + (f"  ← {m['culprit']}" if m.get("culprit") else ""), flush=True)
        print(m["trace"], flush=True)
    print("@@ENVCHECK " + json.dumps({k: v for k, v in r.items() if k != "modules"} | {"modules": {k: {a: b for a, b in v.items() if a != "trace"} for k, v in r["modules"].items()}}, ensure_ascii=False), flush=True)
    sys.exit(0 if r["ok"] else 2)


if __name__ == "__main__":
    main()
