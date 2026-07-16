from __future__ import annotations

from pathlib import Path
import pytest
import sys
import json

# scripts/bench_ocr.py의 main/argparse를 테스트하기 위해
# 별도 함수로 분리했다고 가정
from scripts.bench_ocr import parse_args, main
from img2txt.ocr import OcrLine, Page


def test_parse_args_basic() -> None:
    """기본 인자 파싱."""
    args = parse_args([
        "/tmp/images",
        "/tmp/labels",
        "-o", "/tmp/report.jsonl",
    ])

    assert str(args.image_dir) == "/tmp/images"
    assert str(args.label_dir) == "/tmp/labels"
    assert str(args.output) == "/tmp/report.jsonl"
    assert args.allow_skip is False
    assert args.limit is None


def test_parse_args_with_options() -> None:
    """옵션 포함."""
    args = parse_args([
        "/tmp/images",
        "/tmp/labels",
        "-o", "/tmp/report.jsonl",
        "--allow-skip",
        "--limit", "10",
    ])

    assert args.allow_skip is True
    assert args.limit == 10


def test_parse_args_missing_required() -> None:
    """필수 인자 누락."""
    with pytest.raises(SystemExit):  # argparse는 오류 시 exit
        parse_args(["/tmp/images"])  # label_dir 누락


def test_cli_integration_basic(tmp_path: Path, monkeypatch) -> None:
    """CLI 통합 테스트: 이미지 1개 처리."""
    # 임시 디렉터리 설정
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()

    # 임시 이미지/라벨
    (image_dir / "page_001.png").touch()
    (label_dir / "page_001.txt").write_text("정답")

    output_path = tmp_path / "report.jsonl"

    # Mock OCR: 고정된 2줄 반환
    def fake_recognize(image: Path, page_num: int) -> Page:
        return Page(
            number=page_num,
            lines=[
                OcrLine(text="첫째 줄", confidence=0.95, x=0.1, y=0.9, width=0.8, height=0.03),
                OcrLine(text="둘째 줄", confidence=0.92, x=0.1, y=0.8, width=0.7, height=0.03),
            ],
        )

    # recognize_page를 교체
    monkeypatch.setattr("scripts.bench_ocr.recognize_page", fake_recognize)

    # main 호출
    ret_code = main([str(image_dir), str(label_dir), "-o", str(output_path)])

    # 검증
    assert ret_code == 0, f"main() 반환값이 0이 아님: {ret_code}"
    assert output_path.exists(), f"리포트 파일이 없음: {output_path}"

    # JSONL 파일 검증
    lines = output_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3, f"레코드 수가 3이 아님: {len(lines)}"

    # 각 레코드 검증
    for i, line in enumerate(lines):
        record = json.loads(line)
        assert record["page_id"] == "page_001", f"page_id 불일치 (라인 {i}): {record['page_id']}"
        expected_points = ["raw", "assembled", "corrected"]
        assert record["point"] in expected_points, f"point 값 불명 (라인 {i}): {record['point']}"
