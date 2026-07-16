from __future__ import annotations

from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock
import sys
import json

# scripts/bench_ocr.py의 main/argparse를 테스트하기 위해
# 별도 함수로 분리했다고 가정
from scripts.bench_ocr import parse_args


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


def test_cli_integration_basic(tmp_path: Path) -> None:
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

    # 실제 main 함수 호출 (mock OCR)
    # 이 부분은 구현 후 실제 하네스로 테스트
    # 여기서는 argparse만 테스트하는 것이 기본 범위
