from __future__ import annotations

from collections import Counter
from typing import Callable, Sequence, TypeVar

T = TypeVar("T")


def levenshtein(a: Sequence[T], b: Sequence[T]) -> int:
    """편집거리(Levenshtein distance)를 동적계획법으로 계산.

    플랜 인터페이스의 str 시그니처를 Sequence[T]로 일반화하여 WER 계산 시 단어 단위 편집거리를 직접 적용 가능하게 했다.
    str도 Sequence[str]의 부분 사례이므로 기존 호출과 하위 호환을 유지한다.

    Args:
        a: 첫 번째 시퀀스 (문자열 또는 리스트).
        b: 두 번째 시퀀스 (문자열 또는 리스트).

    Returns:
        편집거리 (대체/삽입/삭제 최소 연산 횟수).
    """
    m, n = len(a), len(b)

    # DP 테이블: dp[i][j] = a[0:i]와 b[0:j] 사이 편집거리
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    # 초기화: 빈 문자열로의 변환 비용
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    # DP 채우기
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                # 문자 같음: 이전 상태 그대로
                dp[i][j] = dp[i - 1][j - 1]
            else:
                # 최소 연산: 대체(1) / 삽입(1) / 삭제(1)
                dp[i][j] = 1 + min(
                    dp[i - 1][j - 1],  # 대체
                    dp[i - 1][j],      # 삭제
                    dp[i][j - 1],      # 삽입
                )

    return dp[m][n]


def cer(
    reference: str,
    hypothesis: str,
    normalize_fn: Callable[[str], str] | None = None,
) -> float:
    """글자 오류율(Character Error Rate).

    Args:
        reference: 정답 텍스트.
        hypothesis: 가설(모델 출력) 텍스트.
        normalize_fn: 정규화 함수 (제공 시 reference/hypothesis를 정규화 후 비교).

    Returns:
        CER (0~1, 편집거리 / 정답 글자 수).
        정답이 비면 0, 정답 비고 출력 있으면 1.0.
    """
    ref = normalize_fn(reference) if normalize_fn else reference
    hyp = normalize_fn(hypothesis) if normalize_fn else hypothesis

    # 정답 글자 수가 0이면 특수 처리
    if len(ref) == 0:
        return 0.0 if len(hyp) == 0 else 1.0

    distance = levenshtein(ref, hyp)
    return distance / len(ref)


def wer(reference: str, hypothesis: str) -> float:
    """단어 오류율(Word Error Rate).

    정답을 공백 기준으로 분할 후 편집거리(단어 단위)를 계산.

    Args:
        reference: 정답 텍스트.
        hypothesis: 가설 텍스트.

    Returns:
        WER (0~1, 단어 편집거리 / 정답 단어 수).
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()

    # 단어 수가 0이면 특수 처리
    if len(ref_words) == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0

    distance = levenshtein(ref_words, hyp_words)
    return distance / len(ref_words)


def aggregate_micro(pairs: list[tuple[str, str]]) -> float:
    """미시 평균 CER (모든 쌍의 편집거리 합 / 모든 정답 글자 합).

    Args:
        pairs: (정답, 출력) 튜플 리스트.

    Returns:
        Micro CER (0~1).
    """
    total_distance = 0
    total_ref_chars = 0

    for reference, hypothesis in pairs:
        total_distance += levenshtein(reference, hypothesis)
        total_ref_chars += len(reference)

    if total_ref_chars == 0:
        return 0.0

    return total_distance / total_ref_chars


def _char_counter(text: str) -> Counter:
    """모든 공백을 제거한 글자 Counter (multiset 지표용)."""
    return Counter("".join(text.split()))


def char_multiset_diff(reference: str, hypothesis: str) -> tuple[int, int, int]:
    """공백 제외 글자 multiset 차이.

    Args:
        reference: 정답 텍스트(정규화 완료 가정).
        hypothesis: 가설 텍스트(정규화 완료 가정).

    Returns:
        (miss, extra, ref_total):
        - miss: 정답 글자 중 가설이 못 낸 초과분 합.
        - extra: 가설 글자 중 정답에 없는 초과분 합.
        - ref_total: 정답 글자수(공백 제외).
    """
    ref_c = _char_counter(reference)
    hyp_c = _char_counter(hypothesis)
    miss = sum(max(0, ref_c[ch] - hyp_c[ch]) for ch in ref_c)
    extra = sum(max(0, hyp_c[ch] - ref_c[ch]) for ch in hyp_c)
    return miss, extra, sum(ref_c.values())


def char_miss_rate(reference: str, hypothesis: str) -> float:
    """순서무관 글자 놓침률 = miss / 정답 글자수 (0이면 0.0)."""
    miss, _, total = char_multiset_diff(reference, hypothesis)
    return miss / total if total > 0 else 0.0


def char_extra_rate(reference: str, hypothesis: str) -> float:
    """순서무관 글자 추가율 = extra / 정답 글자수 (0이면 0.0)."""
    _, extra, total = char_multiset_diff(reference, hypothesis)
    return extra / total if total > 0 else 0.0
