from __future__ import annotations

import pytest
from img2txt.bench.scoring import levenshtein, cer, wer, aggregate_micro

def test_levenshtein_identical() -> None:
    """같은 문자열: 거리 0."""
    assert levenshtein("hello", "hello") == 0

def test_levenshtein_empty() -> None:
    """빈 문자열: 길이만큼."""
    assert levenshtein("", "abc") == 3
    assert levenshtein("abc", "") == 3
    assert levenshtein("", "") == 0

def test_levenshtein_substitution() -> None:
    """대체: 1 거리."""
    assert levenshtein("cat", "bat") == 1  # c→b

def test_levenshtein_insertion() -> None:
    """삽입: 1 거리."""
    assert levenshtein("cat", "cart") == 1  # r 삽입

def test_levenshtein_deletion() -> None:
    """삭제: 1 거리."""
    assert levenshtein("cart", "cat") == 1  # r 삭제

def test_levenshtein_complex() -> None:
    """여러 연산: "kitten" → "sitting"."""
    # k→s, e→i, insert g
    assert levenshtein("kitten", "sitting") == 3

def test_levenshtein_korean() -> None:
    """한글: '가나다' → '가나바'."""
    assert levenshtein("가나다", "가나바") == 1  # 다→바

def test_cer_perfect() -> None:
    """완전 일치: CER 0.0."""
    result = cer("hello world", "hello world")
    assert result == 0.0

def test_cer_one_error() -> None:
    """1글자 오류: CER = 1/11."""
    result = cer("hello world", "hallo world")  # e→a
    assert abs(result - 1.0 / 11) < 0.001

def test_cer_with_normalization() -> None:
    """정규화 함수 제공: 정규화 후 비교."""
    result = cer(
        "hello  world",
        "hello world",
        normalize_fn=lambda x: x  # 그대로
    )
    # 공백 차이 1개
    assert abs(result - 1.0 / 12) < 0.001

def test_cer_empty_reference() -> None:
    """정답이 비면: CER 무한대 또는 특수 처리."""
    # 스펙: 빈 결과는 정답 글자 전부 누락 오류로 계산
    # 하지만 정답이 비면? 정답 글자 수가 0이므로 거리/0 = undefined
    # 구현: 정답이 비고 출력도 비면 0, 정답 비고 출력 있으면 무한대 또는 1.0
    result = cer("", "")
    assert result == 0.0

    # 정답 비고 출력 있으면: 분자 0, 분모 0 → 관례상 1.0
    result = cer("", "hello")
    assert result == 1.0

def test_wer_perfect() -> None:
    """완전 일치: WER 0.0."""
    result = wer("hello world", "hello world")
    assert result == 0.0

def test_wer_one_word_error() -> None:
    """1단어 오류: WER = 1/2."""
    result = wer("hello world", "hallo world")  # hello→hallo
    assert abs(result - 1.0 / 2) < 0.001

def test_wer_insertion_deletion() -> None:
    """단어 삽입/삭제 (Levenshtein on words)."""
    result = wer("the cat sat", "the big cat sat")  # big 삽입 = 1 거리
    # 정답 3단어, 편집거리 1 → WER = 1/3
    assert abs(result - 1.0 / 3) < 0.001

def test_aggregate_micro_single_page() -> None:
    """미시 평균: 1 쌍."""
    pairs = [("hello world", "hallo world")]  # 1 오류
    result = aggregate_micro(pairs)
    # 편집거리 1, 정답 글자 11 → 1/11
    assert abs(result - 1.0 / 11) < 0.001

def test_aggregate_micro_multiple_pages() -> None:
    """미시 평균: 여러 쌍 합산."""
    pairs = [
        ("a", "a"),        # 0/1
        ("bb", "cc"),      # 2/2
    ]
    result = aggregate_micro(pairs)
    # (0+2)/(1+2) = 2/3
    assert abs(result - 2.0 / 3) < 0.001

def test_aggregate_micro_with_empty_hypothesis() -> None:
    """미시 평균: 빈 출력은 전체 누락으로."""
    pairs = [
        ("hello", ""),  # 5 오류
        ("world", "world"),  # 0 오류
    ]
    result = aggregate_micro(pairs)
    # (5+0)/(5+5) = 5/10 = 0.5
    assert abs(result - 0.5) < 0.001
