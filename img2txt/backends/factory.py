"""백엔드 자동 선택."""
from __future__ import annotations

import logging
import os

from img2txt.backends.base import CorrectionBackend
from img2txt.backends.cli import ClaudeBackend, CodexBackend
from img2txt.backends.api import ApiBackend
from img2txt.backends.ollama import OllamaBackend

logger = logging.getLogger(__name__)


def select_backend(model: str, backend_name: str | None = None) -> CorrectionBackend:
    """백엔드 자동 선택.

    Args:
        model: 사용할 모델명.
        backend_name: 명시할 백엔드명 ("claude"/"codex"/"api"/"ollama").
            None이면 환경 변수로 자동 감지.

    Returns:
        선택된 백엔드 인스턴스.
    """
    # 명시 지정
    if backend_name == "ollama":
        logger.info("명시 지정: Ollama 백엔드")
        return OllamaBackend()
    elif backend_name == "claude":
        logger.info("명시 지정: Claude 백엔드")
        return ClaudeBackend()
    elif backend_name == "codex":
        logger.info("명시 지정: Codex 백엔드")
        return CodexBackend()
    elif backend_name == "api":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        logger.info("명시 지정: API 백엔드")
        return ApiBackend(api_key)

    # 자동 선택 (backend_name이 None이거나 위 4개 아님)
    if os.environ.get("ANTHROPIC_API_KEY"):
        logger.info("자동 선택: ANTHROPIC_API_KEY 감지 → Claude 백엔드")
        return ClaudeBackend()
    elif os.environ.get("OPENAI_API_KEY"):
        logger.info("자동 선택: OPENAI_API_KEY 감지 → Codex 백엔드")
        return CodexBackend()
    else:
        logger.info("자동 선택: API 키 없음 → Ollama 폴백")
        return OllamaBackend()
