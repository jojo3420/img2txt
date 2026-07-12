# img2txt 웹서비스 HTTP 계층 + 프런트 연결 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미 구현된 백엔드 코어에 FastAPI HTTP 계층과 프런트 연결을 얹어, 브라우저에서 이미지 업로드부터 다운로드까지 end-to-end로 동작하는 단일 프로세스 개인 웹서비스를 완성한다.

**Architecture:** `server/routes.py`가 기존 `JobStore`/`JobStorage`/스키마에 얇게 위임하고, `server/app.py`가 `/api`와 빌드된 프런트(`dist/`)를 한 포트에서 서빙한다. 다운로드 파일명 규칙은 `server/naming.py` 헬퍼로 모은다. 잡 상태는 메모리, 산출물은 파일(기존 코어 유지).

**Tech Stack:** Python 3, FastAPI, uvicorn, python-multipart, pytest(TestClient) / 프런트: 기존 Vite + React + React Query 프로토타입.

**선행 스펙:** `docs/superpowers/specs/2026-07-12-web-service-http-frontend-design.md` (Codex 2회 리뷰 반영 최종본). 상위 설계: `docs/superpowers/specs/2026-07-08-img2txt-web-service-design.md`.

## Global Constraints

- Type Hints 100%, Docstring 한국어, `print` 금지(`logging` 사용), 하드코딩 상수는 `server/config.py` 재사용.
- 응답 스키마는 `server/models.py`를 재사용한다(새 스키마 만들지 않음): `Job`, `JobOptions`, `PageFile`, `PageDetail`, `CreateJobResponse`, enum `JobStatus`(queued/processing/done/failed), `FileStatus`(waiting/ocr/correcting/done/failed).
- 업로드 상한: `UPLOAD_MAX_BYTES_PER_FILE`(20MB), `UPLOAD_MAX_FILES`(100), `UPLOAD_MAX_TOTAL_BYTES`(500MB), 동시 잡 `MAX_CONCURRENT_JOBS`(2), 잡 루트 `JOBS_ROOT`(`./jobs`).
- 산출물 경로(잡 디렉터리 기준): 페이지 `output/pages/page-{n:03d}.txt`, 연속본 `output/book.txt`, 보정본 `output/book_corrected.txt`, 대조로그 `output/corrections.log`.
- 오류 계약: 프레임워크 자동검증은 422(`detail` 배열, 그대로 둠). 도메인 검증은 `HTTPException`으로 400/413/404/409 + `{"detail":"<문자열>"}`. 500은 전역 핸들러로 `{"detail":"internal server error"}`만(내부 노출 금지).
- 다운로드 파일명: `{createdAt[:10]}-{원본명stem}-{순번|book|book_corrected|corrections}.{txt|log}`. 연속본/보정본/로그는 첫 페이지 원본명 기준. `Content-Disposition`은 ASCII `filename=` + `filename*=UTF-8''`(RFC 5987) 병기.
- 실행: `uvicorn server.app:app`(단일 프로세스). 프런트는 `npm run build`로 1회 빌드. 개발 반복은 `npm run dev` + vite `/api` proxy.
- OCR은 macOS(Apple Vision) 전용. 실제 OCR/보정 통합은 수동 스모크(자동 테스트는 파이프라인 모킹).

## File Structure

- Create: `server/naming.py`(다운로드 파일명 + Content-Disposition 헬퍼)
- Create: `server/routes.py`(APIRouter, 엔드포인트)
- Create: `server/app.py`(FastAPI 앱, lifespan, 정적 서빙)
- Create: `requirements.txt`(웹 계층 의존성)
- Create: `tests/server/test_naming.py`, `tests/server/test_routes.py`, `tests/server/test_static.py`
- Modify: `.gitignore`(+`jobs/`, +프런트 `dist/`)
- Modify(프런트): `docs/prototype/img2txt-web/vite.config.ts`, `src/main.tsx`, `src/api/types.ts`, `src/api/client.ts`(다운로드 핸들러), `src/pages/UploadPage.tsx`, `src/pages/JobPage.tsx`, `src/pages/ResultPage.tsx` (실제 파일명은 구현 시 확인)

