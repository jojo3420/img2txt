# 읽기순서 인식 채점 지표 교체 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 어순 민감 CER 하나로 OCR 품질을 재던 벤치 하네스에, 순서무관 놓침률(품질 하한)과 읽기순서 CER(부작용 감시)을 병행 지표로 도입하고 baseline 4세트로 재검증한다.

**Architecture:** AI Hub 라벨 어댑터의 단어 join을 `id`순 → 좌표 기반 읽기순서로 교체하면, 그 정답 하나로 CER(순서 반영)과 놓침/추가율(순서 무관 글자 multiset)이 파생된다. scoring에 multiset 지표 함수를 추가하고, `_score_outputs`와 `report.summarize`에 배선한다. 재측정은 캐시된 OCR 출력을 재사용해 OCR을 다시 돌리지 않는다.

**Tech Stack:** Python 3, pytest, 표준 라이브러리(`collections.Counter`, `statistics.median`, `json`).

## Global Constraints

- Type Hints 100%, Docstring 한국어 (`CLAUDE.md` 코딩 스타일).
- `print` 금지 → `logging`. 하드코딩 금지.
- 정규화 기준: multiset 지표는 `normalize_strict` 적용 문자열에서 모든 공백 제거(`"".join(text.split())`) 후 글자 Counter.
- 놓침률/추가율 분모 = 정답 글자수(공백 제외). 분모 0이면 rate 0.0.
- CER 계산 코드(`scoring.cer`/`wer`/`levenshtein`)는 변경 금지 — 정답 소스(어댑터)만 읽기순서로 교체.
- 커밋은 각 Task 끝에서 Conventional Commit. 커밋 실행 전 사용자 확인(전역 규칙: 커밋은 요청 시). 스코프 밖 파일(`.idea/`, `tobyteam/`, `bench_data/`) 커밋 금지.
- 스펙: `docs/superpowers/specs/2026-07-17-reading-order-metric-design.md`.

---

## File Structure

- `img2txt/bench/scoring.py` (수정): `char_multiset_diff`, `char_miss_rate`, `char_extra_rate` 추가.
- `img2txt/bench/aihub.py` (수정): `_group_into_rows`, `_reading_order_words`, `reading_order_diagnostics` 추가. `aihub_label_adapter` 읽기순서로 교체. `_validate_bbox` x/y 검증 추가.
- `img2txt/bench/dataset.py` (수정): `PagePair.reading_order_meta` 필드, `load_pairs` `meta_adapter` 파라미터.
- `img2txt/bench/report.py` (수정): `PageRecord` 신규 필드 4개 + `reading_order_meta`, `summarize` 신규 집계.
- `scripts/bench_ocr.py` (수정): `_score_outputs` 지표 계산 + 빈정답 진단 + meta 복사, `_create_error_records` 신규 필드, 어댑터/meta_adapter 배선.
- `scripts/remeasure_reading_order.py` (생성): 캐시 출력 기반 재측정.
- `docs/bench/2026-07-17-reading-order-metric.md` (생성): 재측정 리포트.
- `docs/superpowers/specs/2026-07-13-ocr-llm-quality-harness-design.md` (수정): 5.3/5.6/6/7.3 개정.
- 테스트: `tests/bench/test_scoring.py`, `tests/bench/test_aihub.py`, `tests/bench/test_dataset.py`, `tests/bench/test_report.py` (전부 기존 파일 수정).

---

## Task 1: scoring — 순서무관 글자 multiset 지표

**Files:**
- Modify: `img2txt/bench/scoring.py` (파일 끝에 추가)
- Test: `tests/bench/test_scoring.py`

**Interfaces:**
- Produces:
  - `char_multiset_diff(reference: str, hypothesis: str) -> tuple[int, int, int]` — `(miss, extra, ref_total)` 공백 제외 글자 기준.
  - `char_miss_rate(reference: str, hypothesis: str) -> float`
  - `char_extra_rate(reference: str, hypothesis: str) -> float`

- [ ] **Step 1: 실패 테스트 작성**

`tests/bench/test_scoring.py` 끝에 추가:

