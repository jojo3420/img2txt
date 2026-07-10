"""구독 CLI(claude, codex) 기반 보정 백엔드."""
from __future__ import annotations

import logging
import os
import subprocess

from img2txt.backends.base import SEGMENT_HEADER, split_corrected_segments

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC: float = 120.0
BATCH_SYSTEM_PROMPT: str = (
    "다음 문단 목록에서 오탈자와 띄어쓰기만 교정한다. "
    "재작성, 추가, 삭제, 요약은 금지하고, 고칠 것이 없으면 원문 그대로이다. "
    "각 문단마다 `===문단 1===`, `===문단 2===` 처럼 번호를 넣은 헤더를 한 줄 먼저 출력하고, "
    "그 아래 교정된 문단 텍스트만 출력하라. 번호는 입력 번호와 동일하고, "
    "헤더 외에 설명, 요약, 기타 텍스트는 금지된다."
)
SINGLE_SYSTEM_PROMPT: str = (
    "다음 문단에서 오탈자와 띄어쓰기만 교정하고, "
    "재작성, 추가, 삭제, 요약은 금지하다. "
    "고칠 것이 없으면 원문 그대로 출력하고, 설명이나 기타 텍스트는 금지된다."
)


class CliBackend:
    """구독 CLI 기반 보정 백엔드."""

    def __init__(self, cli_name: str, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> None:
        """초기화.

        Args:
            cli_name: 실행할 CLI 도구명 (claude, codex).
            timeout_sec: 프로세스 타임아웃 초 (기본 120).
        """
        self.cli_name: str = cli_name
        self.timeout_sec: float = timeout_sec

    def _run_subprocess(self, prompt: str) -> str:
        """CLI를 subprocess로 실행해 결과를 반환한다.

        Args:
            prompt: CLI로 전달할 프롬프트.

        Returns:
            CLI 표준출력.

        Raises:
            subprocess.TimeoutExpired: 타임아웃 시 자식 프로세스 kill 후 발생.
            RuntimeError: CLI 반환 코드 오류 또는 빈 출력.
        """
        if self.cli_name == "claude":
            cmd = ["claude", "-p", prompt]
        elif self.cli_name == "codex":
            cmd = ["codex", "exec", "-m", "gpt-5.5", "--output-last-message", prompt]
        else:
            raise ValueError(f"미지원 CLI: {self.cli_name}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                env=os.environ.copy(),  # 환경 변수 전파
            )
            # CLI 실패 처리
            if result.returncode != 0:
                stderr_preview = result.stderr[:200] if result.stderr else "(없음)"
                raise RuntimeError(
                    f"{self.cli_name} 반환 코드 {result.returncode}: {stderr_preview}"
                )
            # 빈 출력 처리
            if not result.stdout.strip():
                raise RuntimeError(f"{self.cli_name} 빈 응답")
            return result.stdout
        except subprocess.TimeoutExpired as error:
            logger.error("CLI 타임아웃 (%0.1f초), 프로세스 kill 및 재발생", self.timeout_sec)
            raise

    def correct_batch(self, paragraphs: list[str], model: str) -> list[str]:
        """배치 프롬프트로 CLI 호출해 보정한다.

        Args:
            paragraphs: 보정할 문단 목록.
            model: (미사용, CLI는 내부 모델 사용).

        Returns:
            보정된 문단 목록. 세그먼트 분리 실패 시 단건 폴백.

        Note:
            세그먼트 분리 실패(개수 불일치/번호 누락) 시 단건 폴백.
            타임아웃/예외 시 원문 그대로 반환.
        """
        if not paragraphs:
            return []

        # 배치 프롬프트 구성
        batch_text = "\n\n".join(f"{i+1}. {p}" for i, p in enumerate(paragraphs))
        full_prompt = f"{BATCH_SYSTEM_PROMPT}\n\n{batch_text}"

        try:
            response = self._run_subprocess(full_prompt)
        except subprocess.TimeoutExpired as error:
            logger.error("배치 보정 타임아웃, 원문 그대로 반환")
            return paragraphs
        except Exception as error:
            logger.error("배치 보정 실패: %s, 원문 반환", error)
            return paragraphs

        # 세그먼트 분리
        segments = split_corrected_segments(response, len(paragraphs))
        if segments is None:
            logger.warning(
                "세그먼트 분리 실패 (예상 %d개), 단건 폴백 시도",
                len(paragraphs)
            )
            return self._fallback_single_paragraph(paragraphs)

        logger.info("배치 보정 완료: %d개 세그먼트 복원", len(segments))
        return segments

    def _fallback_single_paragraph(self, paragraphs: list[str]) -> list[str]:
        """단건 보정으로 폴백 (개수 불일치 시 최후 수단)."""
        logger.info("단건 폴백 시작: %d개 문단", len(paragraphs))
        results: list[str] = []
        for i, paragraph in enumerate(paragraphs, start=1):
            try:
                prompt = f"{SINGLE_SYSTEM_PROMPT}\n\n{paragraph}"
                response = self._run_subprocess(prompt)
                # 빈 응답이면 원문 유지
                stripped = response.strip()
                results.append(stripped if stripped else paragraph)
            except Exception as error:
                logger.warning("문단 %d 폴백 실패: %s", i, error)
                results.append(paragraph)
        return results


class ClaudeBackend(CliBackend):
    """claude -p 기반 보정 백엔드."""

    def __init__(self, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> None:
        """초기화.

        Args:
            timeout_sec: 프로세스 타임아웃 초.
        """
        super().__init__("claude", timeout_sec)


class CodexBackend(CliBackend):
    """codex exec -m gpt-5.5 기반 보정 백엔드."""

    def __init__(self, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> None:
        """초기화.

        Args:
            timeout_sec: 프로세스 타임아웃 초.
        """
        super().__init__("codex", timeout_sec)
