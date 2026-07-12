"""다운로드 파일명 헬퍼 테스트."""
from server.models import FileStatus, Job, JobOptions, JobStatus, PageFile
from server.naming import content_disposition, download_name


def _job(first_name: str) -> Job:
    """테스트용 Job 생성."""
    return Job(
        id="job-1",
        createdAt="2026-07-12T22:00:00Z",
        options=JobOptions(correct=False, backend="codex", model="gpt-5.5"),
        status=JobStatus.DONE,
        files=[PageFile(id="f1", filename=first_name, pageNumber=1,
                        sizeBytes=10, status=FileStatus.DONE)],
    )


def test_download_name_page_book_corrected():
    """kind별 다운로드 파일명 테스트."""
    job = _job("scan.jpg")

    # kind="page"
    assert download_name(job, "page", 1) == "2026-07-12-scan-1.txt"

    # kind="book"
    assert download_name(job, "book") == "2026-07-12-scan-book.txt"


def test_content_disposition():
    """Content-Disposition 헤더 생성 테스트."""
    # ASCII 이름
    result = content_disposition("2026-07-12-scan-book.txt")
    assert 'filename="2026-07-12-scan-book.txt"' in result

    # UTF-8 한글 포함
    result = content_disposition("2026-07-12-한글-book.txt")
    assert "filename*=UTF-8''" in result
    assert '%ED%95%9C%EA%B8%80' in result  # "한글" 인코딩됨
