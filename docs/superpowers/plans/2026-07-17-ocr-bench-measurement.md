# OCR 벤치 실측 (어댑터 + baseline + 전처리 A/B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI Hub 페이지형 공공문서 데이터(반입 완료, Validation 4세트 x 약 2,900페이지)로 하네스를 실가동한다 — 라벨 어댑터 구현 → baseline 실측 → 전처리 레버 3종 A/B 판정.

**Architecture:** Task 1만 코드 작업(라벨 어댑터 + CLI 연결). Task 2~3은 기존 CLI(`scripts/bench_ocr.py`) 실행과 결과 기록으로, 컨트롤러가 직접 수행한다 (macOS Apple Vision 실OCR 필요 — 서브에이전트 위임 불필요).

**Tech Stack:** Python 3.13 (`.venv`), 표준 라이브러리만. 실측은 로컬 Apple Vision OCR (외부 전송 없음 — 컴플라이언스 안전).

**데이터 사실 (인스펙션 확정, 2026-07-17):**
- 위치: `bench_data/023.OCR 데이터(공공)/01-1.정식개방데이터/Validation/{01.원천데이터,02.라벨링데이터}/`
- 세트 4개: AF_2010_5270218_0001 (2,898p), AF_1990_5270218_0010 (2,970p), AF_1980_5350073_0002 (2,992p), AF_b1980_5350073_0001 (2,874p) — 원천(jpg)과 라벨(json)이 같은 stem으로 1:1
- 라벨 JSON 최상위 키: `Annotation`, `Bbox`, `Dataset`, `Images`. `Bbox`는 단어 목록: `{"data": "단어", "id": 순번, "x": [4좌표], "y": [4좌표], ...}`
- 스모크 표본: **AF_2010 세트** (가장 현대 인쇄물에 가까움), `--limit 50`

## Global Constraints

- 외부 의존 추가 없음. from __future__ import annotations, Type Hints 100%, 한국어 docstring, print 금지(logging), 하드코딩 금지(상수), 함수 50줄 이내.
- 정답 복원 규칙: Bbox를 `id` 오름차순 정렬 후 `data`를 공백 한 칸으로 join (줄바꿈 복원은 하지 않음 — normalize_strict가 공백류를 단일 공백으로 접기 때문에 채점에 영향 없음, WER 단어 경계도 보존됨).
- 매칭 실패는 기본 중단(--allow-skip 시만 스킵), 빈 OCR은 정답 전체 누락 계산 (기존 하네스 규약).
- bench_data/는 git 추적 금지 (기등록). 실측 리포트(JSONL)는 bench_data/reports/에 (커밋 안 함), **판정 요약 문서만** docs/bench/에 커밋.
- 테스트: `.venv/bin/python -m pytest tests/bench/ -q`, 커밋 전 전체 1회.

---

### Task 1: AI Hub 라벨 어댑터 + CLI --label-format

**Files:**
- Create: `img2txt/bench/aihub.py`
- Modify: `scripts/bench_ocr.py` (parse_args + main의 어댑터 선택)
- Test: `tests/bench/test_aihub.py`

**Interfaces:**
- Consumes: 라벨 JSON 구조 (위 "데이터 사실" 참조)
- Produces: `aihub_label_adapter(label_path: Path) -> str` — Bbox id순 공백 join 텍스트. CLI 인자 `--label-format {txt,aihub}` (기본 `txt`) — `aihub`면 load_pairs에 이 어댑터 전달.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/bench/test_aihub.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from img2txt.bench.aihub import aihub_label_adapter


