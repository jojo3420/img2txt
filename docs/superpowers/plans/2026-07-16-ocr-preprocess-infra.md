# OCR 전처리 실험 인프라 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스펙 6절(OCR 전처리 실험)을 실행할 수 있는 인프라를 만든다 — 전처리 레버 3종(대비/업스케일/deskew) + confidence 필터 + 라벨 인스펙션 도구 + 실행 메타 레코드(스펙 5.6 갭 해소).

**Architecture:** 기존 하네스(PR #8, `img2txt/bench/`)에 전처리 모듈을 추가하고 러너에 `preprocess_fn`(Path→Path)을 주입한다. CLI가 `--preprocess` 레버와 `--min-confidence`를 연결하고, JSONL 첫 줄에 재현용 실행 메타를 기록한다. AI Hub 라벨 인스펙션 도구는 데이터 반입 즉시 어댑터를 확정할 수 있게 준비한다.

**Tech Stack:** Python 3.13 (`.venv`), Pillow(기존 의존), 표준 라이브러리만 추가 사용. deskew는 projection profile 자체 구현.

**스코프 밖 (데이터 반입 후 후속 플랜):** AI Hub(dataSetSn=71299) 라벨 어댑터 확정, baseline 실측 스모크(30~50페이지), 레버별 A/B 실측 판정. 라벨 구조가 미확인(스펙 5.4/8절)이라 데이터 없이 계획하면 placeholder가 되므로 분리한다. 이 플랜의 마지막 절 "후속 플랜 게이트" 참조.

## Global Constraints

- 외부 의존 추가 없음 (Pillow는 기존 의존, 그 외 표준 라이브러리만).
- 전처리 설정값은 상수로 고정한다 (대비 강도, 확대 배율, deskew 각도 범위/스텝) — Codex 리뷰 #14 반영. 값 튜닝은 실측 단계에서 상수 변경으로만.
- 각 레버는 독립 적용해 효과를 분리 측정한다 (스펙 6절). 레버 조합은 이번 스코프 밖.
- `confidence_threshold` 필터는 개선이 아닌 트레이드오프로 분류 — 측정 수단만 제공 (스펙 6절).
- deskew 실패(신뢰 낮음/각도 0)는 원본 유지 (Codex 리뷰 #14: 글자 잘림 방지).
- OCR(recognize_page)은 macOS 전용 — 모든 테스트는 가짜 함수/합성 이미지로 격리 (실 OCR 호출 금지).
- `bench_data/`는 git 추적 금지 (AI Hub 라이선스/대용량) — .gitignore 등록.
- from __future__ import annotations. Type Hints 100%, 한국어 docstring(스펙 명칭은 영어), print 금지(logging — 단 인스펙션 도구의 결과 출력은 CLI 결과물이므로 print 허용), 하드코딩 금지(상수), 함수 50줄 이내.
- 테스트 실행: `.venv/bin/python -m pytest tests/bench/ -q`, 커밋 전 전체 1회 `.venv/bin/python -m pytest tests/ -q`.
- 커밋: `<타입>: <설명>` 형식, 변경 파일만 명시적 `git add <경로>` (git add -A / . / -u 금지).

---

### Task 1: 라벨 인스펙션 도구 + bench_data 규약

**Files:**
- Create: `scripts/inspect_labels.py`
- Modify: `.gitignore` (bench_data/ 추가)
- Test: `tests/bench/test_inspect_labels.py`

**Interfaces:**
- Consumes: 없음 (독립)
- Produces: `inspect_dir(label_dir: Path, sample_count: int = 3) -> dict` — 반환 dict 키: `"extension_counts": dict[str, int]`, `"total_files": int`, `"samples": list[dict]` (각 샘플: `{"name": str, "kind": "json"|"text", "top_level_keys": list[str] | None, "preview": str}`). AI Hub 데이터 반입 직후 라벨 구조를 파악해 어댑터를 확정하는 근거를 만든다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/bench/test_inspect_labels.py
from __future__ import annotations

import json
from pathlib import Path

from scripts.inspect_labels import inspect_dir


def test_inspect_json_labels(tmp_path: Path) -> None:
    """JSON 라벨: 확장자 분포와 최상위 키를 보고한다."""
    (tmp_path / "page_001.json").write_text(
        json.dumps({"images": [], "annotations": [{"text": "가나다"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "page_002.json").write_text(
        json.dumps({"images": [], "annotations": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = inspect_dir(tmp_path)

    assert result["total_files"] == 2
    assert result["extension_counts"] == {".json": 2}
    assert result["samples"][0]["kind"] == "json"
    assert set(result["samples"][0]["top_level_keys"]) == {"images", "annotations"}


def test_inspect_text_labels(tmp_path: Path) -> None:
    """텍스트 라벨: kind=text, preview에 본문 앞부분이 담긴다."""
    (tmp_path / "page_001.txt").write_text("정답 텍스트입니다", encoding="utf-8")

    result = inspect_dir(tmp_path)

    assert result["extension_counts"] == {".txt": 1}
    assert result["samples"][0]["kind"] == "text"
    assert "정답 텍스트" in result["samples"][0]["preview"]


def test_inspect_sample_count_limit(tmp_path: Path) -> None:
    """샘플은 sample_count개까지만 수집한다."""
    for i in range(5):
        (tmp_path / f"page_{i:03d}.txt").write_text(f"본문 {i}", encoding="utf-8")

    result = inspect_dir(tmp_path, sample_count=2)

    assert result["total_files"] == 5
    assert len(result["samples"]) == 2
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/bench/test_inspect_labels.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.inspect_labels'`

- [ ] **Step 3: 구현**

```python
# scripts/inspect_labels.py
#!/usr/bin/env python3
"""AI Hub 라벨 구조 인스펙션 도구.

데이터 반입 직후 라벨 어댑터를 확정하기 위해 확장자 분포와
샘플 구조(JSON 최상위 키 / 텍스트 미리보기)를 보고한다.
결과 출력은 CLI 결과물이므로 print를 사용한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PREVIEW_CHARS: int = 300
DEFAULT_SAMPLE_COUNT: int = 3


def _sample_entry(path: Path) -> dict:
    """파일 1개의 구조 요약을 만든다."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(raw)
            keys = sorted(data.keys()) if isinstance(data, dict) else None
            return {
                "name": path.name,
                "kind": "json",
                "top_level_keys": keys,
                "preview": raw[:PREVIEW_CHARS],
            }
        except json.JSONDecodeError:
            pass
    return {
        "name": path.name,
        "kind": "text",
        "top_level_keys": None,
        "preview": raw[:PREVIEW_CHARS],
    }


def inspect_dir(label_dir: Path, sample_count: int = DEFAULT_SAMPLE_COUNT) -> dict:
    """라벨 디렉터리의 확장자 분포와 샘플 구조를 요약한다.

    Args:
        label_dir: 라벨 디렉터리.
        sample_count: 구조를 덤프할 샘플 파일 수.

    Returns:
        extension_counts / total_files / samples 요약 dict.
    """
    files = sorted(p for p in label_dir.glob("*") if p.is_file())
    extension_counts: dict[str, int] = {}
    for p in files:
        ext = p.suffix.lower()
        extension_counts[ext] = extension_counts.get(ext, 0) + 1
    samples = [_sample_entry(p) for p in files[:sample_count]]
    return {
        "extension_counts": extension_counts,
        "total_files": len(files),
        "samples": samples,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점: 요약을 JSON으로 출력한다."""
    parser = argparse.ArgumentParser(description="라벨 구조 인스펙션")
    parser.add_argument("label_dir", type=Path, help="라벨 디렉터리 경로")
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLE_COUNT, help="샘플 수")
    args = parser.parse_args(argv)

    if not args.label_dir.is_dir():
        print(f"디렉터리 없음: {args.label_dir}", file=sys.stderr)
        return 1
    result = inspect_dir(args.label_dir, args.samples)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`.gitignore` 끝에 추가:

```
# 벤치 실측 데이터 (AI Hub 라이선스/대용량 — 커밋 금지)
bench_data/
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/bench/test_inspect_labels.py -q`
Expected: 3 passed

- [ ] **Step 5: 전체 회귀 + 커밋**

Run: `.venv/bin/python -m pytest tests/ -q` → 기존 통과 수 유지 확인

```bash
git add scripts/inspect_labels.py tests/bench/test_inspect_labels.py .gitignore
git commit -m "feat: 라벨 인스펙션 도구 + bench_data 규약"
```

---

### Task 2: 전처리 모듈 (대비/업스케일/deskew)

**Files:**
- Create: `img2txt/bench/preprocess.py`
- Test: `tests/bench/test_preprocess.py`

**Interfaces:**
- Consumes: 없음 (Pillow만)
- Produces:
  - `LEVERS: dict[str, Callable[[Image.Image], Image.Image]]` — 키: `"contrast"`, `"upscale"`, `"deskew"`
  - `apply_lever(lever: str, image_path: Path, work_dir: Path) -> Path` — 레버 적용본을 work_dir에 저장하고 그 경로 반환. 알 수 없는 레버는 `ValueError`.
  - `estimate_skew_degrees(image: Image.Image) -> float` — deskew 내부 각도 추정 (테스트 노출용).
  - 상수: `CONTRAST_FACTOR = 1.5`, `UPSCALE_FACTOR = 2.0`, `DESKEW_MAX_DEGREES = 3.0`, `DESKEW_STEP_DEGREES = 0.5`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/bench/test_preprocess.py
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from img2txt.bench.preprocess import (
    LEVERS,
    UPSCALE_FACTOR,
    apply_lever,
    estimate_skew_degrees,
)


def _make_striped_image(width: int = 400, height: int = 300) -> Image.Image:
    """가로 검은 줄무늬(텍스트 행 모사) 흰 배경 합성 이미지."""
    image = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(image)
    for top in range(30, height - 30, 40):
        draw.rectangle([20, top, width - 20, top + 12], fill=0)
    return image


def test_levers_registry() -> None:
    """레버 3종이 등록돼 있다."""
    assert set(LEVERS.keys()) == {"contrast", "upscale", "deskew"}


def test_upscale_doubles_size(tmp_path: Path) -> None:
    """upscale: 가로/세로가 UPSCALE_FACTOR배."""
    src = tmp_path / "page_001.png"
    _make_striped_image().save(src)

    out_path = apply_lever("upscale", src, tmp_path / "work")

    with Image.open(out_path) as out:
        assert out.size == (int(400 * UPSCALE_FACTOR), int(300 * UPSCALE_FACTOR))
    assert out_path.parent == tmp_path / "work"


def test_contrast_spreads_midtones(tmp_path: Path) -> None:
    """contrast: 중간 회색 두 값의 간격이 넓어진다."""
    src = tmp_path / "page_001.png"
    image = Image.new("L", (10, 10), color=120)
    image.paste(140, (0, 0, 5, 10))
    image.save(src)

    out_path = apply_lever("contrast", src, tmp_path / "work")

    with Image.open(out_path) as out:
        values = sorted(set(out.getdata()))
    assert values[-1] - values[0] > 20


def test_estimate_skew_recovers_known_angle() -> None:
    """기울인 줄무늬 이미지에서 각도를 ±0.5도 내로 추정한다."""
    rotated = _make_striped_image().rotate(2.0, expand=True, fillcolor=255)

    estimated = estimate_skew_degrees(rotated)

    assert estimated == pytest.approx(-2.0, abs=0.5)


def test_deskew_keeps_straight_image(tmp_path: Path) -> None:
    """이미 반듯한 이미지는 각도 0 → 원본 그대로 저장."""
    src = tmp_path / "page_001.png"
    straight = _make_striped_image()
    straight.save(src)

    out_path = apply_lever("deskew", src, tmp_path / "work")

    with Image.open(out_path) as out:
        assert out.size == straight.size


def test_unknown_lever_raises(tmp_path: Path) -> None:
    """미등록 레버는 ValueError."""
    src = tmp_path / "page_001.png"
    _make_striped_image().save(src)

    with pytest.raises(ValueError):
        apply_lever("sharpen", src, tmp_path / "work")
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/bench/test_preprocess.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'img2txt.bench.preprocess'`

- [ ] **Step 3: 구현**

```python
# img2txt/bench/preprocess.py
"""OCR 전처리 레버 (스펙 6절): 대비 향상 / 해상도 업스케일 / deskew.

설정값은 상수로 고정한다 (재현성). 각 레버는 독립 적용 전제.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

CONTRAST_FACTOR: float = 1.5
UPSCALE_FACTOR: float = 2.0
DESKEW_MAX_DEGREES: float = 3.0
DESKEW_STEP_DEGREES: float = 0.5
# 각도 탐색은 축소본에서 수행 (속도) — 판정 각도만 원본에 적용
DESKEW_SEARCH_WIDTH: int = 500
BINARIZE_THRESHOLD: int = 128
WHITE: int = 255


def _contrast(image: Image.Image) -> Image.Image:
    """대비 향상: 중간 톤을 벌려 글자-배경 경계를 강화한다."""
    return ImageEnhance.Contrast(image).enhance(CONTRAST_FACTOR)


def _upscale(image: Image.Image) -> Image.Image:
    """해상도 업스케일: LANCZOS 보간으로 UPSCALE_FACTOR배 확대."""
    new_size = (int(image.width * UPSCALE_FACTOR), int(image.height * UPSCALE_FACTOR))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _row_variance(image: Image.Image) -> float:
    """이진화된 행 합의 분산 — 텍스트 행이 수평일수록 커진다."""
    binary = image.point(lambda p: 0 if p < BINARIZE_THRESHOLD else 1)
    pixels = list(binary.getdata())
    width, height = binary.size
    rows = [sum(pixels[y * width : (y + 1) * width]) for y in range(height)]
    mean = sum(rows) / len(rows)
    return sum((r - mean) ** 2 for r in rows) / len(rows)


def estimate_skew_degrees(image: Image.Image) -> float:
    """projection profile로 기울기 각도를 추정한다.

    후보 각도(-DESKEW_MAX~+DESKEW_MAX, DESKEW_STEP 간격)로 회전해 보고
    행 분산이 최대가 되는 각도를 반환한다 (그 각도만큼 회전하면 반듯해짐).
    """
    gray = image.convert("L")
    if gray.width > DESKEW_SEARCH_WIDTH:
        ratio = DESKEW_SEARCH_WIDTH / gray.width
        gray = gray.resize((DESKEW_SEARCH_WIDTH, max(1, int(gray.height * ratio))))

    best_angle = 0.0
    best_score = _row_variance(gray)
    steps = int(DESKEW_MAX_DEGREES / DESKEW_STEP_DEGREES)
    for i in range(-steps, steps + 1):
        angle = i * DESKEW_STEP_DEGREES
        if angle == 0.0:
            continue
        candidate = gray.rotate(angle, expand=False, fillcolor=WHITE)
        score = _row_variance(candidate)
        if score > best_score:
            best_score = score
            best_angle = angle
    return best_angle


def _deskew(image: Image.Image) -> Image.Image:
    """deskew: 추정 각도만큼 회전. 각도 0이면 원본 유지 (글자 잘림 방지)."""
    angle = estimate_skew_degrees(image)
    if angle == 0.0:
        return image
    logger.info("deskew 적용: %.1f도", angle)
    return image.rotate(angle, expand=True, fillcolor=WHITE)


LEVERS: dict[str, Callable[[Image.Image], Image.Image]] = {
    "contrast": _contrast,
    "upscale": _upscale,
    "deskew": _deskew,
}


def apply_lever(lever: str, image_path: Path, work_dir: Path) -> Path:
    """레버를 적용한 이미지를 work_dir에 저장하고 경로를 반환한다.

    Args:
        lever: LEVERS 키 중 하나.
        image_path: 원본 이미지 경로.
        work_dir: 전처리본 저장 디렉터리 (없으면 생성).

    Returns:
        전처리된 이미지 경로 (원본과 같은 파일명).

    Raises:
        ValueError: 미등록 레버.
    """
    if lever not in LEVERS:
        raise ValueError(f"알 수 없는 전처리 레버: {lever} (지원: {sorted(LEVERS)})")
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / image_path.name
    with Image.open(image_path) as image:
        processed = LEVERS[lever](image)
        processed.save(out_path)
    return out_path
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/bench/test_preprocess.py -q`
Expected: 6 passed

주의: `test_estimate_skew_recovers_known_angle`이 각도 부호로 실패하면 PIL `rotate`의 방향(반시계 양수)과 추정 부호를 맞춰 테스트가 아닌 구현/부호 해석을 점검한다. 원본을 +2.0도로 돌렸으므로 반듯하게 만드는 보정 각도는 -2.0도다.

- [ ] **Step 5: 전체 회귀 + 커밋**

Run: `.venv/bin/python -m pytest tests/ -q`

```bash
git add img2txt/bench/preprocess.py tests/bench/test_preprocess.py
git commit -m "feat: OCR 전처리 레버 3종 (contrast/upscale/deskew)"
```

---

### Task 3: 러너 전처리 주입 + CLI 레버/confidence 연결

**Files:**
- Modify: `img2txt/bench/runner.py` (run_points에 preprocess_fn 파라미터, 현재 37~66행 시그니처/1단계 부근)
- Modify: `scripts/bench_ocr.py` (parse_args 24~64행, _score_page 151~172행, main 175~241행)
- Test: `tests/bench/test_runner.py`, `tests/bench/test_bench_cli.py` (기존 파일에 테스트 추가)

**Interfaces:**
- Consumes: Task 2의 `apply_lever(lever, image_path, work_dir) -> Path`
- Produces:
  - `run_points(..., preprocess_fn: Callable[[Path], Path] | None = None)` — recognize 직전에 image_path 치환
  - CLI 인자 `--preprocess {contrast,upscale,deskew}` (기본 None=baseline), `--min-confidence FLOAT` (기본 None=필터 없음)
  - `_make_recognize_fn(min_confidence: float | None) -> RecognizeFn` — 모듈 전역 `recognize_page`를 호출 시점에 참조(late binding)해 기존 monkeypatch 통합 테스트와 호환

- [ ] **Step 1: 실패 테스트 작성 — runner**

`tests/bench/test_runner.py`의 `TestRunPoints` 클래스 안(마지막 메서드 뒤)에 추가. 기존 파일 스타일 그대로 (인라인 fake + `Page`/`OcrLine`은 파일 상단에서 이미 import됨):

```python
    def test_run_points_applies_preprocess_fn(self, tmp_path: Path):
        """preprocess_fn이 있으면 변환된 경로가 recognize_fn에 전달된다."""
        received: list[Path] = []
        original = tmp_path / "page_001.png"
        preprocessed = tmp_path / "work" / "page_001.png"

        def fake_preprocess(image_path: Path) -> Path:
            return preprocessed

        def fake_recognize(image: Path, page_num: int) -> Page:
            received.append(image)
            return Page(
                number=page_num,
                lines=[
                    OcrLine(text="가나다", confidence=0.9, x=0.1, y=0.9, width=0.8, height=0.03),
                ],
            )

        def fake_correct(paragraphs, model, backend):
            return paragraphs, []

        outputs = run_points(
            image_path=original,
            page_id="page_001",
            recognize_fn=fake_recognize,
            correct_fn=fake_correct,
            backend=None,
            preprocess_fn=fake_preprocess,
        )

        assert received == [preprocessed], "recognize_fn은 전처리된 경로를 받아야 함"
        assert "가나다" in outputs.raw
```

- [ ] **Step 2: 실패 테스트 작성 — CLI**

`tests/bench/test_bench_cli.py` 끝에 추가 (`parse_args`, `main`, `Page`, `OcrLine`, `json`, `Path`는 파일 상단에서 이미 import됨):

```python
def test_parse_args_preprocess_and_confidence() -> None:
    """--preprocess와 --min-confidence 파싱 + 기본값."""
    args = parse_args([
        "/tmp/images",
        "/tmp/labels",
        "-o", "/tmp/report.jsonl",
        "--preprocess", "upscale",
        "--min-confidence", "0.5",
    ])
    assert args.preprocess == "upscale"
    assert args.min_confidence == 0.5

    defaults = parse_args(["/tmp/images", "/tmp/labels", "-o", "/tmp/report.jsonl"])
    assert defaults.preprocess is None
    assert defaults.min_confidence is None


def test_min_confidence_filters_lines(tmp_path: Path, monkeypatch) -> None:
    """--min-confidence: 임계 미만 confidence 줄이 raw에서 제외된다."""
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()
    (image_dir / "page_001.png").touch()
    (label_dir / "page_001.txt").write_text("정답")
    output_path = tmp_path / "report.jsonl"

    def fake_recognize(image: Path, page_num: int) -> Page:
        return Page(
            number=page_num,
            lines=[
                OcrLine(text="높음", confidence=0.9, x=0.1, y=0.9, width=0.8, height=0.03),
                OcrLine(text="낮음", confidence=0.2, x=0.1, y=0.8, width=0.7, height=0.03),
            ],
        )

    monkeypatch.setattr("scripts.bench_ocr.recognize_page", fake_recognize)

    ret_code = main([
        str(image_dir), str(label_dir), "-o", str(output_path),
        "--min-confidence", "0.5",
    ])

    assert ret_code == 0
    lines = output_path.read_text(encoding="utf-8").strip().split("\n")
    raw_records = [json.loads(l) for l in lines if json.loads(l).get("point") == "raw"]
    assert len(raw_records) == 1
    assert "높음" in raw_records[0]["output_text"]
    assert "낮음" not in raw_records[0]["output_text"]


def test_preprocess_lever_wired(tmp_path: Path, monkeypatch) -> None:
    """--preprocess: recognize가 전처리본 경로(preprocessed/<레버>/)를 받는다."""
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()
    output_path = tmp_path / "report.jsonl"

    from PIL import Image
    Image.new("L", (40, 30), color=255).save(image_dir / "page_001.png")
    (label_dir / "page_001.txt").write_text("정답")

    received: list[Path] = []

    def fake_recognize(image: Path, page_num: int) -> Page:
        received.append(Path(image))
        return Page(
            number=page_num,
            lines=[
                OcrLine(text="본문", confidence=0.9, x=0.1, y=0.9, width=0.8, height=0.03),
            ],
        )

    monkeypatch.setattr("scripts.bench_ocr.recognize_page", fake_recognize)

    ret_code = main([
        str(image_dir), str(label_dir), "-o", str(output_path),
        "--preprocess", "upscale",
    ])

    assert ret_code == 0
    assert len(received) == 1
    assert received[0].parent == output_path.parent / "preprocessed" / "upscale"
    assert received[0].name == "page_001.png"
```

- [ ] **Step 3: 실패 확인**

Run: `.venv/bin/python -m pytest tests/bench/test_runner.py tests/bench/test_bench_cli.py -q`
Expected: 새 테스트 FAIL — `TypeError: run_points() got an unexpected keyword argument 'preprocess_fn'`, `AttributeError: 'Namespace' object has no attribute 'preprocess'`

- [ ] **Step 4: 구현 — runner.py**

`run_points` 시그니처에 키워드 파라미터 추가 + 1단계 앞에 적용:

```python
def run_points(
    image_path: Path,
    page_id: str,
    recognize_fn: RecognizeFn,
    correct_fn: CorrectFn,
    backend: CorrectionBackend | None,
    preprocess_fn: Callable[[Path], Path] | None = None,
) -> PointOutputs:
```

docstring Args에 `preprocess_fn: 전처리 함수 (Path -> 전처리본 Path). None이면 원본 사용.` 추가. 함수 본문 1단계(page_num 추출) 뒤, `recognize_fn` 호출 직전에:

```python
    if preprocess_fn is not None:
        image_path = preprocess_fn(image_path)
```

- [ ] **Step 5: 구현 — bench_ocr.py**

parse_args에 추가:

```python
    parser.add_argument(
        "--preprocess",
        choices=sorted(LEVERS.keys()),
        default=None,
        help="전처리 레버 (기본: 없음=baseline)"
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="OCR confidence 필터 임계값 (기본: 필터 없음)"
    )
```

import에 `from dataclasses import replace`, `import functools`, `from img2txt.bench.preprocess import LEVERS, apply_lever` 추가.

confidence 필터와 recognize 래퍼 (모듈 전역 recognize_page를 호출 시점에 참조해 monkeypatch 호환):

```python
def _make_recognize_fn(min_confidence: float | None):
    """recognize_page 래퍼 생성. min_confidence가 있으면 미만 줄을 제외한다."""

    def _recognize(image_path: Path, page_num: int):
        page = recognize_page(image_path, page_num)
        if min_confidence is None:
            return page
        kept = [line for line in page.lines if line.confidence >= min_confidence]
        return replace(page, lines=kept)

    return _recognize
```

주의: `recognize_page`가 함수 안 전역 조회이므로 `monkeypatch.setattr(bench_ocr, "recognize_page", fake)`가 계속 동작한다. `replace`는 `dataclasses.replace` — Page의 나머지 필드를 몰라도 lines만 교체된다. Page가 dataclass가 아니면 이 지점에서 멈추고 BLOCKED 보고 (임의 우회 금지).

`_score_page`가 주입을 받도록 변경:

```python
def _score_page(pair, start_time: float, recognize_fn, preprocess_fn) -> list[PageRecord]:
```

본문의 `run_points(...)` 호출을 `recognize_fn=recognize_fn, preprocess_fn=preprocess_fn`으로 교체 (`recognize_page` 직접 참조 제거). main()에서 조립:

```python
    recognize_fn = _make_recognize_fn(args.min_confidence)
    preprocess_fn = None
    if args.preprocess:
        work_dir = args.output.parent / "preprocessed" / args.preprocess
        preprocess_fn = functools.partial(apply_lever, args.preprocess, work_dir=work_dir)
```

루프의 호출을 `_score_page(pair, start_time, recognize_fn, preprocess_fn)`으로 교체.

주의: `functools.partial(apply_lever, args.preprocess, work_dir=work_dir)`은 `apply_lever(lever, image_path, work_dir)`의 2번째 위치 인자로 image_path를 받는다 — `partial(f, lever)(image_path)` 형태가 되는지 확인 (apply_lever 시그니처 순서: lever, image_path, work_dir).

- [ ] **Step 6: 통과 확인 + 기존 통합 테스트 회귀**

Run: `.venv/bin/python -m pytest tests/bench/ -q`
Expected: 전체 통과 (기존 monkeypatch 통합 테스트 포함 — _make_recognize_fn의 late binding 확인 지점)

- [ ] **Step 7: 전체 회귀 + 커밋**

Run: `.venv/bin/python -m pytest tests/ -q`

```bash
git add img2txt/bench/runner.py scripts/bench_ocr.py tests/bench/test_runner.py tests/bench/test_bench_cli.py
git commit -m "feat: 벤치 CLI 전처리 레버 + confidence 필터 연결"
```

---

### Task 4: 실행 메타 레코드 (스펙 5.6 재현 메타)

**Files:**
- Modify: `img2txt/bench/report.py` (write_jsonl에 run_meta 파라미터, build_run_meta 신설)
- Modify: `scripts/bench_ocr.py` (main에서 메타 구성-전달, 235행 write_jsonl 호출부)
- Test: `tests/bench/test_report.py`, `tests/bench/test_bench_cli.py` (기존 파일에 추가)

**Interfaces:**
- Consumes: Task 3의 CLI 인자 (preprocess, min_confidence)
- Produces:
  - `build_run_meta(image_dir: Path, page_count: int, preprocess: str | None, min_confidence: float | None) -> dict` — 키: `record_type`("run_meta" 고정), `run_id`(ISO 시각 기반), `image_dir`, `dataset_hash`(파일명:크기 정렬 목록의 md5), `page_count`, `preprocess`, `min_confidence`, `python_version`, `ocrmac_version`("unknown" 폴백), `created_at`(ISO)
  - `write_jsonl(records, output_path, run_meta: dict | None = None)` — run_meta가 있으면 첫 줄에 기록 (기존 호출 하위 호환)

- [ ] **Step 1: 실패 테스트 작성**

`tests/bench/test_report.py`에 추가:

```python
def test_build_run_meta_fields(tmp_path: Path) -> None:
    """실행 메타: 필수 필드와 record_type 마커."""
    (tmp_path / "page_001.png").write_bytes(b"fake")

    meta = build_run_meta(
        image_dir=tmp_path, page_count=1, preprocess="upscale", min_confidence=0.5
    )

    assert meta["record_type"] == "run_meta"
    assert meta["page_count"] == 1
    assert meta["preprocess"] == "upscale"
    assert meta["min_confidence"] == 0.5
    assert len(meta["dataset_hash"]) == 32
    assert meta["python_version"].startswith("3.")


def test_write_jsonl_with_run_meta(tmp_path: Path) -> None:
    """run_meta가 있으면 JSONL 첫 줄이 메타 레코드다."""
    record = PageRecord(
        page_id="page_001",
        point="raw",
        reference_text="정답",
        output_text="정딥",
        normalized_ref="정답",
        normalized_output="정딥",
        cer_strict=0.5,
        cer_lenient=0.5,
        wer=1.0,
        processing_time_ms=10.0,
        empty=False,
        error_status="",
    )
    output = tmp_path / "report.jsonl"

    write_jsonl([record], output, run_meta={"record_type": "run_meta", "run_id": "r1"})

    lines = output.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["record_type"] == "run_meta"
    assert json.loads(lines[1])["page_id"] == "page_001"
```

`build_run_meta`, `PageRecord`, `write_jsonl`, `json`, `Path` import는 test_report.py 상단 기존 import에 없는 것만 추가한다.

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/bench/test_report.py -q`
Expected: 새 테스트 FAIL — `ImportError: cannot import name 'build_run_meta'`

- [ ] **Step 3: 구현 — report.py**

```python
def build_run_meta(
    image_dir: Path,
    page_count: int,
    preprocess: str | None,
    min_confidence: float | None,
) -> dict[str, Any]:
    """재현용 실행 메타 (스펙 5.6). 데이터셋 해시는 파일명:크기 기반."""
    entries = sorted(
        f"{p.name}:{p.stat().st_size}" for p in image_dir.glob("*") if p.is_file()
    )
    dataset_hash = hashlib.md5("\n".join(entries).encode("utf-8")).hexdigest()
    try:
        ocrmac_version = importlib.metadata.version("ocrmac")
    except importlib.metadata.PackageNotFoundError:
        ocrmac_version = "unknown"
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "record_type": "run_meta",
        "run_id": f"run-{now}",
        "image_dir": str(image_dir),
        "dataset_hash": dataset_hash,
        "page_count": page_count,
        "preprocess": preprocess,
        "min_confidence": min_confidence,
        "python_version": platform.python_version(),
        "ocrmac_version": ocrmac_version,
        "created_at": now,
    }
```

import 추가: `import hashlib`, `import importlib.metadata`, `import platform`, `from datetime import datetime`. `write_jsonl`은 파일을 연 직후 run_meta가 있으면 `json.dumps(run_meta, ensure_ascii=False)` 한 줄을 먼저 쓴다 (시그니처: `run_meta: dict[str, Any] | None = None`).

- [ ] **Step 4: 구현 — bench_ocr.py 연결**

main()의 `write_jsonl(records, args.output)` 호출을:

```python
    run_meta = build_run_meta(
        image_dir=args.image_dir,
        page_count=len(pairs),
        preprocess=args.preprocess,
        min_confidence=args.min_confidence,
    )
    write_jsonl(records, args.output, run_meta=run_meta)
```

import에 `build_run_meta` 추가.

기존 CLI 테스트 수정 (메타 라인 1개 추가 반영):
- `test_cli_integration_basic` (test_bench_cli.py:85): `assert len(lines) == 3`을 `assert len(lines) == 4`로 바꾸고, 레코드 루프를 `records = [json.loads(l) for l in lines if "page_id" in json.loads(l)]` 방식으로 메타 라인과 분리한 뒤 `len(records) == 3` + 첫 줄 `json.loads(lines[0])["record_type"] == "run_meta"`를 검증한다.
- Task 3에서 추가한 `test_min_confidence_filters_lines`/`test_preprocess_lever_wired`는 point 키 필터 방식이라 메타 라인과 무관 (수정 불필요 — `.get("point")` 사용 확인).

- [ ] **Step 5: 통과 확인 + 전체 회귀 + 커밋**

Run: `.venv/bin/python -m pytest tests/bench/ -q` → 전체 통과
Run: `.venv/bin/python -m pytest tests/ -q`

```bash
git add img2txt/bench/report.py scripts/bench_ocr.py tests/bench/test_report.py tests/bench/test_bench_cli.py
git commit -m "feat: 벤치 리포트 실행 메타 레코드 (재현 메타)"
```

---

## 구현 순서 및 의존성

```
Task 1 (inspect_labels) [독립]
Task 2 (preprocess)     [독립]
Task 3 (러너/CLI 연결)   [Task 2 의존]
Task 4 (실행 메타)       [Task 3 의존 — CLI 인자 참조]
```

## 검증 기준 (Task 완료 조건)

- 각 Task: 신규 테스트 통과 + `.venv/bin/python -m pytest tests/ -q` 전체 회귀 통과
- 코드 스타일: Type Hints 100%, 한국어 docstring, print 금지(인스펙션 CLI 결과 출력 예외), 함수 50줄 이내
- 전 Task 완료 후: `--preprocess`/`--min-confidence`/메타 레코드가 가짜 OCR 통합 테스트로 end-to-end 검증됨

## 후속 플랜 게이트 (이 플랜의 태스크가 아님 — 데이터 반입 후 별도 플랜)

1. **[사용자 액션] AI Hub 데이터 반입**: dataSetSn=71299 다운로드(가입/승인 필요) → `bench_data/raw/images/`, `bench_data/raw/labels/`에 배치. 접근 조건/컴플라이언스(스펙 8절: 상업적 사용, 외부 LLM 전송 가능 여부) 확인.
2. **인스펙션**: `.venv/bin/python scripts/inspect_labels.py bench_data/raw/labels` → 라벨 구조 확정.
3. **후속 플랜 작성**: AI Hub 라벨 어댑터(인스펙션 결과 기반 코드 확정) → baseline 스모크 30~50페이지 (`--limit 50`, 원시 OCR 지점이 주 지표 — 도메인 불일치 리스크는 스펙 8절) → 레버별 A/B 실측 (`--preprocess contrast|upscale|deskew` 독립 실행) → 결과 비교 문서.
