"""Pydantic 스키마 (스펙 7.1 JSON 정의와 일치)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class FileStatus(str, Enum):
    """파일 처리 상태."""

    WAITING = "waiting"
    OCR = "ocr"
    CORRECTING = "correcting"
    DONE = "done"
    FAILED = "failed"


class JobStatus(str, Enum):
    """잡 전체 상태."""

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class PageFile(BaseModel):
    """업로드된 파일 정보."""

    id: str
    filename: str
    pageNumber: int
    sizeBytes: int
    status: FileStatus
    previewText: str | None = None
    error: str | None = None


class JobSummary(BaseModel):
    """잡 요약."""

    successPages: int
    failedPages: int
    removedFooterLines: int
    corrected: int | None = None
    kept: int | None = None
    guardBlocked: int | None = None


class JobOptions(BaseModel):
    """잡 옵션."""

    correct: bool
    backend: str = "codex"
    model: str = "gpt-5.5"


class Job(BaseModel):
    """잡 상태 (폴링용)."""

    id: str
    createdAt: str
    options: JobOptions
    status: JobStatus
    files: list[PageFile]
    summary: JobSummary | None = None
    phase: str = "ocr"
    correction: dict[str, int] | None = None
    correctionError: str | None = None
    correctedStale: bool = False


class PageDetail(BaseModel):
    """페이지 상세 보기."""

    pageNumber: int
    filename: str
    original: str
    corrected: str | None = None


class CreateJobResponse(BaseModel):
    """POST /api/jobs 응답."""

    id: str
