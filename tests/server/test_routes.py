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
