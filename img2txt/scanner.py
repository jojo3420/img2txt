"""책 스캔 이미지 수집과 페이지 순서 정렬."""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"})
_LAST_NUMBER_PATTERN: re.Pattern[str] = re.compile(r"(\d+)(?!.*\d)")


def extract_page_number(path: Path) -> int | None:
    """파일명(stem)의 마지막 숫자를 페이지 번호로 추출한다. 없으면 None."""
    match = _LAST_NUMBER_PATTERN.search(path.stem)
    return int(match.group(1)) if match else None


def collect_images(input_dir: Path) -> list[Path]:
    """지원 이미지(jpg/jpeg/png/webp/tif/tiff, 대소문자 무시)를 모아 파일명 마지막 숫자 기준 자연 정렬한다.

    숫자가 없는 파일은 warning 후 맨 뒤에 이름순으로 배치한다 (스펙 7절).
    """
    images = [
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    numbered = sorted(
        (path for path in images if extract_page_number(path) is not None),
        key=lambda path: extract_page_number(path) or 0,
    )
    unnumbered = sorted(path for path in images if extract_page_number(path) is None)
    for path in unnumbered:
        logger.warning("파일명에 숫자가 없어 맨 뒤에 배치: %s", path.name)
    return numbered + unnumbered