```python
from img2txt.bench.scoring import (
    char_multiset_diff,
    char_miss_rate,
    char_extra_rate,
)


def test_char_multiset_diff_perfect_match():
    # 완전 일치: miss=0, extra=0, 공백 제외 글자수=4
    assert char_multiset_diff("가 나 다 라", "라다 나가") == (0, 0, 4)


def test_char_miss_rate_partial_miss():
    # 정답 4글자 중 '라' 누락 → 1/4
    assert char_miss_rate("가나다라", "가나다") == 0.25


def test_char_extra_rate_hallucination():
    # 정답에 없는 '마' 2개 초과 → 2/4
    assert char_extra_rate("가나다라", "가나다라마마") == 0.5


def test_char_rates_order_independent():
    # 순서만 다르면 놓침/추가 모두 0
    assert char_miss_rate("가나다", "다나가") == 0.0
    assert char_extra_rate("가나다", "다나가") == 0.0


def test_char_rates_empty_reference_returns_zero():
    # 정답이 비면 분모 0 → rate 0.0 (빈정답 진단은 호출부에서 별도 처리)
    assert char_miss_rate("", "가나") == 0.0
    assert char_extra_rate("", "가나") == 0.0
    assert char_multiset_diff("", "가나") == (0, 2, 0)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/bench/test_scoring.py -k "char_" -v`
Expected: FAIL (`ImportError: cannot import name 'char_multiset_diff'`)

- [ ] **Step 3: 구현**

`img2txt/bench/scoring.py` 파일 끝에 추가 (상단 import에 `from collections import Counter` 추가):

```python
def _char_counter(text: str) -> Counter:
    """모든 공백을 제거한 글자 Counter (multiset 지표용)."""
    return Counter("".join(text.split()))


def char_multiset_diff(reference: str, hypothesis: str) -> tuple[int, int, int]:
    """공백 제외 글자 multiset 차이.

    Args:
        reference: 정답 텍스트(정규화 완료 가정).
        hypothesis: 가설 텍스트(정규화 완료 가정).

    Returns:
        (miss, extra, ref_total):
        - miss: 정답 글자 중 가설이 못 낸 초과분 합.
        - extra: 가설 글자 중 정답에 없는 초과분 합.
        - ref_total: 정답 글자수(공백 제외).
    """
    ref_c = _char_counter(reference)
    hyp_c = _char_counter(hypothesis)
    miss = sum(max(0, ref_c[ch] - hyp_c[ch]) for ch in ref_c)
    extra = sum(max(0, hyp_c[ch] - ref_c[ch]) for ch in hyp_c)
    return miss, extra, sum(ref_c.values())


def char_miss_rate(reference: str, hypothesis: str) -> float:
    """순서무관 글자 놓침률 = miss / 정답 글자수 (0이면 0.0)."""
    miss, _, total = char_multiset_diff(reference, hypothesis)
    return miss / total if total > 0 else 0.0


def char_extra_rate(reference: str, hypothesis: str) -> float:
    """순서무관 글자 추가율 = extra / 정답 글자수 (0이면 0.0)."""
    _, extra, total = char_multiset_diff(reference, hypothesis)
    return extra / total if total > 0 else 0.0
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/bench/test_scoring.py -k "char_" -v`
Expected: PASS (5개)

- [ ] **Step 5: 커밋**

```bash
git add img2txt/bench/scoring.py tests/bench/test_scoring.py
git commit -m "feat: 순서무관 글자 놓침률/추가율 지표 추가"
```

---

## Task 2: aihub — 좌표 기반 읽기순서 정답 복원 + 진단

**Files:**
- Modify: `img2txt/bench/aihub.py`
- Test: `tests/bench/test_aihub.py`

**Interfaces:**
- Consumes: 없음.
- Produces:
  - `aihub_label_adapter(label_path: Path) -> str` (기존 시그니처 유지, 반환이 읽기순서 join으로 변경).
  - `reading_order_diagnostics(label_path: Path) -> dict` — `{"bbox_count": int, "row_count": int, "median_height": float, "suspicious_layout_flag": bool}`.

- [ ] **Step 1: 실패 테스트 작성**

`tests/bench/test_aihub.py` 수정. 기존 `test_adapter_joins_words_in_id_order`를 읽기순서 기대값으로 교체하고, 아래 테스트를 추가한다. import에 `reading_order_diagnostics` 추가.

