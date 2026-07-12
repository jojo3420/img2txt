"""다운로드 파일명 헬퍼."""
from urllib.parse import quote

from server.models import Job


_KIND_SUFFIX = {
    "book": "book",
    "corrected": "book_corrected",
    "corrections": "corrections_log",
}


def _safe_stem(filename: str) -> str:
    """파일명에서 확장자를 제거하고 특수문자를 언더스코어로 치환.

    Args:
        filename: 원본 파일명 (예: "scan.jpg")

    Returns:
        안전한 stem (예: "scan")
    """
    # 확장자 제거
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    # 공백, 슬래시 등 위험 문자를 언더스코어로
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
    return safe


def download_name(job: Job, kind: str, page: int | None = None) -> str:
    """다운로드 파일명 생성.

    Args:
        job: Job 인스턴스
        kind: 파일 종류 ("page", "book", "corrected", "corrections")
        page: kind="page"일 때 페이지 번호

    Returns:
        파일명 (예: "2026-07-12-scan-1.txt")

    Raises:
        ValueError: kind가 미지원일 때
    """
    date = job.createdAt[:10]
    first_stem = _safe_stem(job.files[0].filename)

    if kind == "page":
        # kind="page"일 때는 page 파라미터 필수
        return f"{date}-{first_stem}-{page}.txt"

    if kind in _KIND_SUFFIX:
        return f"{date}-{first_stem}-{_KIND_SUFFIX[kind]}.txt"

    raise ValueError(f"unknown kind: {kind}")


def content_disposition(name: str) -> str:
    """Content-Disposition 헤더 값 생성.

    RFC 5987을 준수하여 ASCII filename과 UTF-8 인코딩된 filename*를 모두 포함.

    Args:
        name: 파일명 (한글 포함 가능)

    Returns:
        Content-Disposition 헤더 값
    """
    # ASCII 폴백 (한글 제거됨)
    ascii_name = name.encode("ascii", "replace").decode("ascii").replace('"', "")

    # UTF-8 인코딩 (RFC 5987 format)
    utf8_name = quote(name.encode("utf-8"), safe="")

    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'