---

## Task 1: 다운로드 파일명 헬퍼 (`server/naming.py`)

**Files:**
- Create: `server/naming.py`
- Test: `tests/server/test_naming.py`

**Interfaces:**
- Consumes: `server.models.Job`(`createdAt: str`, `files: list[PageFile]`, `PageFile.filename`, `PageFile.pageNumber`)
- Produces: `download_name(job: Job, kind: str, page: int | None = None) -> str`, `content_disposition(name: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/server/test_naming.py
from urllib.parse import quote
from server.models import Job, JobOptions, JobStatus, PageFile, FileStatus
from server.naming import download_name, content_disposition


def _job(first_name: str) -> Job:
    return Job(
        id="job-1",
        createdAt="2026-07-12T22:00:00Z",
        options=JobOptions(correct=False, backend="codex", model="gpt-5.5"),
        status=JobStatus.DONE,
        files=[PageFile(id="f1", filename=first_name, pageNumber=1,
                        sizeBytes=10, status=FileStatus.DONE)],
    )


def test_download_name_page_book_corrected():
    job = _job("scan.jpg")
    assert download_name(job, "page", page=1) == "2026-07-12-scan-1.txt"
    assert download_name(job, "book") == "2026-07-12-scan-book.txt"
    assert download_name(job, "corrected") == "2026-07-12-scan-book_corrected.txt"
    assert download_name(job, "corrections") == "2026-07-12-scan-corrections.log"


def test_download_name_sanitizes_and_encodes_korean():
    job = _job('책 "1".jpg')
    name = download_name(job, "book")
    # 따옴표 제거, 한글 유지
    assert '"' not in name
    header = content_disposition(name)
    assert "filename=" in header and "filename*=UTF-8''" in header
    assert quote(name) in header
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/server/test_naming.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.naming'`.

- [ ] **Step 3: Write minimal implementation**

```python
# server/naming.py
"""다운로드 파일명 규칙과 Content-Disposition 생성."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from server.models import Job

_MAX_STEM: int = 100
_KIND_SUFFIX: dict[str, str] = {
    "book": "book.txt",
    "corrected": "book_corrected.txt",
    "corrections": "corrections.log",
}


def _safe_stem(filename: str) -> str:
    """원본 파일명에서 확장자를 떼고 헤더에 안전한 stem을 만든다."""
    stem = Path(Path(filename).name).stem
    stem = "".join(
        ch for ch in stem if ch >= " " and ch not in '"\\/\n\r'
    ).strip()[:_MAX_STEM]
    return stem or "download"


def download_name(job: Job, kind: str, page: int | None = None) -> str:
    """다운로드 파일명을 규칙에 맞춰 생성한다.

    Args:
        job: 대상 잡.
        kind: page/book/corrected/corrections 중 하나.
        page: kind=page일 때 페이지 번호(pageNumber).

    Returns:
        규칙에 맞는 파일명.
    """
    date = job.createdAt[:10]
    first_stem = _safe_stem(job.files[0].filename)
    if kind == "page":
        entry = next(f for f in job.files if f.pageNumber == page)
        return f"{date}-{_safe_stem(entry.filename)}-{page}.txt"
    if kind in _KIND_SUFFIX:
        return f"{date}-{first_stem}-{_KIND_SUFFIX[kind]}"
    raise ValueError(f"unknown kind: {kind}")


def content_disposition(name: str) -> str:
    """ASCII 폴백과 RFC 5987 인코딩을 병기한 Content-Disposition 값."""
    ascii_name = name.encode("ascii", "replace").decode("ascii").replace('"', "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/server/test_naming.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add server/naming.py tests/server/test_naming.py
git commit -m "feat: add download filename helper (server.naming)"
```

---

## Task 2: 의존성 + FastAPI 앱 골격 (`server/app.py`)

**Files:**
- Create: `requirements.txt`, `server/app.py`
- Modify: `.gitignore`
- Test: `tests/server/test_static.py`(부트 검증)

