"""캘리브레이션용 좌표 덤프: 이미지들의 줄별 텍스트와 좌표를 표로 출력한다."""
from __future__ import annotations

import sys
from pathlib import Path

from img2txt.ocr import recognize_page


def main() -> None:
    """인자로 받은 이미지 각각의 줄 좌표를 위→아래 순서로 출력한다."""
    for argument in sys.argv[1:]:
        path = Path(argument)
        page = recognize_page(path, 0)
        print(f"===== {path.name} =====")
        for line in page.lines:
            print(
                f"yc={line.y_center:.3f} x={line.x:.3f} "
                f"w={line.width:.3f} h={line.height:.3f} | {line.text[:40]}"
            )


if __name__ == "__main__":
    main()
