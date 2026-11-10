"""nvdiffrast 가 '실제로' 도는지 검사 — 불러오기만이 아니라 CUDA 확장(nvdiffrast.torch)·CUDA 컨텍스트·작은 삼각형 래스터화까지.
설치 스크립트와 사전 검사가 함께 써요.   python -m worker.nvcheck   →  "@@NVCHECK {json}" 한 줄, 통과하면 종료 코드 0.

실패 종류(kind):
  not_installed  nvdiffrast 꾸러미가 없음                         → 설치 문제
  build          꾸러미는 있는데 CUDA 확장을 못 불러옴(컴파일 안 됨) → 설치 문제(CUDA 컴파일러·--no-build-isolation)
  no_torch       PyTorch 를 못 불러옴                              → 설치 문제
  no_cuda        PyTorch 가 그래픽카드를 못 씀                      → CUDA 런타임 문제(드라이버·WSL)
  runtime        컨텍스트 만들기·래스터화가 실패                     → CUDA 런타임 문제
  wrong          돌긴 했는데 결과가 틀림                             → CUDA 런타임 문제"""
import json
import sys

FIX_INSTALL = "인체 3D 화면에서 [설치 시작]을 다시 눌러 주세요(CUDA 12.1 컴파일러를 먼저 준비한 뒤 nvdiffrast 를 다시 만들어요)."
FIX_RUNTIME = "윈도우의 NVIDIA 드라이버를 최신으로 올리고, PowerShell 에서 wsl --shutdown 으로 WSL 을 다시 시작한 뒤 [다시 확인]을 눌러 주세요."
BUILD_WORDS = ("nvcc", "ninja", "compil", "cuda_home", "cuda_path", "_nvdiffrast_c", "undefined symbol", "cannot open shared object", "no module named", "g++", "gcc", "build")


def classify(stage, exc):
    """어느 단계(import_pkg/import_torch_ext/context/raster)에서 무슨 오류가 났는지 → (kind, 한국어 설명, 해결 방법)."""
    msg = f"{exc.__class__.__name__}: {exc}"
    low = msg.lower()
    if stage == "import_pkg":
        return "not_installed", "nvdiffrast 가 설치돼 있지 않아요.", FIX_INSTALL
    if stage == "import_torch_ext" or any(w in low for w in BUILD_WORDS):
        return "build", "nvdiffrast 의 CUDA 확장을 불러오지 못했어요(설치 때 컴파일이 안 됐어요).", FIX_INSTALL
    return "runtime", "nvdiffrast 가 그래픽카드에서 그리기를 실패했어요(CUDA 실행 문제).", FIX_RUNTIME


def check():
    out = {"ok": False, "kind": None, "text": "", "fix": "", "detail": "", "pixels": None, "version": None}

    def bad(kind, text, fix, detail=""):
        out.update(kind=kind, text=text, fix=fix, detail=str(detail)[-600:])
        return out

    try:
        import torch
    except Exception as e:  # noqa: BLE001
        return bad("no_torch", "PyTorch 를 불러오지 못해요.", FIX_INSTALL, repr(e))
    try:
        import nvdiffrast
        out["version"] = getattr(nvdiffrast, "__version__", "?")
    except Exception as e:  # noqa: BLE001
        return bad(*classify("import_pkg", e), repr(e))
    try:
        import nvdiffrast.torch as dr          # 0.4 부터는 여기서 컴파일된 확장(_nvdiffrast_c)을 불러와요
    except Exception as e:  # noqa: BLE001
        return bad(*classify("import_torch_ext", e), repr(e))
    if not torch.cuda.is_available():
        return bad("no_cuda", "PyTorch 가 그래픽카드(CUDA)를 쓰지 못해요.", FIX_RUNTIME)
    stage = "context"
    try:
        ctx = dr.RasterizeCudaContext(device="cuda")
        stage = "raster"
        pos = torch.tensor([[[-0.8, -0.8, 0.0, 1.0], [0.8, -0.8, 0.0, 1.0], [0.0, 0.8, 0.0, 1.0]]], dtype=torch.float32, device="cuda")
        tri = torch.tensor([[0, 1, 2]], dtype=torch.int32, device="cuda")
        rast, _ = dr.rasterize(ctx, pos, tri, resolution=[64, 64])
        n = int((rast[..., 3] > 0).sum().item())
    except Exception as e:  # noqa: BLE001
        return bad(*classify(stage, e), repr(e))
    out["pixels"] = n
    if not 900 <= n <= 1700:                    # 이 삼각형은 64×64 그림의 약 1310화소를 덮어요
        return bad("wrong", f"nvdiffrast 가 그린 결과가 이상해요(삼각형 {n}화소, 기대 약 1310).", FIX_RUNTIME)
    out.update(ok=True, kind="ok", text=f"nvdiffrast {out['version']} — 그래픽카드에서 삼각형 그리기 확인({n}화소)")
    return out


def main():
    r = check()
    print("@@NVCHECK " + json.dumps(r, ensure_ascii=False), flush=True)
    sys.exit(0 if r["ok"] else 2)


if __name__ == "__main__":
    main()
