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
- 사용자가 만들라고 분명히 말했을 때만 빌드·배포해요.
- 버전: 새 기능은 가운데 숫자(4.0 → 4.1), 고침만 있으면 끝 숫자(4.0 → 4.0.1). 사용자가 다른 번호를 말하면 그 번호로.
- `VERSION.txt` 는 끝에 줄바꿈이 없어요. `README.txt` 는 **UTF-8 BOM + CRLF** 를 지켜요.
- README 변경 내역은 맨 위에 `[버전] 제목` 을 넣고, 항목은 `추가 / 변경 / 삭제 / 수정` 과 마지막 `미검증` 줄만 써요.
- `LocalAI-Studio/hub/updater.py` 와 `release-tools/apply_update.py` 는 항상 같아야 해요(`cmp` 로 확인).
- 빌드 전에 `__pycache__` 를 지워요.
- 사용자의 결과물(outputs)·모델 파일은 **절대 자동으로 지우지 않아요**. 정리 기능은 확인을 받은 뒤에만.
- `settings.json`(API 키 들어 있음)은 읽어서 보여 주거나 내보내지 않아요.
- 미성년자 + 성적 내용 차단(`blocked()` / `BLOCK_MSG`)은 어떤 기능에서도 빼지 않아요.
- 실제 엔진(ComfyUI·Blender·GPU)으로 확인 못 한 부분은 README 의 `미검증` 줄에 꼭 적어요.
- **깃허브에는 대화 내용·릴리즈 노트를 올리지 않아요.** 커밋 메시지는 짧게(예: `v4.1`, `3D 리깅 화면`), GitHub Releases 는 만들지 않아요.
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

## 빌드(출시)

```bash
find LocalAI-Studio -name __pycache__ -type d -exec rm -rf {} +
cmp LocalAI-Studio/hub/updater.py release-tools/apply_update.py
echo "한 줄 요약" > release-tools/notes_<버전>.txt      # 커밋하지 않는 파일
python3 release-tools/build_update.py --tree LocalAI-Studio --out outputs --notes release-tools/notes_<버전>.txt
```

`outputs/LocalAI-Studio-update-<버전>.bat` 을 사용자에게 파일로 전달해요(`outputs/` 는 커밋하지 않음). 출시한 커밋에는 `v<버전>` 태그를 붙여요.

## 지금 상태

마지막 출시: **4.0.1**(태그 `v4.0.1`). 다음 판 **4.1** 을 만드는 중이에요.

### 4.1 할 일

1. **3D 리깅(사람형 캐릭터 뼈대·가중치)** — 일부 됨
   - 됨: `hub/rig_fit.py`(numpy 만 쓰는 관절 어림, Mixamo 뼈 이름 → Unity·Unreal Humanoid 자동 매핑), `hub/blender_game.py` 의 `rig()`(뼈대 → 자동 가중치 → 빈 정점은 가장 가까운 뼈)·`preview_motion()`(확인용 움직임 GLB)·LOD 에 뼈대 다시 연결,
     `hub/server/27_m3d.py` 의 `tpose` 작업(Qwen-Image 2.1 로 앞 사진을 T자 자세로, 원본은 `view_front_orig.png`)·`rig` 옵션·`rig_preview.glb` 제공·되돌리기(`/api/m3d/slot` restore)
   - 남음: 화면(`web/js/70-m3d.js`·`index.html` — Blender 칸에 '뼈대 넣기', 방향 칸에 'T자 자세로 바꾸기'·'원래 자세로', 결과에 움직임 미리보기와 뼈대 정보), `test/fake_blender.py` 가 `rig` 를 흉내 내기,
     테스트(`test/humanoid.py` 의 가짜 사람 정점으로 `rig_fit` 확인 + 3D 흐름), README
2. **3D 장면 전체(사진 속 여러 물체)** — 계획: 원본 사진에서 물체를 눌러 고르기(기존 MobileSAM `/api/sam/segment`) → 물체마다 잘라 TRELLIS.2 → 깊이(`get_depth`) 로 위치·크기 어림 → Blender 로 한 장면(GLB·FBX·.blend), Blender 없으면 물체별 GLB + 배치 json. 가려진 물체는 선택적으로 Qwen 편집으로 채우기
3. **다시 켜도 올려 둔 사진 이어서 쓰기** — 편집 창 등 각 화면에 올린 사진을 서버에 저장해 두고, 프로그램을 다시 켜면 그대로 불러오기(지우기 버튼 포함, 자동 삭제 없음)
4. **기능별 엔진 점검·사양별 추천** — 기능마다 쓰는 엔진이 지금 기준으로 좋은지 확인하고, 그래픽카드 메모리 8/12/16/24GB 별 추천을 '설치와 모델'에 정리

### 미검증(실제 PC 에서 확인 필요)

- TRELLIS.2·Pixal3D 실제 그래프(4.0.1 에서 RemeshMesh 의 DynamicCombo 하위 칸 `sign_mode.qef` 등 누락을 고침 — 다른 노드에서도 비슷한 오류가 나면 `wf_fit` 과 그래프를 함께 확인)
- Blender 실제 실행(가져오기·LOD·FBX/OBJ 내보내기, 리깅)
- ComfyUI 의 DynamicCombo 하위 칸은 API 형식에서 `부모.자식` 키로 넣어요(예: `"sign_mode.qef": false`)
