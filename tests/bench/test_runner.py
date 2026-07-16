"""파이프라인 러너 테스트 (OCR-레이아웃-조립-보정 3지점 출력)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from img2txt.bench.runner import PointOutputs, run_points
from img2txt.corrector import CorrectionRecord, CorrectionStatus
from img2txt.ocr import OcrLine, Page


class TestRunPoints:
    """run_points() 3지점 출력 검증."""

    def test_run_points_basic_flow(self):
        """기본 흐름: OCR인식 -> 레이아웃 분석 -> 조립 (보정 제외)."""
        # 페이크 OCR: 2줄 반환
        def fake_recognize(image: Path, page_num: int) -> Page:
            return Page(
                number=page_num,
                lines=[
                    OcrLine(text="첫째 줄", confidence=0.95, x=0.1, y=0.9, width=0.8, height=0.03),
                    OcrLine(text="둘째 줄", confidence=0.92, x=0.1, y=0.8, width=0.7, height=0.03),
                ],
            )

        def fake_correct(paragraphs, model, backend):
            return paragraphs, []

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)

        try:
            outputs = run_points(
                image_path=image_path,
                page_id="page_001",
                recognize_fn=fake_recognize,
                correct_fn=fake_correct,
                backend=None,
            )

            assert outputs.page_id == "page_001"
            assert "첫째 줄" in outputs.raw
            assert "둘째 줄" in outputs.raw
            assert outputs.assembled == outputs.corrected  # 보정 없음
            assert not outputs.empty
        finally:
            image_path.unlink(missing_ok=True)

    def test_run_points_with_correction(self):
        """보정 흐름: backend 있을 때 원시 → 조립 → 보정본."""
        correct_fn_called = []

        def fake_recognize(image: Path, page_num: int) -> Page:
            return Page(
                number=page_num,
                lines=[
                    OcrLine(text="원시 텍스트", confidence=0.9, x=0.0, y=0.9, width=0.9, height=0.05),
                ],
            )

        def fake_correct(paragraphs, model, backend):
            correct_fn_called.append(True)
            corrected = ["보정된 텍스트"]
            records = [
                CorrectionRecord(
                    index=0,
                    status=CorrectionStatus.CORRECTED,
                    reason="오타 수정",
                    model=model,
                    before="원시 텍스트",
                    after="보정된 텍스트",
                )
            ]
            return corrected, records

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)

        try:
            # backend가 있으면 correct_fn이 호출됨
            outputs = run_points(
                image_path=image_path,
                page_id="page_002",
                recognize_fn=fake_recognize,
                correct_fn=fake_correct,
                backend="test_backend",
            )

            assert len(correct_fn_called) > 0, "backend가 있으면 correct_fn이 호출되어야 함"
            assert outputs.raw != outputs.corrected
            assert "보정된 텍스트" in outputs.corrected
        finally:
            image_path.unlink(missing_ok=True)

    def test_run_points_empty_page(self):
        """빈 페이지 처리: empty=True, correct_fn 호출 안 함."""
        correct_fn_called = []

        # 빈 Page 반환
        def fake_recognize(image: Path, page_num: int) -> Page:
            return Page(number=page_num, lines=[])

        def fake_correct(paragraphs, model, backend):
            correct_fn_called.append(True)
            return paragraphs, []

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)

        try:
            outputs = run_points(
                image_path=image_path,
                page_id="page_001",
                recognize_fn=fake_recognize,
                correct_fn=fake_correct,
                backend=None,
            )

            assert not outputs.empty  # assembled에 "[페이지 N 누락]"이 있으므로
            assert len(correct_fn_called) == 0, "빈 페이지에서는 correct_fn이 호출되지 않아야 함"
            assert outputs.assembled == outputs.corrected
            assert outputs.segments == []
        finally:
            image_path.unlink(missing_ok=True)

    def test_run_points_segments(self):
        """segments 추출: 조립본의 문단들."""
        def fake_recognize(image: Path, page_num: int) -> Page:
            return Page(
                number=page_num,
                lines=[
                    OcrLine(text="문단 1", confidence=0.95, x=0.1, y=0.9, width=0.8, height=0.03),
                    OcrLine(text="문단 2", confidence=0.92, x=0.1, y=0.5, width=0.7, height=0.03),
                ],
            )

        def fake_correct(paragraphs, model, backend):
            return paragraphs, []

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)

        try:
            outputs = run_points(
                image_path=image_path,
                page_id="page_003",
                recognize_fn=fake_recognize,
                correct_fn=fake_correct,
                backend=None,
            )

            assert len(outputs.segments) > 0
            assert all(isinstance(seg, str) for seg in outputs.segments)
        finally:
            image_path.unlink(missing_ok=True)
    def test_run_points_nonstandard_page_id(self):
        """비표준 page_id 처리: 숫자 없는 경우 및 scan001 형식."""
        def fake_recognize(image: Path, page_num: int) -> Page:
            return Page(
                number=page_num,
                lines=[
                    OcrLine(text="테스트 텍스트", confidence=0.9, x=0.0, y=0.9, width=0.9, height=0.05),
                ],
            )

        def fake_correct(paragraphs, model, backend):
            return paragraphs, []

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image_path = Path(tmp.name)

        try:
            # 비표준 page_id 1: scan001 (숫자 포함)
            outputs1 = run_points(
                image_path=image_path,
                page_id="scan001",
                recognize_fn=fake_recognize,
                correct_fn=fake_correct,
                backend=None,
            )
            assert outputs1.page_id == "scan001"
            assert "테스트 텍스트" in outputs1.raw

            # 비표준 page_id 2: 숫자 없음 (fallback to 0)
            outputs2 = run_points(
                image_path=image_path,
                page_id="no_number",
                recognize_fn=fake_recognize,
                correct_fn=fake_correct,
                backend=None,
            )
            assert outputs2.page_id == "no_number"
            assert "테스트 텍스트" in outputs2.raw
        finally:
            image_path.unlink(missing_ok=True)

