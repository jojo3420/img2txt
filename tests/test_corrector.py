"""corrector 배치 처리 테스트: 백엔드 Mock, 길이 가드, 긴 문단 인덱스 정합성."""
from __future__ import annotations

from unittest.mock import Mock

from img2txt.corrector import (
    CorrectionRecord,
    CorrectionStatus,
    all_requests_failed,
    classify_correction,
    correct_paragraphs,
)
from img2txt.writer import format_corrections_log


def test_batch_correction_normal() -> None:
    """배치 정상 보정: 3개 문단, 일부 교정/유지."""
    backend = Mock()
    backend.correct_batch.return_value = [
        "그는 결단코 다짐했다.",
        "오류 없는 문단.",
        "20세기 최고의 트레이더"
    ]

    results, records = correct_paragraphs(
        ["그는 경단로 다짐했다.", "오류 없는 문단.", "20 세기 최고의 트레이더"],
        model="test",
        backend=backend,
    )

    assert len(results) == 3
    assert results[0] == "그는 결단코 다짐했다."
    assert results[1] == "오류 없는 문단."
    assert results[2] == "20세기 최고의 트레이더"

    assert records[0].status is CorrectionStatus.CORRECTED
    assert records[1].status is CorrectionStatus.KEPT
    assert records[2].status is CorrectionStatus.CORRECTED


def test_long_paragraph_index_integrity() -> None:
    """긴 문단 인덱스 정합성: [짧, 긴, 짧] 순서에서 긴 것만 SKIPPED_LONG, 결과는 원위치 복원."""
    backend = Mock()
    backend.correct_batch.return_value = ["교정1", "교정3"]

    long_para = "가" * 3000
    short1 = "짧은1"
    short2 = "짧은2"

    results, records = correct_paragraphs(
        [short1, long_para, short2],
        model="test",
        backend=backend,
        batch_size=10,
    )

    assert len(results) == 3
    assert results[0] == "교정1"
    assert results[1] == long_para  # 긴 문단은 원문 유지
    assert results[2] == "교정3"

    assert records[0].status is CorrectionStatus.CORRECTED
    assert records[1].status is CorrectionStatus.SKIPPED_LONG
    assert records[2].status is CorrectionStatus.CORRECTED


def test_multi_batch_with_long_paragraph_index_integrity() -> None:
    """다중 배치([짧,짧,긴,짧,짧], batch_size=2)에서 원위치 복원 정합성."""
    backend = Mock()
    backend.correct_batch.side_effect = [
        ["교정1", "교정2"],   # 배치1: 짧은1,2
        ["교정4", "교정5"],   # 배치2: 짧은4,5
    ]
    paragraphs = ["짧은1", "짧은2", "가" * 3000, "짧은4", "짧은5"]
    results, records = correct_paragraphs(paragraphs, model="test", backend=backend, batch_size=2)
    assert len(results) == 5
    assert results == ["교정1", "교정2", "가" * 3000, "교정4", "교정5"]
    assert records[2].status is CorrectionStatus.SKIPPED_LONG
    assert backend.correct_batch.call_count == 2


def test_guard_blocks_large_length_change() -> None:
    """길이 가드 GUARD_BLOCKED: 백엔드 결과가 길이 초과."""
    backend = Mock()
    original = "가" * 100
    oversized = "가" * 130  # +30% > max(5, 10%)
    backend.correct_batch.return_value = [oversized]

    results, records = correct_paragraphs(
        [original],
        model="test",
        backend=backend,
    )

    assert results == [original]
    assert records[0].status is CorrectionStatus.GUARD_BLOCKED
    assert records[0].after == oversized  # 차단 전 값 기록


def test_classify_correction_kept() -> None:
    """classify_correction: 변경 없음 -> KEPT."""
    assert classify_correction("text", "text") is CorrectionStatus.KEPT


def test_classify_correction_guarded() -> None:
    """classify_correction: 길이 초과 -> GUARD_BLOCKED."""
    original = "가" * 100
    oversized = "가" * 130
    assert classify_correction(original, oversized) is CorrectionStatus.GUARD_BLOCKED


def test_classify_correction_corrected() -> None:
    """classify_correction: 정상 변경 -> CORRECTED."""
    assert classify_correction("경단로", "결단코") is CorrectionStatus.CORRECTED


def test_all_requests_failed_detection() -> None:
    """all_requests_failed: SKIPPED_LONG 제외, FAILED만 카운트."""
    records = [
        CorrectionRecord(1, CorrectionStatus.SKIPPED_LONG, "긴 문단", "m", "a", "a"),
        CorrectionRecord(2, CorrectionStatus.FAILED, "타임아웃", "m", "b", "b"),
    ]
    assert all_requests_failed(records) is True

    records2 = [
        CorrectionRecord(1, CorrectionStatus.KEPT, "변경 없음", "m", "a", "a"),
    ]
    assert all_requests_failed(records2) is False


def test_batch_mismatch_fallback_to_original() -> None:
    """배치 개수 불일치: 원문 유지."""
    backend = Mock()
    backend.correct_batch.return_value = ["교정1"]  # 2개 예상, 1개만 반환

    results, records = correct_paragraphs(
        ["문단1", "문단2"],
        model="test",
        backend=backend,
    )

    # 개수 불일치 시 원문 유지
    assert results == ["문단1", "문단2"]


def test_backend_exception_fallback() -> None:
    """백엔드 예외: 원문 유지."""
    backend = Mock()
    backend.correct_batch.side_effect = RuntimeError("백엔드 에러")

    results, records = correct_paragraphs(
        ["문단1", "문단2"],
        model="test",
        backend=backend,
    )

    assert results == ["문단1", "문단2"]
