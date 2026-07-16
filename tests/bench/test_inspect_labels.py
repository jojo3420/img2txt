from __future__ import annotations

import json
from pathlib import Path

from scripts.inspect_labels import inspect_dir


def test_inspect_json_labels(tmp_path: Path) -> None:
	"""JSON 라벨: 확장자 분포와 최상위 키를 보고한다."""
	(tmp_path / "page_001.json").write_text(
		json.dumps({"images": [], "annotations": [{"text": "가나다"}]}, ensure_ascii=False),
		encoding="utf-8",
	)
	(tmp_path / "page_002.json").write_text(
		json.dumps({"images": [], "annotations": []}, ensure_ascii=False),
		encoding="utf-8",
	)

	result = inspect_dir(tmp_path)

	assert result["total_files"] == 2
	assert result["extension_counts"] == {".json": 2}
	assert result["samples"][0]["kind"] == "json"
	assert set(result["samples"][0]["top_level_keys"]) == {"images", "annotations"}


def test_inspect_text_labels(tmp_path: Path) -> None:
	"""텍스트 라벨: kind=text, preview에 본문 앞부분이 담긴다."""
	(tmp_path / "page_001.txt").write_text("정답 텍스트입니다", encoding="utf-8")

	result = inspect_dir(tmp_path)

	assert result["extension_counts"] == {".txt": 1}
	assert result["samples"][0]["kind"] == "text"
	assert "정답 텍스트" in result["samples"][0]["preview"]


def test_inspect_sample_count_limit(tmp_path: Path) -> None:
	"""샘플은 sample_count개까지만 수집한다."""
	for i in range(5):
		(tmp_path / f"page_{i:03d}.txt").write_text(f"본문 {i}", encoding="utf-8")

	result = inspect_dir(tmp_path, sample_count=2)

	assert result["total_files"] == 5
	assert len(result["samples"]) == 2


def test_inspect_invalid_json(tmp_path: Path) -> None:
	"""손상 JSON: kind=invalid_json, top_level_keys=None."""
	(tmp_path / "page_001.json").write_text("{broken", encoding="utf-8")

	result = inspect_dir(tmp_path)

	assert result["total_files"] == 1
	assert result["samples"][0]["kind"] == "invalid_json"
	assert result["samples"][0]["top_level_keys"] is None
	assert "{broken" in result["samples"][0]["preview"]
