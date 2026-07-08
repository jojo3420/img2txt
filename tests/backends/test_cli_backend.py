"""CLI 백엔드(Claude/Codex subprocess 런너) 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
import subprocess
from img2txt.backends.cli import CliBackend, ClaudeBackend, CodexBackend


def test_cli_backend_timeout():
    """타임아웃 시 자식 프로세스 kill 후 원문 반환."""
    backend = CliBackend("claude", timeout_sec=0.1)
    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired("claude", 0.1)
        # 타임아웃 시 원문 반환 (graceful fallback)
        result = backend.correct_batch(["원문"], "model")
        assert result == ["원문"]


def test_cli_backend_batch_parsing():
    """마커 파싱으로 개수 검증."""
    backend = CliBackend("claude", timeout_sec=5)
    response = "텍스트 내용\n[CORRECT:2,KEPT:1,GUARD:0]"
    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=response, returncode=0)
        result = backend.correct_batch(["문단1", "문단2", "문단3"], "model")
        # 마커 검증: 2+1+0 = 3개 (입력 3개와 일치)
        assert len(result) == 3


def test_claude_backend_init():
    """Claude 백엔드 초기화."""
    backend = ClaudeBackend(timeout_sec=60.0)
    assert backend.cli_name == "claude"
    assert backend.timeout_sec == 60.0


def test_codex_backend_init():
    """Codex 백엔드 초기화."""
    backend = CodexBackend(timeout_sec=60.0)
    assert backend.cli_name == "codex"
    assert backend.timeout_sec == 60.0


def test_cli_backend_marker_mismatch_fallback():
    """개수 불일치 시 단건 폴백."""
    backend = CliBackend("claude", timeout_sec=5)
    # 마커에서 2+1+0=3개라고 하지만 입력은 2개
    response = "텍스트\n[CORRECT:2,KEPT:1,GUARD:0]"

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        # 배치 호출 후 폴백 시 단건 호출
        mock_run.side_effect = [
            MagicMock(stdout=response, returncode=0),  # 배치 호출
            MagicMock(stdout="교정됨", returncode=0),  # 폴백 1
            MagicMock(stdout="교정됨", returncode=0),  # 폴백 2
        ]
        result = backend.correct_batch(["문단1", "문단2"], "model")
        assert len(result) == 2


def test_cli_backend_empty_paragraphs():
    """빈 문단 목록."""
    backend = CliBackend("fake-cli", timeout_sec=5)
    result = backend.correct_batch([], "model")
    assert result == []


def test_cli_backend_no_marker_in_response():
    """응답에 마커가 없을 때 원문 반환."""
    backend = CliBackend("claude", timeout_sec=5)
    response = "마커 없는 응답입니다"

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=response, returncode=0)
        result = backend.correct_batch(["문단1", "문단2"], "model")
        # 마커 미검출 → 원문 반환
        assert result == ["문단1", "문단2"]


def test_cli_backend_exception_fallback():
    """CLI 예외 시 원문 반환."""
    backend = CliBackend("claude", timeout_sec=5)

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        mock_run.side_effect = RuntimeError("CLI 실행 오류")
        result = backend.correct_batch(["문단1", "문단2"], "model")
        # 예외 → 원문 반환
        assert result == ["문단1", "문단2"]
