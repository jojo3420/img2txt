"""웹 서버의 이미지 변환과 보정 파이프라인."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
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
from img2txt.scanner import collect_images, extract_page_number
from img2txt.writer import (
    format_corrections_log,
    write_page_texts,
    write_text_file,
)
from server.models import FileStatus, Job, JobStatus, JobSummary
from server.storage import JobStorage

logger = logging.getLogger(__name__)
UpdateCallback = Callable[[Job], None]
_RETRY_MARKER = ".retry-transaction.json"


def _layout_path(job_path: Path, page_number: int) -> Path:
    """페이지별 레이아웃 보조 파일 경로를 만든다."""
    return job_path / "output" / "layouts" / f"page-{page_number:03d}.json"


def _stored_layout_payload(layout: PageLayout) -> dict[str, object]:
    """레이아웃을 JSON 저장용 값으로 바꾼다."""
    return {
        "number": layout.number,
        "paragraphs": layout.paragraphs,
        "first_is_continuation": layout.first_is_continuation,
        "is_empty": layout.is_empty,
        "removed_footer_lines": len(layout.footer_lines),
    }


def save_stored_layout(path: Path, layout: PageLayout) -> None:
    """재조립에 필요한 레이아웃 정보만 JSON으로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_stored_layout_payload(layout), ensure_ascii=False),
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


def _fsync_directory(path: Path) -> None:
    """파일명 변경까지 디스크에 반영되도록 디렉터리를 동기화한다."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes_durable(path: Path, content: bytes) -> None:
    """같은 디렉터리의 임시 파일을 거쳐 바이트를 안전하게 쓴다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _recover_pending_replacement(output_dir: Path) -> None:
    """중단된 재시도 트랜잭션을 실제 백업 파일로 되돌린다."""
    marker = output_dir / _RETRY_MARKER
    if not marker.exists():
        return

    payload = json.loads(marker.read_text(encoding="utf-8"))
    entries = list(payload["entries"])
    backup_paths: list[Path] = []
    for entry in entries:
        target = output_dir / str(entry["target"])
        backup_name = entry["backup"]
        if backup_name is None:
            target.unlink(missing_ok=True)
            _fsync_directory(target.parent)
            continue
        backup = output_dir / str(backup_name)
        if not backup.exists():
            raise RuntimeError(f"재시도 백업 파일 누락: {backup}")
        _write_bytes_durable(target, backup.read_bytes())
        backup_paths.append(backup)

    marker.unlink()
    try:
        _fsync_directory(output_dir)
    except OSError as error:
        logger.warning(
            "복구 표시 파일 삭제 동기화 실패, 백업 유지: %s",
            error,
        )
        return
    for backup in backup_paths:
        try:
            backup.unlink(missing_ok=True)
        except OSError as error:
            logger.warning("복구 백업 정리 실패: %s", error)


def _replace_text_outputs(changes: dict[Path, str]) -> None:
    """파일 기반 복구 기록을 남기고 여러 텍스트를 교체한다."""
    output_dir = Path(
        os.path.commonpath([str(path.parent) for path in changes])
    )
    _recover_pending_replacement(output_dir)

    transaction_id = uuid.uuid4().hex
    entries: list[dict[str, str | None]] = []
    backup_paths: list[Path] = []
    for target in changes:
        backup: Path | None = None
        if target.exists():
            backup = target.parent / (
                f".{target.name}.retry-{transaction_id}.bak"
            )
            with backup.open("wb") as handle:
                handle.write(target.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(backup.parent)
            backup_paths.append(backup)
        entries.append(
            {
                "target": str(target.relative_to(output_dir)),
                "backup": (
                    str(backup.relative_to(output_dir))
                    if backup is not None
                    else None
                ),
            }
        )

    marker = output_dir / _RETRY_MARKER
    marker_content = json.dumps(
        {"entries": entries},
        ensure_ascii=False,
    ).encode("utf-8")
    _write_bytes_durable(marker, marker_content)

    temporary_paths: dict[Path, Path] = {}
    try:
        for target, text in changes.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=target.parent,
                delete=False,
            ) as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_paths[target] = Path(handle.name)
        for target, temporary in temporary_paths.items():
            os.replace(temporary, target)
            _fsync_directory(target.parent)
    except Exception:
        _recover_pending_replacement(output_dir)
        raise
    else:
        try:
            marker.unlink()
        except Exception:
            _recover_pending_replacement(output_dir)
            raise
        try:
            _fsync_directory(output_dir)
        except OSError as error:
            logger.warning(
                "재시도 커밋 동기화 실패, 복구 백업 유지: %s",
                error,
            )
            return
        for backup in backup_paths:
            try:
                backup.unlink(missing_ok=True)
            except OSError as error:
                logger.warning("커밋된 재시도 백업 정리 실패: %s", error)
    finally:
        for temporary in temporary_paths.values():
            temporary.unlink(missing_ok=True)


