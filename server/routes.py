"""HTTP API 라우트."""
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from server.config import JOBS_ROOT, UPLOAD_MAX_BYTES_PER_FILE, UPLOAD_MAX_FILES, UPLOAD_MAX_TOTAL_BYTES
from server.jobs import JobStore
from server.models import CreateJobResponse, Job, JobOptions, JobStatus, PageDetail
from server.naming import content_disposition, download_name
from server.storage import build_job_path, stream_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# backend → model 매핑
_MODEL_BY_BACKEND: dict[str, str] = {
    "codex": "gpt-5.5",
    "claude": "claude",
}

# 이메일 검증 정규식
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def get_store(request: Request) -> JobStore:
    """요청 컨텍스트에서 JobStore를 반환한다."""
    return request.app.state.job_store


def _read_chunk(upload: UploadFile, max_bytes: int) -> bytes:
    """업로드 파일에서 청크를 읽는다.

    Args:
        upload: 업로드 파일
        max_bytes: 읽을 최대 바이트 수

    Returns:
        읽은 바이트 데이터

    Raises:
        HTTPException: 상한 초과 시 413
    """
    chunk = upload.file.read(8192)
    if len(chunk) > max_bytes:
        raise HTTPException(413, "file size exceeds limit")
    return chunk


def _is_jpeg_magic(data: bytes) -> bool:
    """JPEG 매직넘버를 검증한다."""
    return len(data) >= 3 and data[:3] == b"\xff\xd8\xff"


@router.post("/jobs", status_code=201, response_model=CreateJobResponse)
def create_job_route(
    files: list[UploadFile] = File(...),
    correct: bool = Form(False),
    backend: str = Form("codex"),
    store: JobStore = Depends(get_store),
) -> CreateJobResponse:
    """파일을 업로드하고 새 잡을 생성한다.

    Args:
        files: 업로드할 이미지 파일 목록
        correct: 보정 활성 여부
        backend: 사용할 백엔드 ("codex" 또는 "claude")
        store: JobStore 인스턴스

    Returns:
        생성된 잡의 ID

    Raises:
        HTTPException: 파일 검증 실패 시 400, 크기 초과 시 413
    """
    if len(files) > UPLOAD_MAX_FILES:
        raise HTTPException(400, "too many files")

    # correct=false일 때 backend를 codex로 고정
    if not correct:
        backend = "codex"

    # backend 검증
    if backend not in _MODEL_BY_BACKEND:
        raise HTTPException(400, "invalid backend")

    collected: list[tuple[str, bytes]] = []
    total_bytes = 0

    for upload in files:
        filename = upload.filename or "unknown"

        # 파일명 및 content-type 검증
        if Path(filename).suffix.lower() not in (".jpg", ".jpeg"):
            raise HTTPException(400, "invalid file type")
        if upload.content_type != "image/jpeg":
            raise HTTPException(400, "invalid file type")

        # 첫 청크 읽기
        chunk = _read_chunk(upload, UPLOAD_MAX_BYTES_PER_FILE)

        # JPEG 매직넘버 검증
        if not _is_jpeg_magic(chunk):
            raise HTTPException(400, "invalid file type")

        # 파일 크기 검증
        if len(chunk) + total_bytes > UPLOAD_MAX_TOTAL_BYTES:
            raise HTTPException(413, "total upload size exceeds limit")

        total_bytes += len(chunk)
        collected.append((filename, chunk))

    # JobOptions 생성
    options = JobOptions(
        correct=correct,
        backend=backend,
        model=_MODEL_BY_BACKEND[backend],
    )

    job_id = store.create_job(collected, options)
    return CreateJobResponse(id=job_id)


@router.get("/jobs/{job_id}", response_model=Job)
def get_job_route(job_id: str, store: JobStore = Depends(get_store)) -> Job:
    """잡 상태를 반환한다.

    Args:
        job_id: 조회할 잡 ID
        store: JobStore 인스턴스

    Returns:
        잡 정보

    Raises:
        HTTPException: 잡이 없으면 404
    """
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.post("/jobs/{job_id}/retry/{file_id}")
def retry_route(
    job_id: str, file_id: str, store: JobStore = Depends(get_store)
) -> dict[str, str]:
    """실패한 페이지 한 장의 재시도를 요청한다.

    Args:
        job_id: 재시도할 잡 ID
        file_id: 재시도할 파일 ID
        store: JobStore 인스턴스

    Returns:
        상태 응답

    Raises:
        HTTPException: 잡이 없으면 404, 파일이 없으면 404, 재시도 불가능하면 409
    """
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not any(f.id == file_id for f in job.files):
        raise HTTPException(404, "file not found")
    if not store.retry_file(job_id, file_id):
        raise HTTPException(409, "file is not retryable")
    return {"status": "ok"}


