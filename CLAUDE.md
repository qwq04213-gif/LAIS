# LAIS — 로컬 AI 스튜디오 개발 안내

윈도우 PC 에서 도는 한국어 웹 화면 하나로 ComfyUI(그림·영상·3D)와 Ollama(대화)를 묶어 쓰는 통합 패키지예요.
사용자는 개발자가 아니고, 결과물은 윈도우용 업데이트 파일(`LocalAI-Studio-update-<버전>.bat`)로 받아 설치해요.

## 폴더

| 폴더 | 내용 |
|---|---|
| `LocalAI-Studio/` | 배포되는 앱 그대로(사용자 PC 의 설치 폴더와 같은 모양) |
| `LocalAI-Studio/hub/hub.py` | 허브 서버. `hub/server/NN_*.py` 를 번호 순서대로 **같은 이름 공간에 exec** 해요(다른 파일의 이름을 import 없이 씀) |
| `LocalAI-Studio/hub/web/` | 화면. `web/js/*.js` 는 **파일 이름 순서대로 이어 붙여** 한 스크립트로 내려가요(전역 const 이름이 겹치면 안 됨) |
| `LocalAI-Studio/hub/flows.py` | ComfyUI 그래프(API 형식) 만드는 함수들 |
| `LocalAI-Studio/hub/models.json` · `features.json` · `profiles.json` | 추천 모델 목록, 이미지 기능 정의, 모델 프로필 |
| `LocalAI-Studio/README.txt` · `VERSION.txt` | 사용 설명 + 변경 내역(앱 안 '변경 내역' 화면이 이 파일을 읽어요), 현재 버전 |
| `release-tools/` | `build_update.py`(업데이트 .bat·zip 만들기), `apply_update.py`(= `hub/updater.py`), `history.json` |
| `test/` | 가짜 ComfyUI·Ollama·파일 서버(`mocks.py`)로 도는 테스트, `runpar.py`(2개씩 동시 실행) |
| `rmbg-test/` | 배경 지우기 테스트용 실제 모델(u2netp.onnx) |

## 작업 규칙

- 사용자에게는 **한국어**로, 짧게, 표 위주로 알려요. 전문 용어 대신 화면에 나오는 말을 써요.
  **진행 중 안내·중간 보고·질문까지 모든 대화를 한국어로** 해요(영어로 쓰지 않기 — 사용자 요청).
- 사용자가 만들라고 분명히 말했을 때만 빌드·배포해요.
- 버전: 새 기능은 가운데 숫자(4.0 → 4.1), 고침만 있으면 끝 숫자(4.0 → 4.0.1). 사용자가 다른 번호를 말하면 그 번호로.
- `VERSION.txt` 는 끝에 줄바꿈이 없어요. `README.txt` 는 **UTF-8 BOM + CRLF** 를 지켜요.
- README 변경 내역은 맨 위에 `[버전] 제목` 을 넣고, 항목은 `추가 / 변경 / 삭제 / 수정` 과 마지막 `미검증` 줄만 써요.
- `LocalAI-Studio/hub/updater.py` 와 `release-tools/apply_update.py` 는 항상 같아야 해요(`cmp` 로 확인).
- 빌드 전에 `__pycache__` 를 지워요.
- 사용자의 결과물(outputs)·모델 파일은 **절대 자동으로 지우지 않아요**. 정리 기능은 확인을 받은 뒤에만.
- `settings.json`(API 키 들어 있음)은 읽어서 보여 주거나 내보내지 않아요.
- 실제 엔진(ComfyUI·Blender·GPU)으로 확인 못 한 부분은 README 의 `미검증` 줄에 꼭 적어요.
- **깃허브에는 코드만 올려요. 대화 내용·제작 메모·릴리즈 노트는 절대 올리지 않고 대화에만 적어요(사용자 요청).** 커밋 메시지는 짧게(예: `v4.1`, `3D 리깅 화면`), GitHub Releases 는 만들지 않아요.
  빌드용 메모(`release-tools/notes_*.txt`)·개인 작업 기록은 `.gitignore` 에 있어요 — 커밋하지 마세요.

## 테스트

```bash
pip install pillow numpy playwright onnxruntime   # 처음 한 번(크로미움: python -m playwright install chromium)
cd test
TMPDIR=/tmp/tt python3 runpar.py test_m3d ui_test64          # 고친 곳 관련 테스트만 먼저
TMPDIR=/tmp/tt python3 runpar.py $(ls test_*.py ui_test*.py)  # 출시 전 전체 회귀(140개 남짓, 수십 분)
```

