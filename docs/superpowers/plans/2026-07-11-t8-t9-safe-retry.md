# T8/T9 Safe Pipeline and Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 자연 정렬된 이미지 변환, 보정 실패 시 원본 보존, 기존 페이지를 훼손하지 않는 단일 페이지 재시도를 구현한다.

**Architecture:** `server.pipeline`이 OCR, 레이아웃 JSON, 조립, 보정을 담당한다. `server.jobs`는 자연 정렬된 업로드 메타데이터와 백그라운드 실행 상태만 관리하며 재시도도 파이프라인 함수를 재사용한다. 페이지별 레이아웃 JSON을 `book.txt` 재조립의 원본으로 사용한다.

**Tech Stack:** Python 3.13, Pydantic, `asyncio`, `ThreadPoolExecutor`, pytest

## Global Constraints

- 기존 `img2txt`의 scanner, OCR, layout, assembler, corrector, writer 로직을 재사용한다.
- 보정 실패는 변환 결과 `book.txt`를 삭제하거나 잡 전체 실패로 바꾸지 않는다.
- 재시도는 실패한 한 페이지만 OCR하며 `book_corrected.txt`와 `corrections.log`를 수정하지 않는다.
- 내부 업로드 이름은 `upload-<uuid>-page-<순번>.jpg`, 공개 파일명은 원본 이름을 유지한다.
- 외부 OCR과 보정 백엔드만 테스트에서 대체한다.
- 핵심 서비스 테스트만 작성하며 파일별 핵심 테스트를 3개 이하로 제한한다.
- 테스트 명령은 프로젝트 가상환경을 사용하는 `rtk pytest`로 실행한다.

---

### Task 1: 변환 파이프라인과 레이아웃 보조 파일

**Files:**
- Create: `server/pipeline.py`
- Create: `tests/server/test_pipeline.py`

**Interfaces:**
- Consumes: `collect_images(Path) -> list[Path]`, `recognize_page(Path, int) -> Page`, `analyze_page(Page) -> PageLayout`, `assemble(list[PageLayout]) -> str`
- Produces: `run_convert_pipeline(job, job_path, storage, on_update) -> None`, `load_stored_layout(path) -> tuple[PageLayout, int]`

- [ ] **Step 1: 일부 OCR 실패 테스트 작성**

```python
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from img2txt.ocr import OcrLine, Page
from server.models import FileStatus, Job, JobOptions, JobStatus, PageFile
from server.pipeline import run_convert_pipeline
from server.storage import JobStorage


def _job(file_count: int) -> Job:
    return Job(
        id="job-1",
        createdAt="2026-07-11T00:00:00Z",
        options=JobOptions(correct=False),
        status=JobStatus.PROCESSING,
        files=[
            PageFile(
                id=f"file-{number}", filename=f"page-{number}.jpg",
                pageNumber=number, sizeBytes=1, status=FileStatus.WAITING,
            )
            for number in range(1, file_count + 1)
        ],
    )


def _page(number: int, text: str) -> Page:
    return Page(number, [OcrLine(text, 1.0, 0.1, 0.5, 0.8, 0.02)])


def test_convert_keeps_other_pages_when_one_ocr_fails(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "upload-a-page-0001.jpg").write_bytes(b"1")
    (uploads / "upload-b-page-0002.jpg").write_bytes(b"2")

    def fake_recognize(_path: Path, number: int) -> Page:
        if number == 2:
            raise RuntimeError("ocr failed")
        return _page(number, "첫 페이지")

    monkeypatch.setattr("server.pipeline.recognize_page", fake_recognize)
    job = _job(2)
    asyncio.run(run_convert_pipeline(job, tmp_path, JobStorage(tmp_path), MagicMock()))

    book = (tmp_path / "output" / "book.txt").read_text(encoding="utf-8")
    assert "첫 페이지" in book
    assert "[페이지 2 누락]" in book
    assert job.files[0].status is FileStatus.DONE
    assert job.files[1].status is FileStatus.FAILED
    assert job.status is JobStatus.DONE
```