def _write_label(path: Path, bbox: list[dict]) -> None:
    payload = {
        "Annotation": {"object_recognition": 1},
        "Bbox": bbox,
        "Dataset": {"identifier": "OCR(public)"},
        "Images": {"identifier": "AF_TEST_0001", "width": 100, "height": 100},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_adapter_joins_words_in_id_order(tmp_path: Path) -> None:
    """Bbox를 id 오름차순으로 공백 join한다 (원본 순서가 뒤섞여도)."""
    label = tmp_path / "AF_TEST_0001.json"
    _write_label(label, [
        {"data": "우리의", "id": 2, "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]},
        {"data": "창원은", "id": 1, "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]},
        {"data": "자랑", "id": 3, "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]},
    ])

    assert aihub_label_adapter(label) == "창원은 우리의 자랑"


def test_adapter_empty_bbox_returns_empty(tmp_path: Path) -> None:
    """Bbox가 비면 빈 문자열 (빈 페이지 라벨)."""
    label = tmp_path / "AF_TEST_0002.json"
    _write_label(label, [])

    assert aihub_label_adapter(label) == ""


def test_adapter_missing_bbox_key_raises(tmp_path: Path) -> None:
    """Bbox 키 자체가 없으면 KeyError (형식 이상 조기 발견 — 조용한 빈 정답 금지)."""
    label = tmp_path / "AF_TEST_0003.json"
    label.write_text(json.dumps({"Images": {}}, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(KeyError):
        aihub_label_adapter(label)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/bench/test_aihub.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'img2txt.bench.aihub'`

- [ ] **Step 3: 구현**

```python
# img2txt/bench/aihub.py
"""AI Hub 페이지형 공공문서 OCR(dataSetSn=71299) 라벨 어댑터.

라벨 JSON의 Bbox(단어 목록)를 id 오름차순으로 공백 join해 정답 텍스트를
복원한다. 줄바꿈은 복원하지 않는다 — 채점 정규화(normalize_strict)가
공백류를 단일 공백으로 접으므로 CER/WER에 영향이 없다.
"""
from __future__ import annotations

import json
from pathlib import Path


def aihub_label_adapter(label_path: Path) -> str:
    """AI Hub 라벨 JSON에서 정답 텍스트를 복원한다.

    Args:
        label_path: 라벨 JSON 경로.

    Returns:
        Bbox id 오름차순으로 공백 join한 정답 텍스트.

    Raises:
        KeyError: Bbox 키가 없는 형식 이상 라벨 (조기 발견 목적).
    """
    payload = json.loads(label_path.read_text(encoding="utf-8"))
    words = sorted(payload["Bbox"], key=lambda entry: entry["id"])
    return " ".join(entry["data"] for entry in words)
```

`scripts/bench_ocr.py` 수정:
- import에 `from img2txt.bench.aihub import aihub_label_adapter` 추가
- parse_args에 추가:

```python
    parser.add_argument(
        "--label-format",
        choices=["txt", "aihub"],
        default="txt",
        help="라벨 형식 (기본 txt: 평문, aihub: 페이지형 공공문서 JSON)"
    )
```

- main()의 load_pairs 호출부에서 어댑터 선택:

```python
    adapter = aihub_label_adapter if args.label_format == "aihub" else _default_label_adapter
    pairs = load_pairs(args.image_dir, args.label_dir, adapter, allow_skip=args.allow_skip)
```

- `tests/bench/test_bench_cli.py`에 파싱 테스트 추가:

```python
def test_parse_args_label_format() -> None:
    """--label-format 파싱 + 기본값 txt."""
    args = parse_args([
        "/tmp/images", "/tmp/labels", "-o", "/tmp/report.jsonl",
        "--label-format", "aihub",
    ])
    assert args.label_format == "aihub"

    defaults = parse_args(["/tmp/images", "/tmp/labels", "-o", "/tmp/report.jsonl"])
    assert defaults.label_format == "txt"
```

- [ ] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/bench/ -q` → 전체 통과
Run: `.venv/bin/python -m pytest tests/ -q`

- [ ] **Step 5: 커밋**

```bash
git add img2txt/bench/aihub.py tests/bench/test_aihub.py scripts/bench_ocr.py tests/bench/test_bench_cli.py
git commit -m "feat: AI Hub 페이지형 라벨 어댑터 + --label-format"
```

---

### Task 2: baseline 실측 스모크 (컨트롤러 직접 실행)

- [ ] AF_2010 세트로 50페이지 baseline 실행:

```bash
V="bench_data/023.OCR 데이터(공공)/01-1.정식개방데이터/Validation"
mkdir -p bench_data/reports
.venv/bin/python scripts/bench_ocr.py \
  "$V/01.원천데이터/VS_OCR(public)_AF_2010_5270218_0001" \
  "$V/02.라벨링데이터/VL_OCR(public)_AF_2010_5270218_0001" \
  --label-format aihub --limit 50 \
  -o bench_data/reports/baseline-2010.jsonl
```

- [ ] 검증 기준: 종료코드 0, 매칭 실패 0 (allow-skip 미사용으로 확인), error_status 레코드 0건, 요약의 3지점 CER 수치 기록 (corrected==assembled 확인 — backend=None)
- [ ] 원본 대조 1건: 리포트의 페이지 1개를 골라 이미지와 output_text/reference_text 눈으로 대조 (환각 방지 크로스 체크)

### Task 3: 전처리 레버 A/B 실측 + 판정 문서 (컨트롤러 직접 실행)

- [ ] 레버별 3회 실행 (같은 50페이지):

```bash
for lever in contrast upscale deskew; do
  .venv/bin/python scripts/bench_ocr.py \
    "$V/01.원천데이터/VS_OCR(public)_AF_2010_5270218_0001" \
    "$V/02.라벨링데이터/VL_OCR(public)_AF_2010_5270218_0001" \
    --label-format aihub --limit 50 --preprocess $lever \
    -o bench_data/reports/$lever-2010.jsonl
done
```

- [ ] 4개 리포트의 요약(raw 지점 micro CER strict/lenient, 처리시간)을 표로 비교
- [ ] 판정 규칙 (스펙 6절): baseline 대비 CER이 낮아진 레버만 "채택 후보". 처리시간 증가는 트레이드오프로 병기
- [ ] `docs/bench/2026-07-17-preprocess-ab-2010.md` 작성: 실행 조건(run_meta 인용), 비교표, 판정, 한계(50페이지 스모크, 공공문서 도메인 — 책 아님), 다음 단계(다른 연대 세트 확대 여부)
- [ ] 커밋: `docs: 전처리 A/B 실측 결과 (2010 세트 50p)` (판정 문서만 — JSONL은 bench_data라 미추적)

## 구현 순서 및 의존성

Task 1 (어댑터) → Task 2 (baseline) → Task 3 (A/B + 판정)

## 검증 기준

- Task 1: 신규 테스트 + 전체 회귀 통과
- Task 2~3: 실행 종료코드 0, error_status 0건, 판정 문서에 run_meta(run_id/dataset_hash/preprocess_config) 인용 포함 (재현성)
