"""보정 백엔드 인터페이스 + 마커 헬퍼."""
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


MARKER_FORMAT: str = "[CORRECT:{corrected},KEPT:{kept},GUARD:{guard}]"
_MARKER_PATTERN: re.Pattern[str] = re.compile(
    r"\[CORRECT:(\d+),KEPT:(\d+),GUARD:(\d+)\]"
)


def build_markers(corrected_count: int, kept_count: int,
                  guard_blocked_count: int) -> str:
    """마커 번들 생성: 백엔드 응답에서 개수 추출용 (스펙 6절).

    Args:
        corrected_count: 보정된 문단 개수.
        kept_count: 유지된 문단 개수.
        guard_blocked_count: 가드에 의해 차단된 개수.

    Returns:
        마커 문자열 형식 "[CORRECT:n,KEPT:m,GUARD:g]".
    """
    return MARKER_FORMAT.format(
        corrected=corrected_count,
        kept=kept_count,
        guard=guard_blocked_count
    )


def parse_markers(text: str) -> tuple[int, int, int] | None:
    """응답 텍스트에서 마커 파싱 (스펙 6절).

    Args:
        text: 마커를 포함할 수 있는 텍스트.

    Returns:
        (corrected, kept, guard) 튜플, 또는 마커가 없으면 None.
    """
    match = _MARKER_PATTERN.search(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def validate_marker_count(expected: int, actual: int) -> bool:
    """파싱된 개수와 실제 개수 일치 검증 (오프셋 에러 감지, 스펙 6절).

    Args:
        expected: 예상한 개수.
        actual: 실제 개수.

    Returns:
        일치하면 True, 불일치하면 False.
    """
    return expected == actual
