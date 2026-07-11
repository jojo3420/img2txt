# img2txt — 한글 책 스캔 OCR 변환-보정 도구

한글 책을 스캔한 이미지(jpg/jpeg) 폴더를 넣으면 **읽기 좋은 텍스트 파일**로 바꿔주는 CLI 도구입니다.
단순히 글자만 뽑는 게 아니라 꼬리말(페이지 번호-책 제목)을 지우고, 줄바꿈으로 쪼개진 문단을 원래대로 복원하며, 페이지 경계를 넘어가는 문장을 이어붙입니다. 여기에 로컬 LLM(Ollama)으로 OCR 오탈자를 교정하는 보정 도구를 별도로 제공합니다.

- 언어 대상: 한국어 책 본문 (`ko-KR`)
- OCR 엔진: Apple Vision (macOS 전용, 별도 API 키-서버 불필요)
- 보정 엔진: 로컬 Ollama (인터넷-유료 API 불필요, 데이터 외부 유출 없음)

---

## 두 개의 도구

도구는 독립 실행되는 서브커맨드 2개로 나뉩니다.

| 도구 | 하는 일 | 입력 | 출력 |
|------|---------|------|------|
| `convert` | 스캔 이미지 → 텍스트 변환 | jpg/jpeg 폴더 | `pages/page-NNN.txt`(검수용), `book.txt`(읽기용) |
| `correct` | 텍스트의 OCR 오탈자 교정 | `book.txt` 같은 연속본 | `book_corrected.txt`(보정본), `corrections.log`(전/후 대조) |

`convert`가 만든 원문본(`book.txt`)은 절대 수정하지 않고, `correct`는 별도 파일로 보정본을 냅니다. 원문을 항상 보존하므로 보정 모델을 바꿔가며 여러 번 재실행할 수 있습니다.

---

## 요구 사항

- **macOS** (`convert`의 OCR은 Apple Vision에 의존). `correct`만 쓰는 경우는 OS 무관.
- **Python 3.13**
- 파이썬 패키지: `ocrmac`, `Pillow` (`convert`에만 필요, 지연 임포트라 `correct`만 쓸 땐 없어도 됨)
- **Ollama** (`correct`에만 필요): 로컬에 설치-실행되어 있어야 하며 모델이 pull 되어 있어야 함

```bash
# convert용 (macOS)
pip install ocrmac Pillow

# correct용
# 1) https://ollama.com 에서 Ollama 설치 후 서버 실행
ollama serve
# 2) 기본 모델 내려받기
ollama pull qwen3:14b
```

---

## 가상환경 세팅

프로젝트 루트에 Python 3.13 가상환경(`.venv`)을 만들어 사용합니다.

```bash
# 1) 가상환경 생성
python3.13 -m venv .venv

# 2) 활성화 (zsh/bash)
source .venv/bin/activate

# 3) 패키지 설치
pip install ocrmac Pillow pytest
```

`.venv/`는 `.gitignore`에 등록되어 있어 커밋되지 않습니다.

### IntelliJ 연동

1. `File → Project Structure → SDKs` 에서 `+` → **Add Python SDK...**
2. **Virtualenv Environment → Existing environment** 선택 → `<프로젝트 루트>/.venv/bin/python3.13` 지정
3. `Project Structure → Modules` 에서 모듈 SDK를 방금 등록한 인터프리터로 설정

이후 IntelliJ 내장 터미널-Run 구성이 자동으로 `.venv`를 사용합니다.

---

## 사용법

패키지 형태로 `python -m img2txt <서브커맨드>`로 실행합니다.

### 1) convert — 이미지를 텍스트로

```bash
python -m img2txt convert <입력폴더> [-o 출력폴더] [-v]
```

| 인자 | 설명 | 기본값 |
|------|------|--------|
| `입력폴더` | jpg/jpeg가 들어 있는 폴더 (확장자 대소문자 무시) | 필수 |
| `-o`, `--output` | 출력 폴더 | `./output` |
| `-v`, `--verbose` | DEBUG 로그 출력 | 꺼짐 |

예:

```bash
python -m img2txt convert ./scan/chapter01 -o ./output
```

출력 구조:

```
output/
├── pages/
│   ├── page-001.txt   # 검수용: OCR 줄 단위 원본 그대로
│   ├── page-002.txt
│   └── ...
└── book.txt           # 읽기용: 꼬리말 제거 + 문단 복원 + 페이지 경계 병합
```

### 2) correct — OCR 오탈자 보정

```bash
python -m img2txt correct <연속본txt> [--model 모델명] [-o 출력폴더] [-v]
```

| 인자 | 설명 | 기본값 |
|------|------|--------|
| `연속본txt` | `convert`가 만든 `book.txt` 등 텍스트 파일 | 필수 |
| `--model` | Ollama 모델명 | `qwen3:14b` |
| `-o`, `--output` | 출력 폴더 | 입력 파일과 같은 폴더 |
| `-v`, `--verbose` | DEBUG 로그 출력 | 꺼짐 |

예:

```bash
python -m img2txt correct ./output/book.txt
```

출력:

```
output/
├── book_corrected.txt   # 보정본
└── corrections.log      # 바뀐 문단만 전/후 대조 (사람 검수용)
```

> ⚠️ 보정은 문단마다 LLM에 순차 요청하므로 느립니다. 실측(qwen3:14b, 124문단)에서 문단당 평균 약 52초, 전체 약 107분이 걸렸습니다. **긴 책은 백그라운드 실행을 권장**합니다.

