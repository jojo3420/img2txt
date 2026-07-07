# 책 스캔 OCR 정식 구현 계획 (convert + correct)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 책 스캔 jpg 폴더를 읽기 좋은 연속 텍스트로 바꾸는 `convert` 도구와, 로컬 LLM(Ollama)으로 OCR 오류를 보정하는 `correct` 도구를 정식 품질로 구현한다.

**Architecture:** Apple Vision(ocrmac)의 bounding box 좌표로 꼬리말 제거/제목 분류/문단 복원을 수행하는 순수 로직(layout, assembler)과 I/O(scanner, ocr, writer, corrector)를 분리한다. layout/assembler는 OCR 없이 합성 OcrLine으로 단위 테스트한다. 스펙: `docs/superpowers/specs/2026-07-07-korean-ocr-formal-design.md` (듀얼 리뷰 Must 3건+Should 8건 반영판).

**Tech Stack:** Python 3.13 (`.venv`), ocrmac 1.0.1, pillow 12.3.0 (둘 다 설치됨), pytest (Task 1에서 설치), Ollama HTTP API는 표준 라이브러리 `urllib`로 호출 (신규 런타임 의존성 0).

## Global Constraints

- 모든 명령은 프로젝트 루트(`/Users/joel.silver/Workspace/gitroom/python/img2txt`)에서 실행. Python은 `.venv/bin/python`, pytest는 `.venv/bin/pytest`.
- 타입 힌트 100%, docstring은 한국어, `print` 금지(`logging` 사용. 예외: `scripts/` 하위 일회성 캘리브레이션 도구), 하드코딩 금지(이름 있는 상수, 상태값은 Enum).
- 모든 파일 입출력은 `encoding="utf-8"` 고정. 기존 출력 파일은 덮어쓴다.
- `ocrmac`은 함수 안에서 지연 임포트한다 (macOS 외 환경에서 correct 도구가 import 단계에서 죽지 않게). 모듈 상단 임포트 금지.
- layout 임계값 4개(`FOOTER_BAND`, `FOOTER_MAX_WIDTH_RATIO`, `INDENT_MIN`, `TITLE_HEIGHT_RATIO`)는 Task 3 캘리브레이션에서 실측으로 확정하고 근거 주석을 단다. layout 함수는 임계값을 파라미터(기본값=모듈 상수)로 받아 테스트가 상수 변경에 흔들리지 않게 한다.
- 좌표계: Vision 정규화 좌표(0~1), 원점은 좌하단. y가 클수록 위쪽.
- 커밋 형식: `<타입>: <설명>` (feat/fix/refactor/docs/test/chore).
- 실측 이미지 폴더: `/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장` (jpg 31장, 파일명 마지막 숫자 2~32).
- PoC 산출물 `ocr_book.py`는 Task 11에서 삭제한다. 그 전까지 수정하지 않는다.

---

### Task 1: 프로젝트 골격 + scanner (이미지 수집/자연 정렬)

**Files:**
- Create: `pyproject.toml`, `img2txt/__init__.py`, `img2txt/scanner.py`
- Test: `tests/__init__.py`(빈 파일), `tests/test_scanner.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `scanner.collect_images(input_dir: Path) -> list[Path]`, `scanner.extract_page_number(path: Path) -> int | None` — Task 7의 cli가 사용

- [ ] **Step 1: pytest 설치 + 설정 파일 작성**

```bash
.venv/bin/pip install pytest
```

`pyproject.toml` 생성:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
markers = [
    "macos: macOS 전용 실제 OCR 통합 테스트 (CI 제외 가능)",
]
```

`img2txt/__init__.py` 생성:

```python
"""책 스캔 OCR 변환-보정 도구 패키지."""
```

`tests/__init__.py`는 빈 파일로 생성.

- [ ] **Step 2: 실패하는 테스트 작성** — `tests/test_scanner.py`

```python
"""scanner 테스트: 자연 정렬, 확장자 허용 폭, 숫자 없는 파일, 빈 폴더."""
from pathlib import Path

from img2txt.scanner import collect_images, extract_page_number


def _touch(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(b"")
    return path


def test_natural_sort_2_before_10(tmp_path: Path) -> None:
    _touch(tmp_path, "책 - 10.jpg")
    _touch(tmp_path, "책 - 2.jpg")
    assert [p.name for p in collect_images(tmp_path)] == ["책 - 2.jpg", "책 - 10.jpg"]


def test_uppercase_and_jpeg_collected(tmp_path: Path) -> None:
    _touch(tmp_path, "scan - 4.jpeg")
    _touch(tmp_path, "scan - 3.JPG")
    _touch(tmp_path, "노트.txt")
    assert [p.name for p in collect_images(tmp_path)] == ["scan - 3.JPG", "scan - 4.jpeg"]


def test_file_without_number_goes_last(tmp_path: Path) -> None:
    _touch(tmp_path, "표지.jpg")
    _touch(tmp_path, "책 - 2.jpg")
    assert [p.name for p in collect_images(tmp_path)] == ["책 - 2.jpg", "표지.jpg"]


def test_empty_folder_returns_empty_list(tmp_path: Path) -> None:
    assert collect_images(tmp_path) == []


def test_extract_last_number_with_multiple_numbers() -> None:
    assert extract_page_number(Path("1,2,3장 - 15.jpg")) == 15
    assert extract_page_number(Path("표지.jpg")) is None
```

- [ ] **Step 3: 실패 확인**

Run: `.venv/bin/pytest tests/test_scanner.py -v`
Expected: 전부 FAIL 또는 collection error — `ModuleNotFoundError: No module named 'img2txt.scanner'`

- [ ] **Step 4: 구현** — `img2txt/scanner.py`

```python
"""책 스캔 이미지 수집과 페이지 순서 정렬."""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg"})
_LAST_NUMBER_PATTERN: re.Pattern[str] = re.compile(r"(\d+)(?!.*\d)")


def extract_page_number(path: Path) -> int | None:
    """파일명(stem)의 마지막 숫자를 페이지 번호로 추출한다. 없으면 None."""
    match = _LAST_NUMBER_PATTERN.search(path.stem)
    return int(match.group(1)) if match else None


def collect_images(input_dir: Path) -> list[Path]:
    """jpg/jpeg(대소문자 무시)를 모아 파일명 마지막 숫자 기준 자연 정렬한다.

    숫자가 없는 파일은 warning 후 맨 뒤에 이름순으로 배치한다 (스펙 7절).
    """
    images = [
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    numbered = sorted(
        (path for path in images if extract_page_number(path) is not None),
        key=lambda path: extract_page_number(path) or 0,
    )
    unnumbered = sorted(path for path in images if extract_page_number(path) is None)
    for path in unnumbered:
        logger.warning("파일명에 숫자가 없어 맨 뒤에 배치: %s", path.name)
    return numbered + unnumbered
```

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/pytest tests/test_scanner.py -v`
Expected: 5 passed

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml img2txt/__init__.py img2txt/scanner.py tests/__init__.py tests/test_scanner.py
git commit -m "feat: img2txt 패키지 골격과 scanner(자연 정렬) 구현"
```

---

### Task 2: 데이터 모델 + ocr (ocrmac 래핑, y좌표 정렬)

**Files:**
- Create: `img2txt/ocr.py`
- Test: `tests/test_integration_ocr.py`