async def run_convert_pipeline(
    job: Job,
    job_path: Path,
    storage: JobStorage,
    on_update: UpdateCallback,
) -> None:
    """모든 이미지를 OCR하고 페이지·연속본 텍스트를 만든다."""
    del storage  # T9와 공유하는 공개 인터페이스를 유지한다.
    image_paths = collect_images(job_path / "uploads")
    image_numbers = [extract_page_number(path) for path in image_paths]
    expected_numbers = [file.pageNumber for file in job.files]
    if not image_paths or image_numbers != expected_numbers:
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
    if failed_count == len(pages):
        job.status = JobStatus.FAILED
    elif job.options.correct:
        job.status = JobStatus.PROCESSING
    else:
        job.status = JobStatus.DONE
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

        job.status = JobStatus.PROCESSING
        job.phase = "correcting"
        job.correction = {"done": 0, "total": len(paragraphs)}
        on_update(job)
        backend = select_backend(job.options.model, job.options.backend)
        corrected, records = correct_paragraphs(
            paragraphs,
            job.options.model,
            backend,
        )
        job.correction = {
            "done": len(records),
            "total": len(paragraphs),
        }
        write_text_file(
            output_dir / "corrections.log",
            format_corrections_log(records),
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
        corrected_count = sum(
            1 for record in records
            if record.status is CorrectionStatus.CORRECTED
        )
        kept_count = sum(
            1 for record in records
            if record.status is CorrectionStatus.KEPT
        )
        guard_blocked_count = sum(
            1 for record in records
            if record.status is CorrectionStatus.GUARD_BLOCKED
        )
        if job.summary is not None:
            job.summary.corrected = corrected_count
            job.summary.kept = kept_count
            job.summary.guardBlocked = guard_blocked_count
        job.correctionError = None
        job.status = JobStatus.DONE
        on_update(job)
    except Exception as error:
        logger.error("보정 파이프라인 실패: %s", error)
        job.correctionError = str(error)
        job.status = JobStatus.DONE
        on_update(job)


async def retry_page_pipeline(
    job: Job,
    job_path: Path,
    page_number: int,
    on_update: UpdateCallback,
) -> bool:
    """페이지 하나만 다시 OCR하고 기존 레이아웃과 안전하게 재조립한다."""
    _recover_pending_replacement(job_path / "output")
    file_entry = next(
        (item for item in job.files if item.pageNumber == page_number),
        None,
    )
    if file_entry is None:
        return False

    image_paths = [
        path
        for path in collect_images(job_path / "uploads")
        if extract_page_number(path) == page_number
    ]
    if len(image_paths) != 1:
        file_entry.status = FileStatus.FAILED
        file_entry.error = "재시도할 페이지 이미지를 찾을 수 없습니다"
        on_update(job)
        return False

    file_entry.status = FileStatus.OCR
    on_update(job)
    try:
        page = recognize_page(image_paths[0], page_number)
        replacement = analyze_page(page)
        layouts: list[PageLayout] = []
        footer_counts: list[int] = []

        for number in range(1, len(job.files) + 1):
            if number == page_number:
                layouts.append(replacement)
                footer_counts.append(len(replacement.footer_lines))
            else:
                layout, footer_count = load_stored_layout(
                    _layout_path(job_path, number)
                )
                layouts.append(layout)
                footer_counts.append(footer_count)

        page_text = "\n".join(line.text for line in page.lines)
        layout_text = json.dumps(
            _stored_layout_payload(replacement),
            ensure_ascii=False,
        )
        _replace_text_outputs(
            {
                job_path
                / "output"
                / "pages"
                / f"page-{page_number:03d}.txt": page_text,
                _layout_path(job_path, page_number): layout_text,
                job_path / "output" / "book.txt": assemble(layouts),
            }
        )

        file_entry.status = FileStatus.DONE
        file_entry.error = None
        file_entry.previewText = page_text[:80]
        if job.summary is not None:
            job.summary.successPages = sum(
                1 for item in job.files if item.status is FileStatus.DONE
            )
            job.summary.failedPages = sum(
                1 for item in job.files if item.status is FileStatus.FAILED
            )
            job.summary.removedFooterLines = sum(footer_counts)
        on_update(job)
        return True
    except Exception as error:
        logger.error("페이지 %d 재시도 실패: %s", page_number, error)
        file_entry.status = FileStatus.FAILED
        file_entry.error = str(error)
        on_update(job)
        return False
