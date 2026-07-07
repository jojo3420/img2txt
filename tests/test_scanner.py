"""
scanner 모듈 테스트.

이미지 수집, 자연 정렬, 페이지 번호 추출 기능을 검증합니다.
"""

import logging
import re
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from img2txt import scanner


logger = logging.getLogger(__name__)


class TestNaturalSort:
    """자연 정렬(natural sort) 테스트."""

    def test_natural_sort_numeric_sequences(self) -> None:
        """숫자 시퀀스를 자연 정렬해야 한다.

        렉시콘 정렬(lexicographic sort)이 아닌 숫자 기반 정렬으로
        1, 2, 3, ..., 10, 11 순서를 유지해야 합니다.
        """
        paths = [
            Path("page_10.jpg"),
            Path("page_2.jpg"),
            Path("page_1.jpg"),
            Path("page_11.jpg"),
            Path("page_3.jpg"),
        ]
        result = scanner.natural_sort(paths)
        expected = [
            Path("page_1.jpg"),
            Path("page_2.jpg"),
            Path("page_3.jpg"),
            Path("page_10.jpg"),
            Path("page_11.jpg"),
        ]
        assert result == expected

    def test_natural_sort_mixed_prefix_numeric(self) -> None:
        """문자 접두사와 숫자를 혼합한 파일명을 자연 정렬해야 한다."""
        paths = [
            Path("scan_100.jpg"),
            Path("scan_20.jpg"),
            Path("scan_3.jpg"),
            Path("scan_1.jpg"),
        ]
        result = scanner.natural_sort(paths)
        expected = [
            Path("scan_1.jpg"),
            Path("scan_3.jpg"),
            Path("scan_20.jpg"),
            Path("scan_100.jpg"),
        ]
        assert result == expected

    def test_natural_sort_preserves_order_when_equal(self) -> None:
        """같은 숫자를 가진 파일은 안정 정렬으로 렉시콘 순서를 따른다."""
        paths = [
            Path("page_1_b.jpg"),
            Path("page_1_a.jpg"),
            Path("page_2.jpg"),
        ]
        result = scanner.natural_sort(paths)
        # 첫 번째 숫자는 같지만, 다음 문자 '_a' < '_b'이므로
        # page_1_a가 page_1_b 앞에 정렬됨
        expected = [
            Path("page_1_a.jpg"),
            Path("page_1_b.jpg"),
            Path("page_2.jpg"),
        ]
        assert result == expected


class TestExtractPageNumber:
    """페이지 번호 추출 테스트."""

    def test_extract_page_number_from_simple_name(self) -> None:
        """'page_<숫자>.jpg' 형식에서 숫자를 추출해야 한다."""
        path = Path("page_42.jpg")
        result = scanner.extract_page_number(path)
        assert result == 42

    def test_extract_page_number_with_leading_zeros(self) -> None:
        """앞의 영(0)을 가진 숫자를 정수로 반환해야 한다."""
        path = Path("page_007.jpg")
        result = scanner.extract_page_number(path)
        assert result == 7

    def test_extract_page_number_returns_none_if_no_number(self) -> None:
        """파일명에 숫자가 없으면 None을 반환해야 한다."""
        path = Path("no_number.jpg")
        result = scanner.extract_page_number(path)
        assert result is None

    def test_extract_page_number_multiple_numbers_first_one(self) -> None:
        """여러 숫자가 있으면 처음 나오는 것을 반환해야 한다."""
        path = Path("book_001_chapter_02.jpg")
        result = scanner.extract_page_number(path)
        assert result == 1

    def test_extract_page_number_zero(self) -> None:
        """0도 유효한 페이지 번호여야 한다."""
        path = Path("page_0.jpg")
        result = scanner.extract_page_number(path)
        assert result == 0


class TestCollectImages:
    """이미지 수집 테스트."""

    def test_collect_images_finds_jpg_files(self) -> None:
        """디렉토리에서 .jpg 파일을 모두 찾아야 한다."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # jpg 파일 생성
            (tmppath / "page_1.jpg").touch()
            (tmppath / "page_2.jpg").touch()
            # jpeg 파일도 찾아야 함
            (tmppath / "page_3.jpeg").touch()
            # 다른 형식은 무시
            (tmppath / "readme.txt").touch()
            (tmppath / "cover.png").touch()

            result = scanner.collect_images(tmppath)

            # 모든 jpg/jpeg 파일이 포함되어야 함
            assert len(result) == 3
            filenames = {p.name for p in result}
            assert "page_1.jpg" in filenames
            assert "page_2.jpg" in filenames
            assert "page_3.jpeg" in filenames
            assert "readme.txt" not in filenames
            assert "cover.png" not in filenames

    def test_collect_images_is_case_insensitive(self) -> None:
        """파일 확장자 대소문자를 구분하지 않아야 한다."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "page_1.JPG").touch()
            (tmppath / "page_2.Jpg").touch()
            (tmppath / "page_3.JPEG").touch()
            (tmppath / "page_4.JpEg").touch()

            result = scanner.collect_images(tmppath)

            assert len(result) == 4

    def test_collect_images_returns_naturally_sorted_paths(self) -> None:
        """반환 경로는 자연 정렬되어 있어야 한다."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # 비순차적 순서로 파일 생성
            (tmppath / "page_10.jpg").touch()
            (tmppath / "page_2.jpg").touch()
            (tmppath / "page_1.jpg").touch()
            (tmppath / "page_11.jpg").touch()

            result = scanner.collect_images(tmppath)

            # 자연 정렬 순서: 1, 2, 10, 11
            expected_order = [
                Path("page_1.jpg"),
                Path("page_2.jpg"),
                Path("page_10.jpg"),
                Path("page_11.jpg"),
            ]
            result_names = [p.name for p in result]
            expected_names = [p.name for p in expected_order]
            assert result_names == expected_names

    def test_collect_images_empty_directory(self) -> None:
        """이미지가 없는 디렉토리는 빈 리스트를 반환해야 한다."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            result = scanner.collect_images(tmppath)
            assert result == []

    def test_collect_images_nonexistent_directory_raises_error(self) -> None:
        """존재하지 않는 디렉토리는 오류를 발생시켜야 한다."""
        nonexistent = Path("/nonexistent/path/to/directory")
        with pytest.raises(FileNotFoundError):
            scanner.collect_images(nonexistent)