- [ ] **Step 2: 실패 확인**

Run: `rtk pytest tests/server/test_pipeline.py::test_convert_keeps_other_pages_when_one_ocr_fails -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'server.pipeline'`.

- [ ] **Step 3: 레이아웃 저장과 변환 최소 구현**

`server/pipeline.py`에 다음 책임을 구현한다.

```python
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from img2txt.assembler import assemble
from img2txt.layout import PageLayout, analyze_page
from img2txt.ocr import Page, recognize_page
from img2txt.scanner import collect_images
from img2txt.writer import write_page_texts, write_text_file
from server.models import FileStatus, Job, JobStatus, JobSummary
from server.storage import JobStorage

logger = logging.getLogger(__name__)
UpdateCallback = Callable[[Job], None]


def _layout_path(job_path: Path, page_number: int) -> Path:
    return job_path / "output" / "layouts" / f"page-{page_number:03d}.json"


def save_stored_layout(path: Path, layout: PageLayout) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "number": layout.number,
        "paragraphs": layout.paragraphs,
        "first_is_continuation": layout.first_is_continuation,
        "is_empty": layout.is_empty,
        "removed_footer_lines": len(layout.footer_lines),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_stored_layout(path: Path) -> tuple[PageLayout, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    layout = PageLayout(
        number=int(payload["number"]),
        paragraphs=list(payload["paragraphs"]),
        first_is_continuation=bool(payload["first_is_continuation"]),
        is_empty=bool(payload["is_empty"]),
    )
    return layout, int(payload["removed_footer_lines"])


async def run_convert_pipeline(
    job: Job,
    job_path: Path,
    storage: JobStorage,
    on_update: UpdateCallback,
) -> None:
    del storage
    image_paths = collect_images(job_path / "uploads")
    if not image_paths or len(image_paths) != len(job.files):
        job.status = JobStatus.FAILED
        on_update(job)
        return

    pages: list[Page] = []
    layouts: list[PageLayout] = []
    failed_count = 0
    for image_path, file_entry in zip(image_paths, job.files):
        file_entry.status = FileStatus.OCR
        on_update(job)
        try:
            page = recognize_page(image_path, file_entry.pageNumber)
            layout = analyze_page(page)
            file_entry.status = FileStatus.DONE
            file_entry.error = None
            file_entry.previewText = "\n".join(line.text for line in page.lines)[:80]
        except Exception as error:
            logger.warning("OCR 실패: %s", error)
            page = Page(number=file_entry.pageNumber)
            layout = analyze_page(page)
            file_entry.status = FileStatus.FAILED
            file_entry.error = str(error)
            failed_count += 1
        pages.append(page)
        layouts.append(layout)
        on_update(job)

    output_dir = job_path / "output"
    write_page_texts(output_dir / "pages", pages)
    for layout in layouts:
        save_stored_layout(_layout_path(job_path, layout.number), layout)
    write_text_file(output_dir / "book.txt", assemble(layouts))
    job.summary = JobSummary(
        successPages=len(pages) - failed_count,
        failedPages=failed_count,
        removedFooterLines=sum(len(layout.footer_lines) for layout in layouts),
    )
    job.status = JobStatus.DONE
    on_update(job)
```

- [ ] **Step 4: 일부 실패 테스트 통과 확인**

Run: `rtk pytest tests/server/test_pipeline.py::test_convert_keeps_other_pages_when_one_ocr_fails -v`

Expected: PASS.

- [ ] **Step 5: 전체 OCR 실패 테스트 작성**

```python
def test_convert_marks_job_failed_when_all_ocr_fails(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "upload-a-page-0001.jpg").write_bytes(b"1")
    monkeypatch.setattr(
        "server.pipeline.recognize_page",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("ocr failed")),
    )
    job = _job(1)
    asyncio.run(run_convert_pipeline(job, tmp_path, JobStorage(tmp_path), MagicMock()))
    assert job.status is JobStatus.FAILED
    assert job.summary is not None
    assert job.summary.failedPages == 1
```

