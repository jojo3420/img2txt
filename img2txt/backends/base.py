"""보정 백엔드 인터페이스."""
from __future__ import annotations

import re
from typing import Protocol


class CorrectionBackend(Protocol):
    """보정 백엔드 추상 인터페이스."""

    def correct_batch(self, paragraphs: list[str], model: str) -> list[str]:
        """문단 목록을 배치 보정한다.

        Args:
            paragraphs: 보정할 문단 목록.
            model: 모델명 (문자열, 백엔드별 해석 다름).

        Returns:
            보정된 문단 목록 (길이 = 입력과 동일).
        """
        ...


SEGMENT_HEADER: str = "===문단 {index}==="
_SEGMENT_PATTERN: re.Pattern[str] = re.compile(
    r"^===문단 (\d+)===$",
    re.MULTILINE
)


def split_corrected_segments(response: str, expected: int) -> list[str] | None:
    """센티넬 헤더로 응답을 세그먼트로 분리해 교정 문단 복원 (스펙 4.2).

    Args:
        response: 모델 응답 텍스트 (각 문단이 ===문단 N=== 헤더로 구분).
        expected: 예상 세그먼트 개수 (입력 문단 수).

    Returns:
        순서대로 정렬된 교정 문단 리스트. 번호 불일치/누락/중복 시 None.
    """
    matches = list(_SEGMENT_PATTERN.finditer(response))
    if len(matches) != expected:
        return None

    # 각 매치의 번호 추출 및 검증
    segments: dict[int, str] = {}
    for i, match in enumerate(matches):
        header_line_end = match.end()
        segment_num = int(match.group(1))

        # 번호 검증: 1..expected 범위이고 중복 없음
        if segment_num < 1 or segment_num > expected or segment_num in segments:
            return None

        # 다음 헤더 위치 또는 문자열 끝
        if i + 1 < len(matches):
            next_header_start = matches[i + 1].start()
            text = response[header_line_end:next_header_start]
        else:
            text = response[header_line_end:]

        # 앞뒤 공백 제거
        segments[segment_num] = text.strip()

    # 1..expected가 모두 있는지 확인
    if set(segments.keys()) != set(range(1, expected + 1)):
        return None

    # 순서대로 반환
    return [segments[i] for i in range(1, expected + 1)]
