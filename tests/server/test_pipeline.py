"""서버 변환·보정 파이프라인 핵심 테스트."""
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from img2txt.corrector import CorrectionRecord, CorrectionStatus
from img2txt.ocr import OcrLine, Page
from server.models import FileStatus, Job, JobOptions, JobStatus, PageFile
from server.pipeline import run_convert_pipeline, run_correct_pipeline
from server.storage import JobStorage


def _job(file_count: int) -> Job:
    return Job(
        id="job-1",
        createdAt="2026-07-11T00:00:00Z",
        options=JobOptions(correct=False),
        status=JobStatus.PROCESSING,
        files=[
            PageFile(
                id=f"file-{number}",
                filename=f"page-{number}.jpg",
                pageNumber=number,
                sizeBytes=1,
                status=FileStatus.WAITING,
            )
            for number in range(1, file_count + 1)
        ],
    )


def _page(number: int, text: str) -> Page:
    return Page(
        number,
        [OcrLine(text, 1.0, 0.1, 0.5, 0.8, 0.02)],
    )


def test_convert_keeps_other_pages_when_one_ocr_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "upload-a-page-0001.jpg").write_bytes(b"1")
    (uploads / "upload-b-page-0002.jpg").write_bytes(b"2")

    def fake_recognize(_path: Path, number: int) -> Page:
        if number == 2:
            raise RuntimeError("ocr failed")
        return _page(number, "첫 페이지")

    monkeypatch.setattr("server.pipeline.recognize_page", fake_recognize)
    job = _job(2)
    asyncio.run(
        run_convert_pipeline(job, tmp_path, JobStorage(tmp_path), MagicMock())
    )

    book = (tmp_path / "output" / "book.txt").read_text(encoding="utf-8")
    assert "첫 페이지" in book
    assert "[페이지 2 누락]" in book
    assert job.files[0].status is FileStatus.DONE
    assert job.files[1].status is FileStatus.FAILED
    assert job.status is JobStatus.DONE


def test_convert_marks_job_failed_when_all_ocr_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "upload-a-page-0001.jpg").write_bytes(b"1")
    monkeypatch.setattr(
        "server.pipeline.recognize_page",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("ocr failed")),
    )
    job = _job(1)

    asyncio.run(
        run_convert_pipeline(job, tmp_path, JobStorage(tmp_path), MagicMock())
    )

    assert job.status is JobStatus.FAILED
    assert job.summary is not None
    assert job.summary.failedPages == 1


def test_correction_failure_preserves_book_and_finishes_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    book = output / "book.txt"
    book.write_text("원문", encoding="utf-8")
    job = _job(1)
    job.status = JobStatus.DONE
    record = CorrectionRecord(
        1,
        CorrectionStatus.FAILED,
        "실패",
        "gpt-5.5",
        "원문",
        "원문",
    )
    monkeypatch.setattr("server.pipeline.select_backend", lambda *_args: object())
    monkeypatch.setattr(
        "server.pipeline.correct_paragraphs",
        lambda *_args: (["원문"], [record]),
    )
    updates: list[tuple[JobStatus, str, dict[str, int]]] = []

    def record_update(current: Job) -> None:
        updates.append(
            (
                current.status,
                current.phase,
                dict(current.correction or {}),
            )
        )

    asyncio.run(
        run_correct_pipeline(job, tmp_path, JobStorage(tmp_path), record_update)
    )

    assert book.read_text(encoding="utf-8") == "원문"
    assert not (output / "book_corrected.txt").exists()
    assert "상태=실패" in (output / "corrections.log").read_text(
        encoding="utf-8"
    )
    assert (
        JobStatus.PROCESSING,
        "correcting",
        {"done": 0, "total": 1},
    ) in updates
    assert job.correction == {"done": 1, "total": 1}
    assert job.status is JobStatus.DONE
    assert job.correctionError
