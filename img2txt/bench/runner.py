"""파이프라인 러너: 원시 OCR / 조립본 / 보정본 3지점 출력."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from img2txt.assembler import assemble
from img2txt.bench.normalize import normalize_strict
from img2txt.layout import analyze_page
from img2txt.ocr import Page

if TYPE_CHECKING:
    from img2txt.backends.base import CorrectionBackend
    from img2txt.corrector import CorrectionRecord

logger = logging.getLogger(__name__)

# 타입 별칭
RecognizeFn = Callable[[Path, int], Page]
CorrectFn = Callable[[list[str], str, object], tuple[list[str], list]]


@dataclass
class PointOutputs:
    """3지점 출력 (원시 OCR / 조립본 / 보정본)."""

    page_id: str
    raw: str
    assembled: str
    corrected: str
    segments: list[str] = field(default_factory=list)
    empty: bool = False


def run_points(
    image_path: Path,
    page_id: str,
    recognize_fn: RecognizeFn,
    correct_fn: CorrectFn,
    backend: CorrectionBackend | None,
) -> PointOutputs:
    """이미지 1장을 3지점까지 처리하고 출력한다.

    Args:
        image_path: 이미지 경로.
        page_id: 페이지 식별자.
        recognize_fn: OCR 함수 (Path, int -> Page). 테스트용 의존성 주입.
        correct_fn: 보정 함수. 테스트용 의존성 주입.
        backend: 보정 백엔드 (None이면 보정 스킵).

    Returns:
        PointOutputs: 3지점 (raw, assembled, corrected) + 메타데이터.
    """
    # 1단계: page_id에서 page_num 추출 및 OCR 인식
    page_num = int(page_id.split("_")[-1])
    page = recognize_fn(image_path, page_num)

    # 2단계: 원시 텍스트 정규화
    raw_lines = [normalize_strict(line.text) for line in page.lines]
    raw_text = " ".join(raw_lines)

    # 3단계: 레이아웃 분석 및 조립
    layout = analyze_page(page)
    assembled_text = assemble([layout])
    assembled_normalized = normalize_strict(assembled_text)

    # 4단계: 보정 (backend가 None이면 스킵)
    paragraphs = list(layout.paragraphs) if layout.paragraphs else []
    if backend and paragraphs:
        corrected_paragraphs, _ = correct_fn(paragraphs, "", backend)
        corrected_text = "\n\n".join(corrected_paragraphs)
    else:
        corrected_text = assembled_text
    corrected_normalized = normalize_strict(corrected_text)

    # 5단계: 최종 출력 구성
    segments = [p for p in paragraphs if p.strip()]
    return PointOutputs(
        page_id=page_id,
        raw=normalize_strict(raw_text),
        assembled=assembled_normalized,
        corrected=corrected_normalized,
        segments=segments,
        empty=layout.is_empty,
    )
