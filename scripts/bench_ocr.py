#!/usr/bin/env python3
"""OCR 품질 측정 하네스 CLI."""
from __future__ import annotations

import argparse
import functools
import json
import logging
import sys
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Callable

# 프로젝트 모듈
from img2txt.bench.aihub import aihub_label_adapter
from img2txt.bench.normalize import normalize_strict, normalize_lenient
from img2txt.bench.scoring import cer, wer
from img2txt.bench.dataset import load_pairs, PagePair
from img2txt.bench.runner import run_points, RecognizeFn
from img2txt.bench.report import PageRecord, write_jsonl, summarize, build_run_meta
from img2txt.bench.preprocess import LEVERS, apply_lever
from img2txt.ocr import recognize_page, Page
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
    parser.add_argument(
        "--preprocess",
        choices=sorted(LEVERS.keys()),
        default=None,
        help="전처리 레버 (기본: 없음=baseline)"
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="OCR confidence 필터 임계값 (기본: 필터 없음)"
    )
    parser.add_argument(
        "--label-format",
        choices=["txt", "aihub"],
        default="txt",
        help="라벨 형식 (기본 txt: 평문, aihub: 페이지형 공공문서 JSON)"
    )

    return parser.parse_args(argv)


def _default_label_adapter(label_path: Path) -> str:
    """기본 라벨 어댑터: txt 파일 읽기.

    Note: 실제 AI Hub 어댑터 구조는 미확인. 별도 태스크 대상.
    """
    return label_path.read_text(encoding="utf-8").strip()


def _make_recognize_fn(min_confidence: float | None) -> RecognizeFn:
    """recognize_page 래퍼 생성. min_confidence가 있으면 미만 줄을 제외한다."""

    def _recognize(image_path: Path, page_num: int) -> Page:
        page = recognize_page(image_path, page_num)
        if min_confidence is None:
            return page
        kept = [line for line in page.lines if line.confidence >= min_confidence]
        return replace(page, lines=kept)

    return _recognize


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
    normalized_ref = normalize_strict(pair.reference_text)
    for point in ["raw", "assembled", "corrected"]:
        elapsed_ms = (time.time() - start_time) * 1000
        record = PageRecord(
            page_id=pair.page_id,
            point=point,
            reference_text=pair.reference_text,
            output_text="",
            normalized_ref=normalized_ref,
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


def _score_page(
    pair: PagePair,
    start_time: float,
    recognize_fn: RecognizeFn,
    preprocess_fn: Callable[[Path], Path] | None
) -> list[PageRecord]:
    """페이지 3지점 채점 (raw, assembled, corrected).

    Args:
        pair: PagePair 인스턴스.
        start_time: 처리 시작 시간.
        recognize_fn: OCR 함수.
        preprocess_fn: 전처리 함수.

    Returns:
        3개의 PageRecord (raw, assembled, corrected) 리스트.
    """
    try:
        outputs = run_points(
            image_path=pair.image_path,
            page_id=pair.page_id,
            recognize_fn=recognize_fn,
            correct_fn=correct_paragraphs,
            backend=None,
            preprocess_fn=preprocess_fn,
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

    if args.min_confidence is not None and not 0.0 <= args.min_confidence <= 1.0:
        logger.error("min-confidence는 0~1 범위여야 함: %s", args.min_confidence)
        return 1

    # 데이터 로드
    try:
        adapter = aihub_label_adapter if args.label_format == "aihub" else _default_label_adapter
        pairs = load_pairs(args.image_dir, args.label_dir, adapter, allow_skip=args.allow_skip)
    except FileNotFoundError as e:
        logger.error("라벨 누락: %s", e)
        return 1

    # 제한 적용
    if args.limit:
        pairs = pairs[: args.limit]

    if not pairs:
        logger.error("처리할 페이지 없음")
        return 1

    logger.info("처리 페이지: %d개", len(pairs))

    # 동시 실행 충돌 방지: run_suffix로 전처리 경로 격리
    run_suffix = uuid.uuid4().hex[:8]

    # 인식 및 전처리 함수 조립
    recognize_fn = _make_recognize_fn(args.min_confidence)
    preprocess_fn = None
    if args.preprocess:
        work_dir = args.output.parent / "preprocessed" / f"{args.preprocess}-{run_suffix}"
        preprocess_fn = functools.partial(apply_lever, args.preprocess, work_dir=work_dir)

    # 3지점 채점
    records: list[PageRecord] = []
    for pair in pairs:
        logger.info("처리 중: %s", pair.page_id)
        start_time = time.time()
        records.extend(_score_page(pair, start_time, recognize_fn, preprocess_fn))

    # 전체 페이지가 오류 레코드뿐인지 확인
    error_records = [r for r in records if r.error_status]
    if error_records and len(error_records) == len(records):
        logger.error("모든 페이지 처리 실패")
        return 1

    # 리포트 저장
    run_meta = build_run_meta(
        image_dir=args.image_dir,
        page_count=len(pairs),
        preprocess=args.preprocess,
        min_confidence=args.min_confidence,
        pairs=pairs,
        run_suffix=run_suffix,
    )
    write_jsonl(records, args.output, run_meta=run_meta)

    # 요약 출력
    summary = summarize(records)
    logger.info("요약: %s", json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
