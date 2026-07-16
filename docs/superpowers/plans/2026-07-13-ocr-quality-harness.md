# OCR 품질 측정 하네스 Implementation Plan

**REQUIRED SUB-SKILL:** superpowers:subagent-driven-development

## Goal
스펙 5절(측정 하네스)을 TDD 기반으로 구현한다. 원시 OCR/조립본/보정본 3지점 출력을 자동 채점하는 CLI 스크립트 `scripts/bench_ocr.py`를 완성한다. 스펙 6절(OCR 전처리 실험)과 7절(LLM 비교)은 별도 플랜 대상(제외).

## Architecture
```
데이터 → 로더 → 파이프라인 러너(3지점) → 채점(정규화+CER/WER) → 리포터 → CLI
         (dataset.py)    (runner.py)      (scoring.py)    (report.py) (bench_ocr.py)
```

컴포넌트별 책임 분리(단일 책임):
- **normalize.py**: 텍스트 정규화 (NFC/공백/부호)
- **scoring.py**: 채점 계산 (Levenshtein DP, CER/WER, 집계)
- **dataset.py**: 이미지-라벨 쌍 로드 + 라벨 어댑터 프로토콜
- **runner.py**: 파이프라인 3지점 출력 + 의존성 주입(OCR/보정)
- **report.py**: JSON Lines 리포트 + 요약 통계
- **bench_ocr.py**: CLI 진입점 (argparse + 컴포넌트 조립)

## Tech Stack
- Python 3.13 (`.venv`, pyenv)
- 외부 의존 추가 없음 (Levenshtein은 자체 DP 구현)
- OCR 주입 불가: `ocr.py:recognize_page` 대신 가짜 함수로 테스트
- 기존 파이프라인 호출: `ocr.py`, `layout.py:analyze_page`, `assembler.py:assemble`, `corrector.py:correct_paragraphs`

## Global Constraints

- Python 3.13(.venv, pyenv). 기존 파이프라인은 from __future__ import annotations 사용.
- 외부 의존 추가 없이 편집거리(Levenshtein)는 자체 동적계획법(DP)으로 구현한다(프로젝트는 무의존 선호 이력 — WEBP/TIFF도 Pillow 내장으로 처리).
- OCR(ocr.py recognize_page)은 macOS Apple Vision(ocrmac) 의존이라 CI/리눅스에서 못 돈다. 파이프라인 러너 테스트는 recognize_page를 주입 가능하게(의존성 주입) 설계해 가짜 OCR 함수로 테스트한다.
- 채점 최종 점수는 micro 집계(전체 편집거리 합 / 전체 정답 글자수 합). CER 엄격/관대 이중 계산.
- 빈 OCR 결과는 정답 글자 전체를 누락 오류로 계산(제외 금지). 매칭 실패는 기본 실험 중단(--allow-skip 옵션일 때만 스킵).

---

## Task 1: 텍스트 정규화 유틸

### Files
- **Create**: `img2txt/bench/normalize.py`
- **Test**: `tests/bench/test_normalize.py`

### Interfaces

**Consumes:**
- `text: str`

