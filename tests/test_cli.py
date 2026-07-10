"""CLI 백엔드 파서 및 가용성 검사 테스트."""
from __future__ import annotations

from unittest.mock import patch

from img2txt.cli import check_backend_availability, build_parser


def test_parser_correct_backend_default() -> None:
    """correct 서브커맨드: --backend 기본값은 codex."""
    parser = build_parser()
    args = parser.parse_args(["correct", "test.txt"])
    assert args.backend == "codex"


def test_parser_correct_backend_choices() -> None:
    """correct 서브커맨드: --backend 선택지."""
    parser = build_parser()
    args = parser.parse_args(["correct", "test.txt", "--backend", "claude"])
    assert args.backend == "claude"

    args = parser.parse_args(["correct", "test.txt", "--backend", "ollama"])
    assert args.backend == "ollama"


def test_parser_correct_model_default() -> None:
    """correct 서브커맨드: --model 기본값은 None."""
    parser = build_parser()
    args = parser.parse_args(["correct", "test.txt"])
    assert args.model is None


def test_parser_correct_model_explicit() -> None:
    """correct 서브커맨드: --model 명시적 지정."""
    parser = build_parser()
    args = parser.parse_args(["correct", "test.txt", "--model", "qwen3:7b"])
    assert args.model == "qwen3:7b"


def test_check_backend_availability_codex_found() -> None:
    """codex 찾음."""
    with patch("img2txt.cli.shutil.which") as mock_which:
        mock_which.return_value = "/usr/local/bin/codex"
        result = check_backend_availability("codex", None)
        assert result is None


def test_check_backend_availability_codex_not_found() -> None:
    """codex 못 찾음."""
    with patch("img2txt.cli.shutil.which") as mock_which:
        mock_which.return_value = None
        result = check_backend_availability("codex", None)
        assert result is not None
        assert "codex" in result


def test_check_backend_availability_claude_found() -> None:
    """claude 찾음."""
    with patch("img2txt.cli.shutil.which") as mock_which:
        mock_which.return_value = "/usr/local/bin/claude"
        result = check_backend_availability("claude", None)
        assert result is None


def test_check_backend_availability_claude_not_found() -> None:
    """claude 못 찾음."""
    with patch("img2txt.cli.shutil.which") as mock_which:
        mock_which.return_value = None
        result = check_backend_availability("claude", None)
        assert result is not None
        assert "claude" in result


def test_check_backend_availability_ollama_without_model() -> None:
    """ollama인데 --model 없음."""
    result = check_backend_availability("ollama", None)
    assert result is not None
    assert "--model" in result


def test_check_backend_availability_ollama_with_model() -> None:
    """ollama + --model 지정."""
    with patch("img2txt.cli.check_server") as mock_check:
        mock_check.return_value = None
        result = check_backend_availability("ollama", "qwen3:7b")
        assert result is None
        mock_check.assert_called_once()


def test_check_backend_availability_ollama_server_error() -> None:
    """ollama 서버 접속 불가."""
    with patch("img2txt.cli.check_server") as mock_check:
        mock_check.return_value = "Ollama 서버에 접속할 수 없습니다."
        result = check_backend_availability("ollama", "qwen3:7b")
        assert result is not None
        assert "Ollama" in result