- [ ] **Step 6: 전체 실패 테스트가 올바르게 실패하는지 확인**

Run: `rtk pytest tests/server/test_pipeline.py::test_convert_marks_job_failed_when_all_ocr_fails -v`

Expected: FAIL with `JobStatus.DONE != JobStatus.FAILED`.

- [ ] **Step 7: 전체 실패 상태 결정 구현**

`run_convert_pipeline` 마지막 상태 할당을 다음으로 교체한다.

```python
job.status = JobStatus.FAILED if failed_count == len(pages) else JobStatus.DONE
```

- [ ] **Step 8: 변환 테스트 통과 확인**

Run: `rtk pytest tests/server/test_pipeline.py -v`

Expected: 2 passed.

- [ ] **Step 9: 커밋**

```bash
git add server/pipeline.py tests/server/test_pipeline.py
git commit -m "feat: add safe server conversion pipeline"
```

---

### Task 2: 보정 실패 시 변환 결과 보존

**Files:**
- Modify: `server/pipeline.py`
- Modify: `tests/server/test_pipeline.py`

**Interfaces:**
- Consumes: `select_backend(model: str, backend_name: str | None)`, `correct_paragraphs(paragraphs, model, backend)`, `all_requests_failed(records)`
- Produces: `run_correct_pipeline(job, job_path, storage, on_update) -> None`

- [ ] **Step 1: 전체 보정 실패 테스트 작성**

```python
from img2txt.corrector import CorrectionRecord, CorrectionStatus
from server.pipeline import run_correct_pipeline


def test_correction_failure_preserves_book_and_finishes_job(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    book = output / "book.txt"
    book.write_text("원문", encoding="utf-8")
    job = _job(1)
    job.status = JobStatus.DONE
    record = CorrectionRecord(1, CorrectionStatus.FAILED, "실패", "gpt-5.5", "원문", "원문")
    monkeypatch.setattr("server.pipeline.select_backend", lambda *_args: object())
    monkeypatch.setattr("server.pipeline.correct_paragraphs", lambda *_args: (["원문"], [record]))

    asyncio.run(run_correct_pipeline(job, tmp_path, JobStorage(tmp_path), MagicMock()))

    assert book.read_text(encoding="utf-8") == "원문"
    assert not (output / "book_corrected.txt").exists()
    assert job.status is JobStatus.DONE
    assert job.correctionError
```

- [ ] **Step 2: 실패 확인**

Run: `rtk pytest tests/server/test_pipeline.py::test_correction_failure_preserves_book_and_finishes_job -v`

Expected: FAIL because `run_correct_pipeline` is not defined.

- [ ] **Step 3: 최소 구현**

```python
from img2txt.backends.factory import select_backend
from img2txt.corrector import (
    CorrectionStatus,
    all_requests_failed,
    correct_paragraphs,
)
from img2txt.writer import format_corrections_log


async def run_correct_pipeline(
    job: Job,
    job_path: Path,
    storage: JobStorage,
    on_update: UpdateCallback,
) -> None:
    del storage
    output_dir = job_path / "output"
    book_path = output_dir / "book.txt"
    try:
        paragraphs = [part for part in book_path.read_text(encoding="utf-8").split("\n\n") if part.strip()]
        if not paragraphs:
            raise ValueError("처리할 문단이 없습니다")
        job.phase = "correcting"
        on_update(job)
        backend = select_backend(job.options.model, job.options.backend)
        corrected, records = correct_paragraphs(paragraphs, job.options.model, backend)
        if all_requests_failed(records):
            job.correctionError = "보정 서비스 요청이 모두 실패했습니다"
            job.status = JobStatus.DONE
            on_update(job)
            return
        write_text_file(output_dir / "book_corrected.txt", "\n\n".join(corrected))
        write_text_file(output_dir / "corrections.log", format_corrections_log(records))
        job.correction = {
            "corrected": sum(r.status is CorrectionStatus.CORRECTED for r in records),
            "kept": sum(r.status is CorrectionStatus.KEPT for r in records),
            "guardBlocked": sum(r.status is CorrectionStatus.GUARD_BLOCKED for r in records),
        }
        if job.summary is not None:
            job.summary.corrected = job.correction["corrected"]
            job.summary.kept = job.correction["kept"]
            job.summary.guardBlocked = job.correction["guardBlocked"]
        job.correctionError = None
        job.status = JobStatus.DONE
        on_update(job)
    except Exception as error:
        job.correctionError = str(error)
        job.status = JobStatus.DONE
        on_update(job)
```

