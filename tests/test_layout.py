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