**Interfaces:**
- Consumes: 없음
- Produces: `OcrLine(text: str, confidence: float, x: float, y: float, width: float, height: float)` (frozen dataclass, `y_center` property 포함), `Page(number: int, lines: list[OcrLine])`, `sort_lines_top_to_bottom(lines: list[OcrLine]) -> list[OcrLine]`, `recognize_page(image_path: Path, page_number: int) -> Page` — Task 3~7이 사용

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_integration_ocr.py`

정렬은 순수 함수라 합성 데이터로, 실제 OCR은 macos marker로 검증한다.

```python
"""ocr 테스트: y좌표 정렬(단위) + 실제 이미지 1장 OCR(macOS 통합)."""
from pathlib import Path

import pytest

from img2txt.ocr import OcrLine, recognize_page, sort_lines_top_to_bottom

SAMPLE_IMAGE = Path(
    "/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장/주식시장을 이긴 전략들 - 10.jpg"
)


def _line(text: str, y: float) -> OcrLine:
    return OcrLine(text=text, confidence=1.0, x=0.1, y=y, width=0.8, height=0.02)


def test_sort_lines_top_to_bottom() -> None:
    lines = [_line("아래", 0.1), _line("위", 0.9), _line("중간", 0.5)]
    assert [l.text for l in sort_lines_top_to_bottom(lines)] == ["위", "중간", "아래"]


@pytest.mark.macos
def test_recognize_real_page() -> None:
    if not SAMPLE_IMAGE.exists():
        pytest.skip("실측 이미지 없음")
    page = recognize_page(SAMPLE_IMAGE, 10)
    assert page.number == 10
    assert len(page.lines) > 10
    assert any("주식시장" in line.text for line in page.lines)
    y_centers = [line.y_center for line in page.lines]
    assert y_centers == sorted(y_centers, reverse=True)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_integration_ocr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'img2txt.ocr'`

- [ ] **Step 3: 구현** — `img2txt/ocr.py`

```python
"""Apple Vision OCR 래핑: 이미지 1장 -> 위→아래 정렬된 Page."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

OCR_LANGUAGE: str = "ko-KR"


@dataclass(frozen=True)
class OcrLine:
    """OCR로 인식된 한 줄. 좌표는 Vision 정규화 좌표(0~1, 좌하단 원점)."""

    text: str
    confidence: float
    x: float
    y: float
    width: float
    height: float

    @property
    def y_center(self) -> float:
        """줄의 세로 중심 좌표 (좌하단 원점이므로 클수록 위쪽)."""
        return self.y + self.height / 2.0


@dataclass
class Page:
    """책 한 페이지의 OCR 결과."""

    number: int
    lines: list[OcrLine] = field(default_factory=list)


def sort_lines_top_to_bottom(lines: list[OcrLine]) -> list[OcrLine]:
    """줄을 y 중심 내림차순(위→아래)으로 정렬한다. Vision 반환 순서에 의존하지 않는다."""
    return sorted(lines, key=lambda line: line.y_center, reverse=True)


def recognize_page(image_path: Path, page_number: int) -> Page:
    """이미지 1장을 OCR해 위→아래로 정렬된 Page를 반환한다."""
    # ocrmac/PIL은 macOS Vision 의존이라 지연 임포트한다 (correct 전용 환경 보호)
    from ocrmac import ocrmac
    from PIL import Image, ImageOps

    with Image.open(image_path) as image:
        upright = ImageOps.exif_transpose(image)
        annotations = ocrmac.OCR(upright, language_preference=[OCR_LANGUAGE]).recognize()
    lines = [
        OcrLine(text=text, confidence=confidence, x=bx, y=by, width=bw, height=bh)
        for text, confidence, (bx, by, bw, bh) in annotations
    ]
    return Page(number=page_number, lines=sort_lines_top_to_bottom(lines))
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_integration_ocr.py -v`
Expected: 2 passed (macOS 로컬 기준. 통합 테스트만 제외하려면 `-m "not macos"`)

- [ ] **Step 5: 커밋**

```bash
git add img2txt/ocr.py tests/test_integration_ocr.py
git commit -m "feat: OcrLine/Page 데이터 모델과 ocrmac 래핑(ocr) 구현"
```

---

### Task 3: 좌표 캘리브레이션 — layout 임계값 실측 확정 (게이트 1)

**Files:**
- Create: `scripts/dump_coords.py`, `img2txt/layout.py` (이 태스크에서는 상수 4개만)

**Interfaces:**
- Consumes: `ocr.recognize_page`
- Produces: `layout.FOOTER_BAND: float`, `layout.FOOTER_MAX_WIDTH_RATIO: float`, `layout.INDENT_MIN: float`, `layout.TITLE_HEIGHT_RATIO: float` — Task 4~5의 기본값

- [ ] **Step 1: 덤프 스크립트 작성** — `scripts/dump_coords.py`

일회성 캘리브레이션 도구라 print를 허용한다 (산출물 코드 아님).

```python
"""캘리브레이션용 좌표 덤프: 이미지들의 줄별 텍스트와 좌표를 표로 출력한다."""
from __future__ import annotations

import sys
from pathlib import Path

from img2txt.ocr import recognize_page


def main() -> None:
    """인자로 받은 이미지 각각의 줄 좌표를 위→아래 순서로 출력한다."""
    for argument in sys.argv[1:]:
        path = Path(argument)
        page = recognize_page(path, 0)
        print(f"===== {path.name} =====")
        for line in page.lines:
            print(
                f"yc={line.y_center:.3f} x={line.x:.3f} "
                f"w={line.width:.3f} h={line.height:.3f} | {line.text[:40]}"
            )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실측 3장 덤프 실행**

일반 본문(10), 챕터 시작(2), 곡면 왜곡 최악(28) — PoC 검수에서 선정한 페이지.

```bash
.venv/bin/python scripts/dump_coords.py \
  "/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장/주식시장을 이긴 전략들 - 10.jpg" \
  "/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장/주식시장을 이긴 전략들 - 2.jpg" \
  "/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장/주식시장을 이긴 전략들 - 28.jpg"
```

Expected: 페이지당 줄별 `yc/x/w/h/텍스트` 목록. 마지막 줄(꼬리말)의 yc가 본문 최저 yc보다 뚜렷이 작아야 한다.

- [ ] **Step 3: 임계값 4개 결정**

덤프에서 다음을 읽어 결정한다 (판정이 모호하면 페이지를 2장 추가 덤프):

- `FOOTER_BAND`: 꼬리말 yc 최대값과 본문 최저 yc의 중간값 (예: 꼬리말 yc 0.045, 본문 최저 0.11이면 0.08)
- `FOOTER_MAX_WIDTH_RATIO`: 꼬리말 w / 본문 최대 w 비율 관찰값 + 여유 (숫자 없는 오탈자형 꼬리말도 걸리게)
- `INDENT_MIN`: 문단 시작 줄 x - 일반 줄 최소 x 차이의 약 절반
- `TITLE_HEIGHT_RATIO`: 제목 h / 본문 h 중앙값 비율과 1.0 사이 중간 (페이지 2의 제목 줄 기준)

- [ ] **Step 4: 상수 기록** — `img2txt/layout.py` 생성 (상수만, 함수는 Task 4~5)

```python
"""페이지 레이아웃 분석: 꼬리말 식별, 제목 분류, 문단 시작 감지."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 캘리브레이션 근거 (2026-07-07, scripts/dump_coords.py로 페이지 2/10/28 실측):
#   <실측 수치 요약을 여기에 기록 — 예: 꼬리말 yc 최대 0.045, 본문 최저 yc 0.11>
FOOTER_BAND: float = 0.08              # 실측값으로 교체
FOOTER_MAX_WIDTH_RATIO: float = 0.60   # 실측값으로 교체
INDENT_MIN: float = 0.015              # 실측값으로 교체
TITLE_HEIGHT_RATIO: float = 1.40       # 실측값으로 교체
```

주의: 위 숫자는 초기 추정치다. 반드시 Step 3의 실측값으로 교체하고, 주석의 `<실측 수치 요약>`을 실제 관찰 수치로 채운다. 실측 없이 추정치를 커밋하는 것은 이 태스크의 실패다.

- [ ] **Step 5: 커밋**

```bash
git add scripts/dump_coords.py img2txt/layout.py
git commit -m "feat: 좌표 캘리브레이션으로 layout 임계값 4개 확정"
```

---

### Task 4: layout — 꼬리말 분리 (위치 + 보조 조건)

**Files:**
- Modify: `img2txt/layout.py`
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `ocr.OcrLine`, Task 3의 상수
- Produces: `split_footer(lines: list[OcrLine], footer_band: float = FOOTER_BAND, footer_max_width_ratio: float = FOOTER_MAX_WIDTH_RATIO) -> tuple[list[OcrLine], list[OcrLine]]` (반환: (본문 줄, 꼬리말 줄)) — Task 5가 사용

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_layout.py`