```python
from img2txt.bench.aihub import aihub_label_adapter, reading_order_diagnostics


def test_adapter_reads_top_to_bottom_left_to_right(tmp_path: Path) -> None:
    """id 순서와 무관하게 좌표 읽기순서(위→아래, 행 내 좌→우)로 join."""
    label = tmp_path / "AF_TEST_0001.json"
    # 윗줄(y~0): '창원은'(x=0) '우리의'(x=100) / 아랫줄(y~100): '자랑'(x=0)
    # id는 읽기순서와 어긋나게 부여
    _write_label(label, [
        {"data": "자랑", "id": 1, "x": [0, 0, 90, 90], "y": [100, 150, 100, 150]},
        {"data": "우리의", "id": 2, "x": [100, 100, 190, 190], "y": [0, 50, 0, 50]},
        {"data": "창원은", "id": 3, "x": [0, 0, 90, 90], "y": [0, 50, 0, 50]},
    ])

    assert aihub_label_adapter(label) == "창원은 우리의 자랑"


def test_adapter_missing_xy_raises(tmp_path: Path) -> None:
    """x/y 좌표 누락 → ValueError (경계 방어)."""
    label = tmp_path / "AF_TEST_NOXY.json"
    _write_label(label, [{"data": "가", "id": 1}])
    with pytest.raises(ValueError):
        aihub_label_adapter(label)


def test_adapter_xy_length_mismatch_raises(tmp_path: Path) -> None:
    """x/y 길이 불일치 → ValueError."""
    label = tmp_path / "AF_TEST_LEN.json"
    _write_label(label, [{"data": "가", "id": 1, "x": [0, 0, 1, 1], "y": [0, 1]}])
    with pytest.raises(ValueError):
        aihub_label_adapter(label)


def test_diagnostics_flags_over_merged_layout(tmp_path: Path) -> None:
    """단어 다수가 극소수 행으로 뭉치면 suspicious_layout_flag=True."""
    label = tmp_path / "AF_TEST_DIAG.json"
    # 12개 단어가 전부 같은 y (한 행) → row_count<=2, bbox_count>=12
    bbox = [
        {"data": f"w{i}", "id": i, "x": [i * 10, i * 10, i * 10 + 5, i * 10 + 5], "y": [0, 10, 0, 10]}
        for i in range(1, 13)
    ]
    _write_label(label, bbox)
    diag = reading_order_diagnostics(label)
    assert diag["bbox_count"] == 12
    assert diag["suspicious_layout_flag"] is True
```

기존 `test_adapter_joins_words_in_id_order`는 삭제(위 `test_adapter_reads_top_to_bottom_left_to_right`로 대체). 기존 `test_adapter_empty_bbox_returns_empty`, `test_adapter_missing_bbox_key_raises`, `test_adapter_malformed_bbox_raises`는 그대로 둔다(좌표가 이미 포함돼 있어 통과).

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/bench/test_aihub.py -v`
Expected: FAIL (`ImportError: reading_order_diagnostics` 및 읽기순서/검증 테스트 실패)

- [ ] **Step 3: 구현**

`img2txt/bench/aihub.py` 상단 import에 추가:

```python
import math
from statistics import median
```

`_validate_bbox`의 for 루프 안, `data` 검증 다음에 x/y 검증을 추가:

```python
        for axis in ("x", "y"):
            if axis not in entry:
                raise ValueError(f"entry에 {axis} 좌표 누락 (파일: {label_path})")
            coords = entry[axis]
            if not isinstance(coords, list) or not coords:
                raise ValueError(f"{axis}는 비어있지 않은 리스트여야 함 (파일: {label_path})")
            for v in coords:
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise ValueError(f"{axis} 좌표는 숫자여야 함 (파일: {label_path})")
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    raise ValueError(f"{axis} 좌표에 NaN/무한대 (파일: {label_path})")
        if len(entry["x"]) != len(entry["y"]):
            raise ValueError(f"x/y 길이 불일치 (파일: {label_path})")
```

`aihub_label_adapter`의 마지막 두 줄(`words = sorted(...)`, `return " ".join(...)`)을 교체하고, 아래 헬퍼/진단 함수를 파일에 추가:

```python
def _entry_geometry(entry: dict) -> dict:
    """Bbox entry에서 정렬용 좌표 파생."""
    xs, ys = entry["x"], entry["y"]
    y_top, y_bot = min(ys), max(ys)
    return {
        "data": entry["data"],
        "x_left": min(xs),
        "y_center": (y_top + y_bot) / 2,
        "height": y_bot - y_top,
    }