- [ ] **Step 4: 파이프라인 테스트 통과 확인**

Run: `rtk pytest tests/server/test_pipeline.py -v`

Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add server/pipeline.py tests/server/test_pipeline.py
git commit -m "feat: preserve conversion output on correction failure"
```

---

### Task 3: JobStore 생성과 백그라운드 실행

**Files:**
- Create: `server/jobs.py`
- Create: `tests/server/test_jobs.py`

**Interfaces:**
- Consumes: `run_convert_pipeline`, `run_correct_pipeline`, `JobStorage.save_uploaded_file(job_id, filename, data)`
- Produces: `JobStore.create_job(files, options) -> str`, `JobStore.get_job(job_id) -> Job | None`, `JobStore.shutdown() -> None`

- [ ] **Step 1: 자연 정렬과 실제 저장 시그니처 테스트 작성**

```python
from unittest.mock import MagicMock

from img2txt.scanner import collect_images
from server.jobs import JobStore
from server.models import JobOptions


def test_create_job_naturally_sorts_files_and_uses_internal_names(tmp_path):
    store = JobStore(tmp_path, max_concurrent=1)
    store.executor.submit = MagicMock()
    job_id = store.create_job(
        [("page-10.jpg", b"10"), ("page-2.jpg", b"2")],
        JobOptions(correct=False),
    )
    job = store.get_job(job_id)
    assert job is not None
    assert [file.filename for file in job.files] == ["page-2.jpg", "page-10.jpg"]
    assert [file.pageNumber for file in job.files] == [1, 2]
    saved = collect_images(tmp_path / job_id / "uploads")
    assert len(saved) == 2
    assert saved[0].name.endswith("page-0001.jpg")
    store.shutdown()
```

- [ ] **Step 2: 실패 확인**

Run: `rtk pytest tests/server/test_jobs.py::test_create_job_naturally_sorts_files_and_uses_internal_names -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'server.jobs'`.

- [ ] **Step 3: JobStore 최소 구현**

```python
from __future__ import annotations

import asyncio
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from img2txt.scanner import extract_page_number
from server.config import JOBS_ROOT, MAX_CONCURRENT_JOBS
from server.models import FileStatus, Job, JobOptions, JobStatus, PageFile
from server.pipeline import run_convert_pipeline, run_correct_pipeline
from server.storage import JobStorage


def _file_sort_key(item: tuple[str, bytes]) -> tuple[int, int, str]:
    name = item[0]
    number = extract_page_number(Path(name))
    return (number is None, number or 0, name)


