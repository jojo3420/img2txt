"""웹 서버의 이미지 변환과 보정 파이프라인."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from img2txt.assembler import assemble
from img2txt.backends.factory import select_backend
from img2txt.corrector import (
    CorrectionStatus,
    all_requests_failed,
    correct_paragraphs,
)
from img2txt.layout import PageLayout, analyze_page
from img2txt.ocr import Page, recognize_page
from img2txt.scanner import collect_images
from img2txt.writer import (
    format_corrections_log,
    write_page_texts,
    write_text_file,
)
from server.models import FileStatus, Job, JobStatus, JobSummary
from server.storage import JobStorage

logger = logging.getLogger(__name__)
UpdateCallback = Callable[[Job], None]


def _layout_path(job_path: Path, page_number: int) -> Path:
    """페이지별 레이아웃 보조 파일 경로를 만든다."""
    return job_path / "output" / "layouts" / f"page-{page_number:03d}.json"


def save_stored_layout(path: Path, layout: PageLayout) -> None:
    """재조립에 필요한 레이아웃 정보만 JSON으로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "number": layout.number,
        "paragraphs": layout.paragraphs,
        "first_is_continuation": layout.first_is_continuation,
        "is_empty": layout.is_empty,
        "removed_footer_lines": len(layout.footer_lines),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def load_stored_layout(path: Path) -> tuple[PageLayout, int]:
    """저장한 레이아웃과 제거된 꼬리말 수를 읽는다."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    layout = PageLayout(
        number=int(payload["number"]),
        paragraphs=list(payload["paragraphs"]),
        first_is_continuation=bool(payload["first_is_continuation"]),
        is_empty=bool(payload["is_empty"]),
    )
    return layout, int(payload["removed_footer_lines"])


async def run_convert_pipeline(
    job: Job,
    job_path: Path,
    storage: JobStorage,
    on_update: UpdateCallback,
) -> None:
    """모든 이미지를 OCR하고 페이지·연속본 텍스트를 만든다."""
    del storage  # T9와 공유하는 공개 인터페이스를 유지한다.
    image_paths = collect_images(job_path / "uploads")
    if not image_paths or len(image_paths) != len(job.files):
        job.status = JobStatus.FAILED
        on_update(job)
        return

    pages: list[Page] = []
    layouts: list[PageLayout] = []
    failed_count = 0

    for image_path, file_entry in zip(image_paths, job.files):
        file_entry.status = FileStatus.OCR
        on_update(job)
        try:
            page = recognize_page(image_path, file_entry.pageNumber)
            layout = analyze_page(page)
            file_entry.status = FileStatus.DONE
            file_entry.error = None
            file_entry.previewText = "\n".join(line.text for line in page.lines)[:80]
        except Exception as error:
            logger.warning("OCR 실패: %s (%s)", image_path.name, error)
            page = Page(number=file_entry.pageNumber)
            layout = analyze_page(page)
            file_entry.status = FileStatus.FAILED
            file_entry.error = str(error)
            failed_count += 1

        pages.append(page)
        layouts.append(layout)
        on_update(job)

    output_dir = job_path / "output"
    write_page_texts(output_dir / "pages", pages)
    for layout in layouts:
        save_stored_layout(_layout_path(job_path, layout.number), layout)
    write_text_file(output_dir / "book.txt", assemble(layouts))

    job.summary = JobSummary(
        successPages=len(pages) - failed_count,
        failedPages=failed_count,
        removedFooterLines=sum(len(layout.footer_lines) for layout in layouts),
    )
    job.status = (
        JobStatus.FAILED if failed_count == len(pages) else JobStatus.DONE
    )
    on_update(job)


async def run_correct_pipeline(
    job: Job,
    job_path: Path,
    storage: JobStorage,
    on_update: UpdateCallback,
) -> None:
    """연속본을 보정하되 실패하면 기존 변환 결과를 보존한다."""
    del storage  # T9와 공유하는 공개 인터페이스를 유지한다.
    output_dir = job_path / "output"
    book_path = output_dir / "book.txt"

    try:
        paragraphs = [
            part
            for part in book_path.read_text(encoding="utf-8").split("\n\n")
            if part.strip()
        ]
        if not paragraphs:
            raise ValueError("처리할 문단이 없습니다")

        job.phase = "correcting"
        on_update(job)
        backend = select_backend(job.options.model, job.options.backend)
        corrected, records = correct_paragraphs(
            paragraphs,
            job.options.model,
            backend,
        )

        if all_requests_failed(records):
            job.correctionError = "보정 서비스 요청이 모두 실패했습니다"
            job.status = JobStatus.DONE
            on_update(job)
            return

        write_text_file(
            output_dir / "book_corrected.txt",
            "\n\n".join(corrected),
        )
        write_text_file(
            output_dir / "corrections.log",
            format_corrections_log(records),
        )
        job.correction = {
            "corrected": sum(
                1 for record in records
                if record.status is CorrectionStatus.CORRECTED
            ),
            "kept": sum(
                1 for record in records
                if record.status is CorrectionStatus.KEPT
            ),
            "guardBlocked": sum(
                1 for record in records
                if record.status is CorrectionStatus.GUARD_BLOCKED
            ),
        }
        if job.summary is not None:
            job.summary.corrected = job.correction["corrected"]
            job.summary.kept = job.correction["kept"]
            job.summary.guardBlocked = job.correction["guardBlocked"]
        job.correctionError = None
        job.status = JobStatus.DONE
        on_update(job)
    except Exception as error:
        logger.error("보정 파이프라인 실패: %s", error)
        job.correctionError = str(error)
        job.status = JobStatus.DONE
        on_update(job)
