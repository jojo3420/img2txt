"""파일 저장소: 안전한 파일명, 잡 레이아웃, 스트리밍."""
from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path
from typing import Iterator

from server.config import JOBS_ROOT

logger = logging.getLogger(__name__)
CHUNK_SIZE: int = 64 * 1024

_ALLOWED_EXT: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"})
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(filename: str) -> str:
    """경로 조작을 차단하되 원본 파일명(정렬용 숫자)을 보존한다.

    Args:
        filename: 원본 파일명(신뢰 불가 입력).

    Returns:
        안전한 파일명. 경로 구분자-위험 문자를 제거하고 확장자를 유효 포맷으로 정규화(.jpg/.jpeg/.png/.webp/.tif/.tiff).
        알 수 없는 확장자는 .jpg로 fallback.
    """
    base = os.path.basename(filename.replace("\\", "/"))
    stem, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext not in _ALLOWED_EXT:
        ext = ".jpg"
    stem = _SAFE_CHARS.sub("_", stem).lstrip(".")
    if not stem:
        stem = f"page-{uuid.uuid4().hex[:8]}"
    return f"{stem}{ext}"


def build_job_path(jobs_root: Path, job_id: str) -> Path:
    """잡 경로를 생성한다.

    Args:
        jobs_root: 잡 루트 디렉터리.
        job_id: 잡 ID.

    Returns:
        잡 경로.
    """
    return jobs_root / job_id


def build_file_path(job_path: Path, original_filename: str) -> Path:
    """파일 경로를 생성한다.

    Args:
        job_path: 잡 경로.
        original_filename: 원본 파일명.

    Returns:
        업로드 디렉터리 내 안전한 파일명 경로.
    """
    return job_path / "uploads" / sanitize_filename(original_filename)


def read_text_file(path: Path) -> str:
    """파일을 UTF-8 텍스트로 읽는다.

    Args:
        path: 파일 경로.

    Returns:
        파일 내용.

    Raises:
        FileNotFoundError: 파일이 없는 경우.
    """
    return path.read_text(encoding="utf-8")


def stream_file(path: Path) -> Iterator[bytes]:
    """파일을 청크 단위로 스트리밍한다.

    Args:
        path: 파일 경로.

    Yields:
        파일 청크(바이트).

    Raises:
        FileNotFoundError: 파일이 없는 경우.
    """
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk


class JobStorage:
    """잡별 파일 저장소 관리자."""

    def __init__(self, jobs_root: Path = JOBS_ROOT) -> None:
        """초기화.

        Args:
            jobs_root: 잡 루트 디렉터리 (기본값: config.JOBS_ROOT).
        """
        self.jobs_root: Path = jobs_root

    def create_job_dir(self, job_id: str) -> Path:
        """잡 디렉터리와 업로드 폴더를 생성한다.

        Args:
            job_id: 잡 ID.

        Returns:
            생성된 잡 경로.
        """
        job_path = build_job_path(self.jobs_root, job_id)
        job_path.mkdir(parents=True, exist_ok=True)
        (job_path / "uploads").mkdir(exist_ok=True)
        logger.info("잡 디렉터리 생성: %s", job_path)
        return job_path

    def save_uploaded_file(self, job_id: str, filename: str, data: bytes) -> Path:
        """업로드된 파일을 저장한다.

        Args:
            job_id: 잡 ID.
            filename: 원본 파일명.
            data: 파일 내용(바이트).

        Returns:
            저장된 파일 경로.
        """
        job_path = build_job_path(self.jobs_root, job_id)
        file_path = build_file_path(job_path, filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)
        logger.info("파일 저장: %s (%d bytes)", file_path.name, len(data))
        return file_path

    def read_output_file(self, job_id: str, filename: str) -> str:
        """출력 파일을 읽는다.

        Args:
            job_id: 잡 ID.
            filename: 파일명.

        Returns:
            파일 내용.

        Raises:
            FileNotFoundError: 파일이 없는 경우.
        """
        job_path = build_job_path(self.jobs_root, job_id)
        file_path = job_path / filename
        return read_text_file(file_path)
