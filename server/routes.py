"""HTTP API 라우트."""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from server.config import UPLOAD_MAX_BYTES_PER_FILE, UPLOAD_MAX_FILES, UPLOAD_MAX_TOTAL_BYTES
from server.jobs import JobStore
from server.models import CreateJobResponse, JobOptions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# backend → model 매핑
_MODEL_BY_BACKEND: dict[str, str] = {
    "codex": "gpt-5.5",
    "claude": "claude",
}


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
    correct: str = Query("false"),
    backend: str = Query("codex"),
    store: JobStore = Depends(get_store),
) -> CreateJobResponse:
    """파일을 업로드하고 새 잡을 생성한다.

    Args:
        files: 업로드할 이미지 파일 목록
        correct: 보정 활성 여부 ("true" 또는 "false")
        backend: 사용할 백엔드 ("codex" 또는 "claude")
        store: JobStore 인스턴스

    Returns:
        생성된 잡의 ID

    Raises:
        HTTPException: 파일 검증 실패 시 400, 크기 초과 시 413
    """
    if len(files) > UPLOAD_MAX_FILES:
        raise HTTPException(400, "too many files")

    correct_bool = correct.lower() == "true"

    # correct=false일 때 backend를 codex로 고정
    if not correct_bool:
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
        correct=correct_bool,
        backend=backend,
        model=_MODEL_BY_BACKEND[backend],
    )

    job_id = store.create_job(collected, options)
    return CreateJobResponse(id=job_id)
