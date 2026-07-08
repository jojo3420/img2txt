"""보정 백엔드 기본 인터페이스 테스트."""
import pytest
from img2txt.backends.base import (
    build_markers,
    parse_markers,
    validate_marker_count,
)


def test_build_markers():
    """마커 빌드 정상 케이스."""
    result = build_markers(10, 5, 2)
    assert result == "[CORRECT:10,KEPT:5,GUARD:2]"


def test_parse_markers_success():
    """마커 파싱 정상 케이스."""
    text = "어떤 텍스트 [CORRECT:10,KEPT:5,GUARD:2] 더 텍스트"
    result = parse_markers(text)
    assert result is not None
    corrected, kept, guard = result
    assert corrected == 10
    assert kept == 5
    assert guard == 2


def test_parse_markers_none():
    """마커 미포함."""
    result = parse_markers("마커 없는 텍스트")
    assert result is None


def test_validate_marker_count_match():
    """개수 일치."""
    assert validate_marker_count(17, 17) is True


def test_validate_marker_count_mismatch():
    """개수 불일치 (가드 차단)."""
    assert validate_marker_count(17, 15) is False