class JobStore:
    def __init__(
        self,
        jobs_root: Path = JOBS_ROOT,
        max_concurrent: int = MAX_CONCURRENT_JOBS,
    ) -> None:
        self.jobs_root = jobs_root
        self.storage = JobStorage(jobs_root)
        self.jobs: dict[str, Job] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self._lock = threading.RLock()
        self.running_count = 0

    def create_job(self, files: list[tuple[str, bytes]], options: JobOptions) -> str:
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        job_path = self.storage.create_job_dir(job_id)
        page_files: list[PageFile] = []
        for page_number, (original_name, data) in enumerate(sorted(files, key=_file_sort_key), start=1):
            file_id = f"file-{uuid.uuid4().hex[:8]}"
            internal_name = f"upload-{file_id}-page-{page_number:04d}.jpg"
            self.storage.save_uploaded_file(job_id, internal_name, data)
            page_files.append(PageFile(
                id=file_id,
                filename=original_name,
                pageNumber=page_number,
                sizeBytes=len(data),
                status=FileStatus.WAITING,
            ))
        job = Job(
            id=job_id,
            createdAt=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            options=options,
            status=JobStatus.QUEUED,
            files=page_files,
        )
        with self._lock:
            self.jobs[job_id] = job
        self.executor.submit(self._run_job, job_id, job_path)
        return job_id

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            job = self.jobs.get(job_id)
            return job.model_copy(deep=True) if job is not None else None

    def _notify_update(self, job: Job) -> None:
        with self._lock:
            self.jobs[job.id] = job

    def _run_job(self, job_id: str, job_path: Path) -> None:
        with self._lock:
            job = self.jobs[job_id]
            self.running_count += 1
            job.status = JobStatus.PROCESSING
        self._notify_update(job)
        try:
            asyncio.run(run_convert_pipeline(job, job_path, self.storage, self._notify_update))
            if job.status is not JobStatus.FAILED and job.options.correct:
                asyncio.run(run_correct_pipeline(job, job_path, self.storage, self._notify_update))
        except Exception as error:
            job.status = JobStatus.FAILED
            job.correctionError = str(error)
            self._notify_update(job)
        finally:
            with self._lock:
                self.running_count -= 1

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `rtk pytest tests/server/test_jobs.py::test_create_job_naturally_sorts_files_and_uses_internal_names -v`

Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add server/jobs.py tests/server/test_jobs.py
git commit -m "feat: add naturally sorted background job store"
```

---

### Task 4: 기존 산출물을 보존하는 단일 페이지 재시도

**Files:**
- Modify: `server/pipeline.py`
- Modify: `server/jobs.py`
- Modify: `tests/server/test_jobs.py`

**Interfaces:**
- Produces: `retry_page_pipeline(job, job_path, page_number, on_update) -> bool`, `JobStore.retry_file(job_id, file_id) -> bool`

- [ ] **Step 1: 재시도 성공 회귀 테스트 작성**

```python
import json

from img2txt.layout import PageLayout
from img2txt.ocr import OcrLine, Page
from server.models import FileStatus, Job, JobOptions, JobStatus, PageFile
from server.pipeline import save_stored_layout


def test_retry_replaces_only_failed_page_and_preserves_corrected_outputs(tmp_path, monkeypatch):
    store = JobStore(tmp_path, max_concurrent=1)
    store.executor.submit = MagicMock()
    job_id = store.create_job(
        [("page-1.jpg", b"1"), ("page-2.jpg", b"2")],
        JobOptions(correct=False),
    )
    job_path = tmp_path / job_id
    output = job_path / "output"
    (output / "pages").mkdir(parents=True)
    (output / "layouts").mkdir(parents=True)
    (output / "pages" / "page-001.txt").write_text("기존 1", encoding="utf-8")
    (output / "pages" / "page-002.txt").write_text("", encoding="utf-8")
    save_stored_layout(output / "layouts" / "page-001.json", PageLayout(1, ["기존 1"], False))
    save_stored_layout(output / "layouts" / "page-002.json", PageLayout(2, [], False, is_empty=True))
    (output / "book.txt").write_text("기존 1\n\n[페이지 2 누락]", encoding="utf-8")
    (output / "book_corrected.txt").write_text("보정본 유지", encoding="utf-8")

    with store._lock:
        live_job = store.jobs[job_id]
        live_job.status = JobStatus.DONE
        live_job.files[1].status = FileStatus.FAILED
        live_job.files[1].error = "old error"

    monkeypatch.setattr(
        "server.pipeline.recognize_page",
        lambda _path, number: Page(number, [OcrLine("복구 2", 1.0, 0.1, 0.5, 0.8, 0.02)]),
    )
    store._run_retry(job_id, job_path, 2)

    assert (output / "pages" / "page-001.txt").read_text(encoding="utf-8") == "기존 1"
    assert "기존 1" in (output / "book.txt").read_text(encoding="utf-8")
    assert "복구 2" in (output / "book.txt").read_text(encoding="utf-8")
    assert (output / "book_corrected.txt").read_text(encoding="utf-8") == "보정본 유지"
    assert store.get_job(job_id).files[1].status is FileStatus.DONE
    store.shutdown()
