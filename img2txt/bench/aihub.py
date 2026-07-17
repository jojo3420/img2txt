"""AI Hub 페이지형 공공문서 OCR(dataSetSn=71299) 라벨 어댑터.

라벨 JSON의 Bbox(단어 목록)를 id 오름차순으로 공백 join해 정답 텍스트를
복원한다. 줄바꿈은 복원하지 않는다 — 채점 정규화(normalize_strict)가
공백류를 단일 공백으로 접으므로 CER/WER에 영향이 없다.
"""
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
        KeyError: Bbox 키가 없거나 entry에 id/data 필드가 누락된 형식 이상
            라벨 (조기 발견 목적 — 조용한 빈 정답 금지).
    """
    payload = json.loads(label_path.read_text(encoding="utf-8"))
    words = sorted(payload["Bbox"], key=lambda entry: entry["id"])
    return " ".join(entry["data"] for entry in words)
