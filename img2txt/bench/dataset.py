from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class PagePair:
    """이미지 + 정답 텍스트 쌍."""

    page_id: str
    image_path: Path
    reference_text: str


def load_pairs(
    image_dir: Path,
    label_dir: Path,
    adapter: Callable[[Path], str],
    allow_skip: bool = False,
) -> list[PagePair]:
    """이미지 디렉터리와 라벨 디렉터리를 매칭해 PagePair 리스트 반환.

    Args:
        image_dir: 이미지 파일 디렉터리.
        label_dir: 라벨 파일 디렉터리.
        adapter: 라벨 파일 경로 → 정답 텍스트 함수.
        allow_skip: True면 라벨 누락 페이지만 건너뛰고 나머지 로드,
                   False면 첫 누락 시 FileNotFoundError (기본).

    Returns:
        매칭된 PagePair 리스트 (page_id 정렬).

    Raises:
        FileNotFoundError: 라벨 파일 누락 (allow_skip=False 시만).
    """
    pairs: list[PagePair] = []

    # 이미지 파일 정렬해서 순회
    image_files = sorted(image_dir.glob("*"))

    for image_path in image_files:
        # 확장자 제외하고 page_id 추출
        page_id = image_path.stem

        # 라벨 파일 찾기: 같은 page_id, 같은 확장자 또는 txt (임시)
        # 실제 AI Hub 어댑터에서 정확한 규칙 확정 필요
        label_candidates = list(label_dir.glob(f"{page_id}.*"))

        if not label_candidates:
            if allow_skip:
                logger.warning(f"라벨 파일 누락: {page_id} (스킵)")
                continue
            else:
                raise FileNotFoundError(f"라벨 파일 누락: {page_id}")

        label_path = label_candidates[0]  # 첫 번째 매칭 파일

        # 어댑터로 라벨 읽기
        reference_text = adapter(label_path)

        pair = PagePair(
            page_id=page_id,
            image_path=image_path,
            reference_text=reference_text,
        )
        pairs.append(pair)

    return pairs
