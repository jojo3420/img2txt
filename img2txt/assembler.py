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
