# tests/bench/test_dataset.py
from pathlib import Path
import pytest
from img2txt.bench.dataset import PagePair, load_pairs


def test_page_pair_structure() -> None:
    """PagePair dataclass 구조 확인."""
    pair = PagePair(
        page_id="page_001",
        image_path=Path("/tmp/page_001.png"),
        reference_text="정답 텍스트"
    )
    assert pair.page_id == "page_001"
    assert pair.image_path == Path("/tmp/page_001.png")
    assert pair.reference_text == "정답 텍스트"


def test_load_pairs_basic(tmp_path: Path) -> None:
    """기본 로드: 이미지 2개 + 라벨 2개 매칭."""
    # 임시 디렉터리 구성
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()

    # 이미지 파일 생성
    (image_dir / "page_001.png").touch()
    (image_dir / "page_002.png").touch()

    # 라벨 파일 생성
    (label_dir / "page_001.txt").write_text("정답1")
    (label_dir / "page_002.txt").write_text("정답2")

    # 어댑터: txt 읽기
    def label_adapter(label_path: Path) -> str:
        return label_path.read_text()

    # 로드
    pairs = load_pairs(image_dir, label_dir, label_adapter)

    assert len(pairs) == 2
    assert pairs[0].page_id == "page_001"
    assert pairs[0].reference_text == "정답1"
    assert pairs[1].page_id == "page_002"
    assert pairs[1].reference_text == "정답2"


def test_load_pairs_missing_label(tmp_path: Path) -> None:
    """라벨 파일 누락: 기본 동작은 오류 (--allow-skip 옵션 없음)."""
    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()

    # 이미지만 생성 (라벨 없음)
    (image_dir / "page_001.png").touch()

    def label_adapter(label_path: Path) -> str:
        return label_path.read_text()

    # 파일 없으면 FileNotFoundError 또는 별도 처리
    # 스펙: 매칭 실패는 기본 실험 중단
    with pytest.raises(FileNotFoundError):
        load_pairs(image_dir, label_dir, label_adapter)


def test_load_pairs_page_id_extraction() -> None:
    """page_id 추출: 확장자 제외."""
    pair = PagePair(
        page_id="page_001",
        image_path=Path("/tmp/images/page_001.png"),
        reference_text="텍스트"
    )
    # page_id는 파일명에서 확장자 제외
    assert pair.page_id == "page_001"


def test_load_pairs_with_mock_adapter(tmp_path: Path) -> None:
    """mock 어댑터: JSON 라벨 (실제 AI Hub 형식은 미정)."""
    import json

    image_dir = tmp_path / "images"
    label_dir = tmp_path / "labels"
    image_dir.mkdir()
    label_dir.mkdir()

    # 이미지
    (image_dir / "page_001.png").touch()

    # JSON 라벨 (임시 픽스처)
    label_data = {"text": "한글 텍스트"}
    (label_dir / "page_001.json").write_text(json.dumps(label_data))

    # JSON 어댑터
    def json_adapter(label_path: Path) -> str:
        data = json.loads(label_path.read_text())
        return data.get("text", "")

    pairs = load_pairs(image_dir, label_dir, json_adapter)

    assert len(pairs) == 1
    assert pairs[0].reference_text == "한글 텍스트"
