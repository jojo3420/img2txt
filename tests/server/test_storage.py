"""파일 저장소 테스트."""
import tempfile
from pathlib import Path

from server.storage import sanitize_filename, build_job_path, JobStorage


def test_sanitize_filename_safe():
    """안전한 파일명은 그대로 통과."""
    result = sanitize_filename("page-1-abc123.jpg")
    assert "page-" in result and ".jpg" in result


def test_sanitize_filename_path_traversal():
    """경로 조작(../) 차단."""
    result = sanitize_filename("../../../etc/passwd")
    assert ".." not in result and "/" not in result


def test_sanitize_preserves_sort_number():
    """원본 파일명의 정렬용 숫자를 보존한다(자연 정렬 유지)."""
    assert sanitize_filename("page-2.jpg") == "page-2.jpg"
    assert sanitize_filename("page-10.jpg") == "page-10.jpg"


def test_build_job_path():
    """잡 경로 생성."""
    path = build_job_path(Path("/tmp/jobs"), "job-123")
    assert "job-123" in str(path)


def test_job_storage_create_dir():
    """JobStorage가 잡 디렉터리와 uploads/를 만든다."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = JobStorage(Path(tmpdir))
        job_path = storage.create_job_dir("test-job")
        assert job_path.exists()
        assert (job_path / "uploads").exists()
