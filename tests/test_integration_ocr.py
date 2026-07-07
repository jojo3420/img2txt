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
