"""출력 파일 쓰기. 모든 입출력은 UTF-8 고정."""
from __future__ import annotations

from pathlib import Path

from img2txt.corrector import CorrectionRecord, CorrectionStatus
from img2txt.ocr import Page

ENCODING: str = "utf-8"
PAGE_FILENAME_FORMAT: str = "page-{number:03d}.txt"
LOG_ENTRY_FORMAT: str = "[문단 {index}] 상태={status} 모델={model} 사유={reason}\n--- 전 ---\n{before}\n--- 후 ---\n{after}\n"


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


def format_corrections_log(records: list[CorrectionRecord]) -> str:
    """보정 반영/가드 차단/실패 문단만 전/후 대조 형식으로 만든다 (스펙 규칙 12)."""
    entries = [
        LOG_ENTRY_FORMAT.format(index=r.index, status=r.status.value, model=r.model,
                                reason=r.reason, before=r.before, after=r.after)
        for r in records
        if r.status is not CorrectionStatus.KEPT
    ]
    return "\n".join(entries)
