from __future__ import annotations

from pathlib import Path
import json
import pytest
from img2txt.bench.report import PageRecord, write_jsonl, summarize, build_run_meta


def _rec(point, ref, out, **kw):
    return PageRecord(
        page_id=kw.get("page_id", "p1"),
        point=point,
        reference_text=ref,
        output_text=out,
        normalized_ref=ref,
        normalized_output=out,
        cer_strict=kw.get("cer_strict", 0.0),
        cer_lenient=0.0,
        wer=0.0,
        processing_time_ms=0.0,
        empty=kw.get("empty", False),
        error_status="",
        char_miss_rate=kw.get("char_miss_rate", 0.0),
        char_extra_rate=kw.get("char_extra_rate", 0.0),
        empty_ref_with_output=kw.get("empty_ref_with_output", False),
        empty_ref_extra_chars=kw.get("empty_ref_extra_chars", 0),
    )


def test_page_record_structure() -> None:
    """PageRecord 필드 확인."""
    record = PageRecord(
        page_id="page_001",
        point="raw",
        reference_text="정답",
        output_text="출력",
        normalized_ref="정답",
        normalized_output="출력",
        cer_strict=0.1,
        cer_lenient=0.05,
        wer=0.2,
        processing_time_ms=150.5,
        empty=False,
        error_status="",
    )
    assert record.page_id == "page_001"
    assert record.cer_strict == 0.1


def test_write_jsonl_basic(tmp_path: Path) -> None:
    """JSONL 저장: 2개 레코드."""
    output_path = tmp_path / "report.jsonl"

    records = [
        PageRecord(
            page_id="page_001",
            point="raw",
            reference_text="정답1",
            output_text="출력1",
            normalized_ref="정답1",
            normalized_output="출력1",
            cer_strict=0.1,
            cer_lenient=0.05,
            wer=0.2,
            processing_time_ms=100.0,
            empty=False,
            error_status="",
        ),
        PageRecord(
            page_id="page_002",
            point="assembled",
            reference_text="정답2",
            output_text="출력2",
            normalized_ref="정답2",
            normalized_output="출력2",
            cer_strict=0.2,
            cer_lenient=0.1,
            wer=0.3,
            processing_time_ms=150.0,
            empty=False,
            error_status="",
        ),
    ]

    write_jsonl(records, output_path)

    # 파일 읽기 확인
    with open(output_path) as f:
        lines = f.readlines()

    assert len(lines) == 2
    record1 = json.loads(lines[0])
    assert record1["page_id"] == "page_001"
    assert record1["cer_strict"] == 0.1


def test_summarize_basic() -> None:
    """요약: 지점별 micro CER/WER."""
    records = [
        PageRecord(
            page_id="page_001",
            point="raw",
            reference_text="hello world",  # 11자
            output_text="hallo world",     # 1 오류
            normalized_ref="hello world",
            normalized_output="hallo world",
            cer_strict=1.0 / 11,
            cer_lenient=1.0 / 11,
            wer=1.0 / 2,
            processing_time_ms=100.0,
            empty=False,
            error_status="",
        ),
        PageRecord(
            page_id="page_002",
            point="raw",
            reference_text="hello world",  # 11자
            output_text="hello world",     # 0 오류
            normalized_ref="hello world",
            normalized_output="hello world",
            cer_strict=0.0,
            cer_lenient=0.0,
            wer=0.0,
            processing_time_ms=150.0,
            empty=False,
            error_status="",
        ),
    ]

    summary = summarize(records)

    # 지점별 micro CER = (1+0) / (11+11) = 1/22
    assert "points" in summary
    assert "raw" in summary["points"]
    assert abs(summary["points"]["raw"]["cer_strict"] - 1.0 / 22) < 0.001


def test_summarize_with_empty_page() -> None:
    """요약: 빈 결과 페이지 플래그."""
    records = [
        PageRecord(
            page_id="page_001",
            point="raw",
            reference_text="hello",
            output_text="",
            normalized_ref="hello",
            normalized_output="",
            cer_strict=1.0,
            cer_lenient=1.0,
            wer=1.0,
            processing_time_ms=100.0,
            empty=True,  # 빈 결과
            error_status="",
        ),
    ]

    summary = summarize(records)

    assert summary["empty_page_count"] == 1
    assert summary["empty_page_ratio"] == 1.0


