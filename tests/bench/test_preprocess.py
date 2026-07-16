from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from img2txt.bench.preprocess import (
    LEVERS,
    UPSCALE_FACTOR,
    apply_lever,
    estimate_skew_degrees,
)


def _make_striped_image(width: int = 400, height: int = 300) -> Image.Image:
    """가로 검은 줄무늬(텍스트 행 모사) 흰 배경 합성 이미지."""
    image = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(image)
    for top in range(30, height - 30, 40):
        draw.rectangle([20, top, width - 20, top + 12], fill=0)
    return image


def test_levers_registry() -> None:
    """레버 3종이 등록돼 있다."""
    assert set(LEVERS.keys()) == {"contrast", "upscale", "deskew"}


def test_upscale_doubles_size(tmp_path: Path) -> None:
    """upscale: 가로/세로가 UPSCALE_FACTOR배."""
    src = tmp_path / "page_001.png"
    _make_striped_image().save(src)

    out_path = apply_lever("upscale", src, tmp_path / "work")

    with Image.open(out_path) as out:
        assert out.size == (int(400 * UPSCALE_FACTOR), int(300 * UPSCALE_FACTOR))
    assert out_path.parent == tmp_path / "work"


def test_contrast_spreads_midtones(tmp_path: Path) -> None:
    """contrast: 중간 회색 두 값의 간격이 넓어진다."""
    src = tmp_path / "page_001.png"
    image = Image.new("L", (10, 10), color=120)
    image.paste(140, (0, 0, 5, 10))
    image.save(src)

    out_path = apply_lever("contrast", src, tmp_path / "work")

    with Image.open(out_path) as out:
        values = sorted(set(out.tobytes()))
    assert values[-1] - values[0] > 20


def test_estimate_skew_recovers_known_angle() -> None:
    """기울인 줄무늬 이미지에서 각도를 ±0.5도 내로 추정한다."""
    rotated = _make_striped_image().rotate(2.0, expand=True, fillcolor=255)

    estimated = estimate_skew_degrees(rotated)

    assert estimated == pytest.approx(-2.0, abs=0.5)


def test_deskew_keeps_straight_image(tmp_path: Path) -> None:
    """이미 반듯한 이미지는 각도 0 → 원본 그대로 저장."""
    src = tmp_path / "page_001.png"
    straight = _make_striped_image()
    straight.save(src)

    out_path = apply_lever("deskew", src, tmp_path / "work")

    with Image.open(out_path) as out:
        assert out.size == straight.size


def test_unknown_lever_raises(tmp_path: Path) -> None:
    """미등록 레버는 ValueError."""
    src = tmp_path / "page_001.png"
    _make_striped_image().save(src)

    with pytest.raises(ValueError):
        apply_lever("sharpen", src, tmp_path / "work")


def test_deskew_low_confidence_preserves_uniform(tmp_path: Path) -> None:
    """균일 회색 이미지: deskew 저신뢰 → 원본 유지 (각도 0.0)."""
    src = tmp_path / "page_001.png"
    # 균일한 회색 이미지: 회전해도 행 분산 개선율이 5% 미만
    uniform = Image.new("L", (200, 150), color=180)
    uniform.save(src)

    out_path = apply_lever("deskew", src, tmp_path / "work")

    with Image.open(out_path) as out:
        # 원본 유지되므로 크기 동일
        assert out.size == uniform.size


def test_estimate_skew_high_confidence_recovered(tmp_path: Path) -> None:
    """줄무늬 이미지: 기울임 추정 및 회전 적용."""
    rotated = _make_striped_image().rotate(2.0, expand=True, fillcolor=255)

    estimated = estimate_skew_degrees(rotated)

    # 줄무늬는 분산 개선율이 크므로 각도 추정 (0이 아님)
    assert estimated != 0.0
    assert estimated == pytest.approx(-2.0, abs=0.5)