@router.get("/jobs/{job_id}/pages/{n}", response_model=PageDetail)
def page_detail_route(
    job_id: str, n: int, store: JobStore = Depends(get_store)
) -> PageDetail:
    """페이지 원본 텍스트를 반환한다(보정본은 항상 null).

    Args:
        job_id: 조회할 잡 ID
        n: 페이지 번호
        store: JobStore 인스턴스

    Returns:
        페이지 상세 정보

    Raises:
        HTTPException: 잡이 없으면 404, 페이지가 없으면 404
    """
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    entry = next((f for f in job.files if f.pageNumber == n), None)
    if entry is None:
        raise HTTPException(404, "page not found")
    try:
        original = store.storage.read_output_file(job_id, f"output/pages/page-{n:03d}.txt")
    except FileNotFoundError:
        if job.status is JobStatus.PROCESSING:
            raise HTTPException(409, "page not ready")
        raise HTTPException(404, "page not available")
    return PageDetail(pageNumber=n, filename=entry.filename, original=original, corrected=None)


def _stream_output(
    job: Job, rel_path: str, kind: str, page: int | None = None
) -> StreamingResponse:
    """산출물 파일을 파일명 규칙과 함께 스트리밍한다.

    Args:
        job: Job 인스턴스
        rel_path: 잡 경로 기준 상대 경로 (예: "output/book.txt")
        kind: 파일 종류 ("page", "book", "corrected", "corrections")
        page: kind="page"일 때 페이지 번호

    Returns:
        스트리밍 응답
    """
    path = build_job_path(JOBS_ROOT, job.id) / rel_path
    filename = download_name(job, kind, page)
    headers = {"Content-Disposition": content_disposition(filename)}
    return StreamingResponse(
        stream_file(path), media_type="text/plain; charset=utf-8", headers=headers
    )


@router.get("/jobs/{job_id}/pages/{n}/download")
def page_download_route(
    job_id: str, n: int, store: JobStore = Depends(get_store)
) -> StreamingResponse:
    """페이지 텍스트를 다운로드한다.

    Args:
        job_id: 다운로드할 잡 ID
        n: 페이지 번호
        store: JobStore 인스턴스

    Returns:
        페이지 텍스트를 스트리밍 응답

    Raises:
        HTTPException: 잡이 없으면 404, 페이지가 없으면 404,
                      파일 없는데 처리 중이면 409, 아니면 404
    """
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not any(f.pageNumber == n for f in job.files):
        raise HTTPException(404, "page not found")
    path = build_job_path(JOBS_ROOT, job_id) / f"output/pages/page-{n:03d}.txt"
    if not path.is_file():
        if job.status is JobStatus.PROCESSING:
            raise HTTPException(409, "page not ready")
        raise HTTPException(404, "page not available")
    return _stream_output(job, f"output/pages/page-{n:03d}.txt", "page", n)


@router.get("/jobs/{job_id}/download")
def bundle_download_route(
    job_id: str, type: str = Query(...), store: JobStore = Depends(get_store)
) -> StreamingResponse:
    """연속본/보정본/대조로그를 다운로드한다.

    Args:
        job_id: 다운로드할 잡 ID
        type: 다운로드 종류 ("book", "corrected", "corrections")
        store: JobStore 인스턴스

    Returns:
        파일을 스트리밍 응답

    Raises:
        HTTPException: 잡이 없으면 404, type이 유효하지 않으면 400,
                      보정이 요청되지 않으면 404, 보정 실패하면 404,
                      파일 없는데 처리 중이면 409, 아니면 404
    """
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    output = build_job_path(JOBS_ROOT, job_id) / "output"

    if type == "book":
        if (output / "book.txt").is_file():
            return _stream_output(job, "output/book.txt", "book")
        if job.status is JobStatus.PROCESSING:
            raise HTTPException(409, "conversion in progress")
        raise HTTPException(404, "book not available")

    if type in ("corrected", "corrections"):
        if not job.options.correct:
            raise HTTPException(404, "correction was not requested")
        if job.correctionError:
            raise HTTPException(404, f"correction failed: {job.correctionError}")
        rel = "book_corrected.txt" if type == "corrected" else "corrections.log"
        if (output / rel).is_file():
            return _stream_output(job, f"output/{rel}", type)
        if job.phase == "correcting" or job.status is JobStatus.PROCESSING:
            raise HTTPException(409, "correction in progress")
        raise HTTPException(404, "correction output not available")

    raise HTTPException(400, "invalid type")


@router.post("/intent")
def intent_route(email: str = Body(..., embed=True)) -> dict[str, str]:
    """이메일 형식만 검증하는 스텁(미저장).

    Args:
        email: 검증할 이메일 주소

    Returns:
        상태 응답

    Raises:
        HTTPException: 이메일 형식이 유효하지 않으면 400
    """
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "invalid email")
    return {"status": "ok"}