```python
"""layout 테스트: 꼬리말 분리(위치+보조 조건), 제목 분류, 문단 감지."""
from img2txt.layout import split_footer
from img2txt.ocr import OcrLine


def _line(
    text: str,
    y: float,
    x: float = 0.10,
    width: float = 0.80,
    height: float = 0.020,
) -> OcrLine:
    return OcrLine(text=text, confidence=1.0, x=x, y=y, width=width, height=height)


def test_footer_with_digit_in_band_removed() -> None:
    lines = [_line("본문 줄", 0.50), _line("24 주식시장을 이긴 전략들", 0.03, width=0.30)]
    body, footer = split_footer(lines, footer_band=0.08, footer_max_width_ratio=0.60)
    assert [l.text for l in body] == ["본문 줄"]
    assert [l.text for l in footer] == ["24 주식시장을 이긴 전략들"]


def test_footer_typo_without_digit_removed_by_short_width() -> None:
    # 오탈자형 꼬리말: 숫자가 깨졌어도 본문 대비 짧은 폭으로 잡힌다
    lines = [_line("본문 줄", 0.50), _line("주식시장을 이전 썬택는", 0.03, width=0.25)]
    body, footer = split_footer(lines, footer_band=0.08, footer_max_width_ratio=0.60)
    assert [l.text for l in footer] == ["주식시장을 이전 썬택는"]


def test_body_line_in_band_without_conditions_kept() -> None:
    # 띠에 걸쳤지만 숫자도 없고 본문 폭 그대로인 줄 = 본문으로 보존 (오삭제 불허)
    lines = [_line("본문 줄", 0.50), _line("띠에 걸친 긴 본문 문장이다", 0.06, width=0.80)]
    body, footer = split_footer(lines, footer_band=0.08, footer_max_width_ratio=0.60)
    assert len(body) == 2
    assert footer == []


def test_no_footer_candidates_keeps_all() -> None:
    lines = [_line("본문 1", 0.60), _line("본문 2", 0.40)]
    body, footer = split_footer(lines, footer_band=0.08, footer_max_width_ratio=0.60)
    assert len(body) == 2
    assert footer == []
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_layout.py -v`
Expected: FAIL — `ImportError: cannot import name 'split_footer'`

- [ ] **Step 3: 구현** — `img2txt/layout.py`에 추가

```python
def _contains_digit(text: str) -> bool:
    """줄에 아라비아 숫자가 하나라도 있는지 판단한다."""
    return any(character.isdigit() for character in text)


def split_footer(
    lines: list[OcrLine],
    footer_band: float = FOOTER_BAND,
    footer_max_width_ratio: float = FOOTER_MAX_WIDTH_RATIO,
) -> tuple[list[OcrLine], list[OcrLine]]:
    """줄 목록을 (본문, 꼬리말)로 나눈다 (스펙 규칙 2).

    꼬리말 = 최하단 띠 안 + (숫자 포함 또는 본문 대비 짧은 폭).
    보조 조건 탓에 꼬리말이 남는 실패는 허용, 본문 오삭제는 불허.
    """
    band_outside_widths = [l.width for l in lines if l.y_center >= footer_band]
    max_body_width = max(band_outside_widths, default=0.0)
    body: list[OcrLine] = []
    footer: list[OcrLine] = []
    for line in lines:
        in_band = line.y_center < footer_band
        is_short = max_body_width > 0.0 and line.width < max_body_width * footer_max_width_ratio
        if in_band and (_contains_digit(line.text) or is_short):
            footer.append(line)
        else:
            body.append(line)
    return body, footer
```

파일 상단 import에 `from img2txt.ocr import OcrLine` 추가.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_layout.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add img2txt/layout.py tests/test_layout.py
git commit -m "feat: 위치+보조 조건 기반 꼬리말 분리(split_footer) 구현"
```

---

### Task 5: layout — 제목 분류 + 문단 그룹화 (analyze_page)

**Files:**
- Modify: `img2txt/layout.py`
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `split_footer`, `ocr.Page`, `ocr.OcrLine`
- Produces: `PageLayout(number: int, paragraphs: list[str], first_is_continuation: bool, footer_lines: list[OcrLine], is_empty: bool)` (dataclass), `analyze_page(page: Page, footer_band=..., footer_max_width_ratio=..., indent_min=..., title_height_ratio=...) -> PageLayout` — Task 6~7이 사용

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_layout.py`에 추가

```python
from img2txt.layout import PageLayout, analyze_page
from img2txt.ocr import Page

_KW = dict(footer_band=0.08, footer_max_width_ratio=0.60, indent_min=0.015, title_height_ratio=1.40)


def test_title_line_is_independent_paragraph() -> None:
    page = Page(number=2, lines=[
        _line("훌륭한 투자자는", 0.90, height=0.040),        # 제목 (본문의 2배 높이)
        _line("1983년 미국의 한 일간지", 0.80),               # 본문 (들여쓰기 없음)
        _line("트레이더를 모집한다는", 0.75),
    ])
    layout = analyze_page(page, **_KW)
    assert layout.paragraphs == ["훌륭한 투자자는", "1983년 미국의 한 일간지 트레이더를 모집한다는"]
    assert layout.first_is_continuation is False   # 제목으로 시작 = 병합 대상 아님


def test_indented_line_starts_new_paragraph() -> None:
    page = Page(number=5, lines=[
        _line("앞 문단 마지막 줄이다.", 0.90),
        _line("새 문단 첫 줄이다", 0.85, x=0.13),            # 들여쓰기(0.10+0.015 이상)
        _line("이어지는 둘째 줄이다.", 0.80),
    ])
    layout = analyze_page(page, **_KW)
    assert layout.paragraphs == ["앞 문단 마지막 줄이다.", "새 문단 첫 줄이다 이어지는 둘째 줄이다."]


def test_page_starting_mid_sentence_is_continuation() -> None:
    page = Page(number=3, lines=[
        _line("주겨다는 약속을 지켰다.", 0.90),               # 들여쓰기 없음 = 이전 페이지에서 이어짐
        _line("다음 내용이 계속된다.", 0.85),
    ])
    layout = analyze_page(page, **_KW)
    assert layout.first_is_continuation is True
    assert layout.paragraphs == ["주겨다는 약속을 지켰다. 다음 내용이 계속된다."]


def test_footer_removed_and_empty_page_flagged() -> None:
    footer_only = Page(number=9, lines=[_line("23", 0.03, width=0.05)])
    layout = analyze_page(footer_only, **_KW)
    assert layout.is_empty is True
    empty = Page(number=11, lines=[])
    assert analyze_page(empty, **_KW).is_empty is True
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_layout.py -v`
Expected: 새 테스트 4개 FAIL — `ImportError: cannot import name 'analyze_page'`

