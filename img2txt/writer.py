"""출력 파일 쓰기. 모든 입출력은 UTF-8 고정."""
from __future__ import annotations

from pathlib import Path

from img2txt.ocr import Page

ENCODING: str = "utf-8"
PAGE_FILENAME_FORMAT: str = "page-{number:03d}.txt"


def write_page_texts(pages_dir: Path, pages: list[Page]) -> None:
    """검수용 페이지별 원본 txt를 쓴다 (OCR 줄 단위 그대로, 빈 페이지는 빈 파일)."""
    pages_dir.mkdir(parents=True, exist_ok=True)
    for page in pages:
        path = pages_dir / PAGE_FILENAME_FORMAT.format(number=page.number)
        path.write_text("\n".join(line.text for line in page.lines), encoding=ENCODING)


def write_text_file(path: Path, text: str) -> None:
    """텍스트 파일 하나를 쓴다 (기존 파일 덮어쓰기)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=ENCODING)
