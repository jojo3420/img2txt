"""페이지 레이아웃 분석: 꼬리말 식별, 제목 분류, 문단 시작 감지."""
from __future__ import annotations

import logging

from img2txt.ocr import OcrLine

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
    """줄 목록을 본문과 꼬리말로 분리.

    규칙:
    - 띠에 걸친 줄(y_center < footer_band)중 숫자를 포함하거나
      본문 최대 폭 대비 폭이 footer_max_width_ratio 이하인 줄 = 꼬리말
    - 규칙 실패는 허용, 본문 오삭제는 불허.

    Args:
        lines: 입력 줄 목록.
        footer_band: 꼬리말 y_center 상한값.
        footer_max_width_ratio: 꼬리말 판정을 위한 폭 비율.

    Returns:
        (본문 줄 목록, 꼬리말 줄 목록).
    """
    band_outside_widths = [l.width for l in lines if l.y_center >= footer_band]
    max_body_width = max(band_outside_widths, default=0.0)
    body: list[OcrLine] = []
    footer: list[OcrLine] = []

    for line in lines:
        in_band = line.y_center < footer_band
        is_short = max_body_width and line.width < max_body_width * footer_max_width_ratio

        if in_band and (_contains_digit(line.text) or is_short):
            footer.append(line)
        else:
            body.append(line)

    return body, footer