- [ ] **Step 3: 구현** — `img2txt/layout.py`에 추가

```python
import statistics
from dataclasses import dataclass, field

from img2txt.ocr import OcrLine, Page


@dataclass
class PageLayout:
    """레이아웃 분석이 끝난 페이지: 꼬리말 제거 + 페이지 내 문단 복원 결과."""

    number: int
    paragraphs: list[str]
    first_is_continuation: bool
    footer_lines: list[OcrLine] = field(default_factory=list)
    is_empty: bool = False


def analyze_page(
    page: Page,
    footer_band: float = FOOTER_BAND,
    footer_max_width_ratio: float = FOOTER_MAX_WIDTH_RATIO,
    indent_min: float = INDENT_MIN,
    title_height_ratio: float = TITLE_HEIGHT_RATIO,
) -> PageLayout:
    """페이지 하나를 분석한다: 꼬리말 제거, 제목 분류, 문단 그룹화 (스펙 규칙 2~4, 6)."""
    if not page.lines:
        return PageLayout(page.number, [], False, [], is_empty=True)
    body, footer = split_footer(page.lines, footer_band, footer_max_width_ratio)
    if not footer:
        logger.warning("페이지 %d: 꼬리말 후보 미감지, 제거 생략", page.number)
    if not body:
        return PageLayout(page.number, [], False, footer, is_empty=True)

    median_height = statistics.median(line.height for line in body)
    title_flags = [line.height > median_height * title_height_ratio for line in body]
    # 여백 추정에 제목이 섞이면 기준이 왜곡된다 (스펙 규칙 3) — 제목 제외 최소 x
    non_title_x = [line.x for line, is_title in zip(body, title_flags) if not is_title]
    margin_x = min(non_title_x) if non_title_x else body[0].x

    paragraphs: list[str] = []
    current: list[str] = []
    current_is_title = False
    first_is_continuation = False
    for index, (line, is_title) in enumerate(zip(body, title_flags)):
        starts_new = is_title or line.x >= margin_x + indent_min
        if index == 0:
            first_is_continuation = not starts_new
        elif (starts_new and not (is_title and current_is_title)) or (is_title != current_is_title):
            # 문단 시작이거나 제목<->본문 전환이면 현재 문단을 닫는다.
            # 연속된 제목 줄(두 줄짜리 장 제목)은 하나의 제목 문단으로 합친다.
            paragraphs.append(" ".join(current))
            current = []
        current.append(line.text)
        current_is_title = is_title
    paragraphs.append(" ".join(current))
    return PageLayout(page.number, paragraphs, first_is_continuation, footer, is_empty=False)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_layout.py -v`
Expected: 8 passed (Task 4의 4개 포함)

- [ ] **Step 5: 커밋**

```bash
git add img2txt/layout.py tests/test_layout.py
git commit -m "feat: 제목 분류와 문단 그룹화(analyze_page) 구현"
```

---

### Task 6: assembler — 페이지 경계 병합 + 누락 표식

**Files:**
- Create: `img2txt/assembler.py`
- Test: `tests/test_assembler.py`

**Interfaces:**
- Consumes: `layout.PageLayout`
- Produces: `MISSING_PAGE_MARKER_FORMAT: str`, `assemble(layouts: list[PageLayout]) -> str` (문단 사이 빈 줄 1개인 연속본 텍스트) — Task 7이 사용

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_assembler.py`

```python
"""assembler 테스트: 경계 병합, 새 문단, 제목 페이지, 누락 페이지 표식."""
from img2txt.assembler import assemble
from img2txt.layout import PageLayout


def _page(number: int, paragraphs: list[str], continuation: bool = False, empty: bool = False) -> PageLayout:
    return PageLayout(number=number, paragraphs=paragraphs,
                      first_is_continuation=continuation, footer_lines=[], is_empty=empty)


def test_boundary_merge_joins_split_paragraph() -> None:
    result = assemble([
        _page(2, ["기업에 지원해"]),
        _page(3, ["주겨다는 약속을 지켰다."], continuation=True),
    ])
    assert result == "기업에 지원해 주겨다는 약속을 지켰다."


def test_paragraph_start_not_merged() -> None:
    result = assemble([
        _page(2, ["첫 문단이다."]),
        _page(3, ["새 문단이다."], continuation=False),
    ])
    assert result == "첫 문단이다.\n\n새 문단이다."


def test_title_page_not_merged() -> None:
    # 제목으로 시작하는 페이지는 analyze_page가 continuation=False로 반환한다
    result = assemble([
        _page(4, ["앞 장 마지막 문단."]),
        _page(5, ["Chapter 02 제목", "본문 시작."], continuation=False),
    ])
    assert result == "앞 장 마지막 문단.\n\nChapter 02 제목\n\n본문 시작."


def test_empty_page_inserts_marker_and_blocks_merge() -> None:
    result = assemble([
        _page(2, ["문장이 여기서 끊기고"]),
        _page(3, [], empty=True),
        _page(4, ["여기로 이어지는 것처럼 보인다."], continuation=True),
    ])
    # 누락 페이지를 건너뛴 병합은 소리 없는 본문 훼손 -> 표식 + 병합 금지 (스펙 규칙 5)
    assert result == "문장이 여기서 끊기고\n\n[페이지 3 누락]\n\n여기로 이어지는 것처럼 보인다."
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_assembler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'img2txt.assembler'`

- [ ] **Step 3: 구현** — `img2txt/assembler.py`

```python
"""페이지 레이아웃 목록 -> 문단이 복원된 연속본 텍스트."""
from __future__ import annotations

import logging

from img2txt.layout import PageLayout

logger = logging.getLogger(__name__)

MISSING_PAGE_MARKER_FORMAT: str = "[페이지 {number} 누락]"
PARAGRAPH_SEPARATOR: str = "\n\n"
LINE_JOINT: str = " "