**Interfaces:**
- Consumes: `server.config.JOBS_ROOT`, `MAX_CONCURRENT_JOBS`; `server.jobs.JobStore`; `server.routes.router`(Task 3에서 채움 — 이 태스크에선 빈 `APIRouter(prefix="/api")`를 임시로 둔다)
- Produces: `create_app() -> FastAPI`, 모듈 전역 `app`; 시작 시 `app.state.job_store: JobStore`

- [ ] **Step 1: 의존성 파일과 .gitignore 준비**

`requirements.txt` 생성(웹 계층 추가분. 코어 의존성은 기존 venv에 설치돼 있다고 가정):

```
fastapi
uvicorn[standard]
python-multipart
```

`.gitignore` 끝에 추가:

```
# 웹서비스 산출물 / 빌드
jobs/
docs/prototype/img2txt-web/dist/
```

설치: `pip install -r requirements.txt`

- [ ] **Step 2: 임시 빈 라우터 + 앱 골격 작성**

임시로 `server/routes.py`에 빈 라우터를 만든다(Task 3에서 엔드포인트 추가).

```python
# server/routes.py
"""API 엔드포인트."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")
```

```python
# server/app.py
"""FastAPI 앱 생성과 정적 서빙."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from server.config import JOBS_ROOT, MAX_CONCURRENT_JOBS
from server.jobs import JobStore
from server.routes import router

logger = logging.getLogger(__name__)
DIST_DIR: Path = Path(__file__).resolve().parent.parent / "docs/prototype/img2txt-web/dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 수명주기 동안 단일 JobStore를 유지한다."""
    app.state.job_store = JobStore(JOBS_ROOT, MAX_CONCURRENT_JOBS)
    if not DIST_DIR.exists():
        logger.warning("프런트 빌드(dist/)가 없습니다. `npm run build` 후 실행하세요: %s", DIST_DIR)
    try:
        yield
    finally:
        app.state.job_store.shutdown()


def create_app() -> FastAPI:
    """FastAPI 앱을 생성한다."""
    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
```

- [ ] **Step 3: Write the failing test**

```python
# tests/server/test_static.py
from fastapi.testclient import TestClient
from server.app import create_app


def test_app_boots_and_creates_job_store(tmp_path, monkeypatch):
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    with TestClient(create_app()) as client:
        assert client.app.state.job_store is not None
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python -m pytest tests/server/test_static.py -v`
Expected: PASS (lifespan이 job_store를 세팅). 실패 시 의존성 설치/임포트 확인.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt server/app.py server/routes.py .gitignore tests/server/test_static.py
git commit -m "feat: add FastAPI app skeleton and web deps"
```

---

## Task 3: 업로드 엔드포인트 `POST /api/jobs`

**Files:**
- Modify: `server/routes.py`
- Test: `tests/server/test_routes.py`

**Interfaces:**
- Consumes: `JobStore.create_job(files: list[tuple[str, bytes]], options: JobOptions) -> str`; `config` 상한 상수
- Produces: 라우트 함수 `create_job_route`; 의존성 `get_store(request) -> JobStore`

- [ ] **Step 1: Write the failing test**

```python
# tests/server/test_routes.py
import io
from fastapi.testclient import TestClient
from server.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    # create_job이 실제 파이프라인을 돌리지 않도록 모킹
    monkeypatch.setattr(
        "server.jobs.JobStore.create_job",
        lambda self, files, options: "job-test",
    )
    return TestClient(create_app())


def _jpg(nbytes: int = 8) -> bytes:
    return b"\xff\xd8\xff" + b"\x00" * nbytes


