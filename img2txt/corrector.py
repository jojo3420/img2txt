"""로컬 LLM(Ollama)으로 문단 단위 OCR 오류 보정 + 안전장치."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL: str = "http://localhost:11434"
LENGTH_GUARD_RATIO: float = 0.10   # 스펙 규칙 10 초기값, 캘리브레이션으로 조정 가능
MIN_DIFF_CHARS: int = 5            # 짧은 문단에서 정당한 보정 차단 방지 (절대 하한)
MAX_PARA_CHARS: int = 2000         # 문단 감지 실패 의심 상한 -> 보정 생략
REQUEST_TIMEOUT_SECONDS: float = 120.0
CHECK_TIMEOUT_SECONDS: float = 10.0

# 스펙 규칙 9: 보정 범위 제약 + 실측 오류 쌍 few-shot
SYSTEM_PROMPT: str = (
    "너는 한국어 책 OCR 결과 교정기다. 입력 문단에서 OCR 오류(오탈자, 잘못된 띄어쓰기)만 고쳐라. "
    "문장 재작성, 내용 추가, 삭제, 요약을 금지한다. 고칠 것이 없으면 입력을 그대로 반환하라. "
    "교정된 문단 텍스트만 출력하고 설명은 붙이지 마라.\n"
    "예시1: '그는 경단로 다짐했다' -> '그는 결단코 다짐했다'\n"
    "예시2: '20 세기 최고의 트레이더' -> '20세기 최고의 트레이더'\n"
    "예시3: '가격이 하락하면 손절한다.' -> '가격이 하락하면 손절한다.' (오류 없음, 그대로)"
)


class CorrectionStatus(str, Enum):
    """문단 보정 결과 상태."""

    CORRECTED = "보정"
    KEPT = "유지"
    GUARD_BLOCKED = "가드 차단"
    FAILED = "실패"
    SKIPPED_LONG = "긴 문단 생략"


@dataclass(frozen=True)
class CorrectionRecord:
    """문단 하나의 보정 결과 기록 (corrections.log 재료)."""

    index: int
    status: CorrectionStatus
    reason: str
    model: str
    before: str
    after: str


def check_server(base_url: str, model: str) -> str | None:
    """Ollama 접속과 모델 설치를 점검한다. 문제면 안내 메시지, 정상이면 None."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=CHECK_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return f"Ollama 서버({base_url})에 접속할 수 없습니다. 'ollama serve' 실행 여부를 확인하세요."
    names = {entry["name"] for entry in body.get("models", [])}
    if model not in names and f"{model}:latest" not in names:
        return f"모델 '{model}'이 설치되어 있지 않습니다. 'ollama pull {model}' 후 다시 실행하세요."
    return None


def request_correction(base_url: str, model: str, paragraph: str) -> str:
    """Ollama /api/chat에 문단 보정을 요청해 교정 텍스트를 반환한다."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": paragraph},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }
    http_request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        body = json.loads(response.read().decode("utf-8"))
    return str(body["message"]["content"]).strip()


def _allowed_diff(original_length: int) -> int:
    """길이 가드 허용 편차 = max(절대 하한, 비율) (스펙 규칙 10)."""
    return max(MIN_DIFF_CHARS, int(original_length * LENGTH_GUARD_RATIO))


def correct_paragraphs(
    paragraphs: list[str],
    model: str,
    base_url: str = OLLAMA_BASE_URL,
    request: Callable[[str, str, str], str] = request_correction,
) -> tuple[list[str], list[CorrectionRecord]]:
    """문단 목록을 순차 보정한다. 실패-차단 문단은 원문 유지 (스펙 규칙 8, 10~11)."""
    results: list[str] = []
    records: list[CorrectionRecord] = []
    total = len(paragraphs)
    for index, paragraph in enumerate(paragraphs, start=1):
        logger.info("보정 %d/%d", index, total)
        if len(paragraph) > MAX_PARA_CHARS:
            logger.warning("문단 %d: %d자 초과, 보정 생략", index, MAX_PARA_CHARS)
            results.append(paragraph)
            records.append(CorrectionRecord(index, CorrectionStatus.SKIPPED_LONG,
                                            f"{MAX_PARA_CHARS}자 초과", model, paragraph, paragraph))
            continue
        try:
            corrected = request(base_url, model, paragraph)
        except Exception as error:  # 보정은 향상 수단이지 단일 장애점이 아니다 (스펙 규칙 11)
            logger.warning("문단 %d: 보정 요청 실패, 원문 유지 (%s)", index, error)
            results.append(paragraph)
            records.append(CorrectionRecord(index, CorrectionStatus.FAILED,
                                            str(error), model, paragraph, paragraph))
            continue
        if abs(len(corrected) - len(paragraph)) > _allowed_diff(len(paragraph)):
            logger.warning("문단 %d: 길이 가드 차단 (%d자 -> %d자)", index, len(paragraph), len(corrected))
            results.append(paragraph)
            records.append(CorrectionRecord(index, CorrectionStatus.GUARD_BLOCKED,
                                            f"길이 {len(paragraph)} -> {len(corrected)}",
                                            model, paragraph, corrected))
        elif corrected == paragraph:
            results.append(paragraph)
            records.append(CorrectionRecord(index, CorrectionStatus.KEPT, "변경 없음",
                                            model, paragraph, paragraph))
        else:
            results.append(corrected)
            records.append(CorrectionRecord(index, CorrectionStatus.CORRECTED, "텍스트 변경",
                                            model, paragraph, corrected))
    return results, records


def all_requests_failed(records: list[CorrectionRecord]) -> bool:
    """요청한 문단 전부가 실패했는지 판단한다 (Silent Failure 방지, 스펙 6~7절).

    SKIPPED_LONG은 요청 자체를 안 했으므로 모수에서 제외한다.
    """
    requested = [r for r in records if r.status is not CorrectionStatus.SKIPPED_LONG]
    return bool(requested) and all(r.status is CorrectionStatus.FAILED for r in requested)
