"""assembler 테스트: 경계 병합, 새 문단, 제목 페이지, 누락 페이지 표식."""
from img2txt.assembler import assemble
from img2txt.layout import PageLayout


def _page(number: int, paragraphs: list[str], continuation: bool = False, empty: bool = False) -> PageLayout:
    return PageLayout(number=number, paragraphs=paragraphs,
                      first_is_continuation=continuation, footer_lines=[], is_empty=empty)


def test_boundary_merge_joins_split_paragraph() -> None:
    result = assemble([
        _page(2, ["기업에 지원해"]),
        _page(3, ["주겨다는 약속을 지켰다."], continuation=True),
    ])
    assert result == "기업에 지원해 주겨다는 약속을 지켰다."


def test_paragraph_start_not_merged() -> None:
    result = assemble([
        _page(2, ["첫 문단이다."]),
        _page(3, ["새 문단이다."], continuation=False),
    ])
    assert result == "첫 문단이다.\n\n새 문단이다."


def test_title_page_not_merged() -> None:
    # 제목으로 시작하는 페이지는 analyze_page가 continuation=False로 반환한다
    result = assemble([
        _page(4, ["앞 장 마지막 문단."]),
        _page(5, ["Chapter 02 제목", "본문 시작."], continuation=False),
    ])
    assert result == "앞 장 마지막 문단.\n\nChapter 02 제목\n\n본문 시작."


def test_empty_page_inserts_marker_and_blocks_merge() -> None:
    result = assemble([
        _page(2, ["문장이 여기서 끊기고"]),
        _page(3, [], empty=True),
        _page(4, ["여기로 이어지는 것처럼 보인다."], continuation=True),
    ])
    # 누락 페이지를 건너뛴 병합은 소리 없는 본문 훼손 -> 표식 + 병합 금지 (스펙 규칙 5)
    assert result == "문장이 여기서 끊기고\n\n[페이지 3 누락]\n\n여기로 이어지는 것처럼 보인다."