def _group_into_rows(bbox: list) -> tuple[list[list[dict]], float]:
    """Bbox를 읽기순서 행으로 그룹핑. (rows, median_height) 반환.

    rows는 위→아래 정렬된 행 리스트이며 각 행은 x_left 오름차순 정렬됨.
    양수 height가 없으면(퇴화 좌표) y_center→x_left 단순 정렬로 폴백.
    """
    items = [_entry_geometry(e) for e in bbox]
    heights = [it["height"] for it in items if it["height"] > 0]
    med_h = median(heights) if heights else 0.0

    if med_h <= 0:
        items.sort(key=lambda it: (it["y_center"], it["x_left"]))
        return [[it] for it in items], med_h

    tol = med_h * 0.6
    items.sort(key=lambda it: it["y_center"])
    rows: list[list[dict]] = []
    current = [items[0]]
    row_mean = items[0]["y_center"]
    for it in items[1:]:
        if abs(it["y_center"] - row_mean) <= tol:
            current.append(it)
            row_mean = sum(x["y_center"] for x in current) / len(current)
        else:
            rows.append(current)
            current = [it]
            row_mean = it["y_center"]
    rows.append(current)
    for row in rows:
        row.sort(key=lambda it: it["x_left"])
    return rows, med_h


def _reading_order_words(bbox: list) -> list[str]:
    """Bbox를 읽기순서(위→아래, 행 내 좌→우)로 정렬한 단어 리스트."""
    if not bbox:
        return []
    rows, _ = _group_into_rows(bbox)
    return [it["data"] for row in rows for it in row]


def reading_order_diagnostics(label_path: Path) -> dict:
    """읽기순서 재정렬 진단 메타 (오묶음 이상치 추적용, 관측 전용)."""
    with label_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    bbox = payload["Bbox"]
    _validate_bbox(bbox, label_path)
    if not bbox:
        return {"bbox_count": 0, "row_count": 0, "median_height": 0.0, "suspicious_layout_flag": False}
    rows, med_h = _group_into_rows(bbox)
    # 휴리스틱: 단어 다수가 극소수 행으로 뭉치면 다열/표 오묶음 정황
    suspicious = len(rows) <= 2 and len(bbox) >= 12
    return {
        "bbox_count": len(bbox),
        "row_count": len(rows),
        "median_height": float(med_h),
        "suspicious_layout_flag": suspicious,
    }
```

그리고 `aihub_label_adapter`의 반환부를 아래로 교체:

```python
    return " ".join(_reading_order_words(bbox))
```

docstring의 "id 오름차순" 서술도 "좌표 읽기순서"로 갱신.

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/bench/test_aihub.py -v`
Expected: PASS (전부)

- [ ] **Step 5: 커밋**

```bash
git add img2txt/bench/aihub.py tests/bench/test_aihub.py
git commit -m "feat: AI Hub 라벨을 좌표 기반 읽기순서로 복원 + 오묶음 진단"
```

---

## Task 3: dataset — PagePair에 읽기순서 진단 메타 전달 경로

**Files:**
- Modify: `img2txt/bench/dataset.py`
- Test: `tests/bench/test_dataset.py`

**Interfaces:**
- Consumes: `reading_order_diagnostics`(Task 2) 형태의 `Callable[[Path], dict]`.
- Produces:
  - `PagePair.reading_order_meta: dict` (기본 빈 dict).
  - `load_pairs(..., meta_adapter: Callable[[Path], dict] | None = None)` — 지정 시 각 pair에 메타 채움.

- [ ] **Step 1: 실패 테스트 작성**

`tests/bench/test_dataset.py`에 추가 (기존 import/헬퍼 재사용; 없으면 최소 셋업 포함):

```python
def test_load_pairs_populates_reading_order_meta(tmp_path: Path) -> None:
    """meta_adapter 지정 시 PagePair.reading_order_meta 채움."""
    img_dir = tmp_path / "img"; img_dir.mkdir()
    lbl_dir = tmp_path / "lbl"; lbl_dir.mkdir()
    (img_dir / "p1.jpg").write_bytes(b"x")
    (lbl_dir / "p1.txt").write_text("정답", encoding="utf-8")

    from img2txt.bench.dataset import load_pairs
    pairs = load_pairs(
        img_dir, lbl_dir,
        adapter=lambda p: p.read_text(encoding="utf-8"),
        meta_adapter=lambda p: {"bbox_count": 3, "suspicious_layout_flag": False},
    )
    assert pairs[0].reading_order_meta == {"bbox_count": 3, "suspicious_layout_flag": False}


def test_load_pairs_default_meta_empty(tmp_path: Path) -> None:
    """meta_adapter 미지정 시 reading_order_meta는 빈 dict."""
    img_dir = tmp_path / "img"; img_dir.mkdir()
    lbl_dir = tmp_path / "lbl"; lbl_dir.mkdir()
    (img_dir / "p1.jpg").write_bytes(b"x")
    (lbl_dir / "p1.txt").write_text("정답", encoding="utf-8")

    from img2txt.bench.dataset import load_pairs
    pairs = load_pairs(img_dir, lbl_dir, adapter=lambda p: p.read_text(encoding="utf-8"))
    assert pairs[0].reading_order_meta == {}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/bench/test_dataset.py -k reading_order_meta -v`
