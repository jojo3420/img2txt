"""layout 테스트: 꼬리말 분리(위치+보조 조건), 제목 분류, 문단 감지."""
from img2txt.layout import PageLayout, analyze_page, split_footer
from img2txt.ocr import OcrLine, Page


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


_KW = dict(footer_band=0.08, footer_max_width_ratio=0.60, indent_min=0.015, title_height_ratio=1.40)


def test_title_line_is_independent_paragraph() -> None:
    page = Page(number=2, lines=[
        _line("훌륭한 투자자는", 0.90, height=0.040),        # 제목 (본문의 2배 높이)
        _line("1983년 미국의 한 일간지", 0.80),               # 본문 (들여쓰기 없음)
        _line("트레이더를 모집한다는", 0.75),
    ])
    layout = analyze_page(page, **_KW)
    assert layout.paragraphs == ["훌륭한 투자자는", "1983년 미국의 한 일간지 트레이더를 모집한다는"]
    assert layout.first_is_continuation is False   # 제목으로 시작 = 병합 대상 아님


def test_indented_line_starts_new_paragraph() -> None:
    page = Page(number=5, lines=[
        _line("앞 문단 마지막 줄이다.", 0.90),
        _line("새 문단 첫 줄이다", 0.85, x=0.13),            # 들여쓰기(0.10+0.015 이상)
        _line("이어지는 둘째 줄이다.", 0.80),
    ])
    layout = analyze_page(page, **_KW)
    assert layout.paragraphs == ["앞 문단 마지막 줄이다.", "새 문단 첫 줄이다 이어지는 둘째 줄이다."]


def test_page_starting_mid_sentence_is_continuation() -> None:
    page = Page(number=3, lines=[
        _line("주겨다는 약속을 지켰다.", 0.90),               # 들여쓰기 없음 = 이전 페이지에서 이어짐
        _line("다음 내용이 계속된다.", 0.85),
    ])
    layout = analyze_page(page, **_KW)
    assert layout.first_is_continuation is True
    assert layout.paragraphs == ["주겨다는 약속을 지켰다. 다음 내용이 계속된다."]


def test_footer_removed_and_empty_page_flagged() -> None:
    footer_only = Page(number=9, lines=[_line("23", 0.03, width=0.05)])
    layout = analyze_page(footer_only, **_KW)
    assert layout.is_empty is True
    empty = Page(number=11, lines=[])
    assert analyze_page(empty, **_KW).is_empty is True
