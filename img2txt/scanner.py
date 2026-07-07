"""
이미지 파일 수집 및 자연 정렬 모듈.

책 페이지 이미지를 디렉토리에서 수집하고,
사람이 기대하는 순서(자연 정렬)로 정렬합니다.
"""

import logging
import re
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


def natural_sort(paths: Sequence[Path]) -> list[Path]:
    """경로를 자연 정렬(natural sort)한다.

    자연 정렬은 숫자를 숫자로 인식하여 정렬하므로,
    'page_2.jpg' < 'page_10.jpg' (렉시콘 정렬과 반대).

    Args:
        paths: 정렬할 Path 객체들의 시퀀스.

    Returns:
        자연 정렬된 Path 리스트.
    """

    def extract_sort_key(path: Path) -> tuple:
        """경로의 파일명에서 숫자와 문자를 분리하여 정렬 키를 생성한다.

        예: 'page_001_v2.jpg' -> ('page_', 1, '_v', 2, '.jpg')
        숫자 부분은 정수로 변환하여 숫자 정렬이 가능하게 함.
        """
        filename = path.name
        # 연속된 숫자와 숫자가 아닌 부분으로 분리
        parts = re.split(r'(\d+)', filename)
        # 숫자 부분은 int로 변환하여 정렬 가능하게 함
        key: list = []
        for part in parts:
            if part.isdigit():
                key.append(int(part))
            else:
                key.append(part)
        return tuple(key)

    # 안정 정렬(stable sort)을 사용하여 같은 키를 가진 항목의 원래 순서 유지
    return sorted(paths, key=extract_sort_key)


def extract_page_number(path: Path) -> int | None:
    """파일명에서 첫 번째로 나오는 숫자를 페이지 번호로 추출한다.

    파일명에 숫자가 없으면 None을 반환합니다.

    Args:
        path: 페이지 번호를 추출할 파일 경로.

    Returns:
        추출한 페이지 번호(정수), 또는 숫자가 없으면 None.
        앞의 영(0)은 자동으로 제거됨 (007 -> 7).
    """
    filename = path.name
    match = re.search(r'\d+', filename)
    if match:
        return int(match.group(0))
    return None


def collect_images(input_dir: Path) -> list[Path]:
    """디렉토리에서 jpg/jpeg 이미지 파일을 수집한다.

    대소문자 구분 없이 .jpg/.JPG/.jpeg/.JPEG 등을 모두 찾습니다.
    반환되는 경로는 자연 정렬되어 있습니다.

    Args:
        input_dir: 이미지를 수집할 디렉토리 경로.

    Returns:
        자연 정렬된 이미지 파일 경로 리스트.

    Raises:
        FileNotFoundError: input_dir이 존재하지 않으면 발생.
    """
    if not input_dir.exists():
        raise FileNotFoundError(f"디렉토리가 존재하지 않음: {input_dir}")

    # jpg/jpeg 파일 찾기 (대소문자 구분 없음)
    # 모든 파일을 스캔하고 확장자를 소문자로 변환하여 비교
    images: list[Path] = []
    for file_path in input_dir.iterdir():
        if file_path.is_file():
            suffix = file_path.suffix.lower()
            if suffix in ['.jpg', '.jpeg']:
                images.append(file_path)

    # 자연 정렬
    return natural_sort(images)