```

- [ ] **Step 2: 실패 확인**

Run: `rtk pytest tests/server/test_jobs.py::test_retry_replaces_only_failed_page_and_preserves_corrected_outputs -v`

Expected: FAIL because `_run_retry` is not defined.

- [ ] **Step 3: 파이프라인 재시도 구현**

`server/pipeline.py`에 임시 파일과 백업 복원을 포함해 구현한다.

```python
import os
import tempfile


def _replace_text_outputs(changes: dict[Path, str]) -> None:
    backups = {path: path.read_bytes() if path.exists() else None for path in changes}
    temp_paths: dict[Path, Path] = {}
    try:
        for target, text in changes.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
                handle.write(text)
                temp_paths[target] = Path(handle.name)
        for target, temporary in temp_paths.items():
            os.replace(temporary, target)
    except Exception:
        for target, content in backups.items():
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(content)
        raise
    finally:
        for temporary in temp_paths.values():
            temporary.unlink(missing_ok=True)


async def retry_page_pipeline(
    job: Job,
    job_path: Path,
    page_number: int,
    on_update: UpdateCallback,
) -> bool:
    file_entry = next((item for item in job.files if item.pageNumber == page_number), None)
    if file_entry is None:
        return False
    images = collect_images(job_path / "uploads")
    if page_number < 1 or page_number > len(images):
        return False
    try:
        page = recognize_page(images[page_number - 1], page_number)
        replacement = analyze_page(page)
        layouts: list[PageLayout] = []
        footer_counts: list[int] = []
        for number in range(1, len(job.files) + 1):
            if number == page_number:
                layouts.append(replacement)
                footer_counts.append(len(replacement.footer_lines))
            else:
                layout, footer_count = load_stored_layout(_layout_path(job_path, number))
                layouts.append(layout)
                footer_counts.append(footer_count)
        layout_payload = json.dumps({
            "number": replacement.number,
            "paragraphs": replacement.paragraphs,
            "first_is_continuation": replacement.first_is_continuation,
            "is_empty": replacement.is_empty,
            "removed_footer_lines": len(replacement.footer_lines),
        }, ensure_ascii=False)
        _replace_text_outputs({
            job_path / "output" / "pages" / f"page-{page_number:03d}.txt": "\n".join(line.text for line in page.lines),
            _layout_path(job_path, page_number): layout_payload,
            job_path / "output" / "book.txt": assemble(layouts),
        })
        file_entry.status = FileStatus.DONE
        file_entry.error = None
        file_entry.previewText = "\n".join(line.text for line in page.lines)[:80]
        if job.summary is not None:
            job.summary.successPages = sum(item.status is FileStatus.DONE for item in job.files)
            job.summary.failedPages = sum(item.status is FileStatus.FAILED for item in job.files)
            job.summary.removedFooterLines = sum(footer_counts)
        on_update(job)
        return True
    except Exception as error:
        file_entry.status = FileStatus.FAILED
        file_entry.error = str(error)
        on_update(job)
        return False
```

- [ ] **Step 4: JobStore 재시도 연결**

```python
from server.pipeline import retry_page_pipeline


def retry_file(self, job_id: str, file_id: str) -> bool:
    with self._lock:
        job = self.jobs.get(job_id)
        if job is None or job.status is JobStatus.PROCESSING:
            return False
        file_entry = next((item for item in job.files if item.id == file_id), None)
        if file_entry is None or file_entry.status is not FileStatus.FAILED:
            return False
        file_entry.status = FileStatus.OCR
        job.status = JobStatus.PROCESSING
        page_number = file_entry.pageNumber
    self.executor.submit(self._run_retry, job_id, self.jobs_root / job_id, page_number)
    return True