- ffmpeg 가 있어야 하는 테스트가 있어요. 테스트마다 고정 포트(`TEST_HUB_PORT`)를 쓰고, `TEST_SLOT` 으로 1000씩 띄워 동시에 돌려요.
- 경로는 `test/` 의 한 단계 위(저장소 맨 위)를 기준으로 잡아요. 다른 곳을 쓰려면 `LAS_BASE` 환경 변수.
- 새 ComfyUI 노드를 쓰면 `test/mocks.py` 의 `REQ`(노드별 필수 칸)에 넣어야 가짜 ComfyUI 가 받아 줘요.
- Blender 는 테스트에서 `BLENDER_EXE=test/fake_blender.py`(가짜)로 흐름만 확인해요.
- **3D·이미지 품질 확인은 고해상도·고품질 사람/캐릭터 사진으로 해요(사용자 요청).** 단색·줄무늬 같은 단순한 그림만으로 판단하지 않아요.
  이 환경엔 GPU·실제 3D 엔진이 없으니, 공개 라이선스(CC0 등) 고해상도 얼굴 사진을 가짜 3D(머리·몸)에 무늬로 입혀 '정답'으로 쓰고 결과를 눈으로도 확인해요.

## 빌드(출시)

```bash
find LocalAI-Studio -name __pycache__ -type d -exec rm -rf {} +
cmp LocalAI-Studio/hub/updater.py release-tools/apply_update.py
echo "한 줄 요약" > release-tools/notes_<버전>.txt      # 커밋하지 않는 파일
python3 release-tools/build_update.py --tree LocalAI-Studio --out outputs --notes release-tools/notes_<버전>.txt
```

`outputs/LocalAI-Studio-update-<버전>.bat` 을 사용자에게 파일로 전달해요(`outputs/` 는 커밋하지 않음). 출시한 판은 커밋 메시지를 `v<버전>` 으로 해요(세션에서 태그를 올릴 수 없는 경우가 있어 커밋 메시지로 판을 구분해요).

## 지금 상태

마지막 출시: **4.6**(커밋 `v4.6`). 다음 판 **4.7**.

### 다음 할 일

0. 사용자가 4.5 로 실제 3D(전신 사진)를 만들어 결과 zip 을 보내 주면, 앞·45°·옆·뒤와 옷·손·머리카락·이음새를 그려서 점검하기(시험 도구: 가짜 3D 대신 실제 GLB 를 `photoproj`·렌더러로)
1. (미룸) 움직임 미리보기에서 옷이 몸과 함께 늘어나는 문제(리깅 가중치)

4.6: 결과를 작업 한 번 = 폴더 하나(`job_dir_name`·`JOB_RX`, `out_path`/`out_files` 가 날짜·작업 폴더 둘 다 읽음, 예전 결과는 그대로), 갤러리 3D 미리보기(`photoproj.preview` → `/thumb/`)·전체화면·[보이는 것 전체 선택]/[이 날짜 전체 선택], 3D 지울 때 zip·zip.json 함께(`gal_sides`), 옷·신발 최소 거칠기(`CLOTH_ROUGH`), 방향 그림 반사색 문구. 머리 고르기(`head_split`): 범위 = 보이는 얼굴 점까지 거리×1.1, 안쪽 면(UDF 이중 껍질) 빼기(면 방향은 `project` 에서 전체 맞춤), 겹치면 사진에 보이는 면 중 카메라에 가까운 것. 실제 결과(20k 면)는 얼굴이 평평해서 옆에서 '사진 붙인 판'처럼 보임 — 면 수 20만 권장. 얼굴 앞 머리카락 가닥 자르기는 시도했다가 뺌(UDF 에선 얼굴 겉면도 얇은 층이라 구멍이 남)

4.5.1: 얼굴 찾기 확인(`m3d_face_ok` 피부색·크기)·몸 위쪽 잘라 다시 찾기(`m3d_face_box`) — 실제 결과에서 전신 사진의 작은 얼굴을 가슴으로 잡아 머리 텍스처가 등에 간 문제

4.5: 3D 얼굴 고해상도(`photoproj.head_split` — 공처럼 펼침, 중심=얼굴 앞면에서 머리 두께 절반 뒤, 반경 0.8×얼굴, 겹침·외딴 조각은 몸으로), 밉맵(`fix_samplers`), 가장자리 손질(`m3d_defringe`), 그늘 줄이기·피부 거칠기·색감 맞추기, 사진 위치(줄 단위 범위)·원근(Pixal3D 화각 `PreviewAny` → `dist_e`), 결과 표시(`m3d_photo_res`). 실제 사진 시험 `test/test_m3d_real.py`

