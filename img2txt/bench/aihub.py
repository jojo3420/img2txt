"""AI Hub 페이지형 공공문서 OCR(dataSetSn=71299) 라벨 어댑터.

라벨 JSON의 Bbox(단어 목록)를 id 오름차순으로 공백 join해 정답 텍스트를
복원한다. 줄바꿈은 복원하지 않는다 — 채점 정규화(normalize_strict)가
공백류를 단일 공백으로 접으므로 CER/WER에 영향이 없다.
"""
from __future__ import annotations

import json
from pathlib import Path


def _validate_bbox(bbox: list, label_path: Path) -> None:
    """Bbox 리스트 검증.

    Args:
        bbox: Bbox 리스트.
        label_path: 라벨 파일 경로 (오류 메시지용).

    Raises:
        ValueError: Bbox가 리스트가 아니거나 entry 형식이 잘못된 경우.
    """
    if not isinstance(bbox, list):
        raise ValueError(f"Bbox는 리스트여야 함 (파일: {label_path})")

    seen_ids = set()
    for entry in bbox:
        if not isinstance(entry, dict):
            raise ValueError(f"Bbox entry는 dict여야 함 (파일: {label_path})")

        if "id" not in entry or "data" not in entry:
            raise ValueError(f"entry에 id/data 필드 누락 (파일: {label_path})")

        entry_id = entry["id"]
        # int 확인, bool 제외 (bool은 int의 서브클래스)
        if not isinstance(entry_id, int) or isinstance(entry_id, bool):
            raise ValueError(
                f"id는 정수여야 함, 받음: {type(entry_id).__name__} (파일: {label_path})"
            )

        if entry_id in seen_ids:
            raise ValueError(f"id 중복: {entry_id} (파일: {label_path})")
        seen_ids.add(entry_id)

        entry_data = entry["data"]
        if not isinstance(entry_data, str):
            raise ValueError(
                f"data는 문자열여야 함, 받음: {type(entry_data).__name__} (파일: {label_path})"
            )


def aihub_label_adapter(label_path: Path) -> str:
    """AI Hub 라벨 JSON에서 정답 텍스트를 복원한다.

    Args:
        label_path: 라벨 JSON 경로.

    Returns:
        Bbox id 오름차순으로 공백 join한 정답 텍스트.

    Raises:
        KeyError: Bbox 키가 없거나 entry에 id/data 필드가 누락된 형식 이상
            라벨 (조기 발견 목적 — 조용한 빈 정답 금지).
        ValueError: Bbox가 리스트가 아니거나, id가 정수가 아니거나, id가
            중복되거나, data가 문자열이 아닌 경우.
    """
    with label_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    bbox = payload["Bbox"]
    _validate_bbox(bbox, label_path)

    words = sorted(bbox, key=lambda entry: entry["id"])
    return " ".join(entry["data"] for entry in words)
