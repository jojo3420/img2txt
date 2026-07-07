"""scanner 테스트: 자연 정렬, 확장자 허용 폭, 숫자 없는 파일, 빈 폴더."""
import logging
from pathlib import Path

from img2txt.scanner import collect_images, extract_page_number


def _touch(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(b"")
    return path


def test_natural_sort_2_before_10(tmp_path: Path) -> None:
    _touch(tmp_path, "책 - 10.jpg")
    _touch(tmp_path, "책 - 2.jpg")
    assert [p.name for p in collect_images(tmp_path)] == ["책 - 2.jpg", "책 - 10.jpg"]


def test_uppercase_and_jpeg_collected(tmp_path: Path) -> None:
    _touch(tmp_path, "scan - 4.jpeg")
    _touch(tmp_path, "scan - 3.JPG")
    _touch(tmp_path, "노트.txt")
    assert [p.name for p in collect_images(tmp_path)] == ["scan - 3.JPG", "scan - 4.jpeg"]


def test_file_without_number_goes_last(tmp_path: Path) -> None:
    _touch(tmp_path, "표지.jpg")
    _touch(tmp_path, "책 - 2.jpg")
    assert [p.name for p in collect_images(tmp_path)] == ["책 - 2.jpg", "표지.jpg"]


def test_empty_folder_returns_empty_list(tmp_path: Path) -> None:
    assert collect_images(tmp_path) == []


def test_extract_last_number_with_multiple_numbers() -> None:
    assert extract_page_number(Path("1,2,3장 - 15.jpg")) == 15
    assert extract_page_number(Path("표지.jpg")) is None


def test_warning_logged_for_unnumbered_file(tmp_path: Path, caplog) -> None:
    _touch(tmp_path, "표지.jpg")
    with caplog.at_level(logging.WARNING):
        collect_images(tmp_path)
    assert "표지.jpg" in caplog.text
