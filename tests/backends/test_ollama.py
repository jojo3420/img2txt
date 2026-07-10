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


def test_ollama_correct_batch_empty() -> None:
    """빈 리스트 입력 → 빈 결과."""
    backend = OllamaBackend()
    with patch("img2txt.backends.ollama.request_correction") as mock_req:
        result = backend.correct_batch([], "qwen3:14b")
        assert result == []
        mock_req.assert_not_called()


def test_ollama_correct_batch_partial_failure() -> None:
    """부분 실패 (일부 성공/일부 예외) → 성공 항목은 보정, 실패 항목은 원문 유지."""
    backend = OllamaBackend()
    with patch("img2txt.backends.ollama.request_correction") as mock_req:
        mock_req.side_effect = ["보정됨", Exception("error"), "보정됨"]
        result = backend.correct_batch(["원문1", "원문2", "원문3"], "qwen3:14b")
        assert result == ["보정됨", "원문2", "보정됨"]


def test_ollama_correct_batch_empty_response() -> None:
    """빈 응답 → 원문 유지."""
    backend = OllamaBackend()
    with patch("img2txt.backends.ollama.request_correction") as mock_req:
        mock_req.side_effect = ["", "보정됨", ""]
        result = backend.correct_batch(["원문1", "원문2", "원문3"], "qwen3:14b")
        assert result == ["원문1", "보정됨", "원문3"]


def test_ollama_correct_batch_whitespace_response() -> None:
    """공백만 있는 응답 → 원문 유지."""
    backend = OllamaBackend()
    with patch("img2txt.backends.ollama.request_correction") as mock_req:
        mock_req.side_effect = ["   ", "보정됨", "\n\n"]
        result = backend.correct_batch(["원문1", "원문2", "원문3"], "qwen3:14b")
        assert result == ["원문1", "보정됨", "원문3"]
