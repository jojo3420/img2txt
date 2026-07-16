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
    assert len(lines) == 4, f"레코드 수가 4이 아님: {len(lines)}"

    # 첫 줄은 메타 레코드
    meta_record = json.loads(lines[0])
    assert meta_record["record_type"] == "run_meta"
    assert meta_record["page_count"] == 1

    # 나머지 3개는 데이터 레코드
    data_records = [json.loads(line) for line in lines[1:]]
    assert len(data_records) == 3

    for i, record in enumerate(data_records):
        assert record["page_id"] == "page_001", f"page_id 불일치 (라인 {i+1}): {record['page_id']}"
        expected_points = ["raw", "assembled", "corrected"]
        assert record["point"] in expected_points, f"point 값 불명 (라인 {i+1}): {record['point']}"


def test_cli_all_pages_fail(tmp_path: Path, monkeypatch) -> None:
    """CLI 전체 실패: 모든 페이지 오류 시 exit 1."""
    # 임시 디렉터리 설정
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()

    # 임시 이미지/라벨
    (image_dir / "page_001.png").touch()
    (label_dir / "page_001.txt").write_text("정답")

    output_path = tmp_path / "report.jsonl"

    # Mock OCR: 항상 예외 던짐
    def failing_recognize(image: Path, page_num: int) -> Page:
        raise RuntimeError("OCR 실패")

    # recognize_page를 교체
    monkeypatch.setattr("scripts.bench_ocr.recognize_page", failing_recognize)

    # main 호출
    ret_code = main([str(image_dir), str(label_dir), "-o", str(output_path)])

    # 검증: 모든 페이지 실패했으므로 exit 1
    assert ret_code == 1, f"main() 반환값이 1이 아님: {ret_code}"


def test_parse_args_preprocess_and_confidence() -> None:
    """--preprocess와 --min-confidence 파싱 + 기본값."""
    args = parse_args([
        "/tmp/images",
        "/tmp/labels",
        "-o", "/tmp/report.jsonl",
        "--preprocess", "upscale",
        "--min-confidence", "0.5",
    ])
    assert args.preprocess == "upscale"
    assert args.min_confidence == 0.5

    defaults = parse_args(["/tmp/images", "/tmp/labels", "-o", "/tmp/report.jsonl"])
    assert defaults.preprocess is None
    assert defaults.min_confidence is None


def test_min_confidence_filters_lines(tmp_path: Path, monkeypatch) -> None:
    """--min-confidence: 임계 미만 confidence 줄이 raw에서 제외된다."""
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()
    (image_dir / "page_001.png").touch()
    (label_dir / "page_001.txt").write_text("정답")
    output_path = tmp_path / "report.jsonl"

    def fake_recognize(image: Path, page_num: int) -> Page:
        return Page(
            number=page_num,
            lines=[
                OcrLine(text="높음", confidence=0.9, x=0.1, y=0.9, width=0.8, height=0.03),
                OcrLine(text="낮음", confidence=0.2, x=0.1, y=0.8, width=0.7, height=0.03),
            ],
        )

    monkeypatch.setattr("scripts.bench_ocr.recognize_page", fake_recognize)

    ret_code = main([
        str(image_dir), str(label_dir), "-o", str(output_path),
        "--min-confidence", "0.5",
    ])

    assert ret_code == 0
    lines = output_path.read_text(encoding="utf-8").strip().split("\n")
    raw_records = [json.loads(l) for l in lines if json.loads(l).get("point") == "raw"]
    assert len(raw_records) == 1
    assert "높음" in raw_records[0]["output_text"]
    assert "낮음" not in raw_records[0]["output_text"]


def test_preprocess_lever_wired(tmp_path: Path, monkeypatch) -> None:
    """--preprocess: recognize가 전처리본 경로(preprocessed/<레버>/)를 받는다."""
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()
    output_path = tmp_path / "report.jsonl"

    from PIL import Image
    Image.new("L", (40, 30), color=255).save(image_dir / "page_001.png")
    (label_dir / "page_001.txt").write_text("정답")

    received: list[Path] = []

    def fake_recognize(image: Path, page_num: int) -> Page:
        received.append(Path(image))
        return Page(
            number=page_num,
            lines=[
                OcrLine(text="본문", confidence=0.9, x=0.1, y=0.9, width=0.8, height=0.03),
            ],
        )

    monkeypatch.setattr("scripts.bench_ocr.recognize_page", fake_recognize)

    ret_code = main([
        str(image_dir), str(label_dir), "-o", str(output_path),
        "--preprocess", "upscale",
    ])

    assert ret_code == 0
    assert len(received) == 1
    assert received[0].parent == output_path.parent / "preprocessed" / "upscale"
    assert received[0].name == "page_001.png"