def assemble(layouts: list[PageLayout]) -> str:
    """페이지들을 이어 연속본을 만든다 (스펙 규칙 5~6).

    직전 페이지가 누락(빈/실패)이면 병합하지 않고 표식을 남긴다.
    """
    paragraphs: list[str] = []
    previous_missing = False
    for layout in layouts:
        if layout.is_empty:
            logger.warning("페이지 %d: 빈 페이지, 누락 표식 삽입", layout.number)
            paragraphs.append(MISSING_PAGE_MARKER_FORMAT.format(number=layout.number))
            previous_missing = True
            continue
        page_paragraphs = list(layout.paragraphs)
        if layout.first_is_continuation and paragraphs and not previous_missing:
            paragraphs[-1] = paragraphs[-1] + LINE_JOINT + page_paragraphs.pop(0)
        paragraphs.extend(page_paragraphs)
        previous_missing = False
    return PARAGRAPH_SEPARATOR.join(paragraphs)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_assembler.py -v`
Expected: 4 passed

- [ ] **Step 5: 커밋**

```bash
git add img2txt/assembler.py tests/test_assembler.py
git commit -m "feat: 페이지 경계 병합과 누락 표식(assemble) 구현"
```

---

### Task 7: writer + cli convert + 실측 31장 검증

**Files:**
- Create: `img2txt/writer.py`, `img2txt/cli.py`, `img2txt/__main__.py`

**Interfaces:**
- Consumes: `scanner.collect_images`, `scanner.extract_page_number`, `ocr.recognize_page`, `ocr.Page`, `layout.analyze_page`, `assembler.assemble`
- Produces: `writer.write_page_texts(pages_dir: Path, pages: list[Page]) -> None`, `writer.write_text_file(path: Path, text: str) -> None`, `cli.main(argv: list[str] | None = None) -> int` — Task 9가 cli에 correct를 추가

- [ ] **Step 1: 구현** — `img2txt/writer.py`

writer는 표준 라이브러리 호출의 얇은 래핑이라 단위 테스트를 따로 두지 않는다 (Step 4의 실측 실행이 검증). corrections.log 쓰기는 Task 9에서 추가.

```python
"""출력 파일 쓰기. 모든 입출력은 UTF-8 고정."""
from __future__ import annotations

from pathlib import Path

from img2txt.ocr import Page

ENCODING: str = "utf-8"
PAGE_FILENAME_FORMAT: str = "page-{number:03d}.txt"


def write_page_texts(pages_dir: Path, pages: list[Page]) -> None:
    """검수용 페이지별 원본 txt를 쓴다 (OCR 줄 단위 그대로, 빈 페이지는 빈 파일)."""
    pages_dir.mkdir(parents=True, exist_ok=True)
    for page in pages:
        path = pages_dir / PAGE_FILENAME_FORMAT.format(number=page.number)
        path.write_text("\n".join(line.text for line in page.lines), encoding=ENCODING)


def write_text_file(path: Path, text: str) -> None:
    """텍스트 파일 하나를 쓴다 (기존 파일 덮어쓰기)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=ENCODING)
```

- [ ] **Step 2: 구현** — `img2txt/cli.py` (convert만, correct 서브커맨드는 Task 9)

```python
"""명령 인자 해석과 전체 흐름 조립."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from img2txt.assembler import assemble
from img2txt.layout import analyze_page
from img2txt.ocr import Page, recognize_page
from img2txt.scanner import collect_images, extract_page_number
from img2txt.writer import write_page_texts, write_text_file

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR: str = "./output"
BOOK_FILENAME: str = "book.txt"
PAGES_DIRNAME: str = "pages"
EXIT_OK: int = 0
EXIT_ERROR: int = 1


