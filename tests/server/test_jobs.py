"""잡 저장소와 안전 재시도 핵심 테스트."""
import os
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock

import pytest

import server.pipeline as pipeline_module
from img2txt.layout import PageLayout
from img2txt.ocr import OcrLine, Page
from img2txt.scanner import collect_images
from server.jobs import JobStore
from server.models import FileStatus, JobOptions, JobStatus
from server.pipeline import save_stored_layout


def test_create_job_naturally_sorts_files_and_uses_internal_names(
    tmp_path: Path,
    monkeypatch,
) -> None:
    correction_started = Event()
    release_correction = Event()

    def fake_recognize(_path: Path, number: int) -> Page:
        if number == 1:
            raise RuntimeError("ocr failed")
        return Page(
            number,
            [OcrLine("정상 페이지", 1.0, 0.1, 0.5, 0.8, 0.02)],
        )

    async def blocking_correction(job, _path, _storage, on_update) -> None:
        correction_started.set()
        release_correction.wait(timeout=5)
        job.status = JobStatus.DONE
        on_update(job)

    monkeypatch.setattr("server.pipeline.recognize_page", fake_recognize)
    monkeypatch.setattr("server.jobs.run_correct_pipeline", blocking_correction)
    store = JobStore(tmp_path, max_concurrent=1)
    job_id = store.create_job(
        [("page-10.jpg", b"10"), ("page-2.jpg", b"2")],
        JobOptions(correct=True),
    )
    assert correction_started.wait(timeout=2)
    try:
        job = store.get_job(job_id)
        assert job is not None
        assert [file.filename for file in job.files] == [
            "page-2.jpg",
            "page-10.jpg",
        ]
        assert [file.pageNumber for file in job.files] == [1, 2]
        saved = collect_images(tmp_path / job_id / "uploads")
        assert len(saved) == 2
        assert saved[0].name.endswith("page-0001.jpg")
        assert job.status is JobStatus.PROCESSING
        assert job.files[0].status is FileStatus.FAILED
        assert store.retry_file(job_id, job.files[0].id) is False
    finally:
        release_correction.set()
        store.shutdown()

    finished = store.get_job(job_id)
    assert finished is not None
    assert finished.status is JobStatus.DONE


def test_retry_replaces_only_failed_page_and_preserves_corrected_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = JobStore(tmp_path, max_concurrent=1)
    store.executor.submit = MagicMock()  # type: ignore[method-assign]
    job_id = store.create_job(
        [("page-1.jpg", b"1"), ("page-2.jpg", b"2")],
        JobOptions(correct=False),
    )
    job_path = tmp_path / job_id
    stored_images = collect_images(job_path / "uploads")
    stored_images[0].unlink()
    (job_path / "uploads" / "upload-decoy-page-0099.jpg").write_bytes(b"99")
    output = job_path / "output"
    (output / "pages").mkdir(parents=True)
    (output / "layouts").mkdir(parents=True)
    (output / "pages" / "page-001.txt").write_text(
        "기존 1",
        encoding="utf-8",
    )
    (output / "pages" / "page-002.txt").write_text("", encoding="utf-8")
    save_stored_layout(
        output / "layouts" / "page-001.json",
        PageLayout(1, ["기존 1"], False),
    )
    save_stored_layout(
        output / "layouts" / "page-002.json",
        PageLayout(2, [], False, is_empty=True),
    )
    (output / "book.txt").write_text(
        "기존 1\n\n[페이지 2 누락]",
        encoding="utf-8",
    )
    (output / "book_corrected.txt").write_text(
        "보정본 유지",
        encoding="utf-8",
    )
    (output / "corrections.log").write_text(
        "보정 기록 유지",
        encoding="utf-8",
    )

    with store._lock:
        live_job = store.jobs[job_id]
        live_job.status = JobStatus.DONE
        live_job.files[1].status = FileStatus.FAILED
        live_job.files[1].error = "old error"

    def recognize_target_page(path: Path, number: int) -> Page:
        assert path.name.endswith("page-0002.jpg")
        return Page(
            number,
            [OcrLine("복구 2", 1.0, 0.1, 0.5, 0.8, 0.02)],
        )

    monkeypatch.setattr(
        "server.pipeline.recognize_page",
        recognize_target_page,
    )
    marker = output / ".retry-transaction.json"
    real_fsync_directory = pipeline_module._fsync_directory
    marker_was_visible = False
    commit_fsync_failed = False

    def fail_fsync_after_marker_removal(path: Path) -> None:
        nonlocal marker_was_visible, commit_fsync_failed
        if marker.exists():
            marker_was_visible = True
        if (
            marker_was_visible
            and not marker.exists()
            and path == output
            and not commit_fsync_failed
        ):
            commit_fsync_failed = True
            raise OSError("directory fsync failed")
        real_fsync_directory(path)

    monkeypatch.setattr(
        "server.pipeline._fsync_directory",
        fail_fsync_after_marker_removal,
    )

    store._run_retry(job_id, job_path, 2)

    assert (
        output / "pages" / "page-001.txt"
    ).read_text(encoding="utf-8") == "기존 1"
    book = (output / "book.txt").read_text(encoding="utf-8")
    assert "기존 1" in book
    assert "복구 2" in book
    assert (
        output / "book_corrected.txt"
    ).read_text(encoding="utf-8") == "보정본 유지"
    assert (
        output / "corrections.log"
    ).read_text(encoding="utf-8") == "보정 기록 유지"
    updated = store.get_job(job_id)
    assert updated is not None
    assert updated.files[1].status is FileStatus.DONE
    assert commit_fsync_failed
    store.shutdown()


