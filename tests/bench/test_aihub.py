from __future__ import annotations

import json
from pathlib import Path

import pytest

from img2txt.bench.aihub import aihub_label_adapter, reading_order_diagnostics


def _write_label(path: Path, bbox: list[dict]) -> None:
    payload = {
        "Annotation": {"object_recognition": 1},
        "Bbox": bbox,
        "Dataset": {"identifier": "OCR(public)"},
        "Images": {"identifier": "AF_TEST_0001", "width": 100, "height": 100},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_adapter_reads_top_to_bottom_left_to_right(tmp_path: Path) -> None:
    """id 순서와 무관하게 좌표 읽기순서(위→아래, 행 내 좌→우)로 join."""
    label = tmp_path / "AF_TEST_0001.json"
    # 윗줄(y~0): '창원은'(x=0) '우리의'(x=100) / 아랫줄(y~100): '자랑'(x=0)
    # id는 읽기순서와 어긋나게 부여
    _write_label(label, [
        {"data": "자랑", "id": 1, "x": [0, 0, 90, 90], "y": [100, 150, 100, 150]},
        {"data": "우리의", "id": 2, "x": [100, 100, 190, 190], "y": [0, 50, 0, 50]},
        {"data": "창원은", "id": 3, "x": [0, 0, 90, 90], "y": [0, 50, 0, 50]},
    ])

    assert aihub_label_adapter(label) == "창원은 우리의 자랑"


def test_adapter_empty_bbox_returns_empty(tmp_path: Path) -> None:
    """Bbox가 비면 빈 문자열 (빈 페이지 라벨)."""
    label = tmp_path / "AF_TEST_0002.json"
    _write_label(label, [])

    assert aihub_label_adapter(label) == ""


def test_adapter_missing_bbox_key_raises(tmp_path: Path) -> None:
    """Bbox 키 자체가 없으면 KeyError (형식 이상 조기 발견 — 조용한 빈 정답 금지)."""
    label = tmp_path / "AF_TEST_0003.json"
    label.write_text(json.dumps({"Images": {}}, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(KeyError):
        aihub_label_adapter(label)


@pytest.mark.parametrize("bbox,error_type", [
    # (a) Bbox가 dict인 경우 → ValueError
    ({"not_a_list": True}, ValueError),
    # (b) id가 문자열 "1"인 경우 → ValueError
    ([{"data": "텍스트", "id": "1", "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]}], ValueError),
    # (c) id 중복 → ValueError
    ([
        {"data": "첫째", "id": 1, "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]},
        {"data": "둘째", "id": 1, "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]},
    ], ValueError),
    # (d) data가 숫자인 경우 → ValueError
    ([{"data": 123, "id": 1, "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]}], ValueError),
])
def test_adapter_malformed_bbox_raises(
    tmp_path: Path, bbox: list[dict] | dict, error_type: type
) -> None:
    """Bbox 형식 이상 사항 검증."""
    label = tmp_path / "malformed.json"
    payload = {
        "Annotation": {"object_recognition": 1},
        "Bbox": bbox,
        "Dataset": {"identifier": "OCR(public)"},
        "Images": {"identifier": "AF_TEST_MALFORMED", "width": 100, "height": 100},
    }
    label.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(error_type):
        aihub_label_adapter(label)


def test_adapter_missing_xy_raises(tmp_path: Path) -> None:
    """entry에 x 또는 y 좌표가 없으면 ValueError."""
    label = tmp_path / "missing_xy.json"
    _write_label(label, [
        {"data": "텍스트", "id": 1, "x": [0, 0, 1, 1]},
    ])

    with pytest.raises(ValueError, match="entry에.*y.*누락"):
        aihub_label_adapter(label)


def test_adapter_xy_length_mismatch_raises(tmp_path: Path) -> None:
    """x와 y 길이가 다르면 ValueError."""
    label = tmp_path / "xy_mismatch.json"
    _write_label(label, [
        {"data": "텍스트", "id": 1, "x": [0, 0, 1], "y": [0, 1, 0, 1]},
    ])

    with pytest.raises(ValueError, match="x/y 길이 불일치"):
        aihub_label_adapter(label)


def test_diagnostics_flags_over_merged_layout(tmp_path: Path) -> None:
    """단어 다수가 극소수 행으로 뭉치면 suspicious_layout_flag=True."""
    label = tmp_path / "AF_TEST_DIAG.json"
    # 12개 단어가 전부 같은 y (한 행) → row_count<=2, bbox_count>=12
    bbox = [
        {"data": f"w{i}", "id": i, "x": [i * 10, i * 10, i * 10 + 5, i * 10 + 5], "y": [0, 10, 0, 10]}
        for i in range(1, 13)
    ]
    _write_label(label, bbox)
    diag = reading_order_diagnostics(label)
    assert diag["bbox_count"] == 12
    assert diag["suspicious_layout_flag"] is True
