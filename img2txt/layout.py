"""페이지 레이아웃 분석: 꼬리말 식별, 제목 분류, 문단 시작 감지."""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field

from img2txt.ocr import OcrLine, Page

logger = logging.getLogger(__name__)

# 캘리브레이션 근거 (2026-07-07, scripts/dump_coords.py로 페이지 2/3/9/10/28 실측):
#   꼬리말 yc: 짝수(24/16/42)=0.067~0.068, 홀수(Chapter)=0.065~0.068 (최대 0.068)
#   본문 최저 yc: p10=0.118, p2=0.128, p28=0.112, p9=0.123 (최소 0.112)
#   꼬리말 w: 숫자형(p2/10/28)=0.217~0.225, Chapter형(p9)=0.281
#   본문 최대 w: p2/10/28/3/9 = 0.831~0.881 (평균 0.848)
#   본문 h 최대/중앙값: p2=0.026/0.023(1.13), p10=0.028/0.023(1.22), p28=0.027/0.022(1.23) (모두 1.26 미만 확인)
#   들여쓰기 x 차이: 평균 0.025, 절반=0.0125
FOOTER_BAND: float = 0.09              # 꼬리말 yc 최대(0.068) + 본문 최저 yc(0.112) 중간값
FOOTER_MAX_WIDTH_RATIO: float = 0.35   # Chapter형 꼬리말 0.281/0.848≈0.33 포함, 숫자형 0.22/0.85≈0.26
INDENT_MIN: float = 0.014              # 들여쓰기 차이(0.025) 절반, 안전 마진 적용
TITLE_HEIGHT_RATIO: float = 1.26       # 규칙: (제목h/본문h + 1.0) / 2 = (1.52+1.0)/2 = 1.26


def _contains_digit(text: str) -> bool:
    """텍스트에 숫자가 포함되어 있는지 확인.

    Args:
        text: 검사할 텍스트.

    Returns:
        숫자가 포함되어 있으면 True, 아니면 False.
    """
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
