"""파이프라인 러너: 원시 OCR / 조립본 / 보정본 3지점 출력."""
from __future__ import annotations

import logging
import re
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
    """이미지 1장을 3지점까지 처리하고 원시 출력을 반환한다.

    출력은 원시 텍스트 (normalization 미적용). 채점용 정규화는 bench_ocr.py의
    _score_outputs()에서 수행.

    Args:
        image_path: 이미지 경로.
        page_id: 페이지 식별자 (숫자로 끝나야 함, 예: "page_001", "001.png", "img1").
        recognize_fn: OCR 함수 (Path, int -> Page). 테스트용 의존성 주입.
        correct_fn: 보정 함수. 테스트용 의존성 주입.
        backend: 보정 백엔드 (None이면 보정 스킵).

    Returns:
        PointOutputs: 3지점 (raw, assembled, corrected) 원시 출력 + 메타데이터.
    """
    # 1단계: page_id에서 page_num 추출 (끝자리 숫자만 추출)
    match = re.search(r"(\d+)$", page_id)
    if match:
        page_num = int(match.group(1))
    else:
        page_num = 0
        logger.warning(f"page_id '{page_id}'에서 숫자를 추출할 수 없음, 0으로 설정")
    page = recognize_fn(image_path, page_num)

    # 2단계: 원시 텍스트 (정규화 미적용)
    raw_lines = [line.text for line in page.lines]
    raw_text = " ".join(raw_lines)

    # 3단계: 레이아웃 분석 및 조립
    layout = analyze_page(page)
    assembled_text = assemble([layout])

    # 4단계: 보정 (backend가 None이면 스킵)
    paragraphs = list(layout.paragraphs) if layout.paragraphs else []
    if backend and paragraphs:
        corrected_paragraphs, _ = correct_fn(paragraphs, "", backend)
        corrected_text = "\n\n".join(corrected_paragraphs)
    else:
        corrected_text = assembled_text

    # 5단계: empty 플래그 판정 (정규화 후 빈 문자열 기준)
    assembled_normalized_for_empty = normalize_strict(assembled_text)
    is_empty = not assembled_normalized_for_empty.strip()

    # 6단계: 최종 출력 구성
    segments = [p for p in paragraphs if p.strip()]
    return PointOutputs(
        page_id=page_id,
        raw=raw_text,
        assembled=assembled_text,
        corrected=corrected_text,
        segments=segments,
        empty=is_empty,
    )