def _run_retry(self, job_id: str, job_path: Path, page_number: int) -> None:
    with self._lock:
        job = self.jobs[job_id]
    success = asyncio.run(retry_page_pipeline(job, job_path, page_number, self._notify_update))
    job.status = JobStatus.DONE if success or any(
        item.status is FileStatus.DONE for item in job.files
    ) else JobStatus.FAILED
    self._notify_update(job)
```

- [ ] **Step 5: 재시도 실패 보존 테스트 작성**

```python
def test_retry_failure_keeps_existing_outputs(tmp_path, monkeypatch):
    store = JobStore(tmp_path, max_concurrent=1)
    store.executor.submit = MagicMock()
    job_id = store.create_job([("page-1.jpg", b"1")], JobOptions(correct=False))
    job_path = tmp_path / job_id
    output = job_path / "output"
    (output / "pages").mkdir(parents=True)
    (output / "layouts").mkdir(parents=True)
    page_path = output / "pages" / "page-001.txt"
    book_path = output / "book.txt"
    page_path.write_text("", encoding="utf-8")
    book_path.write_text("[페이지 1 누락]", encoding="utf-8")
    save_stored_layout(
        output / "layouts" / "page-001.json",
        PageLayout(1, [], False, is_empty=True),
    )
    with store._lock:
        live_job = store.jobs[job_id]
        live_job.status = JobStatus.DONE
        live_job.files[0].status = FileStatus.FAILED
        live_job.files[0].error = "old error"
    before_book = book_path.read_bytes()
    before_page = page_path.read_bytes()
    monkeypatch.setattr(
        "server.pipeline.recognize_page",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("retry failed")),
    )

    store._run_retry(job_id, job_path, 1)

    assert book_path.read_bytes() == before_book
    assert page_path.read_bytes() == before_page
    assert store.get_job(job_id).files[0].status is FileStatus.FAILED
    store.shutdown()
```

- [ ] **Step 6: JobStore 테스트 통과 확인**

Run: `rtk pytest tests/server/test_jobs.py -v`

Expected: 3 passed.

- [ ] **Step 7: 전체 서버 핵심 테스트 확인**

Run: `rtk pytest tests/server -v`

Expected: 기존 8개 + 신규 6개 테스트 모두 PASS.

- [ ] **Step 8: 커밋**

```bash
git add server/pipeline.py server/jobs.py tests/server/test_jobs.py
git commit -m "feat: add safe single-page OCR retry"
```

---

### Task 5: 정적 검사와 계획 정합성 마무리

**Files:**
- Modify: `docs/superpowers/plans/2026-07-08-img2txt-web-service.md`

**Interfaces:**
- Produces: 기존 계획서 T8/T9에 보완 설계와 실제 구현 경로를 연결하는 기록

- [ ] **Step 1: 전체 비-macOS 테스트 실행**

Run: `rtk pytest -m 'not macos' -v`

Expected: 0 failed.

- [ ] **Step 2: 타입 검사 실행**

Run: `.venv/bin/python -m mypy --strict server/pipeline.py server/jobs.py`

Expected: `Success: no issues found in 2 source files`.

- [ ] **Step 3: 기존 계획서 체크리스트 갱신**

`docs/superpowers/plans/2026-07-08-img2txt-web-service.md`의 Phase 2 체크리스트에서 T8/T9를 완료로 바꾸고, 각 항목 끝에 다음 문구를 붙인다.

```markdown
(보완 설계: `docs/superpowers/specs/2026-07-11-t8-t9-safe-retry-design.md`)
```

- [ ] **Step 4: 최종 변경 검사**

Run: `git diff --check && git status --short`

Expected: 공백 오류 없음. `.idea/`, `tobyteam/` 외 의도한 문서 변경만 표시.

- [ ] **Step 5: 문서 커밋**

```bash
git add docs/superpowers/plans/2026-07-08-img2txt-web-service.md
git commit -m "docs: mark safe pipeline and retry tasks complete"
```
