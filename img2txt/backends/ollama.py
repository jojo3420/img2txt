"""로컬 Ollama HTTP 보정 백엔드."""
from __future__ import annotations

import logging

from img2txt.corrector import request_correction

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL: str = "http://localhost:11434"


class OllamaBackend:
    """로컬 Ollama /api/chat 기반 보정."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL) -> None:
        """백엔드 초기화.

        Args:
            base_url: Ollama 서버 주소 (기본: localhost:11434).
        """
        self.base_url: str = base_url

    def correct_batch(self, paragraphs: list[str], model: str) -> list[str]:
        """문단 목록을 보정한다 (현재 단건 루프).

        Args:
            paragraphs: 보정할 문단 목록.
            model: Ollama 모델명.

        Returns:
            보정된 문단 목록.
        """
        results: list[str] = []
        for index, paragraph in enumerate(paragraphs, start=1):
            logger.info("Ollama 보정 %d/%d", index, len(paragraphs))
            try:
                corrected = request_correction(self.base_url, model, paragraph)
                results.append(corrected)
            except Exception as error:
                logger.warning("문단 %d 보정 실패, 원문 유지: %s", index, error)
                results.append(paragraph)
        return results
