"""corrector 테스트: 길이 가드(비율+절대 하한), 폴백, 긴 문단 생략, 기록. HTTP는 모킹."""
from img2txt.corrector import (
    CorrectionStatus,
    all_requests_failed,
    correct_paragraphs,
)


def test_normal_correction_applied() -> None:
    fake = lambda base_url, model, paragraph: paragraph.replace("경단로", "결단코")
    results, records = correct_paragraphs(["그는 경단로 다짐했다."], model="m", request=fake)
    assert results == ["그는 결단코 다짐했다."]
    assert records[0].status is CorrectionStatus.CORRECTED


def test_unchanged_paragraph_kept() -> None:
    fake = lambda base_url, model, paragraph: paragraph
    results, records = correct_paragraphs(["오류 없는 문단."], model="m", request=fake)
    assert results == ["오류 없는 문단."]
    assert records[0].status is CorrectionStatus.KEPT


def test_guard_blocks_large_length_change() -> None:
    original = "가" * 100
    fake = lambda base_url, model, paragraph: "가" * 130  # +30% > max(5, 10%)
    results, records = correct_paragraphs([original], model="m", request=fake)
    assert results == [original]
    assert records[0].status is CorrectionStatus.GUARD_BLOCKED


def test_short_paragraph_small_change_allowed_by_absolute_floor() -> None:
    # "20 세기"(5자 문단)에서 공백 1개 제거: 비율 가드(10%=0자)로는 차단되지만 절대 하한 5자 이내 -> 허용
    original = "20 세기"
    fake = lambda base_url, model, paragraph: "20세기"
    results, records = correct_paragraphs([original], model="m", request=fake)
    assert results == ["20세기"]
    assert records[0].status is CorrectionStatus.CORRECTED


def test_request_failure_keeps_original() -> None:
    def broken(base_url: str, model: str, paragraph: str) -> str:
        raise TimeoutError("모의 타임아웃")
    results, records = correct_paragraphs(["원문 유지 문단."], model="m", request=broken)
    assert results == ["원문 유지 문단."]
    assert records[0].status is CorrectionStatus.FAILED


def test_long_paragraph_skipped_without_request() -> None:
    calls: list[str] = []
    def spy(base_url: str, model: str, paragraph: str) -> str:
        calls.append(paragraph)
        return paragraph
    long_paragraph = "가" * 3000
    results, records = correct_paragraphs([long_paragraph], model="m", request=spy)
    assert results == [long_paragraph]
    assert records[0].status is CorrectionStatus.SKIPPED_LONG
    assert calls == []


def test_all_requests_failed_detection() -> None:
    def broken(base_url: str, model: str, paragraph: str) -> str:
        raise ConnectionError("모의 접속 불가")
    _, records = correct_paragraphs(["a", "b"], model="m", request=broken)
    assert all_requests_failed(records) is True
    fake = lambda base_url, model, paragraph: paragraph
    _, ok_records = correct_paragraphs(["a"], model="m", request=fake)
    assert all_requests_failed(ok_records) is False
