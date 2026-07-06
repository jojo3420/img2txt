"""한글 책 스캔 OCR 변환기 (PoC).

책 촬영본 jpg를 Apple Vision OCR(ko-KR)로 읽어
페이지별 txt와 합본 txt를 만든다.
PoC: 경로 하드코딩, 이미지 1장 실패 시 건너뛰고 계속.
"""
import re
from pathlib import Path

from PIL import Image, ImageOps
from ocrmac import ocrmac

INPUT_DIR = Path("/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장")
OUTPUT_DIR = Path(__file__).parent / "output"
PAGES_DIR = OUTPUT_DIR / "pages"


def page_number(path):
    """파일명(확장자 제외)의 마지막 숫자를 반환. 숫자가 없으면 None."""
    numbers = re.findall(r"\d+", path.stem)
    return int(numbers[-1]) if numbers else None


def sort_key(path):
    n = page_number(path)
    if n is None:
        print(f"경고: 파일명에 숫자 없음, 맨 뒤에 배치: {path.name}")
        return (1, 0, path.name)
    return (0, n, path.name)


def ocr_image(path):
    """이미지 1장을 EXIF 회전 반영 후 OCR해서 줄 단위 텍스트로 반환."""
    img = ImageOps.exif_transpose(Image.open(path))
    annotations = ocrmac.OCR(img, language_preference=["ko-KR"]).recognize()
    return "\n".join(text for text, confidence, bbox in annotations)


def main():
    images = sorted(INPUT_DIR.glob("*.jpg"), key=sort_key)
    print(f"대상 이미지: {len(images)}장")
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    book_parts = []
    failed = []
    empty = []
    for i, path in enumerate(images, 1):
        try:
            text = ocr_image(path)
        except Exception as e:
            print(f"[{i}/{len(images)}] 실패: {path.name} ({e})")
            failed.append(path.name)
            continue
        if not text.strip():
            empty.append(path.name)
        (PAGES_DIR / f"{path.stem}.txt").write_text(text, encoding="utf-8")
        book_parts.append(f"===== p.{page_number(path)} =====\n{text}")
        print(f"[{i}/{len(images)}] 완료: {path.name} ({len(text)}자)")

    (OUTPUT_DIR / "book.txt").write_text("\n\n".join(book_parts), encoding="utf-8")
    print(f"결과: 성공 {len(book_parts)}장 / 실패 {len(failed)}장 / 빈 결과 {len(empty)}장")
    if failed:
        print("실패 목록:", ", ".join(failed))
    if empty:
        print("빈 결과 목록:", ", ".join(empty))


if __name__ == "__main__":
    main()
