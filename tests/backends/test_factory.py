import os
from unittest.mock import patch

from img2txt.backends.factory import select_backend
from img2txt.backends.ollama import OllamaBackend
from img2txt.backends.cli import ClaudeBackend


def test_select_backend_explicit():
    """명시 지정: backend_name 우선."""
    backend = select_backend("qwen3:14b", backend_name="ollama")
    assert isinstance(backend, OllamaBackend)


def test_select_backend_auto_claude():
    """자동 선택: ANTHROPIC_API_KEY 감지 시 CLI(Claude)."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "key-xxx"}):
        backend = select_backend("claude-3.5-sonnet")
        assert isinstance(backend, ClaudeBackend)


def test_select_backend_auto_fallback():
    """자동 선택: API 키 없으면 ollama 폴백."""
    with patch.dict(os.environ, {}, clear=True):
        backend = select_backend("qwen3:14b")
        assert isinstance(backend, OllamaBackend)