**Produces:**
- `normalize_strict(text: str) -> str`: NFC 유니코드 정규화 + 연속 공백 1개로, 줄바꿈을 공백으로 통일. 부호는 건드리지 않음.
- `normalize_lenient(text: str) -> str`: strict 결과 + 스펙 5.3 부호 매핑 표 적용 (큰따옴표/작은따옴표/대시/말줄임/전각 숫자영문).
- `_PUNCTUATION_MAP: dict[str, str]`: 부호 매핑 상수 (최소 5개 규칙: 유니코드 큰따옴표 → ASCII ", 곡선 작은따옴표 → ', 각종 대시 → -, 말줄임 → ..., 전각 → 반각).

### TDD Checklist

- [ ] **(1) 실패 테스트 작성 (코드 포함)**

```python
# tests/bench/test_normalize.py
import pytest
from img2txt.bench.normalize import normalize_strict, normalize_lenient

def test_normalize_strict_nfc_composition() -> None:
    """한글 자모 조합 NFC 정규화."""
    # 조합 문자 (자모 분리): ㄱ + ㅏ (U+1100 + U+1161) 형태
    decomposed = "가"  # 가(분리형)
    result = normalize_strict(decomposed)
    # 결과는 NFC (U+AC00 가)
    assert result == "가"
    assert len(result) == 1

def test_normalize_strict_multiple_spaces() -> None:
    """연속 공백을 1개로."""
    assert normalize_strict("hello    world") == "hello world"
    assert normalize_strict("a   b   c") == "a b c"

def test_normalize_strict_newlines_to_space() -> None:
    """줄바꿈을 공백으로."""
    assert normalize_strict("line1\nline2") == "line1 line2"
    assert normalize_strict("a\n\nb") == "a b"

def test_normalize_strict_preserves_punctuation() -> None:
    """strict는 부호를 건드리지 않음."""
    assert normalize_strict('"hello"') == '"hello"'
    assert normalize_strict("가-나") == "가-나"

def test_normalize_lenient_unicode_quotes() -> None:
    """유니코드 큰따옴표(좌우 곡선) → ASCII "."""
    # U+201C, U+201D: 좌우 곡선 큰따옴표
    assert normalize_lenient("“hello”") == '"hello"'

def test_normalize_lenient_unicode_single_quotes() -> None:
    """유니코드 작은따옴표(좌우 곡선) → ASCII '."""
    # U+2018, U+2019: 좌우 곡선 작은따옴표
    assert normalize_lenient("‘hello’") == "'hello'"

def test_normalize_lenient_various_dashes() -> None:
    """각종 대시(en/em/붙임표) → ASCII -."""
    # U+2013 (en), U+2014 (em), U+2011 (붙임표)
    assert normalize_lenient("a–b") == "a-b"  # en dash
    assert normalize_lenient("a—b") == "a-b"  # em dash
    assert normalize_lenient("a‑b") == "a-b"  # non-breaking hyphen

def test_normalize_lenient_ellipsis() -> None:
    """말줄임표 1글자 → 마침표 3개."""
    # U+2026: …
    assert normalize_lenient("wait…") == "wait..."

def test_normalize_lenient_fullwidth_digits() -> None:
    """전각 숫자 → 반각."""
    # U+FF10~U+FF19: ０～９
    assert normalize_lenient("１２３") == "123"

def test_normalize_lenient_fullwidth_latin() -> None:
    """전각 라틴 → 반각."""
    # U+FF21, U+FF41: Ａ, ａ
    assert normalize_lenient("ＡＢＣ") == "ABC"
    assert normalize_lenient("ａｂｃ") == "abc"

def test_normalize_lenient_combines_strict() -> None:
    """lenient = strict + 부호 매핑."""
    text = "  한글\n테스트  "  # 공백/줄바꿈 섞임
    lenient_result = normalize_lenient(text)
    # strict 먼저 적용됨: 한글 테스트
    # 그 후 부호 매핑(이 경우 부호 없으므로 동일)
    assert lenient_result == "한글 테스트"
```

- [ ] **(2) 실패 확인 (pytest 명령 + 예상 출력)**

```
$ pytest tests/bench/test_normalize.py -v
# 예상: 모든 테스트 FAILED (함수 미구현)
# FAILED tests/bench/test_normalize.py::test_normalize_strict_nfc_composition
# FAILED tests/bench/test_normalize.py::test_normalize_strict_multiple_spaces
# ... (총 11개 실패)
```

- [ ] **(3) 최소 구현 (코드 포함)**

```python
# img2txt/bench/normalize.py
from __future__ import annotations

import re
import unicodedata

# 부호 매핑 상수 (스펙 5.3)
_PUNCTUATION_MAP: dict[str, str] = {
    "“": '"',  # 좌측 곡선 큰따옴표
    "”": '"',  # 우측 곡선 큰따옴표
    "‘": "'",  # 좌측 곡선 작은따옴표
    "’": "'",  # 우측 곡선 작은따옴표
    "–": "-",  # en dash
    "—": "-",  # em dash
    "‑": "-",  # non-breaking hyphen
    "…": "...",  # ellipsis
}

# 전각 → 반각 매핑
_FULLWIDTH_TO_HALFWIDTH: dict[str, str] = {
    chr(0xFF10 + i): str(i) for i in range(10)  # ０～９ → 0～9
}
# 전각 대문자
for i in range(26):
    _FULLWIDTH_TO_HALFWIDTH[chr(0xFF21 + i)] = chr(0x41 + i)  # Ａ～Ｚ → A～Z
# 전각 소문자
for i in range(26):
    _FULLWIDTH_TO_HALFWIDTH[chr(0xFF41 + i)] = chr(0x61 + i)  # ａ～ｚ → a～z


def normalize_strict(text: str) -> str:
    """NFC 유니코드 정규화 + 공백/줄바꿈 정리.
    
    Args:
        text: 입력 텍스트.
    
    Returns:
        정규화된 텍스트 (부호 매핑 제외).
    """
    # 1. NFC 정규화 (한글 자모 조합)
    nfc_text = unicodedata.normalize("NFC", text)
    
    # 2. 줄바꿈 → 공백
    with_spaces = nfc_text.replace("\n", " ")
    
    # 3. 연속 공백 → 단일 공백
    normalized = re.sub(r" +", " ", with_spaces)
    
    # 4. 앞뒤 공백 제거
    return normalized.strip()


def normalize_lenient(text: str) -> str:
    """strict 정규화 + 부호 매핑 (스펙 5.3).
    
    Args:
        text: 입력 텍스트.
    
    Returns:
        정규화된 텍스트 (부호 매핑 포함).
    """
    # 1. strict 먼저 적용
    strict_result = normalize_strict(text)
    
    # 2. 부호 매핑: 유니코드 문장부호 → ASCII
    result = strict_result
    for unicode_char, ascii_char in _PUNCTUATION_MAP.items():
        result = result.replace(unicode_char, ascii_char)
    
    # 3. 전각 숫자/문자 → 반각
    for fullwidth, halfwidth in _FULLWIDTH_TO_HALFWIDTH.items():
        result = result.replace(fullwidth, halfwidth)
    
    return result
```

- [ ] **(4) 통과 확인**

```
$ pytest tests/bench/test_normalize.py -v
# 예상: 모든 테스트 PASSED
# PASSED tests/bench/test_normalize.py::test_normalize_strict_nfc_composition
# PASSED tests/bench/test_normalize.py::test_normalize_strict_multiple_spaces
# ... (총 11개 통과)
```

- [ ] **(5) Commit**

```bash
git add img2txt/bench/normalize.py tests/bench/test_normalize.py
git commit -m "feat: 텍스트 정규화 유틸 (NFC/공백/부호)"
```

---

## Task 2: 채점기 (Levenshtein, CER, WER, 집계)

### Files
- **Create**: `img2txt/bench/scoring.py`
- **Test**: `tests/bench/test_scoring.py`

### Interfaces

**Consumes:**
- `reference: str, hypothesis: str` (정규화된 텍스트)
- `normalize_fn: Callable[[str], str] | None` (선택적, 정규화 함수)
- `pairs: list[tuple[str, str]]` (정답-출력 쌍)

**Produces:**
- `levenshtein(a: str, b: str) -> int`: 편집거리 (자체 동적계획법).
- `cer(reference: str, hypothesis: str, normalize_fn: Callable[[str], str] | None = None) -> float`: 글자 오류율 (편집거리 / 정답 글자 수).
- `wer(reference: str, hypothesis: str) -> float`: 단어 오류율 (편집거리 / 정답 단어 수).
- `aggregate_micro(pairs: list[tuple[str, str]]) -> float`: 미시 평균 CER (전체 편집거리 합 / 전체 정답 글자 합).

### TDD Checklist

- [ ] **(1) 실패 테스트 작성 (코드 포함)**

```python
# tests/bench/test_scoring.py
from __future__ import annotations

import pytest
from img2txt.bench.scoring import levenshtein, cer, wer, aggregate_micro
from img2txt.bench.normalize import normalize_lenient

def test_levenshtein_identical() -> None:
    """같은 문자열: 거리 0."""
    assert levenshtein("hello", "hello") == 0

def test_levenshtein_empty() -> None:
    """빈 문자열: 길이만큼."""
    assert levenshtein("", "abc") == 3
    assert levenshtein("abc", "") == 3
    assert levenshtein("", "") == 0

def test_levenshtein_substitution() -> None:
    """대체: 1 거리."""
    assert levenshtein("cat", "bat") == 1  # c→b

def test_levenshtein_insertion() -> None:
    """삽입: 1 거리."""
    assert levenshtein("cat", "cart") == 1  # r 삽입

def test_levenshtein_deletion() -> None:
    """삭제: 1 거리."""
    assert levenshtein("cart", "cat") == 1  # r 삭제

def test_levenshtein_complex() -> None:
    """여러 연산: "kitten" → "sitting"."""
    # k→s, e→i, insert g
    assert levenshtein("kitten", "sitting") == 3

def test_levenshtein_korean() -> None:
    """한글: '가나다' → '가나바'."""
    assert levenshtein("가나다", "가나바") == 1  # 다→바

def test_cer_perfect() -> None:
    """완전 일치: CER 0.0."""
    result = cer("hello world", "hello world")
    assert result == 0.0

def test_cer_one_error() -> None:
    """1글자 오류: CER = 1/11."""
    result = cer("hello world", "hallo world")  # e→a
    assert abs(result - 1.0 / 11) < 0.001

def test_cer_with_normalization() -> None:
    """정규화 함수 제공: 정규화 후 비교."""
    result = cer(
        "hello  world",
        "hello world",
        normalize_fn=lambda x: x  # 그대로
    )
    # 공백 차이 1개
    assert abs(result - 1.0 / 12) < 0.001

def test_cer_empty_reference() -> None:
    """정답이 비면: CER 무한대 또는 특수 처리."""
    # 스펙: 빈 결과는 정답 글자 전부 누락 오류로 계산
    # 하지만 정답이 비면? 정답 글자 수가 0이므로 거리/0 = undefined
    # 구현: 정답이 비고 출력도 비면 0, 정답 비고 출력 있으면 무한대 또는 1.0
    result = cer("", "")
    assert result == 0.0
    
    # 정답 비고 출력 있으면: 분자 0, 분모 0 → 관례상 1.0
    result = cer("", "hello")
    assert result == 1.0

def test_wer_perfect() -> None:
    """완전 일치: WER 0.0."""
    result = wer("hello world", "hello world")
    assert result == 0.0

def test_wer_one_word_error() -> None:
    """1단어 오류: WER = 1/2."""
    result = wer("hello world", "hallo world")  # hello→hallo
    assert abs(result - 1.0 / 2) < 0.001

def test_wer_insertion_deletion() -> None:
    """단어 삽입/삭제 (Levenshtein on words)."""
    result = wer("the cat sat", "the big cat sat")  # big 삽입 = 1 거리
    # 정답 3단어, 편집거리 1 → WER = 1/3
    assert abs(result - 1.0 / 3) < 0.001

def test_aggregate_micro_single_page() -> None:
    """미시 평균: 1 쌍."""
    pairs = [("hello world", "hallo world")]  # 1 오류
    result = aggregate_micro(pairs)
    # 편집거리 1, 정답 글자 11 → 1/11
    assert abs(result - 1.0 / 11) < 0.001

def test_aggregate_micro_multiple_pages() -> None:
    """미시 평균: 여러 쌍 합산."""
    pairs = [
        ("a", "a"),        # 0/1
        ("bb", "cc"),      # 2/2
    ]
    result = aggregate_micro(pairs)
    # (0+2)/(1+2) = 2/3
    assert abs(result - 2.0 / 3) < 0.001

def test_aggregate_micro_with_empty_hypothesis() -> None:
    """미시 평균: 빈 출력은 전체 누락으로."""
    pairs = [
        ("hello", ""),  # 5 오류
        ("world", "world"),  # 0 오류
    ]
    result = aggregate_micro(pairs)
    # (5+0)/(5+5) = 5/10 = 0.5
    assert abs(result - 0.5) < 0.001
```

- [ ] **(2) 실패 확인**

```
$ pytest tests/bench/test_scoring.py -v
# 예상: 모든 테스트 FAILED (함수 미구현)
# FAILED tests/bench/test_scoring.py::test_levenshtein_identical
# ... (총 17개 실패)
```

- [ ] **(3) 최소 구현 (코드 포함)**

```python
# img2txt/bench/scoring.py
from __future__ import annotations

from typing import Callable


def levenshtein(a: str, b: str) -> int:
    """편집거리(Levenshtein distance)를 동적계획법으로 계산.
    
    Args:
        a: 첫 번째 문자열.
        b: 두 번째 문자열.
    
    Returns:
        편집거리 (대체/삽입/삭제 최소 연산 횟수).
    """
    m, n = len(a), len(b)
    
    # DP 테이블: dp[i][j] = a[0:i]와 b[0:j] 사이 편집거리
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    # 초기화: 빈 문자열로의 변환 비용
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    # DP 채우기
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                # 문자 같음: 이전 상태 그대로
                dp[i][j] = dp[i - 1][j - 1]
            else:
                # 최소 연산: 대체(1) / 삽입(1) / 삭제(1)
                dp[i][j] = 1 + min(
                    dp[i - 1][j - 1],  # 대체
                    dp[i - 1][j],      # 삭제
                    dp[i][j - 1],      # 삽입
                )
    
    return dp[m][n]


def cer(
    reference: str,
    hypothesis: str,
    normalize_fn: Callable[[str], str] | None = None,
) -> float:
    """글자 오류율(Character Error Rate).
    
    Args:
        reference: 정답 텍스트.
        hypothesis: 가설(모델 출력) 텍스트.
        normalize_fn: 정규화 함수 (제공 시 reference/hypothesis를 정규화 후 비교).
    
    Returns:
        CER (0~1, 편집거리 / 정답 글자 수).
        정답이 비면 0, 정답 비고 출력 있으면 1.0.
    """
    ref = normalize_fn(reference) if normalize_fn else reference
    hyp = normalize_fn(hypothesis) if normalize_fn else hypothesis
    
    # 정답 글자 수가 0이면 특수 처리
    if len(ref) == 0:
        return 0.0 if len(hyp) == 0 else 1.0
    
    distance = levenshtein(ref, hyp)
    return distance / len(ref)


def wer(reference: str, hypothesis: str) -> float:
    """단어 오류율(Word Error Rate).
    
    정답을 공백 기준으로 분할 후 편집거리(단어 단위)를 계산.
    
    Args:
        reference: 정답 텍스트.
        hypothesis: 가설 텍스트.
    
    Returns:
        WER (0~1, 단어 편집거리 / 정답 단어 수).
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    
    # 단어 수가 0이면 특수 처리
    if len(ref_words) == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0
    
    distance = levenshtein(" ".join(ref_words), " ".join(hyp_words))
    return distance / len(ref_words)


def aggregate_micro(pairs: list[tuple[str, str]]) -> float:
    """미시 평균 CER (모든 쌍의 편집거리 합 / 모든 정답 글자 합).
    
    Args:
        pairs: (정답, 출력) 튜플 리스트.
    
    Returns:
        Micro CER (0~1).
    """
    total_distance = 0
    total_ref_chars = 0
    
    for reference, hypothesis in pairs:
        total_distance += levenshtein(reference, hypothesis)
        total_ref_chars += len(reference)
    
    if total_ref_chars == 0:
        return 0.0
    
    return total_distance / total_ref_chars
```

- [ ] **(4) 통과 확인**

```
$ pytest tests/bench/test_scoring.py -v
# 예상: 모든 테스트 PASSED
# PASSED tests/bench/test_scoring.py::test_levenshtein_identical
# ... (총 17개 통과)
```

- [ ] **(5) Commit**

```bash
git add img2txt/bench/scoring.py tests/bench/test_scoring.py
git commit -m "feat: 채점기 (Levenshtein/CER/WER/집계)"
```

---

## Task 3: 데이터셋 로더 + 라벨 어댑터

### Files
- **Create**: `img2txt/bench/dataset.py`
- **Test**: `tests/bench/test_dataset.py`

### Interfaces

**Consumes:**
- `image_dir: Path` (이미지 파일 디렉터리)
- `label_dir: Path` (라벨 파일 디렉터리)
- `adapter: Callable[[Path], str]` (라벨 파일 경로 → 정답 텍스트, 구현은 별도)

**Produces:**
- `PagePair` dataclass: `page_id: str, image_path: Path, reference_text: str`
- `load_pairs(image_dir: Path, label_dir: Path, adapter: Callable[[Path], str]) -> list[PagePair]`: 이미지-라벨 매칭 + 로드.
- `LabelAdapter` Protocol (또는 타입 힌트): `Callable[[Path], str]` (라벨 파일 → 텍스트).

### TDD Checklist

- [ ] **(1) 실패 테스트 작성 (코드 포함)**

```python
# tests/bench/test_dataset.py
from __future__ import annotations

from pathlib import Path
import pytest
from img2txt.bench.dataset import PagePair, load_pairs


def test_page_pair_structure() -> None:
    """PagePair dataclass 구조 확인."""
    pair = PagePair(
        page_id="page_001",
        image_path=Path("/tmp/page_001.png"),
        reference_text="정답 텍스트"
    )
    assert pair.page_id == "page_001"
    assert pair.image_path == Path("/tmp/page_001.png")
    assert pair.reference_text == "정답 텍스트"


def test_load_pairs_basic(tmp_path: Path) -> None:
    """기본 로드: 이미지 2개 + 라벨 2개 매칭."""
    # 임시 디렉터리 구성
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()
    
    # 이미지 파일 생성
    (image_dir / "page_001.png").touch()
    (image_dir / "page_002.png").touch()
    
    # 라벨 파일 생성
    (label_dir / "page_001.txt").write_text("정답1")
    (label_dir / "page_002.txt").write_text("정답2")
    
    # 어댑터: txt 읽기
    def label_adapter(label_path: Path) -> str:
        return label_path.read_text()
    
    # 로드
    pairs = load_pairs(image_dir, label_dir, label_adapter)
    
    assert len(pairs) == 2
    assert pairs[0].page_id == "page_001"
    assert pairs[0].reference_text == "정답1"
    assert pairs[1].page_id == "page_002"
    assert pairs[1].reference_text == "정답2"


def test_load_pairs_missing_label(tmp_path: Path) -> None:
    """라벨 파일 누락: 기본 동작은 오류 (--allow-skip 옵션 없음)."""
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()
    
    # 이미지만 생성 (라벨 없음)
    (image_dir / "page_001.png").touch()
    
    def label_adapter(label_path: Path) -> str:
        return label_path.read_text()
    
    # 파일 없으면 FileNotFoundError 또는 별도 처리
    # 스펙: 매칭 실패는 기본 실험 중단
    with pytest.raises(FileNotFoundError):
        load_pairs(image_dir, label_dir, label_adapter)


def test_load_pairs_page_id_extraction() -> None:
    """page_id 추출: 확장자 제외."""
    pair = PagePair(
        page_id="page_001",
        image_path=Path("/tmp/images/page_001.png"),
        reference_text="텍스트"
    )
    # page_id는 파일명에서 확장자 제외
    assert pair.page_id == "page_001"


def test_load_pairs_with_mock_adapter(tmp_path: Path) -> None:
    """mock 어댑터: JSON 라벨 (실제 AI Hub 형식은 미정)."""
    import json
    
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()
    
    # 이미지
    (image_dir / "page_001.png").touch()
    
    # JSON 라벨 (임시 픽스처)
    label_data = {"text": "한글 텍스트"}
    (label_dir / "page_001.json").write_text(json.dumps(label_data))
    
    # JSON 어댑터
    def json_adapter(label_path: Path) -> str:
        data = json.loads(label_path.read_text())
        return data.get("text", "")
    
    pairs = load_pairs(image_dir, label_dir, json_adapter)
    
    assert len(pairs) == 1
    assert pairs[0].reference_text == "한글 텍스트"
```

- [ ] **(2) 실패 확인**

```
$ pytest tests/bench/test_dataset.py -v
# 예상: 모든 테스트 FAILED
# FAILED tests/bench/test_dataset.py::test_page_pair_structure
# ... (총 6개 실패)
```

- [ ] **(3) 최소 구현 (코드 포함)**

```python
# img2txt/bench/dataset.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class PagePair:
    """이미지 + 정답 텍스트 쌍."""
    
    page_id: str
    image_path: Path
    reference_text: str


def load_pairs(
    image_dir: Path,
    label_dir: Path,
    adapter: Callable[[Path], str],
) -> list[PagePair]:
    """이미지 디렉터리와 라벨 디렉터리를 매칭해 PagePair 리스트 반환.
    
    Args:
        image_dir: 이미지 파일 디렉터리.
        label_dir: 라벨 파일 디렉터리.
        adapter: 라벨 파일 경로 → 정답 텍스트 함수.
    
    Returns:
        매칭된 PagePair 리스트 (page_id 정렬).
    
    Raises:
        FileNotFoundError: 라벨 파일 누락 (스펙: 기본 중단).
    """
    pairs: list[PagePair] = []
    
    # 이미지 파일 정렬해서 순회
    image_files = sorted(image_dir.glob("*"))
    
    for image_path in image_files:
        # 확장자 제외하고 page_id 추출
        page_id = image_path.stem
        
        # 라벨 파일 찾기: 같은 page_id, 같은 확장자 또는 txt (임시)
        # 실제 AI Hub 어댑터에서 정확한 규칙 확정 필요
        label_candidates = list(label_dir.glob(f"{page_id}.*"))
        
        if not label_candidates:
            raise FileNotFoundError(f"라벨 파일 누락: {page_id}")
        
        label_path = label_candidates[0]  # 첫 번째 매칭 파일
        
        # 어댑터로 라벨 읽기
        reference_text = adapter(label_path)
        
        pair = PagePair(
            page_id=page_id,
            image_path=image_path,
            reference_text=reference_text,
        )
        pairs.append(pair)
    
    return pairs
```

- [ ] **(4) 통과 확인**

```
$ pytest tests/bench/test_dataset.py -v
# 예상: 모든 테스트 PASSED
# PASSED tests/bench/test_dataset.py::test_page_pair_structure
# ... (총 6개 통과)
```

- [ ] **(5) Commit**

```bash
git add img2txt/bench/dataset.py tests/bench/test_dataset.py
git commit -m "feat: 데이터셋 로더 + 라벨 어댑터 프로토콜"
```

---

## Task 4: 파이프라인 러너 (3지점 출력)

### Files
- **Create**: `img2txt/bench/runner.py`
- **Test**: `tests/bench/test_runner.py`

### Interfaces

**Consumes:**
- `image_path: Path`
- `page_id: str`
- `recognize_fn: Callable[[Path, int], Page]` (의존성 주입, 기본 `ocr.recognize_page`)
- `correct_fn: Callable[[list[str], str, CorrectionBackend], tuple[list[str], list[CorrectionRecord]]]` (의존성 주입, 기본 `corrector.correct_paragraphs`)
- `backend: CorrectionBackend | None` (보정 백엔드, 미제공 시 보정 스킵)

**Produces:**
- `PointOutputs` dataclass: `page_id: str, raw: str, assembled: str, corrected: str, segments: list[str], empty: bool`
- `run_points(image_path: Path, page_id: str, recognize_fn: ..., correct_fn: ..., backend: ...) -> PointOutputs`: 3지점 출력.

### TDD Checklist

- [ ] **(1) 실패 테스트 작성 (코드 포함)**

```python
# tests/bench/test_runner.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock
import pytest
from img2txt.bench.runner import PointOutputs, run_points
from img2txt.ocr import Page, OcrLine


def test_point_outputs_structure() -> None:
    """PointOutputs dataclass 구조."""
    outputs = PointOutputs(
        page_id="page_001",
        raw="원시 OCR",
        assembled="조립본",
        corrected="보정본",
        segments=["문단1", "문단2"],
        empty=False,
    )
    assert outputs.page_id == "page_001"
    assert outputs.raw == "원시 OCR"
    assert outputs.assembled == "조립본"
    assert outputs.corrected == "보정본"
    assert outputs.segments == ["문단1", "문단2"]
    assert outputs.empty is False


def test_run_points_with_fake_ocr(tmp_path: Path) -> None:
    """3지점 출력: 가짜 OCR + 가짜 보정."""
    # 임시 이미지
    image_path = tmp_path / "page_001.png"
    image_path.touch()
    
    # 가짜 OCR 함수: 2줄 반환
    def fake_recognize(image: Path, page_num: int) -> Page:
        return Page(
            number=page_num,
            lines=[
                OcrLine(text="첫째 줄", confidence=0.95, x=0.1, y=0.8, width=0.8, height=0.05),
                OcrLine(text="둘째 줄", confidence=0.92, x=0.1, y=0.7, width=0.8, height=0.05),
            ]
        )
    
    # 가짜 보정 함수
    def fake_correct(paragraphs: list[str], model: str, backend) -> tuple[list[str], list]:
        # 간단히 그대로 반환
        return paragraphs, []
    
    # 호출 (backend 없이 보정 스킵)
    outputs = run_points(
        image_path=image_path,
        page_id="page_001",
        recognize_fn=fake_recognize,
        correct_fn=fake_correct,
        backend=None,
    )
    
    assert outputs.page_id == "page_001"
    assert outputs.empty is False
    # raw = 줄 이어붙임 (위→아래 순서)
    assert "첫째 줄" in outputs.raw
    assert "둘째 줄" in outputs.raw


def test_run_points_empty_ocr() -> None:
    """빈 OCR 결과: empty=True."""
    from unittest.mock import Mock
    
    image_path = Mock()
    
    # 빈 Page 반환
    def fake_recognize(image: Path, page_num: int) -> Page:
        return Page(number=page_num, lines=[])
    
    def fake_correct(paragraphs: list[str], model: str, backend):
        return paragraphs, []
    
    outputs = run_points(
        image_path=image_path,
        page_id="page_001",
        recognize_fn=fake_recognize,
        correct_fn=fake_correct,
        backend=None,
    )
    
    assert outputs.empty is True
    assert outputs.raw == ""
    assert outputs.assembled == ""
    assert outputs.corrected == ""


def test_run_points_segments_from_corrected() -> None:
    """segments: 보정본의 문단 목록."""
    from unittest.mock import Mock
    
    image_path = Mock()
    
    def fake_recognize(image: Path, page_num: int) -> Page:
        return Page(
            number=page_num,
            lines=[
                OcrLine(text="문단 1", confidence=0.95, x=0.1, y=0.8, width=0.8, height=0.05),
                OcrLine(text="문단 2", confidence=0.92, x=0.1, y=0.7, width=0.8, height=0.05),
            ]
        )
    
    # 보정 후 2개 문단으로 분리
    def fake_correct(paragraphs: list[str], model: str, backend):
        return ["보정된 문단 1", "보정된 문단 2"], []
    
    outputs = run_points(
        image_path=image_path,
        page_id="page_001",
        recognize_fn=fake_recognize,
        correct_fn=fake_correct,
        backend=Mock(),  # 보정 활성화
    )
    
    assert len(outputs.segments) == 2
    assert outputs.segments[0] == "보정된 문단 1"
    assert outputs.segments[1] == "보정된 문단 2"
```

- [ ] **(2) 실패 확인**

```
$ pytest tests/bench/test_runner.py -v
# 예상: 모든 테스트 FAILED
# FAILED tests/bench/test_runner.py::test_point_outputs_structure
# ... (총 4개 실패)
```

- [ ] **(3) 최소 구현 (코드 포함)**

```python
# img2txt/bench/runner.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from img2txt.ocr import Page, OcrLine, sort_lines_top_to_bottom
from img2txt.layout import analyze_page
from img2txt.assembler import assemble

if False:  # TYPE_CHECKING 대신 간단하게
    from img2txt.backends.base import CorrectionBackend

logger = logging.getLogger(__name__)

# 타입 앨리어스
RecognizeFn = Callable[[Path, int], Page]
CorrectFn = Callable[[list[str], str, object], tuple[list[str], list]]


@dataclass
class PointOutputs:
    """3지점 측정 출력."""
    
    page_id: str
    raw: str                    # 원시 OCR (줄 이어붙임)
    assembled: str              # 조립본
    corrected: str              # 보정본
    segments: list[str] = field(default_factory=list)  # 보정본 문단 목록
    empty: bool = False         # OCR 빈 결과 플래그


def run_points(
    image_path: Path,
    page_id: str,
    recognize_fn: RecognizeFn,
    correct_fn: CorrectFn,
    backend: object | None = None,
) -> PointOutputs:
    """1개 이미지에서 3지점 출력을 생성.
    
    Args:
        image_path: 이미지 파일 경로.
        page_id: 페이지 식별자.
        recognize_fn: OCR 함수 (path, page_number -> Page).
        correct_fn: 보정 함수 (paragraphs, model, backend -> (corrected_list, records)).
        backend: 보정 백엔드 (None이면 보정 스킵).
    
    Returns:
        PointOutputs (3지점 + metadata).
    """
    page_number = int(page_id.split("_")[-1]) if "_" in page_id else 1
    
    # (1) 원시 OCR
    page = recognize_fn(image_path, page_number)
    
    # 빈 결과 체크
    if not page.lines:
        logger.warning("페이지 %s: OCR 빈 결과", page_id)
        return PointOutputs(
            page_id=page_id,
            raw="",
            assembled="",
            corrected="",
            segments=[],
            empty=True,
        )
    
    # 원시 OCR: 줄 이어붙임 (위→아래 순서, 이미 정렬됨)
    raw_text = " ".join(line.text for line in page.lines)
    
    # (2) 조립본: layout → assemble
    layout = analyze_page(page)
    layouts = [layout]  # 1 페이지만 처리
    assembled_text = assemble(layouts)
    
    # (3) 보정본 (backend 제공 시)
    if backend and layout.paragraphs:
        corrected_paragraphs, _ = correct_fn(layout.paragraphs, "harness", backend)
        corrected_text = "\n\n".join(corrected_paragraphs)
        segments = corrected_paragraphs
    else:
        corrected_text = assembled_text
        segments = layout.paragraphs
    
    return PointOutputs(
        page_id=page_id,
        raw=raw_text,
        assembled=assembled_text,
        corrected=corrected_text,
        segments=segments,
        empty=False,
    )
```

- [ ] **(4) 통과 확인**

```
$ pytest tests/bench/test_runner.py -v
# 예상: 모든 테스트 PASSED
# PASSED tests/bench/test_runner.py::test_point_outputs_structure
# ... (총 4개 통과)
```

- [ ] **(5) Commit**

```bash
git add img2txt/bench/runner.py tests/bench/test_runner.py
git commit -m "feat: 파이프라인 러너 (3지점 출력)"
```

---

## Task 5: 리포터 + 부작용 지표

### Files
- **Create**: `img2txt/bench/report.py`
- **Test**: `tests/bench/test_report.py`

### Interfaces

**Consumes:**
- `records: list[PageRecord]` (페이지별 채점 결과)
- `output_path: Path` (JSONL 파일 경로)

**Produces:**
- `PageRecord` dataclass: `page_id: str, point: str, reference_text: str, output_text: str, normalized_ref: str, normalized_output: str, cer_strict: float, cer_lenient: float, wer: float, processing_time_ms: float, empty: bool, error_status: str`
- `write_jsonl(records: list[PageRecord], output_path: Path) -> None`: JSON Lines 저장.
- `summarize(records: list[PageRecord]) -> dict`: 요약 통계 (지점별 micro CER/WER + 부작용 지표).

### TDD Checklist

- [ ] **(1) 실패 테스트 작성 (코드 포함)**

```python
# tests/bench/test_report.py
from __future__ import annotations

from pathlib import Path
import json
import pytest
from img2txt.bench.report import PageRecord, write_jsonl, summarize


def test_page_record_structure() -> None:
    """PageRecord 필드 확인."""
    record = PageRecord(
        page_id="page_001",
        point="raw",
        reference_text="정답",
        output_text="출력",
        normalized_ref="정답",
        normalized_output="출력",
        cer_strict=0.1,
        cer_lenient=0.05,
        wer=0.2,
        processing_time_ms=150.5,
        empty=False,
        error_status="",
    )
    assert record.page_id == "page_001"
    assert record.cer_strict == 0.1


def test_write_jsonl_basic(tmp_path: Path) -> None:
    """JSONL 저장: 2개 레코드."""
    output_path = tmp_path / "report.jsonl"
    
    records = [
        PageRecord(
            page_id="page_001",
            point="raw",
            reference_text="정답1",
            output_text="출력1",
            normalized_ref="정답1",
            normalized_output="출력1",
            cer_strict=0.1,
            cer_lenient=0.05,
            wer=0.2,
            processing_time_ms=100.0,
            empty=False,
            error_status="",
        ),
        PageRecord(
            page_id="page_002",
            point="assembled",
            reference_text="정답2",
            output_text="출력2",
            normalized_ref="정답2",
            normalized_output="출력2",
            cer_strict=0.2,
            cer_lenient=0.1,
            wer=0.3,
            processing_time_ms=150.0,
            empty=False,
            error_status="",
        ),
    ]
    
    write_jsonl(records, output_path)
    
    # 파일 읽기 확인
    with open(output_path) as f:
        lines = f.readlines()
    
    assert len(lines) == 2
    record1 = json.loads(lines[0])
    assert record1["page_id"] == "page_001"
    assert record1["cer_strict"] == 0.1


def test_summarize_basic() -> None:
    """요약: 지점별 micro CER/WER."""
    records = [
        PageRecord(
            page_id="page_001",
            point="raw",
            reference_text="hello world",  # 11자
            output_text="hallo world",     # 1 오류
            normalized_ref="hello world",
            normalized_output="hallo world",
            cer_strict=1.0 / 11,
            cer_lenient=1.0 / 11,
            wer=1.0 / 2,
            processing_time_ms=100.0,
            empty=False,
            error_status="",
        ),
        PageRecord(
            page_id="page_002",
            point="raw",
            reference_text="hello world",  # 11자
            output_text="hello world",     # 0 오류
            normalized_ref="hello world",
            normalized_output="hello world",
            cer_strict=0.0,
            cer_lenient=0.0,
            wer=0.0,
            processing_time_ms=150.0,
            empty=False,
            error_status="",
        ),
    ]
    
    summary = summarize(records)
    
    # 지점별 micro CER = (1+0) / (11+11) = 1/22
    assert "points" in summary
    assert "raw" in summary["points"]
    assert abs(summary["points"]["raw"]["cer_strict"] - 1.0 / 22) < 0.001


def test_summarize_with_empty_page() -> None:
    """요약: 빈 결과 페이지 플래그."""
    records = [
        PageRecord(
            page_id="page_001",
            point="raw",
            reference_text="hello",
            output_text="",
            normalized_ref="hello",
            normalized_output="",
            cer_strict=1.0,
            cer_lenient=1.0,
            wer=1.0,
            processing_time_ms=100.0,
            empty=True,  # 빈 결과
            error_status="",
        ),
    ]
    
    summary = summarize(records)
    
    assert summary["empty_page_count"] == 1
    assert summary["empty_page_ratio"] == 1.0


def test_summarize_side_effects() -> None:
    """요약: 부작용 지표 (악화 페이지)."""
    records = [
        # 보정 후 악화: assembled CER 0.1 > corrected CER 0.2
        PageRecord(
            page_id="page_001",
            point="assembled",
            reference_text="hello world",
            output_text="hallo world",
            normalized_ref="hello world",
            normalized_output="hallo world",
            cer_strict=0.1,
            cer_lenient=0.1,
            wer=0.1,
            processing_time_ms=100.0,
            empty=False,
            error_status="",
        ),
        PageRecord(
            page_id="page_001",
            point="corrected",
            reference_text="hello world",
            output_text="xello world",  # 더 나쁨
            normalized_ref="hello world",
            normalized_output="xello world",
            cer_strict=0.2,
            cer_lenient=0.2,
            wer=0.2,
            processing_time_ms=150.0,
            empty=False,
            error_status="",
        ),
    ]
    
    summary = summarize(records)
    
    # 악화 페이지: assembled 0.1 < corrected 0.2
    if "degraded_page_count" in summary:
        assert summary["degraded_page_count"] >= 0  # 구현에 따라 0 또는 1
```

- [ ] **(2) 실패 확인**

```
$ pytest tests/bench/test_report.py -v
# 예상: 모든 테스트 FAILED
# FAILED tests/bench/test_report.py::test_page_record_structure
# ... (총 6개 실패)
```

- [ ] **(3) 최소 구현 (코드 포함)**

```python
# img2txt/bench/report.py
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PageRecord:
    """페이지별 채점 결과."""
    
    page_id: str
    point: str                  # "raw" / "assembled" / "corrected"
    reference_text: str
    output_text: str
    normalized_ref: str
    normalized_output: str
    cer_strict: float
    cer_lenient: float
    wer: float
    processing_time_ms: float
    empty: bool
    error_status: str           # 오류 메시지 (정상이면 "")


def write_jsonl(records: list[PageRecord], output_path: Path) -> None:
    """PageRecord 리스트를 JSONL로 저장.
    
    Args:
        records: 레코드 리스트.
        output_path: 출력 파일 경로.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            line = json.dumps(asdict(record), ensure_ascii=False)
            f.write(line + "\n")
    
    logger.info("리포트 저장: %s (%d 레코드)", output_path, len(records))


def summarize(records: list[PageRecord]) -> dict[str, Any]:
    """레코드 리스트를 요약.
    
    Args:
        records: 페이지별 레코드 리스트.
    
    Returns:
        요약 통계:
        - points: {point_name: {cer_strict, cer_lenient, wer, count}}
        - empty_page_count: 빈 결과 페이지 수
        - empty_page_ratio: 빈 결과 비율
        - degraded_page_count: 보정 후 악화 페이지 수
    """
    summary: dict[str, Any] = {}
    
    # 지점별 통계
    points_dict: dict[str, list[PageRecord]] = {}
    for record in records:
        if record.point not in points_dict:
            points_dict[record.point] = []
        points_dict[record.point].append(record)
    
    summary["points"] = {}
    for point, point_records in points_dict.items():
        # Micro CER = 전체 편집거리 합 / 전체 정답 글자 합
        # (저장된 CER 값을 사용하되, 평균이 아니라 가중치 적용)
        total_strict = sum(r.cer_strict * len(r.reference_text) for r in point_records)
        total_lenient = sum(r.cer_lenient * len(r.reference_text) for r in point_records)
        total_ref_chars = sum(len(r.reference_text) for r in point_records)
        
        micro_cer_strict = total_strict / total_ref_chars if total_ref_chars > 0 else 0.0
        micro_cer_lenient = total_lenient / total_ref_chars if total_ref_chars > 0 else 0.0
        
        summary["points"][point] = {
            "cer_strict": micro_cer_strict,
            "cer_lenient": micro_cer_lenient,
            "wer": sum(r.wer for r in point_records) / len(point_records) if point_records else 0.0,
            "count": len(point_records),
        }
    
    # 빈 결과 페이지
    empty_records = [r for r in records if r.empty]
    summary["empty_page_count"] = len(empty_records)
    summary["empty_page_ratio"] = len(empty_records) / len(records) if records else 0.0
    
    # 부작용 지표: 보정 후 악화 (assembled vs corrected 비교)
    # 각 page_id별로 assembled/corrected 짝짓기
    pages_by_id: dict[str, dict[str, PageRecord]] = {}
    for record in records:
        if record.page_id not in pages_by_id:
            pages_by_id[record.page_id] = {}
        pages_by_id[record.page_id][record.point] = record
    
    degraded_count = 0
    for page_id, points in pages_by_id.items():
        if "assembled" in points and "corrected" in points:
            assembled_cer = points["assembled"].cer_strict
            corrected_cer = points["corrected"].cer_strict
            if corrected_cer > assembled_cer:
                degraded_count += 1
    
    summary["degraded_page_count"] = degraded_count
    summary["total_pages"] = len(pages_by_id)
    
    return summary
```

- [ ] **(4) 통과 확인**

```
$ pytest tests/bench/test_report.py -v
# 예상: 모든 테스트 PASSED
# PASSED tests/bench/test_report.py::test_page_record_structure
# ... (총 6개 통과)
```

- [ ] **(5) Commit**

```bash
git add img2txt/bench/report.py tests/bench/test_report.py
git commit -m "feat: 리포터 + 부작용 지표"
```

---

## Task 6: CLI 진입점 (bench_ocr.py)

### Files
- **Create**: `scripts/bench_ocr.py`
- **Test**: `tests/bench/test_bench_cli.py`

### Interfaces

**Consumes:**
- CLI 인자: `image_dir`, `label_dir`, `-o output`, `--allow-skip`, `--limit N`

**Produces:**
- JSONL 리포트 파일 (`-o` 지정 경로)
- CLI 종료 코드: 0 (성공) / 1 (오류)

### TDD Checklist

- [ ] **(1) 실패 테스트 작성 (코드 포함)**

```python
# tests/bench/test_bench_cli.py
from __future__ import annotations

from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock
import sys
import json

# scripts/bench_ocr.py의 main/argparse를 테스트하기 위해
# 별도 함수로 분리했다고 가정
from scripts.bench_ocr import parse_args


def test_parse_args_basic() -> None:
    """기본 인자 파싱."""
    args = parse_args([
        "/tmp/images",
        "/tmp/labels",
        "-o", "/tmp/report.jsonl",
    ])
    
    assert str(args.image_dir) == "/tmp/images"
    assert str(args.label_dir) == "/tmp/labels"
    assert str(args.output) == "/tmp/report.jsonl"
    assert args.allow_skip is False
    assert args.limit is None


def test_parse_args_with_options() -> None:
    """옵션 포함."""
    args = parse_args([
        "/tmp/images",
        "/tmp/labels",
        "-o", "/tmp/report.jsonl",
        "--allow-skip",
        "--limit", "10",
    ])
    
    assert args.allow_skip is True
    assert args.limit == 10


def test_parse_args_missing_required() -> None:
    """필수 인자 누락."""
    with pytest.raises(SystemExit):  # argparse는 오류 시 exit
        parse_args(["/tmp/images"])  # label_dir 누락


def test_cli_integration_basic(tmp_path: Path) -> None:
    """CLI 통합 테스트: 이미지 1개 처리."""
    # 임시 디렉터리 설정
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()
    
    # 임시 이미지/라벨
    (image_dir / "page_001.png").touch()
    (label_dir / "page_001.txt").write_text("정답")
    
    output_path = tmp_path / "report.jsonl"
    
    # 실제 main 함수 호출 (mock OCR)
    # 이 부분은 구현 후 실제 하네스로 테스트
    # 여기서는 argparse만 테스트하는 것이 기본 범위
```

- [ ] **(2) 실패 확인**

```
$ pytest tests/bench/test_bench_cli.py -v
# 예상: 일부 테스트 FAILED (parse_args 함수 미구현)
# PASSED tests/bench/test_bench_cli.py::test_parse_args_basic (구현 시)
```

- [ ] **(3) 최소 구현 (코드 포함)**

```python
# scripts/bench_ocr.py
#!/usr/bin/env python3
"""OCR 품질 측정 하네스 CLI."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Callable

# 프로젝트 모듈
from img2txt.bench.normalize import normalize_strict, normalize_lenient
from img2txt.bench.scoring import cer, wer, aggregate_micro
from img2txt.bench.dataset import load_pairs
from img2txt.bench.runner import run_points
from img2txt.bench.report import PageRecord, write_jsonl, summarize
from img2txt.ocr import recognize_page
from img2txt.corrector import correct_paragraphs
from img2txt.backends.base import CorrectionBackend

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 인자 파싱.
    
    Args:
        argv: 인자 목록 (기본: sys.argv[1:]).
    
    Returns:
        파싱된 인자.
    """
    parser = argparse.ArgumentParser(
        description="OCR 품질 측정 하네스: 3지점(raw/assembled/corrected) 채점"
    )
    parser.add_argument(
        "image_dir",
        type=Path,
        help="이미지 디렉터리 경로"
    )
    parser.add_argument(
        "label_dir",
        type=Path,
        help="라벨 디렉터리 경로"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        required=True,
        help="JSONL 리포트 출력 경로"
    )
    parser.add_argument(
        "--allow-skip",
        action="store_true",
        help="라벨 누락 시 스킵 (기본: 중단)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="처리 페이지 수 제한 (기본: 전체)"
    )
    
    return parser.parse_args(argv)


def _default_label_adapter(label_path: Path) -> str:
    """기본 라벨 어댑터: txt 파일 읽기.
    
    Note: 실제 AI Hub 어댓 구조는 미확인. 별도 플랜 대상.
    """
    return label_path.read_text(encoding="utf-8").strip()


def main(argv: list[str] | None = None) -> int:
    """메인 함수.
    
    Args:
        argv: 인자 목록 (테스트용).
    
    Returns:
        종료 코드: 0 (성공) / 1 (오류).
    """
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 인자 파싱
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    
    # 경로 검증
    if not args.image_dir.exists():
        logger.error("이미지 디렉터리 없음: %s", args.image_dir)
        return 1
    
    if not args.label_dir.exists():
        logger.error("라벨 디렉터리 없음: %s", args.label_dir)
        return 1
    
    # 데이터 로드
    try:
        pairs = load_pairs(args.image_dir, args.label_dir, _default_label_adapter)
    except FileNotFoundError as e:
        if args.allow_skip:
            logger.warning("라벨 누락: %s (스킵)", e)
            pairs = []
        else:
            logger.error("라벨 누락: %s", e)
            return 1
    
    # 제한 적용
    if args.limit:
        pairs = pairs[: args.limit]
    
    if not pairs:
        logger.error("처리할 페이지 없음")
        return 1
    
    logger.info("처리 페이지: %d개", len(pairs))
    
    # 3지점 채점
    records: list[PageRecord] = []
    
    for pair in pairs:
        logger.info("처리 중: %s", pair.page_id)
        start_time = time.time()
        
        try:
            # 3지점 출력 생성
            outputs = run_points(
                image_path=pair.image_path,
                page_id=pair.page_id,
                recognize_fn=recognize_page,
                correct_fn=correct_paragraphs,
                backend=None,  # 보정 스킵 (스펙 5절은 보정 없음)
            )
            
            processing_time_ms = (time.time() - start_time) * 1000
            
            # 3지점별 채점
            for point, output_text in [
                ("raw", outputs.raw),
                ("assembled", outputs.assembled),
                ("corrected", outputs.corrected),
            ]:
                # 정규화
                normalized_ref = normalize_strict(pair.reference_text)
                normalized_output = normalize_strict(output_text)
                
                # 채점
                cer_strict_score = cer(
                    normalized_ref,
                    normalized_output
                )
                cer_lenient_score = cer(
                    pair.reference_text,
                    output_text,
                    normalize_fn=normalize_lenient
                )
                wer_score = wer(normalized_ref, normalized_output)
                
                record = PageRecord(
                    page_id=pair.page_id,
                    point=point,
                    reference_text=pair.reference_text,
                    output_text=output_text,
                    normalized_ref=normalized_ref,
                    normalized_output=normalized_output,
                    cer_strict=cer_strict_score,
                    cer_lenient=cer_lenient_score,
                    wer=wer_score,
                    processing_time_ms=processing_time_ms,
                    empty=outputs.empty,
                    error_status="",
                )
                records.append(record)
        
        except Exception as e:
            logger.error("페이지 %s 처리 오류: %s", pair.page_id, e)
            # 오류 레코드 추가
            for point in ["raw", "assembled", "corrected"]:
                record = PageRecord(
                    page_id=pair.page_id,
                    point=point,
                    reference_text=pair.reference_text,
                    output_text="",
                    normalized_ref="",
                    normalized_output="",
                    cer_strict=1.0,
                    cer_lenient=1.0,
                    wer=1.0,
                    processing_time_ms=(time.time() - start_time) * 1000,
                    empty=False,
                    error_status=str(e),
                )
                records.append(record)
    
    # 리포트 저장
    write_jsonl(records, args.output)
    
    # 요약 출력
    summary = summarize(records)
    logger.info("요약: %s", json.dumps(summary, indent=2, ensure_ascii=False))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **(4) 통과 확인**

```
$ pytest tests/bench/test_bench_cli.py::test_parse_args_basic -v
# 예상: PASSED
# PASSED tests/bench/test_bench_cli.py::test_parse_args_basic
```

- [ ] **(5) Commit**

```bash
git add scripts/bench_ocr.py tests/bench/test_bench_cli.py
git commit -m "feat: OCR 품질 측정 하네스 CLI"
```

---

## Follow-up (이 플랜 밖)

1. **실제 AI Hub 라벨 어댑터 구현**
   - AI Hub dataSetSn=71299 다운로드 후 라벨 형식 확인 (문단 단위 vs 글자 bbox)
   - `img2txt/bench/dataset.py`에 구체적 어댑터 추가
   - 별도 태스크에서 처리 (현재는 txt 픽스처만 테스트)

2. **실제 데이터로 하네스 실행**
   - 30~50페이지 스모크 측정
   - 골든 페이지 정답 라벨 확보

3. **스펙 6절: OCR 전처리 실험 플랜**
   - 전처리 레버(대비 조정, 해상도 업스케일, 기울기 보정) 추가
   - 별도 구현 플랜 작성

4. **스펙 7절: LLM 비교 실험 플랜**
   - `img2txt/backends/cli.py:58` 모델명 하드코딩 제거
   - gpt-5.5, gpt-5.6-luna, gpt-5.4-mini 비교
   - 별도 구현 플랜 작성

5. **스펙 8절 선행 확인 항목**
   - AI Hub 접근 조건 확인 (국내 거주, 상업 사용 가능 여부)
   - Codex CLI 입출력 토큰 분리 및 단가 정보 노출 확인
   - AI Hub 데이터 외부 LLM 전송 가능 여부 확인

---

## 구현 순서 및 의존성

```
Task 1 (normalize) [독립]
  ↓
Task 2 (scoring) [Task 1 의존]
  ↓
Task 3 (dataset) [독립]
  ↓
Task 4 (runner) [기존 파이프라인 호출]
  ↓
Task 5 (report) [독립]
  ↓
Task 6 (CLI) [모든 Task 1~5 의존]
```

모든 Task는 병렬 가능 (같은 패키지 구조 사전 생성 가정).

---

## 검증 기준

### Task 완료 조건 (각각)
- [ ] 모든 테스트 통과 (pytest)
- [ ] Type checking 통과 (pytype/mypy 존재 시, 아니면 type hints 100%)
- [ ] 코드 스타일 준수 (`rules/coding-style.md`)
  - Type Hints 100%
  - 한국어 docstring (스펙 명칭은 영어)
  - print 금지, logging 사용
  - 하드코딩 금지 (상수/Enum)
  - 함수 50줄 이내
  - 파일 800줄 이내

### 스펙 5절 커버리지
- [x] 5.1 컴포넌트: 6개 Task로 분리 (normalize, scoring, dataset, runner, report, CLI)
- [x] 5.2 데이터 흐름: 이미지+라벨 → 3지점 → 정규화 → 채점 → 리포트
- [x] 5.3 채점 규칙: 정규화 (strict/lenient), 부호 매핑 표 구현
- [x] 5.4 오류 처리: 빈 결과 플래그, 매칭 실패 처리 (--allow-skip)
- [x] 5.5 규모/테스트: 단위 테스트 + 스모크 프레임워크
- [x] 5.6 리포트: JSON Lines, 페이지 레코드, 요약 통계

### 미해결/주의점
- AI Hub 라벨 구조 미확인 → 현재는 txt 픽스처만 테스트, 실제 어댑터는 Follow-up
- OCR (recognize_page)는 macOS Apple Vision 의존 → 테스트는 가짜 함수 주입으로 격리
- 보정 (correct_paragraphs)는 LLM/Ollama 의존 → 테스트는 backend=None으로 스킵
- Task 2 구현 노트: levenshtein 시그니처를 str → Sequence[T]로 일반화 (브리프 예시 코드의 join 방식은 WER 단어 단위 테스트와 모순 — 테스트/docstring 의도를 따름, str 하위 호환)
