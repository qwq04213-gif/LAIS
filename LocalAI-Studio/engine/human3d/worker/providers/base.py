"""엔진 어댑터의 공통 틀. 엔진마다(SiTH·ECON …) 이 틀을 채워요."""


class Provider:
    name = "base"
    title = ""
    verified = False            # 실제 그래픽카드·실제 모델로 끝까지 확인했는지(확인 전에는 False 로 둬요)

    def __init__(self, cfg):
        self.cfg = cfg          # {"home": worker 가 쓰는 폴더, "python": 파이썬 경로, …}

    def preflight(self):
        """돌릴 준비가 됐는지. {"ready": bool, "checks": [{id, ok, text, fix}], "versions": {...}}"""
        raise NotImplementedError

    def stages(self):
        """차례로 돌릴 단계 목록: [(단계 이름, 함수(job, log))]. 단계 이름은 runtime.WORKER_STAGES 중에서."""
        raise NotImplementedError

    def versions(self):
        return {}