def build_parser() -> argparse.ArgumentParser:
    """convert/correct 서브커맨드를 갖는 파서를 만든다."""
    parser = argparse.ArgumentParser(prog="img2txt", description="책 스캔 OCR 변환-보정 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    convert = subparsers.add_parser("convert", help="jpg 폴더 -> 페이지별 txt + 연속본")
    convert.add_argument("input_dir", help="jpg/jpeg가 있는 폴더")
    convert.add_argument("-o", "--output", default=DEFAULT_OUTPUT_DIR, help="출력 폴더")
    convert.add_argument("-v", "--verbose", action="store_true", help="DEBUG 로그")
    return parser


def run_convert(args: argparse.Namespace) -> int:
    """convert 흐름: 수집 -> OCR -> 레이아웃 -> 조립 -> 쓰기."""
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output)
    image_paths = collect_images(input_dir)
    if not image_paths:
        logger.error("입력 폴더에 jpg/jpeg가 없습니다: %s", input_dir)
        return EXIT_ERROR

    pages: list[Page] = []
    failed = 0
    for order, image_path in enumerate(image_paths, start=1):
        number = extract_page_number(image_path)
        if number is None:
            number = order  # 숫자 없는 파일: 순번으로 대체 (scanner가 맨 뒤 배치)
        logger.info("OCR %d/%d: %s", order, len(image_paths), image_path.name)
        try:
            page = recognize_page(image_path, number)
        except Exception as error:  # OCR 1장 실패는 전체를 멈추지 않는다 (스펙 7절)
            logger.warning("OCR 실패, 건너뜀: %s (%s)", image_path.name, error)
            failed += 1
            page = Page(number=number, lines=[])
        if not page.lines:
            logger.warning("빈 OCR 결과: %s", image_path.name)
        pages.append(page)

    if failed == len(image_paths):
        logger.error("모든 이미지의 OCR이 실패했습니다.")
        return EXIT_ERROR

    layouts = [analyze_page(page) for page in pages]
    write_page_texts(output_dir / PAGES_DIRNAME, pages)
    write_text_file(output_dir / BOOK_FILENAME, assemble(layouts))

    empty_count = sum(1 for page in pages if not page.lines) - failed
    footer_count = sum(len(layout.footer_lines) for layout in layouts)
    logger.info(
        "완료: 성공 %d / 실패 %d / 빈 결과 %d / 제거 꼬리말 %d줄 -> %s",
        len(pages) - failed - empty_count, failed, empty_count, footer_count,
        output_dir / BOOK_FILENAME,
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """엔트리포인트: 로깅 설정 후 서브커맨드를 실행한다."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    if args.command == "convert":
        return run_convert(args)
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
```

`img2txt/__main__.py` 생성 (`python -m img2txt` 실행에 필수 — 스펙 모듈 목록에는 없지만 CLI 사양 충족에 필요한 보완):

```python
"""`python -m img2txt` 엔트리포인트."""
from img2txt.cli import main

raise SystemExit(main())
```

- [ ] **Step 3: 전체 단위 테스트 회귀 확인**

Run: `.venv/bin/pytest -v`
Expected: 지금까지의 테스트 전부 passed

- [ ] **Step 4: 실측 31장 실행**

```bash
.venv/bin/python -m img2txt convert \
  "/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장" -o output_formal
```

Expected: 종료 코드 0, 로그에 `성공 31 / 실패 0 / 빈 결과 0`, `output_formal/pages/` 31개 + `output_formal/book.txt` 생성

- [ ] **Step 5: 꼬리말 잔존 0건 확인 (최종 검증 기준 2)**

```bash
grep -cE "^[0-9]+ 주식시장을 이긴|^Chapter ?[0-9]" output_formal/book.txt; echo "exit=$?"
```

Expected: `0` + `exit=1` (매치 없음). 잔존이 있으면 해당 페이지를 `scripts/dump_coords.py`로 덤프해 임계값 또는 보조 조건을 보정한 뒤 재실행.

- [ ] **Step 6: 커밋**

```bash
git add img2txt/writer.py img2txt/cli.py img2txt/__main__.py
git commit -m "feat: convert CLI 완성 (writer + 흐름 조립 + 실측 31장 통과)"
```

---

### Task 8: corrector — Ollama 클라이언트 + 안전장치

**Files:**
- Create: `img2txt/corrector.py`
- Test: `tests/test_corrector.py`

**Interfaces:**
- Consumes: 없음 (독립 모듈)
- Produces: `CorrectionStatus(str, Enum)` (CORRECTED/KEPT/GUARD_BLOCKED/FAILED/SKIPPED_LONG), `CorrectionRecord(index: int, status: CorrectionStatus, reason: str, model: str, before: str, after: str)`, `check_server(base_url: str, model: str) -> str | None`, `correct_paragraphs(paragraphs: list[str], model: str, base_url: str = OLLAMA_BASE_URL, request: Callable[[str, str, str], str] = request_correction) -> tuple[list[str], list[CorrectionRecord]]`, `all_requests_failed(records: list[CorrectionRecord]) -> bool` — Task 9가 사용

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_corrector.py`

```python
"""corrector 테스트: 길이 가드(비율+절대 하한), 폴백, 긴 문단 생략, 기록. HTTP는 모킹."""
from img2txt.corrector import (
    CorrectionStatus,
    all_requests_failed,
    correct_paragraphs,
)


def test_normal_correction_applied() -> None:
    fake = lambda base_url, model, paragraph: paragraph.replace("경단로", "결단코")
    results, records = correct_paragraphs(["그는 경단로 다짐했다."], model="m", request=fake)
    assert results == ["그는 결단코 다짐했다."]
    assert records[0].status is CorrectionStatus.CORRECTED


def test_unchanged_paragraph_kept() -> None:
    fake = lambda base_url, model, paragraph: paragraph
    results, records = correct_paragraphs(["오류 없는 문단."], model="m", request=fake)
    assert results == ["오류 없는 문단."]
    assert records[0].status is CorrectionStatus.KEPT


def test_guard_blocks_large_length_change() -> None:
    original = "가" * 100
    fake = lambda base_url, model, paragraph: "가" * 130  # +30% > max(5, 10%)
    results, records = correct_paragraphs([original], model="m", request=fake)
    assert results == [original]
    assert records[0].status is CorrectionStatus.GUARD_BLOCKED


def test_short_paragraph_small_change_allowed_by_absolute_floor() -> None:
    # "20 세기"(5자 문단)에서 공백 1개 제거: 비율 가드(10%=0자)로는 차단되지만 절대 하한 5자 이내 -> 허용
    original = "20 세기"
    fake = lambda base_url, model, paragraph: "20세기"
    results, records = correct_paragraphs([original], model="m", request=fake)
    assert results == ["20세기"]
    assert records[0].status is CorrectionStatus.CORRECTED


def test_request_failure_keeps_original() -> None:
    def broken(base_url: str, model: str, paragraph: str) -> str:
        raise TimeoutError("모의 타임아웃")
    results, records = correct_paragraphs(["원문 유지 문단."], model="m", request=broken)
    assert results == ["원문 유지 문단."]
    assert records[0].status is CorrectionStatus.FAILED


def test_long_paragraph_skipped_without_request() -> None:
    calls: list[str] = []
    def spy(base_url: str, model: str, paragraph: str) -> str:
        calls.append(paragraph)
        return paragraph
    long_paragraph = "가" * 3000
    results, records = correct_paragraphs([long_paragraph], model="m", request=spy)
    assert results == [long_paragraph]
    assert records[0].status is CorrectionStatus.SKIPPED_LONG
    assert calls == []


def test_all_requests_failed_detection() -> None:
    def broken(base_url: str, model: str, paragraph: str) -> str:
        raise ConnectionError("모의 접속 불가")
    _, records = correct_paragraphs(["a", "b"], model="m", request=broken)
    assert all_requests_failed(records) is True
    fake = lambda base_url, model, paragraph: paragraph
    _, ok_records = correct_paragraphs(["a"], model="m", request=fake)
    assert all_requests_failed(ok_records) is False
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_corrector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'img2txt.corrector'`

- [ ] **Step 3: 구현** — `img2txt/corrector.py`

```python
"""로컬 LLM(Ollama)으로 문단 단위 OCR 오류 보정 + 안전장치."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL: str = "http://localhost:11434"
LENGTH_GUARD_RATIO: float = 0.10   # 스펙 규칙 10 초기값, 캘리브레이션으로 조정 가능
MIN_DIFF_CHARS: int = 5            # 짧은 문단에서 정당한 보정 차단 방지 (절대 하한)
MAX_PARA_CHARS: int = 2000         # 문단 감지 실패 의심 상한 -> 보정 생략
REQUEST_TIMEOUT_SECONDS: float = 120.0
CHECK_TIMEOUT_SECONDS: float = 10.0

# 스펙 규칙 9: 보정 범위 제약 + 실측 오류 쌍 few-shot
SYSTEM_PROMPT: str = (
    "너는 한국어 책 OCR 결과 교정기다. 입력 문단에서 OCR 오류(오탈자, 잘못된 띄어쓰기)만 고쳐라. "
    "문장 재작성, 내용 추가, 삭제, 요약을 금지한다. 고칠 것이 없으면 입력을 그대로 반환하라. "
    "교정된 문단 텍스트만 출력하고 설명은 붙이지 마라.\n"
    "예시1: '그는 경단로 다짐했다' -> '그는 결단코 다짐했다'\n"
    "예시2: '20 세기 최고의 트레이더' -> '20세기 최고의 트레이더'\n"
    "예시3: '가격이 하락하면 손절한다.' -> '가격이 하락하면 손절한다.' (오류 없음, 그대로)"
)


class CorrectionStatus(str, Enum):
    """문단 보정 결과 상태."""

    CORRECTED = "보정"
    KEPT = "유지"
    GUARD_BLOCKED = "가드 차단"
    FAILED = "실패"
    SKIPPED_LONG = "긴 문단 생략"


@dataclass(frozen=True)
class CorrectionRecord:
    """문단 하나의 보정 결과 기록 (corrections.log 재료)."""

    index: int
    status: CorrectionStatus
    reason: str
    model: str
    before: str
    after: str


def check_server(base_url: str, model: str) -> str | None:
    """Ollama 접속과 모델 설치를 점검한다. 문제면 안내 메시지, 정상이면 None."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=CHECK_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return f"Ollama 서버({base_url})에 접속할 수 없습니다. 'ollama serve' 실행 여부를 확인하세요."
    names = {entry["name"] for entry in body.get("models", [])}
    if model not in names and f"{model}:latest" not in names:
        return f"모델 '{model}'이 설치되어 있지 않습니다. 'ollama pull {model}' 후 다시 실행하세요."
    return None


def request_correction(base_url: str, model: str, paragraph: str) -> str:
    """Ollama /api/chat에 문단 보정을 요청해 교정 텍스트를 반환한다."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": paragraph},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }
    http_request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        body = json.loads(response.read().decode("utf-8"))
    return str(body["message"]["content"]).strip()


def _allowed_diff(original_length: int) -> int:
    """길이 가드 허용 편차 = max(절대 하한, 비율) (스펙 규칙 10)."""
    return max(MIN_DIFF_CHARS, int(original_length * LENGTH_GUARD_RATIO))


