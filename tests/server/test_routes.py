"""HTTP 라우트 테스트."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    """테스트용 클라이언트를 생성하고 JobStore를 설정한다."""
    from server.jobs import JobStore

    monkeypatch.setattr("server.config.JOBS_ROOT", tmp_path / "jobs")
    app = create_app()
    # 명시적으로 JobStore 설정
    app.state.job_store = JobStore(tmp_path / "jobs", 2)
    return TestClient(app)


def test_create_job_accepts_valid_jpeg(client: TestClient) -> None:
    """유효한 JPEG 파일을 업로드하면 201 응답을 반환한다."""
    jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100 + b"\xff\xd9"

    resp = client.post(
        "/api/jobs",
        data={"correct": "false", "backend": "codex"},
        files={"files": ("test.jpg", jpeg_data, "image/jpeg")},
    )

    assert resp.status_code == 201
    result = resp.json()
    assert "id" in result
    assert result["id"].startswith("job-")


def test_create_job_rejects_non_jpeg(client: TestClient) -> None:
    """비-JPEG 파일을 업로드하면 400 응답을 반환한다."""
    png_data = b"\x89PNG\r\n\x1a\n"

    resp = client.post(
        "/api/jobs",
        data={"correct": "false", "backend": "codex"},
        files={"files": ("test.png", png_data, "image/png")},
    )

    assert resp.status_code == 400


def test_create_job_passes_form_options_to_store(
    tmp_path: Path, monkeypatch
) -> None:
    """폼 필드 값(correct, backend)이 JobStore.create_job에 전달된다."""
    from unittest.mock import MagicMock
    from server.app import create_app
    from server.jobs import JobStore

    # JobStore 모킹
    mock_store = MagicMock(spec=JobStore)
    mock_store.create_job.return_value = "job-123"

    app = create_app()
    app.state.job_store = mock_store

    client = TestClient(app)
    jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100 + b"\xff\xd9"

    # correct=true, backend=claude로 요청
    resp = client.post(
        "/api/jobs",
        data={"correct": "true", "backend": "claude"},
        files={"files": ("test.jpg", jpeg_data, "image/jpeg")},
    )

    assert resp.status_code == 201

    # create_job이 호출되었는지 확인
    assert mock_store.create_job.called
    _, options = mock_store.create_job.call_args[0]

    # 폼 값이 정확히 전달되었는지 검증
    assert options.correct is True, "correct=true가 전달되지 않음"
    assert options.backend == "claude", "backend=claude가 전달되지 않음"
    assert options.model == "claude", "model이 claude로 파생되지 않음"


def test_get_job_returns_existing_job(client: TestClient) -> None:
    """존재하는 잡을 조회하면 200과 Job 정보를 반환한다."""
    from unittest.mock import MagicMock
    from server.models import Job, JobOptions, JobStatus

    # 테스트용 Job 객체
    job = Job(
        id="job-1",
        createdAt="2026-07-12T00:00:00Z",
        options=JobOptions(correct=False, backend="codex", model="gpt-5.5"),
        status=JobStatus.DONE,
        files=[],
    )

    # JobStore.get_job을 모킹
    client.app.state.job_store.get_job = MagicMock(return_value=job)

    resp = client.get("/api/jobs/job-1")

    assert resp.status_code == 200
    result = resp.json()
    assert result["id"] == "job-1"
    assert result["status"] == "done"


def test_get_job_returns_404_for_nonexistent_job(client: TestClient) -> None:
    """존재하지 않는 잡을 조회하면 404를 반환한다."""
    from unittest.mock import MagicMock

    # JobStore.get_job을 모킹하여 None 반환
    client.app.state.job_store.get_job = MagicMock(return_value=None)

    resp = client.get("/api/jobs/nonexistent")

    assert resp.status_code == 404


def _one_file_job(file_status):
    """테스트용 단일 파일 잡을 생성한다."""
    from server.models import Job, JobOptions, JobStatus, PageFile

    return Job(
        id="job-1",
        createdAt="2026-07-12T00:00:00Z",
        options=JobOptions(correct=False, backend="codex", model="gpt-5.5"),
        status=JobStatus.DONE,
        files=[
            PageFile(
                id="f1", filename="a.jpg", pageNumber=1, sizeBytes=1, status=file_status
            )
        ],
    )


def test_retry_404_missing_job(client: TestClient) -> None:
    """존재하지 않는 잡에 대한 재시도 요청하면 404를 반환한다."""
    from unittest.mock import MagicMock
    from server.models import FileStatus

    client.app.state.job_store.get_job = MagicMock(return_value=None)

    resp = client.post("/api/jobs/nonexistent/retry/f1")

    assert resp.status_code == 404


def test_retry_404_missing_file(client: TestClient) -> None:
    """존재하지 않는 파일에 대한 재시도 요청하면 404를 반환한다."""
    from unittest.mock import MagicMock
    from server.models import FileStatus

    client.app.state.job_store.get_job = MagicMock(
        return_value=_one_file_job(FileStatus.FAILED)
    )

    resp = client.post("/api/jobs/job-1/retry/does-not-exist")

    assert resp.status_code == 404


def test_retry_409_not_retryable(client: TestClient) -> None:
    """재시도 불가능한 파일에 대한 요청하면 409를 반환한다."""
    from unittest.mock import MagicMock
    from server.models import FileStatus

    client.app.state.job_store.get_job = MagicMock(
        return_value=_one_file_job(FileStatus.DONE)
    )
    client.app.state.job_store.retry_file = MagicMock(return_value=False)

    resp = client.post("/api/jobs/job-1/retry/f1")

    assert resp.status_code == 409


def test_retry_200_success(client: TestClient) -> None:
    """재시도 요청이 성공하면 200을 반환한다."""
    from unittest.mock import MagicMock
    from server.models import FileStatus

    client.app.state.job_store.get_job = MagicMock(
        return_value=_one_file_job(FileStatus.FAILED)
    )
    client.app.state.job_store.retry_file = MagicMock(return_value=True)

    resp = client.post("/api/jobs/job-1/retry/f1")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_page_detail_404_missing_job(client: TestClient) -> None:
    """존재하지 않는 잡에 대한 페이지 조회 요청하면 404를 반환한다."""
    from unittest.mock import MagicMock

    client.app.state.job_store.get_job = MagicMock(return_value=None)

    resp = client.get("/api/jobs/nonexistent/pages/1")

    assert resp.status_code == 404


def test_page_detail_404_missing_page(client: TestClient) -> None:
    """존재하지 않는 페이지를 조회하면 404를 반환한다."""
    from unittest.mock import MagicMock
    from server.models import FileStatus

    client.app.state.job_store.get_job = MagicMock(
        return_value=_one_file_job(FileStatus.DONE)
    )

    resp = client.get("/api/jobs/job-1/pages/99")

    assert resp.status_code == 404


def test_page_detail_returns_page_with_original_and_null_corrected(
    tmp_path: Path, client: TestClient
) -> None:
    """페이지 상세 조회는 원본 텍스트를 반환하고 corrected는 null이다."""
    from unittest.mock import MagicMock
    from server.models import FileStatus

    # 테스트 파일 생성
    job_dir = tmp_path / "jobs" / "job-1" / "output" / "pages"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "page-001.txt").write_text("OCR 결과 텍스트", encoding="utf-8")

    client.app.state.job_store.get_job = MagicMock(
        return_value=_one_file_job(FileStatus.DONE)
    )

    resp = client.get("/api/jobs/job-1/pages/1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["pageNumber"] == 1
    assert data["original"] == "OCR 결과 텍스트"
    assert data["corrected"] is None


def test_intent_accepts_valid_email(client: TestClient) -> None:
    """유효한 이메일 형식으로 의향을 표현하면 200을 반환한다."""
    resp = client.post("/api/intent", json={"email": "user@example.com"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_intent_rejects_invalid_email(client: TestClient) -> None:
    """유효하지 않은 이메일 형식으로 의향을 표현하면 400을 반환한다."""
    resp = client.post("/api/intent", json={"email": "invalid-email"})

    assert resp.status_code == 400


def test_intent_rejects_email_without_domain(client: TestClient) -> None:
    """도메인이 없는 이메일 형식으로 의향을 표현하면 400을 반환한다."""
    resp = client.post("/api/intent", json={"email": "user@domain"})

    assert resp.status_code == 400
