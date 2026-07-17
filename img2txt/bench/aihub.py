"""AI Hub 페이지형 공공문서 OCR(dataSetSn=71299) 라벨 어댑터.

라벨 JSON의 Bbox(단어 목록)를 좌표 읽기순서(위→아래, 행 내 좌→우)로
공백 join해 정답 텍스트를 복원한다. 줄바꿈은 복원하지 않는다 — 채점 정규화(normalize_strict)가
공백류를 단일 공백으로 접으므로 CER/WER에 영향이 없다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median


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

        for axis in ("x", "y"):
            if axis not in entry:
                raise ValueError(f"entry에 {axis} 좌표 누락 (파일: {label_path})")
            coords = entry[axis]
            if not isinstance(coords, list) or not coords:
                raise ValueError(f"{axis}는 비어있지 않은 리스트여야 함 (파일: {label_path})")
            for v in coords:
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise ValueError(f"{axis} 좌표는 숫자여야 함 (파일: {label_path})")
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    raise ValueError(f"{axis} 좌표에 NaN/무한대 (파일: {label_path})")
        if len(entry["x"]) != len(entry["y"]):
            raise ValueError(f"x/y 길이 불일치 (파일: {label_path})")


def aihub_label_adapter(label_path: Path) -> str:
    """AI Hub 라벨 JSON에서 정답 텍스트를 복원한다.

    Args:
        label_path: 라벨 JSON 경로.

    Returns:
        Bbox를 좌표 읽기순서(위→아래, 행 내 좌→우)로 공백 join한 정답 텍스트.

    Raises:
        KeyError: Bbox 키가 없거나 entry에 id/data 필드가 누락된 형식 이상
            라벨 (조기 발견 목적 — 조용한 빈 정답 금지).
        ValueError: Bbox가 리스트가 아니거나, id가 정수가 아니거나, id가
            중복되거나, data가 문자열이 아니거나, x/y 좌표가 누락되거나 형식이 잘못된 경우.
    """
    with label_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    bbox = payload["Bbox"]
    _validate_bbox(bbox, label_path)

    return " ".join(_reading_order_words(bbox))


def _entry_geometry(entry: dict) -> dict:
    """Bbox entry에서 정렬용 좌표 파생."""
    xs, ys = entry["x"], entry["y"]
    y_top, y_bot = min(ys), max(ys)
    return {
        "data": entry["data"],
        "x_left": min(xs),
        "y_center": (y_top + y_bot) / 2,
        "height": y_bot - y_top,
    }


def _group_into_rows(bbox: list) -> tuple[list[list[dict]], float]:
    """Bbox를 읽기순서 행으로 그룹핑. (rows, median_height) 반환.

    rows는 위→아래 정렬된 행 리스트이며 각 행은 x_left 오름차순 정렬됨.
    양수 height가 없으면(퇴화 좌표) y_center→x_left 단순 정렬로 폴백.
    """
    items = [_entry_geometry(e) for e in bbox]
    heights = [it["height"] for it in items if it["height"] > 0]
    med_h = median(heights) if heights else 0.0

    if med_h <= 0:
        items.sort(key=lambda it: (it["y_center"], it["x_left"]))
        return [[it] for it in items], med_h

    tol = med_h * 0.6
    items.sort(key=lambda it: it["y_center"])
    rows: list[list[dict]] = []
    current = [items[0]]
    row_mean = items[0]["y_center"]
    for it in items[1:]:
        if abs(it["y_center"] - row_mean) <= tol:
            current.append(it)
            row_mean = sum(x["y_center"] for x in current) / len(current)
        else:
            rows.append(current)
            current = [it]
            row_mean = it["y_center"]
    rows.append(current)
    for row in rows:
        row.sort(key=lambda it: it["x_left"])
    return rows, med_h


def _reading_order_words(bbox: list) -> list[str]:
    """Bbox를 읽기순서(위→아래, 행 내 좌→우)로 정렬한 단어 리스트."""
    if not bbox:
        return []
    rows, _ = _group_into_rows(bbox)
    return [it["data"] for row in rows for it in row]


def reading_order_diagnostics(label_path: Path) -> dict:
    """읽기순서 재정렬 진단 메타 (오묶음 이상치 추적용, 관측 전용)."""
    with label_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    bbox = payload["Bbox"]
    _validate_bbox(bbox, label_path)
    if not bbox:
        return {"bbox_count": 0, "row_count": 0, "median_height": 0.0, "suspicious_layout_flag": False}
    rows, med_h = _group_into_rows(bbox)
    suspicious = len(rows) <= 2 and len(bbox) >= 12
    return {
        "bbox_count": len(bbox),
        "row_count": len(rows),
        "median_height": float(med_h),
        "suspicious_layout_flag": suspicious,
    }