def test_create_job_accepts_valid_jpeg(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        resp = client.post(
            "/api/jobs",
            data={"correct": "false", "backend": "codex"},
            files=[("files", ("scan.jpg", io.BytesIO(_jpg()), "image/jpeg"))],
        )
    assert resp.status_code == 201
    assert resp.json() == {"id": "job-test"}


def test_create_job_rejects_non_jpeg(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        resp = client.post(
            "/api/jobs",
            data={"correct": "false", "backend": "codex"},
            files=[("files", ("a.png", io.BytesIO(b"\x89PNG"), "image/png"))],
        )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test — expect FAIL** (`404`, 라우트 없음)

Run: `python -m pytest tests/server/test_routes.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `POST /api/jobs`**

`server/routes.py`에 추가:

```python
from pathlib import Path

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile

from server.config import (
    UPLOAD_MAX_BYTES_PER_FILE,
    UPLOAD_MAX_FILES,
    UPLOAD_MAX_TOTAL_BYTES,
)
from server.jobs import JobStore
from server.models import CreateJobResponse, JobOptions

_CHUNK: int = 1024 * 1024
_MODEL_BY_BACKEND: dict[str, str] = {"codex": "gpt-5.5", "claude": "claude"}


def get_store(request: Request) -> JobStore:
    """앱 상태에 보관된 단일 JobStore를 주입한다."""
    return request.app.state.job_store


def _read_limited(upload: UploadFile, already: int) -> bytes:
    """청크로 읽으며 파일당/전체 상한을 실시간 검사한다(초과 시 413)."""
    data = bytearray()
    while True:
        chunk = upload.file.read(_CHUNK)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > UPLOAD_MAX_BYTES_PER_FILE:
            raise HTTPException(413, "file too large")
        if already + len(data) > UPLOAD_MAX_TOTAL_BYTES:
            raise HTTPException(413, "upload too large")
    return bytes(data)


@router.post("/jobs", status_code=201, response_model=CreateJobResponse)
def create_job_route(
    correct: bool = Form(...),
    backend: str = Form("codex"),
    files: list[UploadFile] = File(...),
    store: JobStore = Depends(get_store),
) -> CreateJobResponse:
    """이미지를 검증-수집하고 잡을 생성한다."""
    if not files:
        raise HTTPException(400, "no files")
    if len(files) > UPLOAD_MAX_FILES:
        raise HTTPException(400, "too many files")
    if backend not in _MODEL_BY_BACKEND:
        raise HTTPException(400, "invalid backend")

    collected: list[tuple[str, bytes]] = []
    total = 0
    for upload in files:
        name = upload.filename or ""
        if Path(name).suffix.lower() not in (".jpg", ".jpeg") or upload.content_type != "image/jpeg":
            raise HTTPException(400, "invalid file type")
        data = _read_limited(upload, total)
        if not data or data[:3] != b"\xff\xd8\xff":
            raise HTTPException(400, "not a valid jpeg")
        total += len(data)
        collected.append((name, data))

    # correct=false면 backend 무시하고 기본값. model은 backend에서 파생(요청으로 안 받음).
    effective_backend = backend if correct else "codex"
    options = JobOptions(
        correct=correct,
        backend=effective_backend,
        model=_MODEL_BY_BACKEND[effective_backend],
    )
    return CreateJobResponse(id=store.create_job(collected, options))
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python -m pytest tests/server/test_routes.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add server/routes.py tests/server/test_routes.py
git commit -m "feat: add POST /api/jobs upload endpoint"
```

---

## Task 4: 잡 조회 `GET /api/jobs/{id}`

**Files:**
- Modify: `server/routes.py`, `tests/server/test_routes.py`

**Interfaces:**
- Consumes: `JobStore.get_job(job_id) -> Job | None`
- Produces: 라우트 `get_job_route`

- [ ] **Step 1: Write the failing test**

```python
def test_get_job_404_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr("server.jobs.JobStore.get_job", lambda self, jid: None)
    from server.app import create_app
    with TestClient(create_app()) as client:
        resp = client.get("/api/jobs/nope")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "job not found"}
```

- [ ] **Step 2: Run — expect FAIL** (`404`가 아니라 라우트 없음으로 다른 응답)

Run: `python -m pytest tests/server/test_routes.py::test_get_job_404_when_missing -v`

- [ ] **Step 3: Implement**

`server/routes.py`에 추가(`from server.models import Job` 병합):

```python
@router.get("/jobs/{job_id}", response_model=Job)
def get_job_route(job_id: str, store: JobStore = Depends(get_store)) -> Job:
    """잡 상태를 반환한다."""
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/server/test_routes.py -v`

- [ ] **Step 5: Commit**

```bash
git add server/routes.py tests/server/test_routes.py
git commit -m "feat: add GET /api/jobs/{id}"
```

---

## Task 5: 재시도 `POST /api/jobs/{id}/retry/{fileId}`

**Files:**
- Modify: `server/routes.py`, `tests/server/test_routes.py`

**Interfaces:**
- Consumes: `JobStore.get_job`, `JobStore.retry_file(job_id, file_id) -> bool`
- Produces: 라우트 `retry_route` (404 잡없음/파일없음, 409 재시도불가, 200 성공)

- [ ] **Step 1: Write the failing test**

```python
from server.models import Job, JobOptions, JobStatus, PageFile, FileStatus


def _one_file_job(file_status):
    return Job(
        id="job-1", createdAt="2026-07-12T00:00:00Z",
        options=JobOptions(correct=False, backend="codex", model="gpt-5.5"),
        status=JobStatus.DONE,
        files=[PageFile(id="f1", filename="a.jpg", pageNumber=1, sizeBytes=1, status=file_status)],
    )


def test_retry_404_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr("server.jobs.JobStore.get_job", lambda self, jid: _one_file_job(FileStatus.FAILED))
    from server.app import create_app
    with TestClient(create_app()) as client:
        resp = client.post("/api/jobs/job-1/retry/does-not-exist")
    assert resp.status_code == 404


def test_retry_409_not_retryable(tmp_path, monkeypatch):
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr("server.jobs.JobStore.get_job", lambda self, jid: _one_file_job(FileStatus.DONE))
    monkeypatch.setattr("server.jobs.JobStore.retry_file", lambda self, jid, fid: False)
    from server.app import create_app
    with TestClient(create_app()) as client:
        resp = client.post("/api/jobs/job-1/retry/f1")
    assert resp.status_code == 409
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m pytest tests/server/test_routes.py -k retry -v`

- [ ] **Step 3: Implement**

```python
@router.post("/jobs/{job_id}/retry/{file_id}")
def retry_route(job_id: str, file_id: str, store: JobStore = Depends(get_store)) -> dict[str, str]:
    """실패한 페이지 한 장의 재시도를 요청한다."""
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if not any(f.id == file_id for f in job.files):
        raise HTTPException(404, "file not found")
    if not store.retry_file(job_id, file_id):
        raise HTTPException(409, "file is not retryable")
    return {"status": "ok"}
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/server/test_routes.py -k retry -v`

- [ ] **Step 5: Commit**

```bash
git add server/routes.py tests/server/test_routes.py
git commit -m "feat: add retry endpoint with 404/409 split"
```

---

## Task 6: 페이지 상세 `GET /api/jobs/{id}/pages/{n}`

**Files:**
- Modify: `server/routes.py`, `tests/server/test_routes.py`

**Interfaces:**
- Consumes: `JobStore.get_job`; `store.storage.read_output_file(job_id, "output/pages/page-{n:03d}.txt")`
- Produces: 라우트 `page_detail_route` → `PageDetail`

- [ ] **Step 1: Write the failing test**

```python
def test_page_detail_404_unknown_page(tmp_path, monkeypatch):
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr("server.jobs.JobStore.get_job", lambda self, jid: _one_file_job(FileStatus.DONE))
    from server.app import create_app
    with TestClient(create_app()) as client:
        resp = client.get("/api/jobs/job-1/pages/99")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m pytest tests/server/test_routes.py -k page_detail -v`

- [ ] **Step 3: Implement**

```python
from server.models import JobStatus, PageDetail


@router.get("/jobs/{job_id}/pages/{n}", response_model=PageDetail)
def page_detail_route(job_id: str, n: int, store: JobStore = Depends(get_store)) -> PageDetail:
    """페이지 원본 텍스트를 반환한다(보정본은 항상 null)."""
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
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/server/test_routes.py -k page_detail -v`

- [ ] **Step 5: Commit**

```bash
git add server/routes.py tests/server/test_routes.py
git commit -m "feat: add page detail endpoint"
```

---

## Task 7: 다운로드 엔드포인트 (페이지 + 번들)

**Files:**
- Modify: `server/routes.py`, `tests/server/test_routes.py`

**Interfaces:**
- Consumes: `server.naming.download_name`/`content_disposition`; `server.storage.build_job_path`, `stream_file`; `server.config.JOBS_ROOT`
- Produces: 라우트 `page_download_route`, `bundle_download_route`(`type=book|corrected|corrections`)

- [ ] **Step 1: Write the failing test**

```python
def test_book_download_200_with_filename(tmp_path, monkeypatch):
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr("server.routes.JOBS_ROOT", tmp_path / "jobs")
    # 산출물 파일 생성
    out = (tmp_path / "jobs" / "job-1" / "output")
    out.mkdir(parents=True)
    (out / "book.txt").write_text("본문", encoding="utf-8")
    monkeypatch.setattr("server.jobs.JobStore.get_job", lambda self, jid: _one_file_job(FileStatus.DONE))
    from server.app import create_app
    with TestClient(create_app()) as client:
        resp = client.get("/api/jobs/job-1/download?type=book")
    assert resp.status_code == 200
    assert "2026-07-12-a-book.txt" in resp.headers["content-disposition"]


def test_corrected_download_404_when_not_requested(tmp_path, monkeypatch):
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr("server.routes.JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr("server.jobs.JobStore.get_job", lambda self, jid: _one_file_job(FileStatus.DONE))
    from server.app import create_app
    with TestClient(create_app()) as client:
        resp = client.get("/api/jobs/job-1/download?type=corrected")
    assert resp.status_code == 404
```

> 참고: `_one_file_job`은 `options.correct=False`라 corrected 요청이 404가 되어야 한다.

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m pytest tests/server/test_routes.py -k download -v`

- [ ] **Step 3: Implement**

```python
from fastapi.responses import StreamingResponse

from server.config import JOBS_ROOT
from server.models import Job
from server.naming import content_disposition, download_name
from server.storage import build_job_path, stream_file


def _stream_output(job: Job, rel_path: str, kind: str, page: int | None = None) -> StreamingResponse:
    """산출물 파일을 파일명 규칙과 함께 스트리밍한다."""
    path = build_job_path(JOBS_ROOT, job.id) / rel_path
    headers = {"Content-Disposition": content_disposition(download_name(job, kind, page))}
    return StreamingResponse(
        stream_file(path), media_type="text/plain; charset=utf-8", headers=headers
    )


@router.get("/jobs/{job_id}/pages/{n}/download")
def page_download_route(job_id: str, n: int, store: JobStore = Depends(get_store)) -> StreamingResponse:
    """페이지 텍스트를 다운로드한다."""
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
    job_id: str, type: str = "book", store: JobStore = Depends(get_store)
) -> StreamingResponse:
    """연속본/보정본/대조로그를 다운로드한다."""
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
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/server/test_routes.py -k download -v`

- [ ] **Step 5: Commit**

```bash
git add server/routes.py tests/server/test_routes.py
git commit -m "feat: add download endpoints with state-based responses"
```

---

## Task 8: 의향 스텁 `POST /api/intent`

**Files:**
- Modify: `server/routes.py`, `tests/server/test_routes.py`

**Interfaces:**
- Produces: 라우트 `intent_route`(이메일 형식만 검증, 미저장)

- [ ] **Step 1: Write the failing test**

```python
def test_intent_validates_email(tmp_path, monkeypatch):
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    from server.app import create_app
    with TestClient(create_app()) as client:
        ok = client.post("/api/intent", json={"email": "a@b.com"})
        bad = client.post("/api/intent", json={"email": "nope"})
    assert ok.status_code == 200
    assert bad.status_code == 400
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m pytest tests/server/test_routes.py -k intent -v`

- [ ] **Step 3: Implement**

```python
import re

from fastapi import Body

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/intent")
def intent_route(email: str = Body(..., embed=True)) -> dict[str, str]:
    """이메일 형식만 검증하는 스텁(미저장)."""
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "invalid email")
    return {"status": "ok"}
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/server/test_routes.py -k intent -v`

- [ ] **Step 5: Commit**

```bash
git add server/routes.py tests/server/test_routes.py
git commit -m "feat: add intent stub endpoint"
```

---

## Task 9: 정적 서빙 + SPA 폴백 + 500 핸들러 (`server/app.py`)

**Files:**
- Modify: `server/app.py`, `tests/server/test_static.py`

**Interfaces:**
- Consumes: `DIST_DIR`
- Produces: catch-all 라우트(자산 있으면 서빙, 확장자 자산 미스 404, 화면 경로 index.html), 전역 500 핸들러

- [ ] **Step 1: Write the failing test**

```python
def test_missing_js_asset_is_404_not_index(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    monkeypatch.setattr("server.app.DIST_DIR", dist)
    monkeypatch.setattr("server.app.JOBS_ROOT", tmp_path / "jobs")
    from server.app import create_app
    with TestClient(create_app()) as client:
        asset = client.get("/assets/missing.js")
        page = client.get("/jobs/abc")
    assert asset.status_code == 404
    assert page.status_code == 200
    assert "app" in page.text
```

- [ ] **Step 2: Run — expect FAIL** (catch-all 없음)

Run: `python -m pytest tests/server/test_static.py -v`

- [ ] **Step 3: Implement — `create_app`에 정적 서빙과 예외 핸들러 추가**

`server/app.py`의 `create_app`를 확장:

```python
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse


def create_app() -> FastAPI:
    """FastAPI 앱을 생성한다."""
    app = FastAPI(lifespan=lifespan)
    app.include_router(router)

    @app.exception_handler(Exception)
    async def _on_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """정적 자산 서빙과 SPA 폴백."""
        if full_path.startswith("api/"):
            return PlainTextResponse("not found", status_code=404)
        candidate = (DIST_DIR / full_path).resolve()
        if (DIST_DIR.resolve() in candidate.parents) and candidate.is_file():
            return FileResponse(candidate)
        if Path(full_path).suffix:  # 확장자 있는 자산인데 없음
            return PlainTextResponse("not found", status_code=404)
        index = DIST_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
        return PlainTextResponse(
            "프런트 빌드가 없습니다. `npm run build` 후 재시작하세요.", status_code=200
        )

    return app
```

> 순서 주의: `include_router(router)`가 먼저라 `/api/*`는 라우터가 우선 매칭한다. catch-all은 그 밖만 처리한다.

- [ ] **Step 4: Run — expect PASS (전체 서버 테스트도 함께)**

Run: `python -m pytest tests/server/ -v`
Expected: 전부 PASS.

- [ ] **Step 5: Commit**

```bash
git add server/app.py tests/server/test_static.py
git commit -m "feat: add static serving, SPA fallback, 500 handler"
```

---

## Task 10: 프런트 실제 백엔드 연결 (MSW 제거 + proxy + 타입)

**Files:**
- Modify: `docs/prototype/img2txt-web/src/main.tsx`, `vite.config.ts`, `src/api/types.ts`

**Interfaces:**
- Consumes: 백엔드 `Job`/`JobOptions` 필드
- Produces: MSW 미사용 앱, dev proxy, 확장 타입

- [ ] **Step 1: MSW 비활성화** — `src/main.tsx`의 `enableMocking` 블록을 제거하고 곧바로 렌더:

```tsx
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
```
(기존 `enableMocking().then(...)` 래퍼와 `./mocks/browser` import 삭제. 실제 렌더 JSX는 기존 파일 구조를 따른다.)

- [ ] **Step 2: dev proxy 추가** — `vite.config.ts`의 `defineConfig`에 추가:

```ts
export default defineConfig({
  // ...기존 plugins 유지...
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

- [ ] **Step 3: 타입 확장** — `src/api/types.ts`의 `Job`/`JobOptions`를 백엔드와 일치:

```ts
export interface JobOptions {
  correct: boolean;
  backend: "codex" | "claude";
  model: string; // 읽기 전용 표시값 (서버 파생)
}

export interface Job {
  // ...기존 필드...
  phase: "ocr" | "correcting";
  correction: { done: number; total: number } | null;
  correctionError: string | null;
  correctedStale: boolean;
}
```

- [ ] **Step 4: 빌드로 검증**

Run: `cd docs/prototype/img2txt-web && npm run build`
Expected: 타입 오류 없이 `dist/` 생성. 오류 나면 참조 컴포넌트의 필드 사용을 타입에 맞춘다.

- [ ] **Step 5: Commit**

```bash
git add docs/prototype/img2txt-web/src/main.tsx docs/prototype/img2txt-web/vite.config.ts docs/prototype/img2txt-web/src/api/types.ts
git commit -m "feat: connect frontend to real backend (remove MSW, add proxy, extend types)"
```

---

## Task 11: 프런트 화면 조정 (업로드/진행/결과)

**Files:**
- Modify: `src/pages/UploadPage.tsx`, `src/pages/JobPage.tsx`, `src/pages/ResultPage.tsx`, `src/api/client.ts` (실제 경로는 구현 시 확인)

**Interfaces:**
- Consumes: 확장된 `Job`/`JobOptions` 타입, `/api/jobs/:id/download?type=` 계약

- [ ] **Step 1: UploadPage — 백엔드 선택 + 요청 필드 제한**

- 보정(`correct`)이 켜졌을 때만 활성화되는 백엔드 선택(codex 기본/claude, claude 옆 "실험적" 표기)을 추가한다.
- 표시 모델명은 `codex → gpt-5.5`, `claude → claude`로 라벨만 보여준다(읽기 전용).
- 업로드 요청 `FormData`에는 `correct`와 `backend`만 담는다. `model`은 보내지 않는다.

- [ ] **Step 2: JobPage — 단계/진행/경고 표시**

- `phase`로 "OCR 중 / 보정 중" 문구 분기.
- `correction`이 있으면 진행바 `done/total` 표시.
- `correctionError`가 있으면 "보정 건너뜀" 경고, `correctedStale`면 "보정본이 최신 변환과 다를 수 있음" 경고.
- 폴링 종료: `status`가 `done`/`failed`면 `refetchInterval`을 멈춘다(기존 React Query 구조 활용).

- [ ] **Step 3: ResultPage — 책 전체 비교 + 다운로드 방식 분리**

- 원본 대 보정 비교를 책 전체(`book.txt` vs `book_corrected.txt`) 기준으로 바꾼다. 화면 "표시"는 `fetch`로 `/api/jobs/:id/download?type=book`(및 `corrected`) 본문을 텍스트로 읽어 렌더한다.
- 파일 "저장(다운로드)"은 앵커(`<a href="/api/jobs/:id/download?type=book">`)나 `window.location`으로 직접 열어 브라우저가 서버 `Content-Disposition` 파일명을 쓰게 한다. `client.ts`의 다운로드 함수가 `fetch`로 blob을 만들어 저장하고 있으면, 표시용(fetch 텍스트)과 저장용(앵커)으로 분리한다.
- corrections.log 다운로드 버튼(앵커 `?type=corrections`)을 추가한다. 페이지별 다운로드는 원본(`pages/:n/download`) 유지.

- [ ] **Step 4: 수동 검증 (스모크)**

```bash
# 터미널 1: 백엔드
uvicorn server.app:app
# 터미널 2: 프런트(개발)
cd docs/prototype/img2txt-web && npm run dev
```
브라우저에서 이미지 업로드 → 진행 폴링 → `book.txt` 다운로드 파일명이 `YYYY-MM-DD-<원본>-book.txt`인지 확인.

- [ ] **Step 5: Commit**

```bash
git add docs/prototype/img2txt-web/src
git commit -m "feat: adjust upload/job/result pages for real backend"
```

---

## 최종 검증

- [ ] 전체 자동 테스트: `python -m pytest -q` (기존 + 신규 서버 테스트 모두 통과, 출력 첨부)
- [ ] 프런트 빌드: `cd docs/prototype/img2txt-web && npm run build` 성공
- [ ] 단일 실행 end-to-end(수동 스모크): `npm run build` 후 `uvicorn server.app:app` → `localhost:8000`에서 업로드→다운로드 동작, 파일명 규칙 일치, 보정 미가용 시 book.txt 보존.
