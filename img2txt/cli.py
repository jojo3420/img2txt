"""명령 인자 해석과 전체 흐름 조립."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from img2txt.assembler import assemble
from img2txt.corrector import (
    OLLAMA_BASE_URL,
    all_requests_failed,
    check_server,
    correct_paragraphs,
)
from img2txt.layout import analyze_page
from img2txt.ocr import Page, recognize_page
from img2txt.scanner import collect_images, extract_page_number
from img2txt.writer import format_corrections_log, write_page_texts, write_text_file

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR: str = "./output"
BOOK_FILENAME: str = "book.txt"
PAGES_DIRNAME: str = "pages"
DEFAULT_MODEL: str = "gemma4:latest"
CORRECTED_FILENAME: str = "book_corrected.txt"
CORRECTIONS_LOG_FILENAME: str = "corrections.log"
EXIT_OK: int = 0
EXIT_ERROR: int = 1


def build_parser() -> argparse.ArgumentParser:
    """convert/correct 서브커맨드를 갖는 파서를 만든다."""
    parser = argparse.ArgumentParser(prog="img2txt", description="책 스캔 OCR 변환-보정 도구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    convert = subparsers.add_parser("convert", help="jpg 폴더 -> 페이지별 txt + 연속본")
    convert.add_argument("input_dir", help="jpg/jpeg가 있는 폴더")
    convert.add_argument("-o", "--output", default=DEFAULT_OUTPUT_DIR, help="출력 폴더")
    convert.add_argument("-v", "--verbose", action="store_true", help="DEBUG 로그")
    correct = subparsers.add_parser("correct", help="txt 파일 OCR 오류 보정 (Ollama)")
    correct.add_argument("input_file", help="보정할 txt 파일")
    correct.add_argument("-o", "--output", default=DEFAULT_OUTPUT_DIR, help="출력 폴더")
    correct.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama 모델명 (기본값: {DEFAULT_MODEL})")
    correct.add_argument("-v", "--verbose", action="store_true", help="DEBUG 로그")
    return parser


def run_convert(args: argparse.Namespace) -> int:
    """convert 흐름: 수집 -> OCR -> 레이아웃 -> 조립 -> 쓰기."""
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output)
    image_paths = collect_images(input_dir)
    if not image_paths:
        logger.error("입력 폴더에 jpg/jpeg가 없습니다: %s", input_dir)
        return EXIT_ERROR

    pages: list[Page] = []
    failed = 0
    for order, image_path in enumerate(image_paths, start=1):
        number = extract_page_number(image_path)
        if number is None:
            number = order  # 숫자 없는 파일: 순번으로 대체 (scanner가 맨 뒤 배치)
        logger.info("OCR %d/%d: %s", order, len(image_paths), image_path.name)
        try:
            page = recognize_page(image_path, number)
        except Exception as error:  # OCR 1장 실패는 전체를 멈추지 않는다 (스펙 7절)
            logger.warning("OCR 실패, 건너뜀: %s (%s)", image_path.name, error)
            failed += 1
            page = Page(number=number, lines=[])
        if not page.lines:
            logger.warning("빈 OCR 결과: %s", image_path.name)
        pages.append(page)

    if failed == len(image_paths):
        logger.error("모든 이미지의 OCR이 실패했습니다.")
        return EXIT_ERROR

    layouts = [analyze_page(page) for page in pages]
    write_page_texts(output_dir / PAGES_DIRNAME, pages)
    write_text_file(output_dir / BOOK_FILENAME, assemble(layouts))

    empty_count = sum(1 for page in pages if not page.lines) - failed
    footer_count = sum(len(layout.footer_lines) for layout in layouts)
    logger.info(
        "완료: 성공 %d / 실패 %d / 빈 결과 %d / 제거 꼬리말 %d줄 -> %s",
        len(pages) - failed - empty_count, failed, empty_count, footer_count,
        output_dir / BOOK_FILENAME,
    )
    return EXIT_OK


def run_correct(args: argparse.Namespace) -> int:
    """correct 흐름: 입력 검증 -> 서버 점검 -> 문단 분할 -> 보정 -> 결과 쓰기."""
    input_path = Path(args.input_file)
    if not input_path.is_file():
        logger.error("입력 파일이 없습니다: %s", input_path)
        return EXIT_ERROR

    output_dir = Path(args.output)
    error_message = check_server(OLLAMA_BASE_URL, args.model)
    if error_message:
        logger.error(error_message)
        return EXIT_ERROR

    text = input_path.read_text(encoding="utf-8")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    corrected, records = correct_paragraphs(paragraphs, model=args.model)

    if all_requests_failed(records):
        logger.error("전체 보정 요청이 실패했습니다.")
        return EXIT_ERROR

    write_text_file(output_dir / CORRECTED_FILENAME, "\n\n".join(corrected))
    write_text_file(output_dir / CORRECTIONS_LOG_FILENAME, format_corrections_log(records))

    logger.info(
        "완료: %d개 문단 보정 -> %s, %s",
        len(records), output_dir / CORRECTED_FILENAME, output_dir / CORRECTIONS_LOG_FILENAME,
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """엔트리포인트: 로깅 설정 후 서브커맨드를 실행한다."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    if args.command == "convert":
        return run_convert(args)
    if args.command == "correct":
        return run_correct(args)
    return EXIT_ERROR
