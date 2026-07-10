"""CLI 백엔드(Claude/Codex subprocess 런너) 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
import subprocess
from img2txt.backends.cli import (
    CliBackend,
    ClaudeBackend,
    CodexBackend,
    BATCH_SYSTEM_PROMPT,
    SINGLE_SYSTEM_PROMPT,
)


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


def test_codex_command_passes_prompt_as_positional_arg():
    """codex 명령이 prompt를 위치 인자로 넘긴다 (--output-last-message 파일옵션 오용 회귀 방지)."""
    backend = CodexBackend(timeout_sec=5)
    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="교정됨", returncode=0)
        backend._run_subprocess("PROMPT-SENTINEL")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["codex", "exec", "-m", "gpt-5.5", "PROMPT-SENTINEL"]
        assert "--output-last-message" not in cmd
        assert mock_run.call_args[1]["stdin"] == subprocess.DEVNULL


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


def test_cli_backend_returncode_error_fallback():
    """returncode != 0 → RuntimeError 발생 → 배치 실패 → 원문 유지."""
    backend = CliBackend("claude", timeout_sec=5)

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        # 배치 호출에서 returncode 1 → RuntimeError → except 잡아서 원문 반환
        mock_run.return_value = MagicMock(stdout="", returncode=1, stderr="CLI error")
        result = backend.correct_batch(["문단1", "문단2"], "model")
        # RuntimeError → except Exception → 원문 유지
        assert result == ["문단1", "문단2"]


def test_cli_backend_empty_stdout_raises_error():
    """stdout이 비어있거나 공백뿐 → RuntimeError 발생 → 배치 실패 → 원문 유지."""
    backend = CliBackend("claude", timeout_sec=5)

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        # 배치 호출에서 stdout="" → RuntimeError → except 잡아서 원문 반환
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = backend.correct_batch(["문단1", "문단2"], "model")
        # RuntimeError → except Exception → 원문 유지
        assert result == ["문단1", "문단2"]


def test_cli_backend_fallback_empty_response():
    """단건 폴백에서 빈 응답 → 원문 유지."""
    backend = CliBackend("claude", timeout_sec=5)

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        # 배치 호출 (불일치) → 폴백 시작
        mock_run.side_effect = [
            MagicMock(stdout="세그먼트 없음", returncode=0),  # 배치
            MagicMock(stdout="", returncode=0),  # 폴백 1 (빈 응답)
            MagicMock(stdout="", returncode=0),  # 폴백 2 (빈 응답)
        ]
        result = backend.correct_batch(["문단1", "문단2"], "model")
        # 빈 응답 → 원문 유지
        assert result == ["문단1", "문단2"]


def test_cli_backend_fallback_whitespace_response():
    """단건 폴백에서 공백만 응답 → 원문 유지."""
    backend = CliBackend("claude", timeout_sec=5)

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        # 배치 호출 (불일치) → 폴백 시작
        mock_run.side_effect = [
            MagicMock(stdout="헤더 없음", returncode=0),  # 배치
            MagicMock(stdout="   ", returncode=0),  # 폴백 1 (공백만)
            MagicMock(stdout="\n\n", returncode=0),  # 폴백 2 (개행만)
        ]
        result = backend.correct_batch(["문단1", "문단2"], "model")
        # 공백뿐 → 원문 유지
        assert result == ["문단1", "문단2"]


def test_batch_system_prompt_no_placeholder():
    """BATCH_SYSTEM_PROMPT에 {index} 리터럴이 없고 구체적 예시 포함."""
    assert "{index}" not in BATCH_SYSTEM_PROMPT, "프롬프트에 {index} 플레이스홀더 발견"
    assert "===문단 1===" in BATCH_SYSTEM_PROMPT, "구체적 예시 '===문단 1===' 미포함"
    assert "===문단 2===" in BATCH_SYSTEM_PROMPT, "구체적 예시 '===문단 2===' 미포함"


def test_fallback_uses_single_system_prompt():
    """단건 폴백이 SINGLE_SYSTEM_PROMPT를 포함해 전송."""
    backend = CliBackend("claude", timeout_sec=5)

    with patch("img2txt.backends.cli.subprocess.run") as mock_run:
        # 배치 호출 (불일치) → 폴백
        mock_run.side_effect = [
            MagicMock(stdout="헤더 없음", returncode=0),  # 배치
            MagicMock(stdout="교정됨", returncode=0),  # 폴백 1
        ]
        result = backend.correct_batch(["문단1"], "model")

        # run이 2번 호출됨 (배치 1회 + 폴백 1회)
        assert mock_run.call_count == 2

        # 폴백 호출의 prompt 확인
        fallback_call_prompt = mock_run.call_args_list[1][1]["capture_output"]
        # 실제로는 첫 번째 위치 인자인 cmd를 확인해야 함
        # cmd는 ["claude", "-p", prompt] 형태
        fallback_cmd = mock_run.call_args_list[1][0][0]
        # cmd[2]가 prompt
        assert len(fallback_cmd) == 3
        prompt = fallback_cmd[2]
        assert SINGLE_SYSTEM_PROMPT in prompt, "폴백이 SINGLE_SYSTEM_PROMPT를 포함하지 않음"
        assert "문단1" in prompt, "폴백이 원문을 포함하지 않음"
        assert result == ["교정됨"]
