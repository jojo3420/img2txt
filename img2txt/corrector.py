"""로컬 LLM(Ollama)으로 문단 단위 OCR 오류 보정 + 안전장치."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from img2txt.backends.base import CorrectionBackend

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL: str = "http://localhost:11434"
DEFAULT_BATCH_SIZE: int = 10       # 스펙 4.2: CLI 오버헤드 상쇄, 실측 캘리브레이션 대상
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


def classify_correction(original: str, corrected: str) -> CorrectionStatus:
    """보정 결과를 분류한다 (길이 가드 판정).

    Args:
        original: 원문.
        corrected: 보정된 문단.

    Returns:
        CorrectionStatus 판정.
    """
    if corrected == original:
        return CorrectionStatus.KEPT
    if abs(len(corrected) - len(original)) > _allowed_diff(len(original)):
        return CorrectionStatus.GUARD_BLOCKED
    return CorrectionStatus.CORRECTED


def correct_paragraphs(
    paragraphs: list[str],
    model: str,
    backend: CorrectionBackend,
    batch_size: int = DEFAULT_BATCH_SIZE,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[str], list[CorrectionRecord]]:
    """문단 목록을 배치 보정한다. 실패-차단 문단은 원문 유지 (스펙 규칙 8, 10~11).

    Args:
        paragraphs: 보정할 문단 목록.
        model: 백엔드에 전달할 모델명.
        backend: CorrectionBackend 구현체 (correct_batch 메서드 제공).
        batch_size: 배치당 문단 수 (기본 10).
        progress_callback: 진행 상황 콜백 (done, total) 튜플. 선택적.

    Returns:
        (보정된 문단 리스트, 기록 리스트).
    """
    results: list[str | None] = [None] * len(paragraphs)
    records: list[CorrectionRecord | None] = [None] * len(paragraphs)

    if batch_size < 1:
        raise ValueError("batch_size는 1 이상이어야 합니다")

    # 긴 문단 분리
    short_paragraphs: list[str] = []
    short_to_orig_idx: list[int] = []

    for index, paragraph in enumerate(paragraphs):
        if len(paragraph) > MAX_PARA_CHARS:
            logger.warning("문단 %d: %d자 초과, 보정 생략", index + 1, MAX_PARA_CHARS)
            results[index] = paragraph
            records[index] = CorrectionRecord(
                index + 1,
                CorrectionStatus.SKIPPED_LONG,
                f"{MAX_PARA_CHARS}자 초과",
                model,
                paragraph,
                paragraph,
            )
        else:
            short_paragraphs.append(paragraph)
            short_to_orig_idx.append(index)

    # 배치 처리
    long_done = len(paragraphs) - len(short_paragraphs)
    batch_results: list[str] = []
    failed_flags: list[bool] = []

    # 배치가 없는 경우(모든 문단이 긴 경우) 초기 진행 보고
    if long_done > 0 and len(short_paragraphs) == 0 and progress_callback:
        progress_callback(long_done, len(paragraphs))

    for chunk_start in range(0, len(short_paragraphs), batch_size):
        chunk_end = min(chunk_start + batch_size, len(short_paragraphs))
        chunk = short_paragraphs[chunk_start:chunk_end]
        chunk_failed = False

        try:
            chunk_result = backend.correct_batch(chunk, model)
        except Exception as error:
            logger.error("배치 보정 실패: %s, 원문 유지", error)
            chunk_result = chunk
            chunk_failed = True

        # 개수 불일치 방어
        if len(chunk_result) != len(chunk):
            logger.warning(
                "배치 결과 개수 불일치 (예상 %d개, 수신 %d개), 원문 유지",
                len(chunk), len(chunk_result)
            )
            chunk_result = chunk
            chunk_failed = True

        batch_results.extend(chunk_result)
        failed_flags.extend([chunk_failed] * len(chunk))

        # 배치 완료 후 진행 보고
        if progress_callback:
            progress_callback(long_done + chunk_end, len(paragraphs))

    # 원위치 복원 및 분류
    for batch_idx, orig_idx in enumerate(short_to_orig_idx):
        original = paragraphs[orig_idx]
        corrected = batch_results[batch_idx]

        if failed_flags[batch_idx]:
            results[orig_idx] = original
            records[orig_idx] = CorrectionRecord(
                orig_idx + 1, CorrectionStatus.FAILED,
                "보정 실패 (백엔드 예외/개수 불일치)", model, original, original,
            )
            continue

        status = classify_correction(original, corrected)
        reason: str
        if status is CorrectionStatus.GUARD_BLOCKED:
            reason = f"길이 {len(original)} -> {len(corrected)}"
            results[orig_idx] = original
            logger.warning("문단 %d: 길이 가드 차단 (%d자 -> %d자)", orig_idx + 1, len(original), len(corrected))
        elif status is CorrectionStatus.KEPT:
            reason = "변경 없음"
            results[orig_idx] = original
        else:  # CORRECTED
            reason = "텍스트 변경"
            results[orig_idx] = corrected

        records[orig_idx] = CorrectionRecord(
            orig_idx + 1,
            status,
            reason,
            model,
            original,
            corrected,
        )

    # 불변식 검증 + 타입 좁히기: 모든 원위치가 채워졌는지 확인
    final_results: list[str] = []
    final_records: list[CorrectionRecord] = []
    for i in range(len(paragraphs)):
        result, record = results[i], records[i]
        if result is None or record is None:
            raise RuntimeError(f"결과 인덱스 {i}: 미처리 문단(내부 오류)")
        final_results.append(result)
        final_records.append(record)
    return final_results, final_records


def all_requests_failed(records: list[CorrectionRecord]) -> bool:
    """요청한 문단 전부가 실패했는지 판단한다 (Silent Failure 방지, 스펙 6~7절).

    SKIPPED_LONG은 요청 자체를 안 했으므로 모수에서 제외한다.
    """
    requested = [r for r in records if r.status is not CorrectionStatus.SKIPPED_LONG]
    return bool(requested) and all(r.status is CorrectionStatus.FAILED for r in requested)
