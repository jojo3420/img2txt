# 한글 책 스캔 OCR 변환기 (PoC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 책 촬영본 jpg 31장을 Apple Vision OCR로 읽어 페이지별 txt + 합본 txt를 만들고, 3개 조건으로 PoC 판정을 내린다.

**Architecture:** 단일 스크립트 `ocr_book.py`. 폴더 스캔 → 파일명 마지막 숫자 기준 자연 정렬 → EXIF 회전 반영 후 Apple Vision OCR(한국어) → 페이지별/합본 txt 저장. 실패 이미지는 건너뛰고 로그만 남긴다.

**Tech Stack:** Python 3 (venv), ocrmac (Apple Vision 래퍼), Pillow

## Global Constraints

- 스펙: `docs/superpowers/specs/2026-07-06-korean-ocr-design.md` (듀얼 리뷰 반영본)
- PoC 수준: happy path만, 경로 하드코딩, 테스트/타입 힌트 생략. 단, 이미지 1장 실패 시 "실패 파일명 출력 후 계속"하는 최소 실패 처리는 포함
- 입력: `/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장`의 `*.jpg` (실측 31장, 파일명 마지막 숫자 2~32, 중복 없음)
- OCR 설정: `language_preference=["ko-KR"]`
- 정렬 규칙: 파일명의 **마지막 숫자** 기준 오름차순. 숫자 없으면 경고 출력 후 맨 뒤 배치
- 출력: 프로젝트 루트 기준 `output/pages/<원본파일명(확장자 제외)>.txt` + `output/book.txt` (`===== p.<파일명 숫자> =====` 구분선). 저장 전 디렉터리 생성(`exist_ok=True`)
- PoC 판정 조건 3개: (1) 빈 OCR 결과 0장 (2) 검수 3장(첫 페이지/일반 본문/곡면 왜곡 페이지) 본문 판독 가능 (3) 줄 순서 뒤섞임 없음
- PoC이므로 print 사용 허용 (logging 전환은 정식 구현 항목)
- `output/`과 `.venv/`는 git에 커밋하지 않는다 (추출 텍스트는 개인 이용 한정)

---

### Task 1: 환경 준비와 ocrmac 스모크 테스트

**Files:**
- Create: `.gitignore`
- Create: `.venv/` (커밋 안 함)

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `.venv/bin/python`에 `ocrmac`, `Pillow` 설치된 상태. Task 2가 이 인터프리터로 실행됨

- [ ] **Step 1: venv 생성 및 ocrmac 설치**

Run:
```bash
cd /Users/joel.silver/Workspace/gitroom/python/img2txt
python3 -m venv .venv
.venv/bin/pip install ocrmac
```
Expected: `Successfully installed ocrmac-... pyobjc-... Pillow-...` (pyobjc와 Pillow는 ocrmac 의존성으로 함께 설치됨)

- [ ] **Step 2: .gitignore 작성**

```gitignore
.venv/
output/
__pycache__/
```

- [ ] **Step 3: 스모크 테스트 — 이미지 1장 인식 확인**

