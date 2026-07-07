"""Apple Vision OCR 래핑: 이미지 1장 -> 위→아래 정렬된 Page."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

OCR_LANGUAGE: str = "ko-KR"


@dataclass(frozen=True)
class OcrLine:
    """OCR로 인식된 한 줄. 좌표는 Vision 정규화 좌표(0~1, 좌하단 원점)."""

    text: str
    confidence: float
    x: float
    y: float
    width: float
    height: float

    @property
    def y_center(self) -> float:
        """줄의 세로 중심 좌표 (좌하단 원점이므로 클수록 위쪽)."""
        return self.y + self.height / 2.0


@dataclass
class Page:
    """책 한 페이지의 OCR 결과."""

    number: int
    lines: list[OcrLine] = field(default_factory=list)


def sort_lines_top_to_bottom(lines: list[OcrLine]) -> list[OcrLine]:
    """줄을 y 중심 내림차순(위→아래)으로 정렬한다. Vision 반환 순서에 의존하지 않는다."""
    return sorted(lines, key=lambda line: line.y_center, reverse=True)


def recognize_page(image_path: Path, page_number: int) -> Page:
    """이미지 1장을 OCR해 위→아래로 정렬된 Page를 반환한다."""
    # ocrmac/PIL은 macOS Vision 의존이라 지연 임포트한다 (correct 전용 환경 보호)
    from ocrmac import ocrmac
    from PIL import Image, ImageOps

    with Image.open(image_path) as image:
        upright = ImageOps.exif_transpose(image)
        annotations = ocrmac.OCR(upright, language_preference=[OCR_LANGUAGE]).recognize()
    lines = [
        OcrLine(text=text, confidence=confidence, x=bx, y=by, width=bw, height=bh)
        for text, confidence, (bx, by, bw, bh) in annotations
    ]
    return Page(number=page_number, lines=sort_lines_top_to_bottom(lines))
