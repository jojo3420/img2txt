# tests/bench/test_normalize.py
import pytest
from img2txt.bench.normalize import normalize_strict, normalize_lenient

def test_normalize_strict_nfc_composition() -> None:
    """한글 자모 조합 NFC 정규화."""
    # 조합 문자 (자모 분리): ㄱ + ㅏ (U+1100 + U+1161) 형태
    decomposed = "가"  # 가(분리형)
    result = normalize_strict(decomposed)
    # 결과는 NFC (U+AC00 가)
    assert result == "가"
    assert len(result) == 1

def test_normalize_strict_multiple_spaces() -> None:
    """연속 공백을 1개로."""
    assert normalize_strict("hello    world") == "hello world"
    assert normalize_strict("a   b   c") == "a b c"

def test_normalize_strict_newlines_to_space() -> None:
    """줄바꿈을 공백으로."""
    assert normalize_strict("line1\nline2") == "line1 line2"
    assert normalize_strict("a\n\nb") == "a b"

def test_normalize_strict_preserves_punctuation() -> None:
    """strict는 부호를 건드리지 않음."""
    assert normalize_strict('"hello"') == '"hello"'
    assert normalize_strict("가-나") == "가-나"

def test_normalize_lenient_unicode_quotes() -> None:
    """유니코드 큰따옴표(좌우 곡선) → ASCII "."""
    # U+201C, U+201D: 좌우 곡선 큰따옴표
    assert normalize_lenient("“hello”") == '"hello"'

def test_normalize_lenient_unicode_single_quotes() -> None:
    """유니코드 작은따옴표(좌우 곡선) → ASCII '."""
    # U+2018, U+2019: 좌우 곡선 작은따옴표
    assert normalize_lenient("‘hello’") == "'hello'"

def test_normalize_lenient_various_dashes() -> None:
    """각종 대시(en/em/붙임표) → ASCII -."""
    # U+2013 (en), U+2014 (em), U+2011 (붙임표)
    assert normalize_lenient("a–b") == "a-b"  # en dash
    assert normalize_lenient("a—b") == "a-b"  # em dash
    assert normalize_lenient("a‑b") == "a-b"  # non-breaking hyphen

def test_normalize_lenient_ellipsis() -> None:
    """말줄임표 1글자 → 마침표 3개."""
    # U+2026: …
    assert normalize_lenient("wait…") == "wait..."

def test_normalize_lenient_fullwidth_digits() -> None:
    """전각 숫자 → 반각."""
    # U+FF10~U+FF19: ０～９
    assert normalize_lenient("１２３") == "123"

def test_normalize_lenient_fullwidth_latin() -> None:
    """전각 라틴 → 반각."""
    # U+FF21, U+FF41: Ａ, ａ
    assert normalize_lenient("ＡＢＣ") == "ABC"
    assert normalize_lenient("ａｂｃ") == "abc"

def test_normalize_lenient_combines_strict() -> None:
    """lenient = strict + 부호 매핑."""
    text = "  한글\n테스트  "  # 공백/줄바꿈 섞임
    lenient_result = normalize_lenient(text)
    # strict 먼저 적용됨: 한글 테스트
    # 그 후 부호 매핑(이 경우 부호 없으므로 동일)
    assert lenient_result == "한글 테스트"
