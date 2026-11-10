"""LAIS 본체와 인체 3D worker 가 함께 지키는 약속(단계 이름·파일 이름·주소·오류 코드).
worker 쪽(engine/human3d/worker)에도 같은 값이 들어 있어요 — 한쪽을 바꾸면 다른 쪽도 같이 바꿔요(test_human3d 가 비교해요)."""

API_VERSION = 1
HOST = "127.0.0.1"          # 이 PC 안에서만 접근(밖으로 열지 않아요)
PORT = 17861

# 단계: (이름, 화면에 보이는 말, 전체 진행률에서 차지하는 몫, 어디서 도는지)
STAGES = (
    ("preprocess", "사진 준비 (배경 지우기 · 가운데 맞추기)", 0.03, "hub"),
    ("keypoints", "자세·관절점 찾기", 0.04, "worker"),
    ("smplx_init", "몸 모양 어림 (SMPLer-X)", 0.08, "worker"),
    ("smplx_fit", "몸 모양·자세·위치 맞추기 (SMPL-X)", 0.15, "worker"),
    ("back", "보이지 않는 뒷면 그리기 (AI 추정)", 0.25, "worker"),
    ("geometry", "몸 형태 복원", 0.25, "worker"),
    ("texture", "색 입히기", 0.08, "worker"),
    ("project", "원본 사진 화소 붙이기", 0.04, "hub"),
    ("qa", "메시 검사 · 4방향 그림", 0.05, "hub"),
    ("export", "GLB 저장", 0.03, "hub"),
)
STAGE_IDS = tuple(s[0] for s in STAGES)
STAGE_KO = {s[0]: s[1] for s in STAGES}
WORKER_STAGES = tuple(s[0] for s in STAGES if s[3] == "worker")


def stage_span(stage):
    """이 단계가 전체 진행률에서 차지하는 (시작, 끝)."""
    a = 0.0
    for sid, _, w, _ in STAGES:
        if sid == stage:
            return a, a + w
        a += w
    raise KeyError(stage)


def overall(stage, frac):
    a, b = stage_span(stage)
    return round(a + (b - a) * max(0.0, min(1.0, float(frac))), 4)


# 작업 폴더(outputs/3D-human/<작업 id>/) 안의 파일 이름
OUT_SUB = "3D-human"
FILES = {
    "original": "input/original.png",            # 올린 사진 그대로(크기·화소 안 바꿈)
    "mask": "input/mask.png",                    # 사람 마스크(흰색 = 사람)
    "rgba": "input/rgba.png",                    # 배경 지운 사진
    "square": "images/000.png",                  # 정사각형 가운데 정렬 입력(SiTH 가 읽는 이름)
    "frame": "input/frame.json",                 # 원본 → 정사각형 변환 값(나중에 원본 화소를 되짚을 때 씀)
    "keypoints": "images/000_keypoints.json",    # OpenPose 형식 관절점
    "smplx_obj": "smplx/000_smplx.obj",          # 맞춘 SMPL-X 몸
    "smplx_params": "smplx/debug/000.json",      # SMPL-X 값(자세·체형)
    "back": "back_images/000_000.png",           # 고른 뒷면 그림(AI 추정)
    "back_all": "back_images/all_images",        # 뒷면 후보 전부
    "back_pick": "back_images/pick.json",        # 후보 점수와 고른 이유
    "engine_obj": "meshes/000_reco.obj",         # 엔진 원본(손대지 않은 고밀도 메시)
    "engine_ply": "meshes/000_reco.ply",
    "texture": "result/texture_front.png",       # 사진에서 가져온 색이 어디에 붙었는지(관측/추정 지도)
    "qa": "result/mesh_qa.json",
    "glb": "result/human.glb",
    "log": "job.log",
    "meta": "job.json",                          # 사용한 모델·판·설정·단계별 시간·VRAM
    "diagnosis": "diagnosis.json",               # 실패했을 때: 어느 단계에서 왜
}
VIEWS = (("front", "앞", 0), ("q45", "45도", 45), ("side", "옆", 90), ("back", "뒤", 180))

# worker 가 돌려주는 오류 코드 → 화면에 보일 말
ERRORS = {
    "oom": "그래픽카드 메모리가 모자라요.",
    "no_person": "사진에서 사람을 찾지 못했어요. 한 사람의 몸 전체가 잘 보이는 사진을 써 주세요.",
    "no_model": "필요한 모델 파일이 없어요.",
    "no_smplx": "SMPL-X 몸 모델 파일이 없어요(직접 가입해서 받아야 하는 파일이에요).",
    "no_cuda": "worker 가 그래픽카드(CUDA)를 쓰지 못해요.",
    "cancelled": "사용자가 중단했어요.",
    "stage_failed": "처리 중 오류가 났어요.",
    "not_implemented": "아직 준비되지 않은 엔진이에요.",
}

# 메모리가 모자랄 때 차례로 시도하는 격자 크기(낮출수록 덜 세밀해요). 다시 시도는 최대 2번.
GRID_STEPS = (512, 384, 256)
MAX_OOM_RETRY = 2

DEFAULT_OPTS = {
    "provider": "sith",
    "grid": 512,                # 형태 복원 격자(SiTH 기본 512)
    "chunk": 50000,             # 한 번에 그래픽카드로 보내는 점 수
    "back_candidates": 4,       # 뒷면 후보 수(하나씩 그려서 자동으로 골라요)
    "back_steps": 50,
    "back_res": 512,
    "fp16": True,
    "seed": 0,
    "subdivide": True,
    "project_photo": True,      # 원본 사진 화소 붙이기
}


def clean_opts(o):
    """화면·API 에서 받은 설정을 허용 범위 안으로."""
    o = dict(o or {})
    r = dict(DEFAULT_OPTS)
    if o.get("provider") in ("sith", "econ"):
        r["provider"] = o["provider"]
    try:
        g = int(o.get("grid", r["grid"]))
        r["grid"] = g if g in GRID_STEPS else r["grid"]
        r["chunk"] = max(5000, min(400000, int(o.get("chunk", r["chunk"]))))
        r["back_candidates"] = max(1, min(8, int(o.get("back_candidates", r["back_candidates"]))))
        r["back_steps"] = max(10, min(100, int(o.get("back_steps", r["back_steps"]))))
        r["seed"] = int(o.get("seed", 0)) % (2 ** 31)
    except (TypeError, ValueError):
        pass
    for k in ("fp16", "subdivide", "project_photo"):
        if k in o:
            r[k] = bool(o[k])
    return r
