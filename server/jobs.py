"""메모리 잡 저장소와 제한된 백그라운드 워커."""
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
from server.pipeline import (
    retry_page_pipeline,
    run_convert_pipeline,
    run_correct_pipeline,
)
from server.storage import JobStorage


def _file_sort_key(item: tuple[str, bytes]) -> tuple[bool, int, str]:
    """원본 파일명의 마지막 숫자로 자연 정렬 키를 만든다."""
    name = item[0]
    number = extract_page_number(Path(name))
    return number is None, number or 0, name


class JobStore:
    """메모리 잡 상태와 백그라운드 실행을 관리한다."""

    def __init__(
        self,
        jobs_root: Path = JOBS_ROOT,
        max_concurrent: int = MAX_CONCURRENT_JOBS,
    ) -> None:
        self.jobs_root = jobs_root
        self.max_concurrent = max_concurrent
        self.storage = JobStorage(jobs_root)
        self.jobs: dict[str, Job] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self._lock = threading.RLock()
        self.running_count = 0

    def create_job(
        self,
        files: list[tuple[str, bytes]],
        options: JobOptions,
    ) -> str:
        """파일을 자연 정렬해 저장하고 백그라운드 변환을 시작한다."""
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        job_path = self.storage.create_job_dir(job_id)
        page_files: list[PageFile] = []

        for page_number, (original_name, data) in enumerate(
            sorted(files, key=_file_sort_key),
            start=1,
        ):
            file_id = f"file-{uuid.uuid4().hex[:8]}"
            internal_name = (
                f"upload-{file_id}-page-{page_number:04d}.jpg"
            )
            self.storage.save_uploaded_file(job_id, internal_name, data)
            page_files.append(
                PageFile(
                    id=file_id,
                    filename=original_name,
                    pageNumber=page_number,
                    sizeBytes=len(data),
                    status=FileStatus.WAITING,
                )
            )

        job = Job(
            id=job_id,
            createdAt=(
                datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            options=options,
            status=JobStatus.QUEUED,
            files=page_files,
        )
        with self._lock:
            self.jobs[job_id] = job
        self.executor.submit(self._run_job, job_id, job_path)
        return job_id

    def get_job(self, job_id: str) -> Job | None:
        """외부 변경을 막기 위해 잡 상태 복사본을 반환한다."""
        with self._lock:
            job = self.jobs.get(job_id)
            return job.model_copy(deep=True) if job is not None else None

    def retry_file(self, job_id: str, file_id: str) -> bool:
        """실패한 파일 한 장의 재시도를 백그라운드에 제출한다."""
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None or job.status is JobStatus.PROCESSING:
                return False
            file_entry = next(
                (item for item in job.files if item.id == file_id),
                None,
            )
            if file_entry is None or file_entry.status is not FileStatus.FAILED:
                return False
            previous_job_status = job.status
            file_entry.status = FileStatus.OCR
            job.status = JobStatus.PROCESSING
            page_number = file_entry.pageNumber

        try:
            self.executor.submit(
                self._run_retry,
                job_id,
                self.jobs_root / job_id,
                page_number,
            )
        except Exception as error:
            with self._lock:
                file_entry.status = FileStatus.FAILED
                file_entry.error = str(error)
                job.status = previous_job_status
            return False
        return True

    def _notify_update(self, job: Job) -> None:
        """파이프라인이 바꾼 잡 상태를 저장한다."""
        with self._lock:
            self.jobs[job.id] = job

    def _run_job(self, job_id: str, job_path: Path) -> None:
        """변환 후 선택적으로 보정 파이프라인을 실행한다."""
        with self._lock:
            job = self.jobs[job_id]
            self.running_count += 1
            job.status = JobStatus.PROCESSING
        self._notify_update(job)

        try:
            asyncio.run(
                run_convert_pipeline(
                    job,
                    job_path,
                    self.storage,
                    self._notify_update,
                )
            )
            if job.status is not JobStatus.FAILED and job.options.correct:
                asyncio.run(
                    run_correct_pipeline(
                        job,
                        job_path,
                        self.storage,
                        self._notify_update,
                    )
                )
        except Exception as error:
            job.status = JobStatus.FAILED
            job.correctionError = str(error)
            self._notify_update(job)
        finally:
            with self._lock:
                self.running_count -= 1

    def _run_retry(
        self,
        job_id: str,
        job_path: Path,
        page_number: int,
    ) -> None:
        """페이지 재시도를 실행하고 잡 전체 상태를 다시 계산한다."""
        with self._lock:
            job = self.jobs[job_id]
        try:
            success = asyncio.run(
                retry_page_pipeline(
                    job,
                    job_path,
                    page_number,
                    self._notify_update,
                )
            )
            job.status = (
                JobStatus.DONE
                if success
                or any(
                    item.status is FileStatus.DONE
                    for item in job.files
                )
                else JobStatus.FAILED
            )
        except Exception as error:
            file_entry = next(
                (
                    item
                    for item in job.files
                    if item.pageNumber == page_number
                ),
                None,
            )
            if file_entry is not None:
                file_entry.status = FileStatus.FAILED
                file_entry.error = str(error)
            job.status = (
                JobStatus.DONE
                if any(
                    item.status is FileStatus.DONE
                    for item in job.files
                )
                else JobStatus.FAILED
            )
        self._notify_update(job)

    def shutdown(self) -> None:
        """새 작업을 막고 실행 중인 워커가 끝날 때까지 기다린다."""
        self.executor.shutdown(wait=True)
