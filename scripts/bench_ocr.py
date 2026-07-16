#!/usr/bin/env python3
"""OCR 품질 측정 하네스 CLI."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# 프로젝트 모듈
from img2txt.bench.normalize import normalize_strict, normalize_lenient
from img2txt.bench.scoring import cer, wer
from img2txt.bench.dataset import load_pairs
from img2txt.bench.runner import run_points
from img2txt.bench.report import PageRecord, write_jsonl, summarize
from img2txt.ocr import recognize_page
from img2txt.corrector import correct_paragraphs

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 인자 파싱.

    Args:
        argv: 인자 목록 (기본: sys.argv[1:]).

    Returns:
        파싱된 인자.
    """
    parser = argparse.ArgumentParser(
        description="OCR 품질 측정 하네스: 3지점(raw/assembled/corrected) 채점"
    )
    parser.add_argument(
        "image_dir",
        type=Path,
        help="이미지 디렉터리 경로"
    )
    parser.add_argument(
        "label_dir",
        type=Path,
        help="라벨 디렉터리 경로"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        required=True,
        help="JSONL 리포트 출력 경로"
    )
    parser.add_argument(
        "--allow-skip",
        action="store_true",
        help="라벨 누락 시 스킵 (기본: 중단)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="처리 페이지 수 제한 (기본: 전체)"
    )

    return parser.parse_args(argv)


def _default_label_adapter(label_path: Path) -> str:
    """기본 라벨 어댑터: txt 파일 읽기.

    Note: 실제 AI Hub 어댑터 구조는 미확인. 별도 태스크 대상.
    """
    return label_path.read_text(encoding="utf-8").strip()


def _score_outputs(pair, outputs, start_time: float) -> list[PageRecord]:
    """3지점 출력 채점.

    Args:
        pair: PagePair 인스턴스.
        outputs: PointOutputs (raw, assembled, corrected).
        start_time: 처리 시작 시간.

    Returns:
        PageRecord 리스트 (3개: raw, assembled, corrected).
    """
    records: list[PageRecord] = []
    for point_name in ["raw", "assembled", "corrected"]:
        point_text = getattr(outputs, point_name)
        normalized_ref = normalize_strict(pair.reference_text)
        normalized_output = normalize_strict(point_text)

        cer_strict_score = cer(normalized_ref, normalized_output)
        cer_lenient_score = cer(
            pair.reference_text, point_text, normalize_fn=normalize_lenient
        )
        wer_score = wer(normalized_ref, normalized_output)

        elapsed_ms = (time.time() - start_time) * 1000

        record = PageRecord(
            page_id=pair.page_id,
            point=point_name,
            reference_text=pair.reference_text,
            output_text=point_text,
            normalized_ref=normalized_ref,
            normalized_output=normalized_output,
            cer_strict=cer_strict_score,
            cer_lenient=cer_lenient_score,
            wer=wer_score,
            processing_time_ms=elapsed_ms,
            empty=outputs.empty,
            error_status="",
        )
        records.append(record)
    return records


def _create_error_records(pair, start_time: float, error: Exception) -> list[PageRecord]:
    """오류 발생 시 3지점 오류 레코드 생성.

    Args:
        pair: PagePair 인스턴스.
        start_time: 처리 시작 시간.
        error: 발생한 예외.

    Returns:
        PageRecord 리스트 (3개: 모두 오류 상태).
    """
    records: list[PageRecord] = []
    for point in ["raw", "assembled", "corrected"]:
        elapsed_ms = (time.time() - start_time) * 1000
        record = PageRecord(
            page_id=pair.page_id,
            point=point,
            reference_text=pair.reference_text,
            output_text="",
            normalized_ref="",
            normalized_output="",
            cer_strict=1.0,
            cer_lenient=1.0,
            wer=1.0,
            processing_time_ms=elapsed_ms,
            empty=False,
            error_status=str(error),
        )
        records.append(record)
    return records


def _score_page(pair, start_time: float) -> list[PageRecord]:
    """페이지 3지점 채점 (raw, assembled, corrected).

    Args:
        pair: PagePair 인스턴스.
        start_time: 처리 시작 시간.

    Returns:
        3개의 PageRecord (raw, assembled, corrected) 리스트.
    """
    try:
        outputs = run_points(
            image_path=pair.image_path,
            page_id=pair.page_id,
            recognize_fn=recognize_page,
            correct_fn=correct_paragraphs,
            backend=None,
        )
        return _score_outputs(pair, outputs, start_time)
    except Exception as e:
        logger.error("처리 페이지 오류: %s", e)
        return _create_error_records(pair, start_time, e)


def main(argv: list[str] | None = None) -> int:
    """메인 함수.

    Args:
        argv: 인자 목록 (테스트용).

    Returns:
        종료 코드: 0 (성공) / 1 (오류).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 인자 파싱
    try:
        args = parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1

    # 경로 검증
    if not args.image_dir.exists():
        logger.error("이미지 디렉터리 없음: %s", args.image_dir)
        return 1

    if not args.label_dir.exists():
        logger.error("라벨 디렉터리 없음: %s", args.label_dir)
        return 1

    # 데이터 로드
    try:
        pairs = load_pairs(args.image_dir, args.label_dir, _default_label_adapter)
    except FileNotFoundError as e:
        if args.allow_skip:
            logger.warning("라벨 누락: %s (스킵)", e)
            pairs = []
        else:
            logger.error("라벨 누락: %s", e)
            return 1

    # 제한 적용
    if args.limit:
        pairs = pairs[: args.limit]

    if not pairs:
        logger.error("처리할 페이지 없음")
        return 1

    logger.info("처리 페이지: %d개", len(pairs))

    # 3지점 채점
    records: list[PageRecord] = []
    for pair in pairs:
        logger.info("처리 중: %s", pair.page_id)
        start_time = time.time()
        records.extend(_score_page(pair, start_time))

    # 리포트 저장
    write_jsonl(records, args.output)

    # 요약 출력
    summary = summarize(records)
    logger.info("요약: %s", json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
