"""서버 전역 설정."""
from pathlib import Path

UPLOAD_MAX_BYTES_PER_FILE: int = 20 * 1024 * 1024
UPLOAD_MAX_FILES: int = 100
UPLOAD_MAX_TOTAL_BYTES: int = 500 * 1024 * 1024
MAX_CONCURRENT_JOBS: int = 2
JOBS_ROOT: Path = Path("./jobs")