Expected: FAIL (`TypeError: load_pairs() got an unexpected keyword argument 'meta_adapter'` 또는 속성 없음)

- [ ] **Step 3: 구현**

`img2txt/bench/dataset.py`:
- 상단 import: `from dataclasses import dataclass, field`
- `PagePair`에 필드 추가:

```python
@dataclass
class PagePair:
    """이미지 + 정답 텍스트 쌍."""

    page_id: str
    image_path: Path
    reference_text: str
    reading_order_meta: dict = field(default_factory=dict)
```

- `load_pairs` 시그니처와 pair 생성부 수정:

```python
def load_pairs(
    image_dir: Path,
    label_dir: Path,
    adapter: Callable[[Path], str],
    allow_skip: bool = False,
    meta_adapter: Callable[[Path], dict] | None = None,
) -> list[PagePair]:
```

pair 생성 직전/부분:

```python
        reference_text = adapter(label_path)
        meta = meta_adapter(label_path) if meta_adapter else {}

        pair = PagePair(
            page_id=page_id,
            image_path=image_path,
            reference_text=reference_text,
            reading_order_meta=meta,
        )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/bench/test_dataset.py -v`
Expected: PASS (기존 + 신규 2개)

- [ ] **Step 5: 커밋**

```bash
git add img2txt/bench/dataset.py tests/bench/test_dataset.py
git commit -m "feat: PagePair에 읽기순서 진단 메타 전달 경로 추가"
```

---

## Task 4: report — PageRecord 신규 필드 + summarize 집계

**Files:**
- Modify: `img2txt/bench/report.py`
- Test: `tests/bench/test_report.py`

**Interfaces:**
- Consumes: `char_multiset_diff`(Task 1).
- Produces:
  - `PageRecord` 신규 필드: `char_miss_rate: float`, `char_extra_rate: float`, `empty_ref_with_output: bool`, `empty_ref_extra_chars: int`, `reading_order_meta: dict`(기본 빈 dict).
  - `summarize` 반환 `points[point]`에 `char_miss_rate`, `char_extra_rate`, `empty_ref_hallucination_count` 추가.

- [ ] **Step 1: 실패 테스트 작성**

`tests/bench/test_report.py`에 추가 (헬퍼로 PageRecord 생성; 기존 테스트가 쓰는 생성 방식을 따르되 신규 필드 포함):

```python
from img2txt.bench.report import PageRecord, summarize


def _rec(point, ref, out, **kw):
    return PageRecord(
        page_id=kw.get("page_id", "p1"),
        point=point,
        reference_text=ref,
        output_text=out,
        normalized_ref=ref,
        normalized_output=out,
        cer_strict=kw.get("cer_strict", 0.0),
        cer_lenient=0.0,
        wer=0.0,
        processing_time_ms=0.0,
        empty=kw.get("empty", False),
        error_status="",
        char_miss_rate=kw.get("char_miss_rate", 0.0),
        char_extra_rate=kw.get("char_extra_rate", 0.0),
        empty_ref_with_output=kw.get("empty_ref_with_output", False),
        empty_ref_extra_chars=kw.get("empty_ref_extra_chars", 0),
    )


def test_summarize_micro_miss_extra_rate():
    # raw 지점 2페이지: (정답4,놓침1) + (정답4,놓침0) → micro miss = 1/8
    records = [
        _rec("raw", "가나다라", "가나다"),
        _rec("raw", "마바사아", "마바사아"),
    ]
    s = summarize(records)
    assert abs(s["points"]["raw"]["char_miss_rate"] - (1 / 8)) < 1e-9
    assert s["points"]["raw"]["char_extra_rate"] == 0.0


def test_summarize_counts_empty_ref_hallucination():
    records = [_rec("corrected", "", "환각글자", empty_ref_with_output=True, empty_ref_extra_chars=4)]
    s = summarize(records)
    assert s["points"]["corrected"]["empty_ref_hallucination_count"] == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/bench/test_report.py -k "miss_extra or hallucination" -v`
Expected: FAIL (`TypeError: __init__() missing ... 'char_miss_rate'` 또는 키 없음)

- [ ] **Step 3: 구현**

`img2txt/bench/report.py`:
- import 추가: `from img2txt.bench.scoring import char_multiset_diff`
- `PageRecord`에 필드 추가 (기존 `error_status` 다음, `field` import 필요 시 `from dataclasses import asdict, dataclass, field`):

