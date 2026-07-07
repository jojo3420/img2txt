import pytest
from img2txt.assembler import assemble
from img2txt.layout import PageLayout


def _page(number: int, paragraphs: list[str] | None = None, continuation: bool = False, empty: bool = False) -> PageLayout:
    """Helper to create PageLayout for testing."""
    if paragraphs is None:
        paragraphs = []
    return PageLayout(
        number=number,
        paragraphs=paragraphs,
        first_is_continuation=continuation,
        footer_lines=[],
        is_empty=empty
    )


def test_assemble_empty_list():
    """Empty list returns empty string."""
    result = assemble([])
    assert result == ""


def test_assemble_single_valid_page():
    """Single page with paragraphs is joined."""
    layout = _page(1, ["첫 문단", "둘째 문단"])
    result = assemble([layout])
    assert result == "첫 문단\n\n둘째 문단"


def test_assemble_missing_page_marked():
    """Empty page is marked as missing."""
    layouts = [
        _page(1, ["페이지1"]),
        _page(2, empty=True),
        _page(3, ["페이지3"])
    ]
    result = assemble(layouts)
    assert "[페이지 2 누락]" in result
    assert result == "페이지1\n\n[페이지 2 누락]\n\n페이지3"


def test_assemble_consecutive_empty_pages_no_merge():
    """After missing page, next page is not merged—next page starts fresh."""
    layouts = [
        _page(1, ["페이지1"]),
        _page(2, empty=True),
        _page(3, ["페이지3"]),
    ]
    result = assemble(layouts)
    # Page 2 is missing, so marker is inserted
    # Page 3 starts fresh (no merge with marker)
    assert "[페이지 2 누락]" in result
    assert result == "페이지1\n\n[페이지 2 누락]\n\n페이지3"