def test_summarize_side_effects() -> None:
    """요약: 부작용 지표 (악화 페이지)."""
    records = [
        # 보정 후 악화: assembled CER 0.1 < corrected CER 0.2
        PageRecord(
            page_id="page_001",
            point="assembled",
            reference_text="hello world",
            output_text="hallo world",
            normalized_ref="hello world",
            normalized_output="hallo world",
            cer_strict=0.1,
            cer_lenient=0.1,
            wer=0.1,
            processing_time_ms=100.0,
            empty=False,
            error_status="",
        ),
        PageRecord(
            page_id="page_001",
            point="corrected",
            reference_text="hello world",
            output_text="xello world",  # 더 나쁨
            normalized_ref="hello world",
            normalized_output="xello world",
            cer_strict=0.2,
            cer_lenient=0.2,
            wer=0.2,
            processing_time_ms=150.0,
            empty=False,
            error_status="",
        ),
    ]

    summary = summarize(records)

    # 악화 페이지: assembled 0.1 < corrected 0.2
    assert summary["degraded_page_count"] == 1


def test_build_run_meta_fields(tmp_path: Path) -> None:
    """실행 메타: 필수 필드와 record_type 마커."""
    (tmp_path / "page_001.png").write_bytes(b"fake")

    meta = build_run_meta(
        image_dir=tmp_path, page_count=1, preprocess="upscale", min_confidence=0.5
    )

    assert meta["record_type"] == "run_meta"
    assert meta["page_count"] == 1
    assert meta["preprocess"] == "upscale"
    assert meta["preprocess_config"] == {"upscale_factor": 2.0}
    assert meta["min_confidence"] == 0.5
    assert len(meta["dataset_hash"]) == 32
    assert meta["python_version"].startswith("3.")


def test_write_jsonl_with_run_meta(tmp_path: Path) -> None:
    """run_meta가 있으면 JSONL 첫 줄이 메타 레코드다."""
    record = PageRecord(
        page_id="page_001",
        point="raw",
        reference_text="정답",
        output_text="정딥",
        normalized_ref="정답",
        normalized_output="정딥",
        cer_strict=0.5,
        cer_lenient=0.5,
        wer=1.0,
        processing_time_ms=10.0,
        empty=False,
        error_status="",
    )
    output = tmp_path / "report.jsonl"

    write_jsonl([record], output, run_meta={"record_type": "run_meta", "run_id": "r1"})

    lines = output.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["record_type"] == "run_meta"
    assert json.loads(lines[1])["page_id"] == "page_001"


def test_summarize_micro_miss_extra_rate() -> None:
    """요약: micro miss/extra rate 집계."""
    records = [
        _rec("raw", "abcd", "bcd"),     # miss=1(a), extra=0, total=4 -> 1/4 miss
        _rec("raw", "hello", "hllo"),   # miss=1(e), extra=0, total=5 -> 1/5 miss
        _rec("raw", "xyz", "xyzw"),     # miss=0, extra=1(w), total=3 -> 0 miss, 1/3 extra
        _rec("raw", "test", "test"),    # miss=0, extra=0, total=4 -> 0
    ]
    summary = summarize(records)
    # total_miss = 1 + 1 + 0 + 0 = 2
    # total_extra = 0 + 0 + 1 + 0 = 1
    # total_ref = 4 + 5 + 3 + 4 = 16
    # micro_miss = 2 / 16 = 1/8
    # micro_extra = 1 / 16
    assert summary["points"]["raw"]["char_miss_rate"] == pytest.approx(1 / 8, abs=1e-6)
    assert summary["points"]["raw"]["char_extra_rate"] == pytest.approx(1 / 16, abs=1e-6)


def test_summarize_counts_empty_ref_hallucination() -> None:
    """요약: 빈정답 환각 페이지 수 (empty_ref_with_output 필드 기반)."""
    records = [
        _rec("raw", "", "out1", empty_ref_with_output=True, empty_ref_extra_chars=4),
        _rec("raw", "", ""),
        _rec("raw", "abc", "xyz"),
    ]
    summary = summarize(records)
    # empty_ref_with_output=True인 첫 레코드만 카운트
    assert summary["points"]["raw"]["empty_ref_hallucination_count"] == 1