```python
    char_miss_rate: float = 0.0
    char_extra_rate: float = 0.0
    empty_ref_with_output: bool = False
    empty_ref_extra_chars: int = 0
    reading_order_meta: dict = field(default_factory=dict)
```

- `summarize`의 지점별 루프에서 `summary["points"][point]` 구성 직전에 micro 집계 추가:

```python
        total_miss = total_extra = total_ref_ms = 0
        for r in point_records:
            m, e, t = char_multiset_diff(r.normalized_ref, r.normalized_output)
            total_miss += m
            total_extra += e
            total_ref_ms += t
        micro_miss = total_miss / total_ref_ms if total_ref_ms > 0 else 0.0
        micro_extra = total_extra / total_ref_ms if total_ref_ms > 0 else 0.0
        empty_ref_hallucination = sum(1 for r in point_records if r.empty_ref_with_output)
```

- 같은 루프의 `summary["points"][point] = {...}` dict에 키 추가:

```python
            "char_miss_rate": micro_miss,
            "char_extra_rate": micro_extra,
            "empty_ref_hallucination_count": empty_ref_hallucination,
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/bench/test_report.py -v`
Expected: PASS (기존 + 신규 2개)

- [ ] **Step 5: 커밋**

```bash
git add img2txt/bench/report.py tests/bench/test_report.py
git commit -m "feat: 리포트에 놓침률/추가율/빈정답 환각 집계 추가"
```

---

## Task 5: bench_ocr — 지표 배선 + 빈정답 진단 + meta_adapter

**Files:**
- Modify: `scripts/bench_ocr.py` (`_score_outputs` 117행~, `_create_error_records` 160행~, 어댑터 선택 260행~)
- Test: `tests/bench/test_bench_cli.py` (기존 스모크 테스트 통과 확인 위주)

**Interfaces:**
- Consumes: `char_miss_rate`, `char_extra_rate`(Task 1); `reading_order_diagnostics`(Task 2); `PagePair.reading_order_meta`(Task 3); `PageRecord` 신규 필드(Task 4).
- Produces: 각 PageRecord에 지표/진단/메타 채워 write.

- [ ] **Step 1: 실패 테스트 작성**

`tests/bench/test_bench_cli.py`에 `_score_outputs` 직접 검증 추가:

```python
def test_score_outputs_fills_metrics_and_empty_ref_diag():
    from scripts.bench_ocr import _score_outputs
    from img2txt.bench.dataset import PagePair
    from img2txt.bench.runner import PointOutputs
    import time as _t

    pair = PagePair(page_id="p1", image_path=Path("x.jpg"),
                    reference_text="", reading_order_meta={"bbox_count": 0})
    outputs = PointOutputs(page_id="p1", raw="환각", assembled="환각",
                           corrected="환각", segments=["환각"], empty=False)
    recs = _score_outputs(pair, outputs, _t.time())
    raw = next(r for r in recs if r.point == "raw")
    assert raw.empty_ref_with_output is True
    assert raw.empty_ref_extra_chars == 2
    assert raw.reading_order_meta == {"bbox_count": 0}
```

> 주의: `PointOutputs` 필드는 `img2txt/bench/runner.py`의 정의를 따른다(`page_id, raw, assembled, corrected, segments, empty`). 실제 정의를 열어 인자명을 맞출 것.

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/bench/test_bench_cli.py -k score_outputs -v`
Expected: FAIL (`AttributeError: empty_ref_with_output` 또는 필드 미채움)

- [ ] **Step 3: 구현**

`scripts/bench_ocr.py`:
- import 수정: `from img2txt.bench.scoring import cer, wer, char_miss_rate, char_extra_rate` / `from img2txt.bench.aihub import aihub_label_adapter, reading_order_diagnostics`
- `_score_outputs` 루프 내 `wer_score` 계산 다음에 추가:

```python
        miss_rate = char_miss_rate(normalized_ref, normalized_output)
        extra_rate = char_extra_rate(normalized_ref, normalized_output)
        ref_no_ws = "".join(normalized_ref.split())
        out_no_ws = "".join(normalized_output.split())
        empty_ref_with_output = len(ref_no_ws) == 0 and len(out_no_ws) > 0
        empty_ref_extra_chars = len(out_no_ws) if empty_ref_with_output else 0
```

- 같은 루프의 `PageRecord(...)` 생성에 인자 추가:

```python
            char_miss_rate=miss_rate,
            char_extra_rate=extra_rate,
            empty_ref_with_output=empty_ref_with_output,
            empty_ref_extra_chars=empty_ref_extra_chars,
            reading_order_meta=pair.reading_order_meta,
