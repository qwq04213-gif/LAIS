"""인체 3D 진단 — worker 환경 안에서 돌려, 무엇이 준비됐고 무엇이 빠졌는지 한국어로 알려요.
  python scripts/doctor.py [--home ~/lais-human3d] [--json] [--gpu-test]
--gpu-test: 그래픽카드에 실제로 메모리를 잡아 보고(1GB 씩) 쓸 수 있는 양을 재요. 모델 추론은 하지 않아요."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from worker import runtime as R                      # noqa: E402
from worker.providers.sith import SithProvider       # noqa: E402


def gpu_test():
    """그래픽카드 메모리를 1GB 씩 잡아 봐서 실제로 쓸 수 있는 양(MB)을 재요."""
    try:
        import torch
        if not torch.cuda.is_available():
            return {"ok": False, "text": "CUDA 를 쓸 수 없어요."}
        blocks, got = [], 0
        try:
            while got < 64:
                blocks.append(torch.empty((1024, 1024, 256), dtype=torch.float32, device="cuda"))
                got += 1
        except RuntimeError:
            pass
        del blocks
        torch.cuda.empty_cache()
        return {"ok": got >= 9, "usable_gb": got, "text": f"실제로 잡을 수 있는 그래픽카드 메모리: 약 {got}GB" + ("" if got >= 9 else " — 다른 프로그램을 닫아 주세요.")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "text": f"메모리 시험 실패: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=os.environ.get("HUMAN3D_HOME") or os.path.expanduser("~/lais-human3d"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gpu-test", action="store_true")
    a = ap.parse_args()
    p = SithProvider({"home": a.home, "python": sys.executable})
    rep = p.preflight()
    rep["gpu"] = R.gpu_info()
    if a.gpu_test:
        rep["gpu_test"] = gpu_test()
    if a.json:
        print("@@DOCTOR " + json.dumps(rep, ensure_ascii=False))
        return
    print("── 인체 3D(SiTH) 진단 ──")
    for c in rep["checks"]:
        print(("  [ 됨 ] " if c["ok"] else "  [안 됨] ") + c["text"] + ("" if c["ok"] or not c.get("fix") else "\n          → " + c["fix"]))
    if a.gpu_test:
        print("  " + rep["gpu_test"]["text"])
    print("\n결과: " + ("돌릴 준비가 됐어요." if rep["ready"] else "아직 준비가 덜 됐어요(위의 '안 됨' 항목)."))
    print("※ 준비가 됐다는 것은 '파일과 부품이 있다'는 뜻이에요. 10~12GB 그래픽카드에서 끝까지 돌아가는지는 실제로 한 번 만들어 봐야 알아요.")


if __name__ == "__main__":
    main()
