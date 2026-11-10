"""ECON 어댑터(예비). 아직 연결하지 않았어요 — SiTH 가 사용자 PC 의 메모리에 맞지 않거나 품질에 문제가 있을 때 따로 검토해요.
검증 없이 자동으로 주력 엔진이 되지 않게, 준비 상태는 항상 '안 됨'으로 알려요."""
from .. import runtime as R
from .base import Provider


class EconProvider(Provider):
    name = "econ"
    title = "ECON (예비 — 아직 연결 안 됨)"
    verified = False

    def preflight(self):
        return {"ready": False, "checks": [{"id": "econ", "ok": False, "text": "ECON 은 아직 준비되지 않은 예비 엔진이에요.", "fix": "지금은 SiTH 만 쓸 수 있어요."}], "versions": {}}

    def stages(self):
        def nope(job, log):
            raise R.StageError("not_implemented", "ECON 엔진은 아직 연결되지 않았어요.", "keypoints")
        return [("keypoints", nope)]