def correct_paragraphs(
    paragraphs: list[str],
    model: str,
    base_url: str = OLLAMA_BASE_URL,
    request: Callable[[str, str, str], str] = request_correction,
) -> tuple[list[str], list[CorrectionRecord]]:
    """문단 목록을 순차 보정한다. 실패-차단 문단은 원문 유지 (스펙 규칙 8, 10~11)."""
    results: list[str] = []
    records: list[CorrectionRecord] = []
    total = len(paragraphs)
    for index, paragraph in enumerate(paragraphs, start=1):
        logger.info("보정 %d/%d", index, total)
        if len(paragraph) > MAX_PARA_CHARS:
            logger.warning("문단 %d: %d자 초과, 보정 생략", index, MAX_PARA_CHARS)
            results.append(paragraph)
            records.append(CorrectionRecord(index, CorrectionStatus.SKIPPED_LONG,
                                            f"{MAX_PARA_CHARS}자 초과", model, paragraph, paragraph))
            continue
        try:
            corrected = request(base_url, model, paragraph)
        except Exception as error:  # 보정은 향상 수단이지 단일 장애점이 아니다 (스펙 규칙 11)
            logger.warning("문단 %d: 보정 요청 실패, 원문 유지 (%s)", index, error)
            results.append(paragraph)
            records.append(CorrectionRecord(index, CorrectionStatus.FAILED,
                                            str(error), model, paragraph, paragraph))
            continue
        if abs(len(corrected) - len(paragraph)) > _allowed_diff(len(paragraph)):
            logger.warning("문단 %d: 길이 가드 차단 (%d자 -> %d자)", index, len(paragraph), len(corrected))
            results.append(paragraph)
            records.append(CorrectionRecord(index, CorrectionStatus.GUARD_BLOCKED,
                                            f"길이 {len(paragraph)} -> {len(corrected)}",
                                            model, paragraph, corrected))
        elif corrected == paragraph:
            results.append(paragraph)
            records.append(CorrectionRecord(index, CorrectionStatus.KEPT, "변경 없음",
                                            model, paragraph, paragraph))
        else:
            results.append(corrected)
            records.append(CorrectionRecord(index, CorrectionStatus.CORRECTED, "텍스트 변경",
                                            model, paragraph, corrected))
    return results, records


def all_requests_failed(records: list[CorrectionRecord]) -> bool:
    """요청한 문단 전부가 실패했는지 판단한다 (Silent Failure 방지, 스펙 6~7절).

    SKIPPED_LONG은 요청 자체를 안 했으므로 모수에서 제외한다.
    """
    requested = [r for r in records if r.status is not CorrectionStatus.SKIPPED_LONG]
    return bool(requested) and all(r.status is CorrectionStatus.FAILED for r in requested)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_corrector.py -v`
Expected: 7 passed

- [ ] **Step 5: 커밋**

```bash
git add img2txt/corrector.py tests/test_corrector.py
git commit -m "feat: Ollama 문단 보정기(corrector)와 안전장치 구현"
```

---

### Task 9: cli correct + corrections.log

**Files:**
- Modify: `img2txt/cli.py`, `img2txt/writer.py`
- Test: `tests/test_corrector.py` (로그 포맷 테스트 추가)

**Interfaces:**
- Consumes: `corrector.*` (Task 8 전부), `writer.write_text_file`
- Produces: `writer.format_corrections_log(records: list[CorrectionRecord]) -> str`, cli `correct` 서브커맨드 (`python -m img2txt correct <연속본txt> [--model ...] [-o ...] [-v]`)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_corrector.py`에 추가

```python
from img2txt.corrector import CorrectionRecord
from img2txt.writer import format_corrections_log


def test_corrections_log_includes_changes_only() -> None:
    records = [
        CorrectionRecord(1, CorrectionStatus.KEPT, "변경 없음", "m", "그대로", "그대로"),
        CorrectionRecord(2, CorrectionStatus.CORRECTED, "텍스트 변경", "m", "경단로", "결단코"),
        CorrectionRecord(3, CorrectionStatus.FAILED, "타임아웃", "m", "원문", "원문"),
    ]
    log_text = format_corrections_log(records)
    assert "[문단 1]" not in log_text          # 변경 없는 문단은 기록하지 않음 (스펙 규칙 12)
    assert "[문단 2] 상태=보정 모델=m 사유=텍스트 변경" in log_text
    assert "--- 전 ---\n경단로" in log_text
    assert "--- 후 ---\n결단코" in log_text
    assert "[문단 3] 상태=실패" in log_text
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_corrector.py -v`
Expected: 새 테스트 1개 FAIL — `ImportError: cannot import name 'format_corrections_log'`

- [ ] **Step 3: 구현**

`img2txt/writer.py`에 추가:

```python
from img2txt.corrector import CorrectionRecord, CorrectionStatus

LOG_ENTRY_FORMAT: str = "[문단 {index}] 상태={status} 모델={model} 사유={reason}\n--- 전 ---\n{before}\n--- 후 ---\n{after}\n"


def format_corrections_log(records: list[CorrectionRecord]) -> str:
    """보정 반영/가드 차단/실패 문단만 전/후 대조 형식으로 만든다 (스펙 규칙 12)."""
    entries = [
        LOG_ENTRY_FORMAT.format(index=r.index, status=r.status.value, model=r.model,
                                reason=r.reason, before=r.before, after=r.after)
        for r in records
        if r.status is not CorrectionStatus.KEPT
    ]
    return "\n".join(entries)
```

`img2txt/cli.py` 수정 — `build_parser()`에 correct 서브커맨드 추가:

```python
    correct = subparsers.add_parser("correct", help="연속본 txt -> LLM 보정본")
    correct.add_argument("input_file", help="convert가 만든 연속본 txt (book.txt 등)")
    correct.add_argument("--model", default=DEFAULT_MODEL, help="Ollama 모델명")
    correct.add_argument("-o", "--output", default=None, help="출력 폴더 (기본: 입력 파일 폴더)")
    correct.add_argument("-v", "--verbose", action="store_true", help="DEBUG 로그")
```

상수와 `run_correct` 추가, `main()`의 분기에 `correct` 연결:

```python
from img2txt.corrector import (
    OLLAMA_BASE_URL,
    CorrectionStatus,
    all_requests_failed,
    check_server,
    correct_paragraphs,
)
from img2txt.writer import format_corrections_log

DEFAULT_MODEL: str = "gemma4:latest"
CORRECTED_FILENAME: str = "book_corrected.txt"
CORRECTIONS_LOG_FILENAME: str = "corrections.log"


def run_correct(args: argparse.Namespace) -> int:
    """correct 흐름: 사전 점검 -> 문단 분리 -> 보정 -> 보정본 + 로그 쓰기."""
    input_path = Path(args.input_file)
    if not input_path.is_file():
        logger.error("입력 파일이 없습니다: %s", input_path)
        return EXIT_ERROR
    output_dir = Path(args.output) if args.output else input_path.parent

    error_message = check_server(OLLAMA_BASE_URL, args.model)
    if error_message:
        logger.error(error_message)
        return EXIT_ERROR

    text = input_path.read_text(encoding="utf-8")
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    corrected, records = correct_paragraphs(paragraphs, model=args.model)

    if all_requests_failed(records):
        logger.error("전체 문단 보정 요청이 실패했습니다 (정상 응답 0건). Ollama 상태를 확인하세요.")
        return EXIT_ERROR

    write_text_file(output_dir / CORRECTED_FILENAME, "\n\n".join(corrected))
    write_text_file(output_dir / CORRECTIONS_LOG_FILENAME, format_corrections_log(records))

    counts = {status: sum(1 for r in records if r.status is status) for status in CorrectionStatus}
    logger.info(
        "완료: 보정 %d / 유지 %d / 가드 차단 %d / 실패 %d / 긴 문단 생략 %d -> %s",
        counts[CorrectionStatus.CORRECTED], counts[CorrectionStatus.KEPT],
        counts[CorrectionStatus.GUARD_BLOCKED], counts[CorrectionStatus.FAILED],
        counts[CorrectionStatus.SKIPPED_LONG], output_dir / CORRECTED_FILENAME,
    )
    return EXIT_OK
```