---

## 동작 원리 (변환 파이프라인)

`convert`는 위치 좌표(bounding box) 기반으로 페이지 구조를 해석합니다.

1. **수집-정렬** — 폴더에서 jpg/jpeg를 모아 파일명 마지막 숫자 기준으로 자연 정렬 (`page2` < `page10`). 숫자 없는 파일은 맨 뒤로.
2. **OCR** — 이미지 1장을 Apple Vision으로 인식. EXIF 회전 보정 후, 모든 줄을 y좌표 내림차순(위→아래)으로 정렬.
3. **레이아웃 분석** — 페이지별로:
   - **꼬리말 제거**: 페이지 최하단 띠 안 + (숫자 포함 또는 본문 대비 짧은 줄)인 줄만 제거. 과잉 삭제로 본문이 지워지지 않도록 보조 조건을 둠.
   - **제목 분류**: 글자 높이가 본문 중앙값보다 크게 높은 줄은 제목으로 보고 독립 문단 유지.
   - **문단 시작 감지**: 들여쓰기(왼쪽 여백보다 오른쪽에서 시작)된 줄을 새 문단 시작으로 판단.
4. **연속본 조립** — 페이지 첫 줄이 들여쓰기가 아니면 이전 페이지 마지막 문단에 이어붙임(페이지 경계 병합). 문단 안 줄은 공백 1칸으로 연결.

`correct`는 연속본을 빈 줄 기준 문단으로 나눠 로컬 Ollama에 "OCR 오탈자-띄어쓰기만 고치고 재작성 금지" 지시로 순차 보정합니다.

---

## 안전장치 (Silent Failure 방지)

원문을 훼손하지 않도록 여러 폴백을 둡니다.

- **이미지 1장 OCR 실패** → 경고 후 다음 이미지 계속, 원문은 손대지 않음
- **빈 페이지** → 연속본에서 제외하고 `[페이지 N 누락]` 표식 삽입, 앞뒤 병합 금지(문장이 조용히 훼손되는 것 방지)
- **길이 가드** → 보정 결과가 원문 길이와 `max(5자, 10%)` 이상 차이나면 버리고 원문 유지 (LLM 창작-요약 차단)
- **긴 문단(2000자 초과)** → 문단 감지 실패 의심으로 보정 생략
- **Ollama 미응답-타임아웃** → 해당 문단 원문 유지하고 계속 진행
- **전체 문단 보정 실패(정상 응답 0건)** → 종료 코드 1로 실패를 명확히 알림

**종료 코드**: 정상(부분 실패 포함) `0`, 입력 없음-전체 실패-Ollama 접속 불가-모델 미설치 `1`.

---

## 구현된 기능 목록

**변환 (`convert`)**
- jpg/jpeg 수집 + 파일명 마지막 숫자 기준 자연 정렬 (대소문자 무시, 숫자 없는 파일 맨 뒤 배치)
- Apple Vision 한국어 OCR + EXIF 회전 보정 + y좌표 위→아래 정렬
- 위치 기반 꼬리말(페이지 번호-책 제목) 제거 (본문 오삭제 방지 보조 조건 포함)
- 글자 높이 기반 제목 줄 분류 (독립 문단 유지)
- 들여쓰기(x좌표) 기반 문단 시작 감지 및 문단 복원
- 페이지 경계를 넘는 문단 이어붙이기 (누락 페이지는 병합 금지 + 표식)
- 검수용 페이지별 원본 txt + 읽기용 연속본 txt 동시 출력

**보정 (`correct`)**
- 연속본을 문단 단위로 나눠 로컬 Ollama LLM으로 순차 보정
- 보정 범위 제약 프롬프트(오탈자-띄어쓰기만, 재작성 금지) + 실측 오류 few-shot 예시
- `--model`로 보정 모델 교체 (기본 `qwen3:14b`)
- 길이 가드 / 긴 문단 생략 / 실패 폴백 / 전체 실패 감지
- 시작 시 Ollama 접속-모델 설치 사전 점검
- 원문 보존 + 보정 기록 로그(`corrections.log`, 전/후 대조) 생성

**공통**
- 서브커맨드 2개 독립 실행, 모든 입출력 UTF-8 고정
- 진행-요약 logging (`-v`로 DEBUG), 재실행 시 출력 덮어쓰기

**제품 매핑**: 무료 = `convert`만, 유료 = `convert` + `correct`.

---

## 알려진 한계

- `convert`의 OCR은 macOS(Apple Vision) 전용
- `book.txt`의 오탈자는 원문 충실 방침상 그대로 남음 → 교정은 `correct`의 몫
- 레이아웃 임계값은 특정 책 판형 기준으로 캘리브레이션됨 → 판형이 크게 다르면 상수 조정 필요 (`img2txt/layout.py` 상단 근거 주석 참조)
- 들여쓰기 없이 시작하는 특수 문단(인용 블록 등)은 앞 문단에 붙을 수 있음
- LLM 보정은 느림(문단당 수십 초) → 대량 처리는 백그라운드 권장

---

## 개발

```bash
pytest              # 전체 단위 테스트
pytest -m macos     # macOS 실제 OCR 통합 테스트 (Vision 필요)
```

모듈 구성(단일 책임): `scanner`(수집-정렬) - `ocr`(Vision 래핑) - `layout`(페이지 분석) - `assembler`(연속본 조립) - `corrector`(LLM 보정) - `writer`(파일 쓰기) - `cli`(흐름 조립).
