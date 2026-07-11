"""API 호출 보정 백엔드 (향후 구현 예정)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ApiBackend:
    """Anthropic/OpenAI API 직접 호출 백엔드 (현재 스텁)."""

    def __init__(self, api_key: str, timeout_sec: float = 120.0) -> None:
        """백엔드 초기화.

        Args:
            api_key: API 키.
            timeout_sec: 요청 타임아웃 초 (기본 120).
        """
        self.api_key: str = api_key
        self.timeout_sec: float = timeout_sec

    def correct_batch(self, paragraphs: list[str], model: str) -> list[str]:
        """배치 보정 (스텁).

        Args:
            paragraphs: 보정할 문단 목록.
            model: 모델명.

        Returns:
            원문 그대로 반환 (Phase 5에서 구현).

        Note:
            API 백엔드는 범위 밖이므로 현재 원문을 그대로 반환합니다.
        """
        logger.warning("API 백엔드는 범위 밖 (Phase 5), 원문 그대로 반환")
        return paragraphs
