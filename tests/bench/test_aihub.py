from __future__ import annotations

import json
from pathlib import Path

import pytest

from img2txt.bench.aihub import aihub_label_adapter


def _write_label(path: Path, bbox: list[dict]) -> None:
	payload = {
		"Annotation": {"object_recognition": 1},
		"Bbox": bbox,
		"Dataset": {"identifier": "OCR(public)"},
		"Images": {"identifier": "AF_TEST_0001", "width": 100, "height": 100},
	}
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_adapter_joins_words_in_id_order(tmp_path: Path) -> None:
	"""Bbox를 id 오름차순으로 공백 join한다 (원본 순서가 뒤섞여도)."""
	label = tmp_path / "AF_TEST_0001.json"
	_write_label(label, [
		{"data": "우리의", "id": 2, "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]},
		{"data": "창원은", "id": 1, "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]},
		{"data": "자랑", "id": 3, "x": [0, 0, 1, 1], "y": [0, 1, 0, 1]},
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
