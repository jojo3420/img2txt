# T8/T9 안전 재시도 보완 설계

## 목적

웹 서버의 변환 파이프라인(T8)과 잡 워커(T9)를 실제 코드 계약에 맞게 구현한다. 한 페이지 재시도가 기존 페이지 내용을 훼손하거나 `book.txt`를 잘못 덮어쓰지 않아야 한다.

## 확인된 계획서 결함

- 계획서의 `save_uploaded_file(job_id, file_id, filename, data)` 호출은 실제 시그니처 `save_uploaded_file(job_id, filename, data)`와 다르다.
- 계획서의 `_run_retry`는 기존 페이지를 `Page`로 복원할 수 없다. 페이지별 TXT에는 OCR 좌표, 문단 경계, 다음 페이지와의 연결 정보가 없기 때문이다.
- 같은 재시도 `Page` 객체를 모든 페이지 자리에 넣으면 기존 페이지 내용이 사라지고 `book.txt`가 손상된다.
- 단순 문자열 정렬은 `page-10.jpg`를 `page-2.jpg`보다 앞에 둘 수 있다. 기존 `collect_images`의 자연 정렬을 재사용해야 한다.
- 업로드 목록과 자연 정렬 결과를 따로 관리하면 파일 상태와 실제 이미지가 어긋날 수 있다.

## 선택한 방식

페이지별 `PageLayout`을 JSON 보조 파일로 저장한다.

```text
output/
  pages/page-NNN.txt
  layouts/page-NNN.json
  book.txt
```

JSON에는 `number`, `paragraphs`, `first_is_continuation`, `is_empty`, `removed_footer_lines`를 저장한다. `book.txt` 재조립에 필요하지 않은 OCR 좌표와 꼬리말 원문은 저장하지 않는다. 꼬리말 개수는 재시도 뒤 요약 통계를 다시 계산할 때 사용한다.

다른 선택지는 제외한다.

- 전체 페이지 재-OCR: 안전하지만 느리고 “실패 페이지만 재시도” 계약을 지키지 못한다.
- 페이지 TXT에서 복원: 문단 경계와 페이지 연결 정보가 없어 정확한 재조립이 불가능하다.

## T8 변환 흐름

1. `collect_images(uploads_dir)`로 이미지를 자연 정렬한다.
2. 정렬된 이미지와 `job.files`를 같은 순서로 연결한다.
3. 페이지마다 OCR과 `analyze_page`를 실행한다.
4. OCR 실패 시 빈 `PageLayout`을 만들고 파일 상태를 `failed`로 기록한다. 다른 페이지 처리는 계속한다.
5. 페이지 TXT와 레이아웃 JSON을 저장한다.
6. 모든 레이아웃을 `assemble`에 전달해 `book.txt`를 만든다.
7. 성공 수, 실패 수, 제거한 꼬리말 수를 `JobSummary`에 기록한다.
8. 전체 OCR 실패일 때만 잡을 `failed`로 끝낸다. 일부 성공이면 변환 결과를 제공한다.

보정 실패는 이미 만든 변환 결과를 버리지 않는다. `correctionError`에 원인을 기록하고 잡 상태는 `done`으로 유지한다.

## T9 잡 생성과 실행

- `create_job`은 입력 파일을 원본 파일명 숫자 기준으로 먼저 자연 정렬한다.
- 정렬 순서대로 `pageNumber`를 부여한다. 공개 `PageFile.filename`에는 원본 파일명을 보존한다.
- 디스크에는 `upload-<uuid>-page-<순번>.jpg` 형식의 내부 이름으로 저장한다. 이 형식은 중복 원본 파일의 덮어쓰기를 막고 마지막 숫자가 정렬 순번이 되게 한다.
- 업로드 저장은 실제 `JobStorage.save_uploaded_file(job_id, internal_filename, data)` 시그니처를 사용한다.
- `ThreadPoolExecutor(max_workers=max_concurrent)`가 동시 실행 수를 제한한다.
- 워커는 `queued -> processing -> done|failed` 순서로 상태를 바꾼다.
- 상태 변경은 하나의 잠금으로 보호해 `running_count`와 잡 상태가 동시에 갱신될 때의 충돌을 막는다.

## 단일 페이지 재시도

1. 잡과 `file_id`를 확인한다.
2. 대상 파일 상태를 `ocr`로 바꾼다.
3. `pageNumber`에 해당하는 이미지 한 장만 다시 OCR한다.
4. 기존 나머지 레이아웃 JSON을 모두 읽어 메모리에서 `book.txt` 새 내용을 만든다.
5. 새 페이지 TXT, 레이아웃 JSON, `book.txt`를 각각 임시 파일에 쓴다.
6. 기존 세 파일을 백업한 뒤 교체한다. 교체 중 오류가 나면 백업본으로 되돌린다.
7. 전체 과정이 성공한 뒤에만 재시도 성공으로 기록한다.
8. 실패하면 임시 파일을 지우고 기존 페이지, 레이아웃, `book.txt`를 유지한다.
9. `book_corrected.txt`와 `corrections.log`는 수정하지 않는다.

재시도 성공 후 대상 파일의 `error`를 비우고 상태를 `done`으로 바꾼다. 다른 실패 페이지가 남아 있어도 한 장 이상 성공한 잡은 결과를 계속 제공한다.

## 테스트 범위

핵심 서비스만 테스트하며 한 기능당 최대 3개를 넘기지 않는다.

1. 일부 페이지 OCR 실패: 실패 표식을 포함한 `book.txt`를 만들고 다른 페이지는 보존한다.
2. 전체 페이지 OCR 실패: 잡을 `failed`로 끝낸다.
3. 단일 페이지 재시도: 대상 페이지만 바뀌고 기존 페이지와 보정 산출물은 그대로 유지된다.

실제 Apple Vision OCR과 실제 보정 모델 호출은 통합 테스트에서 다루고, 단위 테스트에서는 해당 외부 경계만 대체한다.

## 범위 밖

- 보정본 자동 재생성
- 서버 재시작 뒤 잡 복구
- 데이터베이스 저장
- 여러 프로세스에서 잡 상태 공유
