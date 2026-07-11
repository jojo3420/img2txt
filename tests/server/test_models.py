from server.models import JobStatus, FileStatus, Job, PageFile, JobOptions


def test_job_model_validation():
    """Job 모델 유효성."""
    job = Job(
        id="job-1",
        createdAt="2026-07-08T12:00:00Z",
        options=JobOptions(correct=True, backend="claude"),
        status=JobStatus.QUEUED,
        files=[],
    )
    assert job.id == "job-1"
    assert job.status == JobStatus.QUEUED


def test_file_status_enum():
    """FileStatus enum."""
    assert FileStatus.WAITING.value == "waiting"
    assert FileStatus.DONE.value == "done"


def test_job_defaults():
    """Job/JobOptions 기본값 (backend=codex, phase=ocr)."""
    job = Job(
        id="job-2",
        createdAt="2026-07-08T12:00:00Z",
        options=JobOptions(correct=False),
        status=JobStatus.QUEUED,
        files=[],
    )
    assert job.options.backend == "codex"
    assert job.phase == "ocr"
    assert job.summary is None