`main()` 분기:

```python
    if args.command == "convert":
        return run_convert(args)
    if args.command == "correct":
        return run_correct(args)
    return EXIT_ERROR
```

- [ ] **Step 4: 통과 확인 + 사전 점검 스모크**

Run: `.venv/bin/pytest -v`
Expected: 전체 passed

Run: `.venv/bin/python -m img2txt correct output_formal/book.txt --model 존재하지않는모델`
Expected: 종료 코드 1 + "모델 '존재하지않는모델'이 설치되어 있지 않습니다" 로그

- [ ] **Step 5: 커밋**

```bash
git add img2txt/cli.py img2txt/writer.py tests/test_corrector.py
git commit -m "feat: correct CLI와 corrections.log 포맷 구현"
```

---

### Task 10: 모델 품질 게이트 — gemma4 샘플 3문단 (게이트 2)

**Files:**
- Create: 없음 (실측 판정 태스크. 결과는 커밋 메시지와 스펙 문서에 기록)

**Interfaces:**
- Consumes: `python -m img2txt correct` (Task 9)
- Produces: 기본 모델 확정 (`cli.DEFAULT_MODEL` 값 유지 또는 교체)

- [ ] **Step 1: 샘플 3문단 파일 작성**

`output_formal/book.txt`에서 다음 3종을 골라 `/tmp` 대신 스크래치 또는 `output_formal/sample3.txt`에 문단(빈 줄 구분) 3개로 저장한다:
1. 오탈자 포함 문단 (실측 예: "경단로" 유형이 있는 문단)
2. "20 세기" 병합 띄어쓰기 오류 문단 (book.txt에서 `grep -n "20 세기" output_formal/book.txt`로 위치 확인)
3. 정상 문단 (오류 없는 짧은 문단)

- [ ] **Step 2: gemma4 보정 실행**

```bash
.venv/bin/python -m img2txt correct output_formal/sample3.txt --model gemma4:latest -o output_formal/gate
```

Expected: 종료 코드 0, `output_formal/gate/book_corrected.txt` + `corrections.log` 생성

- [ ] **Step 3: 판정**

통과 기준 (스펙 규칙 13):
- 오탈자 문단: 실제 오류가 수정됨
- "20 세기" 문단: "20세기"로 붙음
- 정상 문단: corrections.log에 없음 (불필요한 변경 0)

미달이면 `--model qwen3:14b`, `--model exaone3.5:7.8b`로 같은 샘플을 돌려 비교하고, 가장 나은 모델로 `cli.DEFAULT_MODEL`을 교체한다.

- [ ] **Step 4: 결과 기록 및 커밋**

스펙 문서 2절의 "보정 모델" 행에 판정 결과 한 줄을 추가하고 커밋:

```bash
git add docs/superpowers/specs/2026-07-07-korean-ocr-formal-design.md img2txt/cli.py
git commit -m "docs: 모델 품질 게이트 판정 기록 (기본 모델 확정)"
```

---

### Task 11: 최종 검증 4종 + PoC 폐기

**Files:**
- Delete: `ocr_book.py`

**Interfaces:**
- Consumes: 전체 파이프라인

- [ ] **Step 1: 전체 테스트 (최종 검증 기준 1)**

Run: `.venv/bin/pytest -v`
Expected: 전부 passed. 출력을 완료 보고에 첨부한다.

- [ ] **Step 2: 실측 31장 재실행 + 꼬리말 잔존 0건 (기준 2)**

```bash
.venv/bin/python -m img2txt convert "/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장" -o output_formal
grep -cE "^[0-9]+ 주식시장을 이긴|^Chapter ?[0-9]" output_formal/book.txt; echo "exit=$?"
```

Expected: `성공 31 / 실패 0`, grep `0` + `exit=1`

- [ ] **Step 3: 원본 대조 3곳 (기준 3)**

1. 챕터 시작 페이지: `output_formal/pages/page-002.txt`와 `book.txt`의 해당 구간 대조 — 제목("훌륭한 투자자는 타고 나는가, 만들어 지는가?")이 독립 문단인지
2. 페이지 경계 1: `grep -n "지원해 주겨" output_formal/book.txt` — 페이지 2/3 경계의 "지원해 / 주겨다는"이 한 문단으로 복원됐는지 (매치 1건 기대)
3. 페이지 경계 2: `pages/page-010.txt` 마지막 본문 줄과 `page-011.txt` 첫 줄이 book.txt에서 자연스럽게 이어지는지 육안 확인

- [ ] **Step 4: correct 전체 실행 + 표본 검수 요청 (기준 4)**

```bash
.venv/bin/python -m img2txt correct output_formal/book.txt
```

Expected: 종료 코드 0, `output_formal/book_corrected.txt` + `corrections.log` 생성, 요약 로그 출력. 소요 시간을 기록해 스펙 10절의 예상치를 실측치로 갱신한다.

corrections.log에서 변경 문단 표본 5개를 뽑아 **사용자에게 사람 검수를 요청한다** (실제 오류 수정이면서 의미 변형이 없는지 — 이 판정은 사용자 몫).

- [ ] **Step 5: PoC 폐기 + 최종 커밋**

```bash
git rm ocr_book.py
git commit -m "chore: PoC 스크립트 폐기 (정식 구현 완료)"
```

---

## 계획 자체 점검 기록 (Self-Review)

- 스펙 커버리지: 스펙 1절(목표 4산출물)=Task 7/9, 4절(모듈 7+테스트 5)=Task 1~9 (`__main__.py`는 CLI 사양 충족용 보완), 5절 규칙 1=Task 2, 규칙 2=Task 4, 규칙 3~4/6=Task 5, 규칙 5=Task 6, 규칙 7=Task 3, 규칙 8~12=Task 8~9, 규칙 13=Task 10, 6~7절(CLI/에러)=Task 7/9, 8절(테스트 5종)=Task 1/2/4/5/6/8/9, 9절(최종 검증 4종)=Task 11, 10절 한계 실측치 갱신=Task 11 Step 4.
- writer 단위 테스트 부재는 의도된 결정: 표준 라이브러리 얇은 래핑이라 실측 실행(Task 7/11)으로 검증. 스펙 8절 테스트 목록에도 test_writer는 없음.
- 타입 일관성: `OcrLine`/`Page`(Task 2) -> `split_footer`(Task 4) -> `PageLayout`/`analyze_page`(Task 5) -> `assemble`(Task 6) -> cli(Task 7), `CorrectionRecord`/`CorrectionStatus`(Task 8) -> `format_corrections_log`/`run_correct`(Task 9) 시그니처 상호 참조 확인 완료.
