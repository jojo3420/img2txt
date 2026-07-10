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


def test_cli_backend_batch_parsing_with_segments():
    """센티넬 헤더로 세그먼트 복원."""
    backend = CliBackend("claude", timeout_sec=5)
    response = """===문단 1===
교정된 문단1

===문단 2===
교정된 문단2

===문단 3===
교정된 문단3
"""
    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=response, returncode=0)
        result = backend.correct_batch(["원문1", "원문2", "원문3"], "model")
        # 세그먼트 복원: 원문과 다른 텍스트 확인 (no-op 회귀 방지)
        assert len(result) == 3
        assert result[0] == "교정된 문단1"
        assert result[1] == "교정된 문단2"
        assert result[2] == "교정된 문단3"


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


def test_cli_backend_segment_mismatch_fallback():
    """세그먼트 개수 불일치 시 단건 폴백."""
    backend = CliBackend("claude", timeout_sec=5)
    # 세그먼트는 1개만 있지만 입력은 2개 예상
    response = """===문단 1===
교정된 문단 1
"""

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        # 배치 호출 후 폴백 시 단건 호출
        mock_run.side_effect = [
            MagicMock(stdout=response, returncode=0),  # 배치 호출 (불일치)
            MagicMock(stdout="교정됨1", returncode=0),  # 폴백 1
            MagicMock(stdout="교정됨2", returncode=0),  # 폴백 2
        ]
        result = backend.correct_batch(["문단1", "문단2"], "model")
        assert len(result) == 2
        # 폴백 결과 사용
        assert result == ["교정됨1", "교정됨2"]


def test_cli_backend_empty_paragraphs():
    """빈 문단 목록."""
    backend = CliBackend("fake-cli", timeout_sec=5)
    result = backend.correct_batch([], "model")
    assert result == []


def test_cli_backend_no_segment_header_in_response():
    """응답에 세그먼트 헤더가 없을 때 단건 폴백."""
    backend = CliBackend("claude", timeout_sec=5)
    response = "헤더 없는 응답입니다"

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        # 배치 호출 후 폴백 호출
        mock_run.side_effect = [
            MagicMock(stdout=response, returncode=0),  # 배치 호출 (헤더 없음)
            MagicMock(stdout="교정됨1", returncode=0),  # 폴백 1
            MagicMock(stdout="교정됨2", returncode=0),  # 폴백 2
        ]
        result = backend.correct_batch(["문단1", "문단2"], "model")
        # 세그먼트 미검출 → 단건 폴백
        assert len(result) == 2
        assert result == ["교정됨1", "교정됨2"]


def test_cli_backend_exception_fallback():
    """CLI 예외 시 원문 반환."""
    backend = CliBackend("claude", timeout_sec=5)

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        mock_run.side_effect = RuntimeError("CLI 실행 오류")
        result = backend.correct_batch(["문단1", "문단2"], "model")
        # 예외 → 원문 반환
        assert result == ["문단1", "문단2"]
