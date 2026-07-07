"""페이지 텍스트 병합: 레이아웃 문단을 하나의 본문으로 결합, 빈 페이지 표시."""
from __future__ import annotations

import logging

from img2txt.layout import PageLayout

logger = logging.getLogger(__name__)

MISSING_PAGE_MARKER_FORMAT: str = "[페이지 {number} 누락]"
PARAGRAPH_SEPARATOR: str = "\n\n"
LINE_JOINT: str = " "


def assemble(layouts: list[PageLayout]) -> str:
    """레이아웃 목록을 연결한 최종 본문 반환.

    규칙:
    - 각 페이지의 문단을 PARAGRAPH_SEPARATOR(\\n\\n)로 결합
    - 빈 페이지는 [페이지 N 누락] 표식 삽입, 다음 페이지는 새로 시작 (병합 금지)
    - 전체 페이지 목록을 PARAGRAPH_SEPARATOR로 통합

    Args:
        layouts: 페이지별 레이아웃 목록

    Returns:
        최종 본문 텍스트
    """
    paragraphs: list[str] = []
    previous_missing: bool = False

    for layout in layouts:
        # 빈 페이지 처리
        if layout.is_empty:
            logger.warning("페이지 %d: 빈 페이지, 누락 표식 삽입", layout.number)
            paragraphs.append(MISSING_PAGE_MARKER_FORMAT.format(number=layout.number))
            previous_missing = True
        else:
            # 이전 페이지가 누락되었으면 새 페이지는 병합하지 않음
            if previous_missing:
                previous_missing = False
            # 현재 페이지의 문단들을 연결
            page_paragraphs = PARAGRAPH_SEPARATOR.join(layout.paragraphs)
            paragraphs.append(page_paragraphs)

    return PARAGRAPH_SEPARATOR.join(paragraphs)
