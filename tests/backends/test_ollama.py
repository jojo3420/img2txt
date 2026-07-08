"""Ollama 백엔드 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from img2txt.backends.ollama import OllamaBackend


def test_ollama_correct_batch_success() -> None:
    """정상 보정."""
    backend = OllamaBackend()
    with patch("img2txt.backends.ollama.request_correction") as mock_req:
        mock_req.side_effect = ["보정된 문단 1", "보정된 문단 2"]
        result = backend.correct_batch(["원문 1", "원문 2"], "qwen3:14b")
        assert result == ["보정된 문단 1", "보정된 문단 2"]


def test_ollama_correct_batch_exception() -> None:
    """요청 실패 → 원문 유지."""
    backend = OllamaBackend()
    with patch("img2txt.backends.ollama.request_correction") as mock_req:
        mock_req.side_effect = Exception("Network error")
        result = backend.correct_batch(["원문 1"], "qwen3:14b")
        assert result == ["원문 1"]  # 원문 유지
