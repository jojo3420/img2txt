"""OCR 전처리 레버 (스펙 6절): 대비 향상 / 해상도 업스케일 / deskew.

설정값은 상수로 고정한다 (재현성). 각 레버는 독립 적용 전제.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

CONTRAST_FACTOR: float = 1.5
UPSCALE_FACTOR: float = 2.0
DESKEW_MAX_DEGREES: float = 3.0
DESKEW_STEP_DEGREES: float = 0.5
# 각도 탐색은 축소본에서 수행 (속도) — 판정 각도만 원본에 적용
DESKEW_SEARCH_WIDTH: int = 500
BINARIZE_THRESHOLD: int = 128
WHITE: int = 255


def _contrast(image: Image.Image) -> Image.Image:
    """대비 향상: 중간 톤을 벌려 글자-배경 경계를 강화한다."""
    return ImageEnhance.Contrast(image).enhance(CONTRAST_FACTOR)


def _upscale(image: Image.Image) -> Image.Image:
    """해상도 업스케일: LANCZOS 보간으로 UPSCALE_FACTOR배 확대."""
    new_size = (int(image.width * UPSCALE_FACTOR), int(image.height * UPSCALE_FACTOR))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _row_variance(image: Image.Image) -> float:
    """이진화된 행 합의 분산 — 텍스트 행이 수평일수록 커진다."""
    binary = image.point(lambda p: 0 if p < BINARIZE_THRESHOLD else 1)
    data = binary.tobytes()
    width, height = binary.size
    rows = [sum(data[y * width : (y + 1) * width]) for y in range(height)]
    mean = sum(rows) / len(rows)
    return sum((r - mean) ** 2 for r in rows) / len(rows)


def estimate_skew_degrees(image: Image.Image) -> float:
    """projection profile로 기울기 각도를 추정한다.

    후보 각도(-DESKEW_MAX~+DESKEW_MAX, DESKEW_STEP 간격)로 회전해 보고
    행 분산이 최대가 되는 각도를 반환한다 (그 각도만큼 회전하면 반듯해짐).
    """
    gray = image.convert("L")
    if gray.width > DESKEW_SEARCH_WIDTH:
        ratio = DESKEW_SEARCH_WIDTH / gray.width
        gray = gray.resize((DESKEW_SEARCH_WIDTH, max(1, int(gray.height * ratio))))

    best_angle = 0.0
    best_score = _row_variance(gray)
    steps = int(DESKEW_MAX_DEGREES / DESKEW_STEP_DEGREES)
    for i in range(-steps, steps + 1):
        angle = i * DESKEW_STEP_DEGREES
        if angle == 0.0:
            continue
        candidate = gray.rotate(angle, expand=False, fillcolor=WHITE)
        score = _row_variance(candidate)
        if score > best_score:
            best_score = score
            best_angle = angle
    return best_angle


def _deskew(image: Image.Image) -> Image.Image:
    """deskew: 추정 각도만큼 회전. 각도 0이면 원본 유지 (글자 잘림 방지)."""
    angle = estimate_skew_degrees(image)
    if angle == 0.0:
        return image
    logger.info("deskew 적용: %.1f도", angle)
    return image.rotate(angle, expand=True, fillcolor=WHITE)


LEVERS: dict[str, Callable[[Image.Image], Image.Image]] = {
    "contrast": _contrast,
    "upscale": _upscale,
    "deskew": _deskew,
}


def apply_lever(lever: str, image_path: Path, work_dir: Path) -> Path:
    """레버를 적용한 이미지를 work_dir에 저장하고 경로를 반환한다.

    Args:
        lever: LEVERS 키 중 하나.
        image_path: 원본 이미지 경로.
        work_dir: 전처리본 저장 디렉터리 (없으면 생성).

    Returns:
        전처리된 이미지 경로 (원본과 같은 파일명).

    Raises:
        ValueError: 미등록 레버.
    """
    if lever not in LEVERS:
        raise ValueError(f"알 수 없는 전처리 레버: {lever} (지원: {sorted(LEVERS)})")
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / image_path.name
    with Image.open(image_path) as image:
        processed = LEVERS[lever](image)
        processed.save(out_path)
    return out_path
