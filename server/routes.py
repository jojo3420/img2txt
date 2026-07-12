"""HTTP API 라우트."""
import re
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from server.config import JOBS_ROOT, UPLOAD_MAX_BYTES_PER_FILE, UPLOAD_MAX_FILES, UPLOAD_MAX_TOTAL_BYTES
from server.jobs import JobStore
from server.models import CreateJobResponse, Job, JobOptions, JobStatus, PageDetail
from server.naming import content_disposition, download_name
from server.storage import build_job_path, stream_file

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


def _read_limited(upload: UploadFile, max_per_file: int, already_total: int) -> bytes:
    """파일 전체를 청크로 읽으며 파일당/전체 상한을 실시간 검사한다.

    Args:
        upload: 업로드 파일
        max_per_file: 파일당 최대 바이트
        already_total: 이미 누적된 전체 바이트

    Returns:
        읽은 전체 바이트

    Raises:
        HTTPException: 파일당 상한 초과 시 413, 전체 상한 초과 시 413
    """
    _CHUNK_SIZE = 1024 * 1024  # 1MB씩 읽기
    data = bytearray()

    while True:
        chunk = upload.file.read(_CHUNK_SIZE)
        if not chunk:
            break

        data.extend(chunk)

        # 파일당 상한 검사
        if len(data) > max_per_file:
            raise HTTPException(413, "file size exceeds limit")

        # 전체 상한 검사
        if already_total + len(data) > UPLOAD_MAX_TOTAL_BYTES:
            raise HTTPException(413, "total upload size exceeds limit")

    return bytes(data)


def _is_valid_image_magic(data: bytes) -> bool:
    """이미지 파일 매직넘버를 검증한다.

    지원 포맷: JPEG, PNG, WEBP, TIFF

    Args:
        data: 파일 바이트

    Returns:
        유효한 이미지 포맷이면 True, 아니면 False
    """
    # JPEG: 0xFF 0xD8 0xFF
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return True
    # PNG: 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    # WEBP: RIFF ... WEBP
    if (len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP"):
        return True
    # TIFF: little-endian (II*\x00) or big-endian (MM\x00*)
    if len(data) >= 4 and data[0:4] in (b"II*\x00", b"MM\x00*"):
        return True
    return False


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
        if Path(filename).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"):
            raise HTTPException(400, "invalid file type")
        if upload.content_type not in ("image/jpeg", "image/png", "image/webp", "image/tiff"):
            raise HTTPException(400, "invalid file type")

        # 파일 전체 읽기 (파일당/전체 상한 실시간 검사)
        chunk = _read_limited(upload, UPLOAD_MAX_BYTES_PER_FILE, total_bytes)

        # 빈 파일 거절
        if len(chunk) == 0:
            raise HTTPException(400, "empty file")

        # JPEG 매직넘버 검증 (전체 바이트로 검증)
        if not _is_valid_image_magic(chunk):
            raise HTTPException(400, "invalid file type")

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
