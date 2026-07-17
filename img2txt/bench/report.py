from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from img2txt.bench.normalize import normalize_lenient
from img2txt.bench.dataset import PagePair
from img2txt.bench.preprocess import LEVER_CONFIGS
from img2txt.bench.scoring import char_multiset_diff

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
    char_miss_rate: float = 0.0
    char_extra_rate: float = 0.0
    empty_ref_with_output: bool = False
    empty_ref_extra_chars: int = 0
    reading_order_meta: dict = field(default_factory=dict)


def build_run_meta(
    image_dir: Path,
    page_count: int,
    preprocess: str | None,
    min_confidence: float | None,
    pairs: list[PagePair] | None = None,
    run_suffix: str | None = None,
) -> dict[str, Any]:
    """실행 메타 레코드 생성.

    Args:
        image_dir: 이미지 디렉터리 경로.
        page_count: 처리한 페이지 수.
        preprocess: 전처리 레버 이름 또는 None.
        min_confidence: OCR confidence 필터 임계값 또는 None.
        pairs: 실제 처리 대상 PagePair 리스트 (있으면 이를 기준으로 해시 계산).
        run_suffix: run_id에 붙일 suffix (있으면 사용, 없으면 내부 생성).

    Returns:
        메타 레코드 dict.
    """
    now = datetime.now().isoformat(timespec="seconds")

    if pairs:
        # 실제 처리 대상 기준 해시: page_id, image_size, reference_text 길이
        entries = [
            f"{p.page_id}:{p.image_path.stat().st_size}:{len(p.reference_text)}"
            for p in pairs
        ]
        dataset_hash = hashlib.md5("\n".join(entries).encode("utf-8")).hexdigest()
    else:
        # 기존 image_dir 방식 유지 (하위 호환)
        entries = [f"{f.name}:{f.stat().st_size}" for f in sorted(image_dir.glob("*")) if f.is_file()]
        dataset_hash = hashlib.md5("\n".join(entries).encode("utf-8")).hexdigest()

    try:
        ocrmac_version = importlib.metadata.version("ocrmac")
    except importlib.metadata.PackageNotFoundError:
        ocrmac_version = "unknown"

    if run_suffix:
        run_id = f"run-{now}-{run_suffix}"
    else:
        import uuid
        run_suffix = uuid.uuid4().hex[:8]
        run_id = f"run-{now}-{run_suffix}"

    return {
        "record_type": "run_meta",
        "run_id": run_id,
        "image_dir": str(image_dir),
        "dataset_hash": dataset_hash,
        "page_count": page_count,
        "preprocess": preprocess,
        "preprocess_config": LEVER_CONFIGS.get(preprocess) if preprocess else None,
        "min_confidence": min_confidence,
        "python_version": platform.python_version(),
        "ocrmac_version": ocrmac_version,
        "created_at": now,
    }


def write_jsonl(records: list[PageRecord], output_path: Path, run_meta: dict[str, Any] | None = None) -> None:
    """PageRecord 리스트를 JSONL로 저장.

    Args:
        records: 레코드 리스트.
        output_path: 출력 파일 경로.
        run_meta: 실행 메타 레코드 (선택사항).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        if run_meta is not None:
            line = json.dumps(run_meta, ensure_ascii=False)
            f.write(line + "\n")
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
        # Micro CER = 전체 편집거리 합 / 전체 정규화 정답 글자 합
        # strict: 정규화 기준은 normalized_ref
        # lenient: 정규화 기준은 normalize_lenient 후 결과
        total_strict = sum(r.cer_strict * len(r.normalized_ref) for r in point_records)
        total_ref_chars_strict = sum(len(r.normalized_ref) for r in point_records)

        micro_cer_strict = total_strict / total_ref_chars_strict if total_ref_chars_strict > 0 else 0.0

        # Lenient: reference_text를 normalize_lenient로 변환한 길이 기준
        lenient_normalized_lengths = [len(normalize_lenient(r.reference_text)) for r in point_records]
        total_lenient = sum(r.cer_lenient * lenient_len for r, lenient_len in zip(point_records, lenient_normalized_lengths))
        total_ref_chars_lenient = sum(lenient_normalized_lengths)

        micro_cer_lenient = total_lenient / total_ref_chars_lenient if total_ref_chars_lenient > 0 else 0.0

        # Micro miss/extra rate (문자 multiset 기준)
        total_miss = 0
        total_extra = 0
        total_ref_ms = 0
        for r in point_records:
            m, e, t = char_multiset_diff(r.normalized_ref, r.normalized_output)
            total_miss += m
            total_extra += e
            total_ref_ms += t

        micro_miss = total_miss / total_ref_ms if total_ref_ms > 0 else 0.0
        micro_extra = total_extra / total_ref_ms if total_ref_ms > 0 else 0.0

        # 빈정답 환각 페이지 수
        empty_ref_hallucination = sum(1 for r in point_records if len(r.normalized_ref) == 0 and len(r.normalized_output) > 0)

        summary["points"][point] = {
            "cer_strict": micro_cer_strict,
            "cer_lenient": micro_cer_lenient,
            "wer": sum(r.wer for r in point_records) / len(point_records) if point_records else 0.0,
            "count": len(point_records),
            "char_miss_rate": micro_miss,
            "char_extra_rate": micro_extra,
            "empty_ref_hallucination_count": empty_ref_hallucination,
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