4.4.1: 남은 시간을 작업 전체 진행률로 한 곳에서 어림(`08_jobs.py` `eta_update`·`eta_loop` 1초마다, 같은 종류 작업의 진행 곡선 `eta_history.json` — `eta_key`/`eta_learn`), 화면 표시는 `00-core.js` 의 `fmtEta`·`fmtEl`·`etaTxt` 하나로

4.4 에서 넣은 것: 모델 지우기 용량 고침(`delete_files`·`delete_llm`·저장 공간 `llm_orphans`), 3D 사진 붙이기(`photoproj.py` — 카메라 자동 맞춤, `m3d_photo`)·얼굴 키워 붙이기(`m3d_face`, MediaPipe `mediapipe-face`)·캐릭터 면 20만/70만·1536 이면 다시 짜기 1024

4.3 에서 넣은 것: 3D Pixal3D 사진 한 장 기본(`m3d_engine`, MoGe 화각)·캐릭터 텍스처 4096·16GB 이상 1536·작은 사진 자동 키우기(`m3d_enlarge`)·[업스케일로 키우기]·
방향 칸마다 [그리기]·방향/T자 그림 outputs\3D 저장·3D 전체화면, 저장 공간(작업 폴더 표시·정리), 성인 표현 표시(`models.json` 의 `nsfw`)·제한 해제 대화 모델(Qwen3.5·Gemma 4 abliterated)

4.2 에서 넣은 것: 3D 장면 전체(`glbscene.py`), 배경 지우기 경계 다듬기·BiRefNet, LTX-2.5·SeedVR2·Z-Image-Turbo·FLUX 3 Klein(생성·편집)·MOSS 편집·
Qwen 2.1 Turbo·Depth Anything 3·Stable Audio 3·Qwen3.5 27B·Gemma 4, 사양별 추천(`TIERS`, 2026-11 조사), 예전 엔진 정리(`SUPERSEDED` — 제한 해제판 대화 모델은 넣지 않음)

### 미검증(실제 PC 에서 확인 필요)

- 남은 시간: 실제 ComfyUI 작업(영상·3D·하이레스)에서의 정확도
- 3D 머리 전용 텍스처: 실제 Pixal3D 결과에서 머리 범위(목·어깨 경계)·노멀맵 방향·피부 판정
- 3D 사진 붙이기: 실제 Pixal3D·TRELLIS.2 GLB 의 좌표·원근에서 붙는 위치, MediaPipe 얼굴 찾기. 윈도우에서 모델 지운 뒤 실제 용량 감소
- TRELLIS.2·Pixal3D 실제 결과 — 4.1 에서 ComfyUI 공식 예시(workflow_templates `3d_pixal3d_trellis2_image_to_model`)와 같게 맞춤:
  구조 CFGOverride(0.667)+RescaleCFG 0.7+shift 5, 모양 CFGOverride(0.769)+RescaleCFG 0.5·20단계, RemeshMesh `solid`. 멀티뷰 방향: 왼쪽 그림 = 얼굴이 그림 왼쪽
- Blender 실제 실행(가져오기·LOD·FBX/OBJ 내보내기, 리깅·움직임 미리보기)
- ComfyUI 의 DynamicCombo 하위 칸은 API 형식에서 `부모.자식` 키로 넣어요(예: `"sign_mode.fill": 20`)
  — 그 판에 없는 선택지를 넣으면 ComfyUI 가 칸을 통째로 빼서 `missing ... sign_mode` 오류가 나요. `wf_fit` 이 노드의 `_alt` → 그 판 기본값으로 바꿔요(4.1.1).
  4.1 에서 새로 쓴 노드(CFGOverride, RemeshMesh `solid`)는 예전 ComfyUI 에 없을 수 있어요 — 새 노드를 쓸 땐 없을 때의 대안도 만들어요
- 테스트 환경: `test_update` 는 지난판 설치 폴더·빌드 메모가 있어야 해요. `ui_test2/3/25` 는 예전 경로(`/tmp/claude-0/-home-claude/...`, `/tmp/tt/p1.png`)를 써요. `ui_test5` 는 scikit-image, `test_v313` 은 opencv 필요