Run:
```bash
.venv/bin/python -c "
from ocrmac import ocrmac
path = '/Users/joel.silver/Documents/주식시장을 이긴 전략들/1,2,3장/주식시장을 이긴 전략들 - 10.jpg'
r = ocrmac.OCR(path, language_preference=['ko-KR']).recognize()
print(len(r), '개 텍스트 블록')
for text, conf, bbox in r[:3]:
    print(round(conf, 2), repr(text))
"
```
Expected: 블록 수십 개 출력 + 첫 3줄에 한글 문장(예: "수 있게 되었고, PER, PBR등의...")이 신뢰도(0~1 숫자)와 함께 출력. 여기서 한글이 깨지거나 블록이 0개면 중단하고 보고.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: PoC 환경 준비 (.gitignore)"
```

---

### Task 2: ocr_book.py 구현 및 전체 변환 실행

**Files:**
- Create: `ocr_book.py`

**Interfaces:**
- Consumes: Task 1의 `.venv/bin/python` (ocrmac, Pillow 설치됨)
- Produces: `output/pages/*.txt` 31개 + `output/book.txt`. Task 3이 이 산출물을 검수. 함수: `page_number(path) -> int | None`, `ocr_image(path) -> str`

- [ ] **Step 1: ocr_book.py 작성 (전체 코드)**

```python
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
```

- [ ] **Step 2: 전체 변환 실행**

Run:
```bash
.venv/bin/python ocr_book.py
```
Expected: `대상 이미지: 31장` → 페이지마다 `[N/31] 완료: <파일명> (NNNN자)` 로그 → 마지막에 `결과: 성공 31장 / 실패 0장 / 빈 결과 0장`

- [ ] **Step 3: 산출물 개수와 순서 확인**

Run:
```bash
ls output/pages/*.txt | wc -l
grep -c "^===== p\." output/book.txt
grep "^===== p\." output/book.txt | head -5
```
Expected: `31` / `31` / 구분선이 `p.2, p.3, p.4, p.5, p.6` 순서(오름차순)로 출력. 만약 `p.10`이 `p.2`보다 먼저 나오면 정렬 버그이므로 중단하고 보고.

- [ ] **Step 4: Commit**

```bash
git add ocr_book.py
git commit -m "feat: 한글 책 스캔 OCR 변환기 PoC 스크립트"
```

---

### Task 3: PoC 검증 (판정 1개)

**Files:**
- 검수 대상: `output/pages/*.txt`, `output/book.txt` (수정 없음)
- Modify(조건부): `ocr_book.py` — 조건 3 실패 시에만 Y좌표 정렬 추가

**Interfaces:**
- Consumes: Task 2의 output 산출물과 실행 로그 요약(`결과: 성공 N / 실패 N / 빈 결과 N`)
- Produces: PoC 판정(통과/미흡) 보고. 코드 산출물 없음

- [ ] **Step 1: 조건 1 확인 — 빈 OCR 결과 0장**

Run:
```bash
find output/pages -name "*.txt" -size -50c
```
Expected: 출력 없음(50바이트 미만 파일 없음). Task 2 실행 로그의 `빈 결과 0장`과 교차 확인. 빈 파일이 있으면 조건 1 실패.

- [ ] **Step 2: 조건 2-3 확인 — 검수 3장 원본 대조**

검수 3장은 스펙 4절 기준으로 선정한다:
- 첫 페이지: 파일명 숫자 2인 파일
- 일반 본문: 파일명 숫자 10인 파일 (브레인스토밍에서 이미 원본 확인한 페이지)
- 곡면 왜곡 페이지: 원본 이미지를 훑어 오른쪽 가장자리 휘어짐이 가장 큰 파일 1개 선택

각 검수 페이지에 대해: 원본 jpg를 열어 보고(Read 도구) 해당 `output/pages/<이름>.txt`와 대조한다.
- 조건 2: 본문 문장이 흐름을 따라 판독 가능한가 (곡면 왜곡부 포함)
- 조건 3: txt의 줄 순서가 원본의 위→아래 순서와 일치하는가

- [ ] **Step 3(조건부): 조건 3만 실패한 경우 — Y좌표 정렬 헬퍼 추가**

`ocr_book.py`의 `ocr_image`를 아래로 교체 후 Task 2의 Step 2~3 재실행:

```python
def ocr_image(path):
    """이미지 1장을 EXIF 회전 반영 후 OCR해서 줄 단위 텍스트로 반환.

    Vision 좌표계는 좌하단 원점이므로 y가 클수록 위쪽 줄이다.
    """
    img = ImageOps.exif_transpose(Image.open(path))
    annotations = ocrmac.OCR(img, language_preference=["ko-KR"]).recognize()
    annotations.sort(key=lambda a: -a[2][1])
    return "\n".join(text for text, confidence, bbox in annotations)
```

재실행 후에도 실패하거나 한자/혼합 레이아웃 문제가 보이면 livetext 백엔드를 시도한다
(`ocrmac.OCR(img, language_preference=["ko-KR"], framework="livetext")`).
그래도 미흡하면 중단하고 "PaddleOCR 비교 재검토" 판정으로 보고한다.

수정이 발생한 경우에만 Commit:
```bash
git add ocr_book.py
git commit -m "fix: 텍스트 블록 Y좌표 정렬 추가"
```

- [ ] **Step 4: 판정 보고**

사용자에게 판정 1개를 보고한다:
- **통과**: 조건 1-2-3 충족 근거(빈 결과 0장 로그, 검수 3장 파일명과 대조 결과)와 함께 "PoC 통과 — 정식 구현 여부 결정 요청"
- **미흡**: 실패한 조건, 증거(해당 페이지 원본/txt 대조 내용), "PaddleOCR 비교 재검토" 권고
