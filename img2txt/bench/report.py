from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PageRecord:
    """페이지별 채점 결과."""

    page_id: str
    point: str                  # "raw" / "assembled" / "corrected"
    reference_text: str
    output_text: str
    normalized_ref: str
    normalized_output: str
    cer_strict: float
    cer_lenient: float
    wer: float
    processing_time_ms: float
    empty: bool
    error_status: str           # 오류 메시지 (정상이면 "")


def write_jsonl(records: list[PageRecord], output_path: Path) -> None:
    """PageRecord 리스트를 JSONL로 저장.

    Args:
        records: 레코드 리스트.
        output_path: 출력 파일 경로.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            line = json.dumps(asdict(record), ensure_ascii=False)
            f.write(line + "\n")

    logger.info("리포트 저장: %s (%d 레코드)", output_path, len(records))


def summarize(records: list[PageRecord]) -> dict[str, Any]:
    """레코드 리스트를 요약.

    Args:
        records: 페이지별 레코드 리스트.

    Returns:
        요약 통계:
        - points: {point_name: {cer_strict, cer_lenient, wer, count}}
        - empty_page_count: 빈 결과 페이지 수
        - empty_page_ratio: 빈 결과 비율
        - degraded_page_count: 보정 후 악화 페이지 수
    """
    summary: dict[str, Any] = {}

    # 지점별 통계
    points_dict: dict[str, list[PageRecord]] = {}
    for record in records:
        if record.point not in points_dict:
            points_dict[record.point] = []
        points_dict[record.point].append(record)

    summary["points"] = {}
    for point, point_records in points_dict.items():
        # Micro CER = 전체 편집거리 합 / 전체 정답 글자 합
        # (저장된 CER 값을 사용하되, 평균이 아니라 가중치 적용)
        total_strict = sum(r.cer_strict * len(r.reference_text) for r in point_records)
        total_lenient = sum(r.cer_lenient * len(r.reference_text) for r in point_records)
        total_ref_chars = sum(len(r.reference_text) for r in point_records)

        micro_cer_strict = total_strict / total_ref_chars if total_ref_chars > 0 else 0.0
        micro_cer_lenient = total_lenient / total_ref_chars if total_ref_chars > 0 else 0.0

        summary["points"][point] = {
            "cer_strict": micro_cer_strict,
            "cer_lenient": micro_cer_lenient,
            "wer": sum(r.wer for r in point_records) / len(point_records) if point_records else 0.0,
            "count": len(point_records),
        }

    # 빈 결과 페이지
    empty_records = [r for r in records if r.empty]
    summary["empty_page_count"] = len(empty_records)
    summary["empty_page_ratio"] = len(empty_records) / len(records) if records else 0.0

    # 부작용 지표: 보정 후 악화 (assembled vs corrected 비교)
    # 각 page_id별로 assembled/corrected 짝짓기
    pages_by_id: dict[str, dict[str, PageRecord]] = {}
    for record in records:
        if record.page_id not in pages_by_id:
            pages_by_id[record.page_id] = {}
        pages_by_id[record.page_id][record.point] = record

    degraded_count = 0
    for page_id, points in pages_by_id.items():
        if "assembled" in points and "corrected" in points:
            assembled_cer = points["assembled"].cer_strict
            corrected_cer = points["corrected"].cer_strict
            if corrected_cer > assembled_cer:
                degraded_count += 1

    summary["degraded_page_count"] = degraded_count
    summary["total_pages"] = len(pages_by_id)

    return summary
