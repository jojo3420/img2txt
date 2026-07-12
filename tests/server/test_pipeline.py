"""서버 변환-보정 파이프라인 핵심 테스트."""
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from img2txt.corrector import CorrectionRecord, CorrectionStatus
from img2txt.ocr import OcrLine, Page
from server.models import FileStatus, Job, JobOptions, JobStatus, PageFile
from server.pipeline import (
    retry_page_pipeline,
    run_convert_pipeline,
    run_correct_pipeline,
)
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
        lambda *_args, **_kwargs: (["원문"], [record]),
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


def test_retry_page_marks_corrected_as_stale(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """재시도 성공 시 correct=True이고 book_corrected.txt가 존재하면 correctedStale==True."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "upload-a-page-0001.jpg").write_bytes(b"1")
    (uploads / "upload-b-page-0002.jpg").write_bytes(b"2")

    output = tmp_path / "output"
    output.mkdir()
    (output / "book.txt").write_text("첫 페이지", encoding="utf-8")
    (output / "book_corrected.txt").write_text("첫 페이지", encoding="utf-8")

    pages_dir = output / "pages"
    pages_dir.mkdir()
    (pages_dir / "page-0001.txt").write_text("첫 페이지", encoding="utf-8")
    (pages_dir / "page-0002.txt").write_text("두 번째 페이지", encoding="utf-8")

    layouts_dir = output / "layouts"
    layouts_dir.mkdir()
    (layouts_dir / "page-001.json").write_text(
        '{"number": 1, "paragraphs": ["첫 페이지"], "first_is_continuation": false, "is_empty": false, "removed_footer_lines": 0}',
        encoding="utf-8",
    )
    (layouts_dir / "page-002.json").write_text(
        '{"number": 2, "paragraphs": ["두 번째 페이지"], "first_is_continuation": false, "is_empty": false, "removed_footer_lines": 0}',
        encoding="utf-8",
    )

    def fake_recognize(_path: Path, number: int) -> Page:
        return _page(number, "수정된 두 번째")

    monkeypatch.setattr("server.pipeline.recognize_page", fake_recognize)
    job = _job(2)
    job.options.correct = True
    job.status = JobStatus.DONE
    job.files[0].status = FileStatus.DONE
    job.files[1].status = FileStatus.FAILED

    asyncio.run(
        retry_page_pipeline(
            job,
            tmp_path,
            2,
            MagicMock(),
        )
    )

    assert job.correctedStale is True


def test_correct_clears_stale_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """run_correct_pipeline 정상 성공 시 correctedStale==False."""
    output = tmp_path / "output"
    output.mkdir()
    book = output / "book.txt"
    book.write_text("원문 첫 문단\n\n원문 둘째 문단", encoding="utf-8")

    job = _job(1)
    job.options.correct = True
    job.status = JobStatus.DONE
    job.correctedStale = True  # 이전에 stale 표시됨

    def fake_backend(*_args) -> object:
        return object()

    records = [
        CorrectionRecord(
            1,
            CorrectionStatus.KEPT,
            "변경 없음",
            "gpt-5.5",
            "원문 첫 문단",
            "원문 첫 문단",
        ),
        CorrectionRecord(
            2,
            CorrectionStatus.CORRECTED,
            "오류 수정",
            "gpt-5.5",
            "원문 둘째 문단",
            "수정된 둘째 문단",
        ),
    ]

    monkeypatch.setattr("server.pipeline.select_backend", lambda *_: fake_backend())
    monkeypatch.setattr(
        "server.pipeline.correct_paragraphs",
        lambda *_args, **_kwargs: (
            ["원문 첫 문단", "수정된 둘째 문단"],
            records,
        ),
    )

    asyncio.run(
        run_correct_pipeline(job, tmp_path, JobStorage(tmp_path), MagicMock())
    )

    assert job.correctedStale is False


def test_correct_excludes_missing_page_markers_from_correction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """누락 마커가 보정 대상에서 제외되고 book_corrected에 원위치 보존."""
    output = tmp_path / "output"
    output.mkdir()
    book = output / "book.txt"
    # 마커 포함 내용: 문단 0=첫 문단, 문단 1=마커, 문단 2=셋째 문단
    book.write_text(
        "첫 문단\n\n[페이지 2 누락]\n\n셋째 문단",
        encoding="utf-8",
    )

    job = _job(1)
    job.options.correct = True
    job.status = JobStatus.DONE

    captured_paragraphs: list[list[str]] = []

    def fake_correct(
        paragraphs: list[str],
        *_args,
        **_kwargs,
    ) -> tuple[list[str], list[CorrectionRecord]]:
        """전달된 문단을 캡처하고, 마커 없이 보정 결과 반환."""
        captured_paragraphs.append(paragraphs)
        # 마커가 없어야 하므로 2개 문단만 받아야 함
        records = [
            CorrectionRecord(
                i + 1,
                CorrectionStatus.KEPT,
                "변경 없음",
                "gpt-5.5",
                p,
                p,
            )
            for i, p in enumerate(paragraphs)
        ]
        return paragraphs, records

    monkeypatch.setattr("server.pipeline.select_backend", lambda *_: object())
    monkeypatch.setattr("server.pipeline.correct_paragraphs", fake_correct)

    asyncio.run(
        run_correct_pipeline(job, tmp_path, JobStorage(tmp_path), MagicMock())
    )

    # 1. 보정 대상에 마커가 없어야 함
    assert len(captured_paragraphs[0]) == 2
    assert "[페이지" not in captured_paragraphs[0][0]
    assert "[페이지" not in captured_paragraphs[0][1]

    # 2. book_corrected.txt에 마커가 원위치에 보존되어야 함
    corrected_text = (output / "book_corrected.txt").read_text(encoding="utf-8")
    lines = corrected_text.split("\n\n")
    assert len(lines) == 3
    assert lines[0] == "첫 문단"
    assert lines[1] == "[페이지 2 누락]"
    assert lines[2] == "셋째 문단"