```

- `_create_error_records`의 PageRecord 생성에도 신규 필드 기본값 추가 (`char_miss_rate=0.0, char_extra_rate=0.0, empty_ref_with_output=False, empty_ref_extra_chars=0, reading_order_meta=pair.reading_order_meta`). PageRecord 필드에 기본값을 부여했으므로(Task 4) 생략 가능하나, 명시적으로 채워 두 경로 일관.
- 어댑터 선택부(260행) 수정:

```python
        adapter = aihub_label_adapter if args.label_format == "aihub" else _default_label_adapter
        meta_adapter = reading_order_diagnostics if args.label_format == "aihub" else None
        pairs = load_pairs(
            args.image_dir, args.label_dir, adapter,
            allow_skip=args.allow_skip, meta_adapter=meta_adapter,
        )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/bench/test_bench_cli.py -v`
Expected: PASS (기존 스모크 + 신규)

- [ ] **Step 5: 전체 벤치 테스트 회귀 확인**

Run: `pytest tests/bench/ -q`
Expected: PASS (전부)

- [ ] **Step 6: 커밋**

```bash
git add scripts/bench_ocr.py tests/bench/test_bench_cli.py
git commit -m "feat: 하네스에 놓침률/추가율/빈정답 진단/읽기순서 메타 배선"
```

---

## Task 6: 재측정 — 캐시 출력으로 4세트 검증 + 리포트

**Files:**
- Create: `scripts/remeasure_reading_order.py`
- Create: `docs/bench/2026-07-17-reading-order-metric.md`

**Interfaces:**
- Consumes: `aihub` 내부 `_reading_order_words`(Task 2), `scoring.char_miss_rate`/`char_extra_rate`/`cer`(Task 1), `normalize.normalize_strict`.

- [ ] **Step 1: 재측정 스크립트 작성**

`scripts/remeasure_reading_order.py` 생성. 캐시된 baseline JSONL의 `output_text`(raw 지점 `normalized_output`)와 라벨 JSON을 사용해 id순 CER / 읽기순서 CER / 놓침률 / 추가율을 micro 집계한다. id순 join은 "before" 비교용으로 스크립트 내 로컬 함수로 둔다(프로덕션 어댑터는 이미 읽기순서).

```python
#!/usr/bin/env python3
"""읽기순서 지표 재측정 — 캐시된 baseline OCR 출력 재사용(OCR 재실행 없음).

각 세트: id순 CER(before) vs 읽기순서 CER(after) vs 놓침률 vs 추가율 micro 집계.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from img2txt.bench.aihub import _reading_order_words
from img2txt.bench.normalize import normalize_strict
from img2txt.bench.scoring import levenshtein, char_multiset_diff

REPORTS = Path("bench_data/reports")
LBL_ROOT = Path("bench_data/023.OCR 데이터(공공)/01-1.정식개방데이터/Validation/02.라벨링데이터")
SETS = {
    "2010": ("baseline-2010.jsonl", "VL_OCR(public)_AF_2010_5270218_0001"),
    "1990": ("baseline-AF_1990_5270218_0010.jsonl", "VL_OCR(public)_AF_1990_5270218_0010"),
    "1980": ("baseline-AF_1980_5350073_0002.jsonl", "VL_OCR(public)_AF_1980_5350073_0002"),
    "b1980": ("baseline-AF_b1980_5350073_0001.jsonl", "VL_OCR(public)_AF_b1980_5350073_0001"),
}


def _id_order_join(bbox: list) -> str:
    return " ".join(e["data"] for e in sorted(bbox, key=lambda e: e["id"]))


def _measure(jsonl: Path, lbl_dir: Path) -> dict:
    pages = {}
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("point") == "raw":
            pages[r["page_id"]] = r["normalized_output"]

    d_id = d_ro = ref_chars = 0
    miss = extra = ref_ms = 0
    n = 0
    for page_id, hyp in pages.items():
        lp = lbl_dir / f"{page_id}.json"
        if not lp.exists():
            continue
        bbox = json.loads(lp.read_text(encoding="utf-8"))["Bbox"]
        ref_id = normalize_strict(_id_order_join(bbox))
        ref_ro = normalize_strict(" ".join(_reading_order_words(bbox)))
        d_id += levenshtein(ref_id, hyp)
        d_ro += levenshtein(ref_ro, hyp)
        ref_chars += len(ref_id)
        m, e, t = char_multiset_diff(ref_ro, hyp)
        miss += m; extra += e; ref_ms += t
        n += 1
    return {
        "n": n,
        "cer_id": d_id / ref_chars if ref_chars else 0.0,
        "cer_ro": d_ro / ref_chars if ref_chars else 0.0,
        "miss": miss / ref_ms if ref_ms else 0.0,
        "extra": extra / ref_ms if ref_ms else 0.0,
    }


def main() -> None:
    rows = []
    for name, (jsonl, lbl) in SETS.items():
        jp = REPORTS / jsonl
        if not jp.exists():
            print(f"skip {name}: {jp} 없음")
            continue
        res = _measure(jp, LBL_ROOT / lbl)
        rows.append((name, res))
        print(f"{name} n={res['n']} cer_id={res['cer_id']:.4f} "
              f"cer_ro={res['cer_ro']:.4f} miss={res['miss']:.4f} extra={res['extra']:.4f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행 및 검증**

Run: `python scripts/remeasure_reading_order.py`
Expected: 2010 `miss≈0.0098`, b1980 `miss≈0.1777`(truth-check 근사치와 일치), `cer_ro < cer_id` 모든 세트. 불일치 시 읽기순서 로직 재점검.

- [ ] **Step 3: 리포트 작성**

Step 2 출력 수치로 `docs/bench/2026-07-17-reading-order-metric.md` 작성:
- 제목/날짜/근거(스펙, #11), 실행 메타(재측정 방식 = 캐시 출력 재사용, OCR 재실행 없음).
- 4세트 표: `세트 | n | id순 CER | 읽기순서 CER | 놓침률 | 추가율`.
- 해석: 놓침률이 진짜 OCR 품질(2010 약1%, b1980 약17%)을 드러냄, 읽기순서 CER은 id순 대비 하락, 잔차는 라벨 불완전성/휴리스틱임을 명시.
- `docs/bench/2026-07-17-preprocess-ab-2010.md`와 상호 참조.

- [ ] **Step 4: 커밋**

```bash
git add scripts/remeasure_reading_order.py docs/bench/2026-07-17-reading-order-metric.md
git commit -m "feat: 읽기순서 지표 4세트 재측정 스크립트 및 리포트"
```

---

## Task 7: 상위 스펙 개정 (5.3 / 5.6 / 6 / 7.3)

**Files:**
- Modify: `docs/superpowers/specs/2026-07-13-ocr-llm-quality-harness-design.md`

- [ ] **Step 1: 5.3 채점 규칙 개정**

id순 join 서술 → 좌표 읽기순서 join. 지표 3종 정의 추가: 놓침률(주, 품질 하한, 공백 제외 글자 multiset), 읽기순서 CER(부작용 감시, paired delta), 추가율(진단). 산식과 정규화(strict, 공백 제거) 명시.

- [ ] **Step 2: 5.6 리포트 스키마 개정**

PageRecord 신규 필드(`char_miss_rate`, `char_extra_rate`, `empty_ref_with_output`, `empty_ref_extra_chars`, `reading_order_meta`)와 summary 신규 집계(micro 놓침률/추가율, `empty_ref_hallucination_count`) 반영.

- [ ] **Step 3: 6절 전처리 채택 규칙 개정**

레버는 "놓침률 개선(하락) AND 추가율-degraded_page_count 악화 없음"일 때만 채택 후보로 명시.

- [ ] **Step 4: 7.3 D8 판정규칙 개정**

품질 하한 = corrected 놓침률(통과선은 baseline 분포 근거로 LLM 트랙에서 확정), 랭킹 = 비용→속도(기존 유지, 놓침률 게이트 선행), 부작용 감시 = 읽기순서 CER 델타 + degraded_page_count + 추가율 + 빈정답 환각. 읽기순서 CER 델타는 랭킹 축이 아님을 명시.

- [ ] **Step 5: 커밋**

```bash
git add docs/superpowers/specs/2026-07-13-ocr-llm-quality-harness-design.md
git commit -m "docs: 상위 스펙 5.3/5.6/6/7.3 읽기순서 지표로 개정"
```

---

## 완료 기준 (#11 완료조건 대응)

- 좌표 읽기순서 재정렬(Task 2) + 순서무관 놓침률 주지표(Task 1,4,5) 도입 완료.
- 4세트 재측정으로 진짜 OCR 품질 확인(Task 6).
- 스펙 5.3 및 관련 절 개정(Task 7).
- 전체 회귀: `pytest tests/bench/ -q` 그린.