def test_retry_recovers_outputs_after_interrupted_replacement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = JobStore(tmp_path, max_concurrent=1)
    store.executor.submit = MagicMock()  # type: ignore[method-assign]
    job_id = store.create_job(
        [("page-1.jpg", b"1")],
        JobOptions(correct=False),
    )
    job_path = tmp_path / job_id
    output = job_path / "output"
    page_path = output / "pages" / "page-001.txt"
    layout_path = output / "layouts" / "page-001.json"
    book_path = output / "book.txt"
    page_path.parent.mkdir(parents=True)
    layout_path.parent.mkdir(parents=True)
    page_path.write_text("기존 페이지", encoding="utf-8")
    save_stored_layout(
        layout_path,
        PageLayout(1, ["기존 페이지"], False),
    )
    book_path.write_text("기존 페이지", encoding="utf-8")
    with store._lock:
        live_job = store.jobs[job_id]
        live_job.status = JobStatus.DONE
        live_job.files[0].status = FileStatus.FAILED
        live_job.files[0].error = "old error"

    monkeypatch.setattr(
        "server.pipeline.recognize_page",
        lambda _path, number: Page(
            number,
            [OcrLine("복구 페이지", 1.0, 0.1, 0.5, 0.8, 0.02)],
        ),
    )
    real_replace = os.replace

    class SimulatedCrash(BaseException):
        pass

    def crash_while_replacing_layout(source: Path, target: Path) -> None:
        if Path(target) == layout_path:
            raise SimulatedCrash("process stopped")
        real_replace(source, target)

    monkeypatch.setattr(
        "server.pipeline.os.replace",
        crash_while_replacing_layout,
    )
    before = {
        page_path: page_path.read_bytes(),
        layout_path: layout_path.read_bytes(),
        book_path: book_path.read_bytes(),
    }

    with pytest.raises(SimulatedCrash):
        store._run_retry(job_id, job_path, 1)

    marker = output / ".retry-transaction.json"
    assert marker.exists()
    monkeypatch.setattr("server.pipeline.os.replace", real_replace)
    monkeypatch.setattr(
        "server.pipeline.recognize_page",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("retry stopped")),
    )
    store._run_retry(job_id, job_path, 1)

    assert {path: path.read_bytes() for path in before} == before
    assert not marker.exists()
    updated = store.get_job(job_id)
    assert updated is not None
    assert updated.files[0].status is FileStatus.FAILED
    store.shutdown()
