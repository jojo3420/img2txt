"""보정 백엔드 기본 인터페이스 테스트."""
import pytest
from img2txt.backends.base import split_corrected_segments


def test_split_corrected_segments_normal():
    """정상 케이스: 3개 세그먼트 복원."""
    response = """===문단 1===
교정된 문단 1

===문단 2===
교정된 문단 2

===문단 3===
교정된 문단 3
"""
    result = split_corrected_segments(response, expected=3)
    assert result is not None
    assert len(result) == 3
    assert result[0] == "교정된 문단 1"
    assert result[1] == "교정된 문단 2"
    assert result[2] == "교정된 문단 3"


def test_split_corrected_segments_insufficient():
    """개수 부족: 2개만 있는데 3개 기대 → None."""
    response = """===문단 1===
교정된 문단 1

===문단 2===
교정된 문단 2
"""
    result = split_corrected_segments(response, expected=3)
    assert result is None


def test_split_corrected_segments_missing_number():
    """번호 누락: 1과 3은 있지만 2가 없음 → None."""
    response = """===문단 1===
교정된 문단 1

===문단 3===
교정된 문단 3
"""
    result = split_corrected_segments(response, expected=3)
    assert result is None


def test_split_corrected_segments_duplicate_number():
    """번호 중복: 1과 1이 있음 → None."""
    response = """===문단 1===
교정된 문단 1

===문단 1===
교정된 문단 1 (중복)
"""
    result = split_corrected_segments(response, expected=2)
    assert result is None


def test_split_corrected_segments_no_header():
    """헤더 없음 → None."""
    response = "교정된 문단 1\n교정된 문단 2"
    result = split_corrected_segments(response, expected=2)
    assert result is None


def test_split_corrected_segments_whitespace_trim():
    """헤더 전후 공백 제거."""
    response = """===문단 1===
  교정된 문단 1 (앞뒤 공백)

===문단 2===
교정된 문단 2
"""
    result = split_corrected_segments(response, expected=2)
    assert result is not None
    assert result[0] == "교정된 문단 1 (앞뒤 공백)"
    assert result[1] == "교정된 문단 2"


def test_split_corrected_segments_empty_body():
    """빈 본문 (헤더만 있음) → None (데이터 손실 방지)."""
    response = """===문단 1===

===문단 2===
교정된 문단 2
"""
    result = split_corrected_segments(response, expected=2)
    assert result is None


def test_split_corrected_segments_whitespace_only():
    """공백만 있는 본문 → None (공백뿐 strip='' 간주)."""
    response = """===문단 1===


===문단 2===
교정된 문단 2
"""
    result = split_corrected_segments(response, expected=2)
    assert result is None
