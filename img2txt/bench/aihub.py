from __future__ import annotations

import json
from pathlib import Path


def aihub_label_adapter(label_path: Path) -> str:
	"""AI Hub 라벨 JSON에서 정답 텍스트를 복원한다.

	Args:
		label_path: 라벨 JSON 경로.

	Returns:
		Bbox id 오름차순으로 공백 join한 정답 텍스트.

	Raises:
		KeyError: Bbox 키가 없는 형식 이상 라벨 (조기 발견 목적).
	"""
	payload = json.loads(label_path.read_text(encoding="utf-8"))
	words = sorted(payload["Bbox"], key=lambda entry: entry["id"])
	return " ".join(entry["data"] for entry in words)
