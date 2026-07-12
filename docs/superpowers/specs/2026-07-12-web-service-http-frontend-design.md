# img2txt 웹서비스 HTTP 계층 + 프런트 연결 구현 설계

- 작성일: 2026-07-12
- 상태: 사용자 승인됨 (브레인스토밍 완료, Codex 리뷰 반영)
- 선행: `docs/superpowers/specs/2026-07-08-img2txt-web-service-design.md` (상위 설계, 승인됨)
- 리뷰: `docs/review/review-result-20260712-114556.md` (Codex xhigh + Claude 크로스 리뷰)
- 목적: 이미 구현-테스트된 백엔드 코어(`img2txt/backends`, `corrector`, `server/{config,models,storage,jobs,pipeline}`)에 HTTP API 계층과 프런트 연결을 얹어, 브라우저에서 이미지 업로드부터 OCR + 보정, 텍스트 다운로드까지 end-to-end로 동작하는 단일 프로세스 개인 웹서비스를 완성한다.

## 1. 범위

이번 세션에서 만드는 것:
- HTTP API 계층: `server/app.py`(FastAPI 앱) + `server/routes.py`(엔드포인트).
- 단일 프로세스 단일 URL 실행: FastAPI가 `/api`와 빌드된 프런트를 한 포트에서 서빙.
- 결과 파일명 규칙(다운로드 시 이름).
- 프런트 프로토타입의 실제 백엔드 연결(MSW 제거).
- API 계약 테스트(FastAPI `TestClient`).

이번 범위 밖(다음 세션):
- 배치 크기-동시성 캘리브레이션(상위 문서 4.2/4.3).
- 상용 백엔드 보정 품질 게이트.
- 잡 메타데이터 영속화(서버 재시작 후 과거 잡 조회는 계속 불가).

## 2. 확정된 결정사항

| 항목 | 결정 | 근거 |
|------|------|------|
| 실행 모델 | 단일 프로세스-단일 URL. FastAPI가 `/api`와 빌드된 프런트(`dist/`)를 `localhost:8000` 한 포트에서 서빙 | 개인용이라 명령 하나로 실행-주소 하나로 사용. 같은 출처라 CORS(교차 출처 허용) 불필요 |
| 실행 대 개발 분리 | 실행/사용은 same-origin(빌드 서빙), 프런트 개발 반복은 `npm run dev`(vite 개발 서버 :5173) + `/api` proxy로 `localhost:8000` 연결 | 단일 명령은 "사용" 모델이고, 화면 코드 반복 수정에는 핫리로드가 필요. 둘을 분리해 모두 만족 |
| 프런트 연결 | 실행 시 same-origin `/api`, MSW(Mock Service Worker) 제거, `npm run build` 산출물 서빙 | 단일 URL 결정의 귀결 |
| 결과 파일명 | `{실행일자}-{원본파일명}-{순번}.{확장자}` 형식, 다운로드 응답 헤더로만 적용 | 사용자 지정. 디스크 저장명은 상위 문서대로 안전한 내부 이름 유지 |
| 의존성 | `pyproject.toml`에 `fastapi`, `uvicorn[standard]`, `python-multipart` 추가 | 멀티파트 업로드 파싱에 `python-multipart` 필수 |

## 3. 아키텍처

### 3.1 신규 모듈

- `server/app.py`: `create_app() -> FastAPI`. `/api` 라우터 등록, 빌드된 프런트 정적 서빙 + SPA 폴백, lifespan(수명주기)으로 단일 `JobStore` 생성 후 `app.state.job_store`에 보관, 종료 시 `shutdown()`. `app = create_app()`로 `uvicorn server.app:app` 대상 노출.
- `server/routes.py`: `APIRouter(prefix="/api")` + 엔드포인트. `JobStore`는 FastAPI 의존성으로 `request.app.state.job_store`를 주입받아 접근한다(테스트에서 임시 `JOBS_ROOT`를 쓴 `JobStore`로 교체 가능). 기존 `JobStore`/`JobStorage`/스키마에 얇게 위임.
- `server/naming.py`: 다운로드 파일명 생성 헬퍼 1개(5절). storage에 두지 않고 분리해 단일 책임 유지.

### 3.2 실행 흐름

1. 사용자가 프런트를 1회 빌드(`npm run build` → `dist/`).
2. `uvicorn server.app:app` 실행 → `localhost:8000` 접속 시 SPA 로드.
3. SPA가 same-origin `/api/*` 호출 → routes가 처리.
4. `JobStore`는 앱 lifespan 동안 단일 인스턴스. 앱 종료 시 `JobStore.shutdown()`으로 스레드풀 정리.

### 3.3 정적 서빙과 SPA 폴백

- `/api/*`는 API 라우터가 우선 처리.
- 그 외 경로: `dist/`에 해당 파일이 있으면 그 정적 자산을 반환.
- 파일이 없을 때: 경로에 파일 확장자가 있으면(예: `.js`, `.css`, `.png` 자산 요청) 404로 응답하고, 확장자가 없는 화면 경로(예: `/jobs/abc`)만 `index.html`로 폴백한다(React Router 클라이언트 라우팅용). 존재하지 않는 자산까지 `index.html`로 덮으면 오류 원인 추적이 어려워지므로 구분한다.
- `dist/`가 없으면 기동 시 경고 로그로 빌드 필요를 안내한다. API는 정상 동작하고, 루트 접속만 안내 문구를 반환한다(기동 실패로 처리하지 않음 — 개인용 편의).

## 4. 엔드포인트 계약

상위 문서 section 7 계약을 그대로 구현하고, 기존 심볼에 위임한다. 모든 잡 옵션-상태 스키마는 `server/models.py`를 재사용한다.

| 메서드 - 경로 | 동작 | 위임 대상 | 성공 |
|---|---|---|---|
| `POST /api/jobs` (multipart) | 업로드 검증 → 잡 생성-백그라운드 시작 | `JobStore.create_job(files, options)` | 201 `CreateJobResponse` |
| `GET /api/jobs/{id}` | 잡 상태 조회 | `JobStore.get_job` | 200 `Job` |
| `POST /api/jobs/{id}/retry/{fileId}` | 실패 페이지 재-OCR + 재조립 | `JobStore.retry_file` | 200 |
| `GET /api/jobs/{id}/pages/{n}` | 페이지 상세(원본만) | `JobStorage.read_output_file` | 200 `PageDetail` |
| `GET /api/jobs/{id}/pages/{n}/download` | 페이지 텍스트 다운로드 | `stream_file` + 5절 파일명 | 200 스트림 |
| `GET /api/jobs/{id}/download?type=book\|corrected\|corrections` | 연속본-보정본-대조로그 다운로드 | `stream_file` + 5절 파일명 | 200 스트림 |
| `POST /api/intent` | 이메일 형식만 검증하는 스텁(미저장) | 없음 | 200 |

- `{n}`은 배열 인덱스가 아니라 `PageFile.pageNumber`와 일치하는 페이지를 뜻한다.
- `type=corrections`는 상위 문서 5.2의 "corrections.log 다운로드 추가"를 반영한 확장이다. 기존 `type=book|corrected`에 값 하나를 더한다.

### 4.1 업로드(POST /api/jobs) 상세

- 이 라우트는 동기 `def`로 선언한다. FastAPI가 이를 스레드풀에서 실행하므로, `create_job`이 최대 500MB 파일을 디스크에 저장하는 동안 이벤트 루프가 막히지 않는다.
- 검증(상위 문서 M5): 파일 개수 1 이상, 확장자 `jpg`/`jpeg` + `content_type` 확인, 시작 바이트가 JPEG 매직 넘버(`FF D8 FF`)인지 + 빈 파일이 아닌지 확인, 파일당 상한(`UPLOAD_MAX_BYTES_PER_FILE`), 최대 장수(`UPLOAD_MAX_FILES`), 전체 상한(`UPLOAD_MAX_TOTAL_BYTES`).
- 상한을 실효 있게 지키려면 순서가 중요하다. 먼저 개수(`UPLOAD_MAX_FILES`)를 확인하고, 각 파일은 청크 단위로 읽으며 누적 크기가 파일당/전체 상한을 넘는 즉시 중단해 413을 던진다(전체를 다 읽은 뒤 크기를 재면 상한이 무의미). Starlette `UploadFile`의 크기 정보를 쓸 수 있으면 사전 차단에 활용한다.
- 요청 폼 필드는 `correct`(bool)와 `backend`(문자열) 둘뿐이다. **`model`은 요청으로 받지 않는다** — 클라이언트가 보내면 무시하고, 서버가 `backend`에서 파생해 `JobOptions.model`을 채운다(상위 문서 5.1). 파생 규칙: `codex → "gpt-5.5"`, `claude → "claude"`(Claude Code 기본 모델 표기), `correct=false`면 `backend`는 무시하고 기본값 `codex` + `model="gpt-5.5"`로 채운다(보정을 안 하므로 의미 없음).
- `backend`는 `codex`(기본)와 `claude`만 허용. 그 외 값은 400. (`ollama`/`api`는 factory엔 있으나 이번 UI 노출 범위 밖.)
- 파일 저장-자연 정렬-내부 안전명(`upload-<fileId>-page-NNNN.jpg`) 변환은 `create_job`이 이미 담당하므로 라우트는 검증-바이트 수집만 한다.

### 4.2 오류 처리와 상태 코드

오류는 두 갈래다. FastAPI가 요청 스키마 자체를 자동 검증해 내는 오류와, 우리가 라우트 본문에서 도메인 규칙으로 던지는 오류를 구분한다.

- **프레임워크 자동 검증(422)**: 폼 필드 누락-타입 불일치 등 요청 형태 오류는 FastAPI 기본 동작대로 422 + `{"detail": [ ...오류 배열... ]}`로 응답한다(형식을 바꾸지 않는다).
- **도메인 검증(우리 코드)**: 아래는 라우트에서 `HTTPException(status_code, detail="<문자열>")`로 던진다 → `{"detail": "<문자열>"}`.
  - 400: 업로드 규칙 위반(파일 개수 0, 확장자/`content_type`/매직넘버 불일치, 허용 외 `backend`).
  - 413: 파일당/전체 용량 상한 초과.
  - 404: 미존재 잡, 미존재 페이지/파일, 보정 미요청/실패로 영구히 없는 산출물(4.3).
  - 409: 재시도 불가 상태(4.4), 또는 처리 중이라 산출물이 아직 준비되지 않음(4.3).
- **500**: 예기치 못한 예외는 전역 예외 처리기로 잡아 `{"detail": "internal server error"}`만 반환한다(스택-내부 경로 노출 금지).
- 잡 처리 중 실패는 HTTP가 아니라 `Job.status`/`summary`로 표면화한다(상위 문서 방침 승계).

### 4.3 다운로드 상태별 응답

다운로드 엔드포인트는 디스크의 산출물 파일 존재 여부로 응답을 결정한다.

응답은 파일 존재 여부만이 아니라 잡 상태(`status`/`phase`/`options.correct`/`correctionError`)를 함께 보고 사유별로 구분한다. 처리 중(아직 만들어질 수 있음)은 409, 영구적으로 없음(안 만들어짐)은 404로 나눈다.

| 요청 | 잡 상태 조건 | 응답 |
|------|-------------|------|
| `type=book` | `book.txt` 존재 | 200 스트림 |
| `type=book` | 처리 중이라 아직 생성 전(`status=processing`) | 409 `{"detail":"conversion in progress"}` |
| `type=book` | 잡 종료됐는데 파일 없음(전체 OCR 실패) | 404 `{"detail":"book not available"}` |
| `type=corrected`/`corrections` | 파일 존재 | 200 스트림 |
| `type=corrected`/`corrections` | `options.correct=false`(보정 미요청) | 404 `{"detail":"correction was not requested"}` |
| `type=corrected`/`corrections` | 보정 진행 중(`phase=correcting`, 미완료) | 409 `{"detail":"correction in progress"}` |
| `type=corrected`/`corrections` | 보정 실패(`correctionError` 있음) | 404 `{"detail":"correction failed: <사유>"}` |
| `pages/{n}/download` | `{n}`이 `PageFile.pageNumber`에 없음 | 404 `{"detail":"page not found"}` |
| `pages/{n}/download` | 페이지 존재하나 OCR 미완료/실패로 파일 없음 | 처리 중 409 / 실패 404 |

- `Job.correctedStale=true`(재시도로 변환본이 갱신됐지만 보정본은 미갱신)여도 기존 `book_corrected.txt`가 있으면 200으로 내려준다. 최신성 표식은 `Job.correctedStale`로 프런트가 경고를 띄운다(다운로드 자체는 막지 않음).
- 화면 "표시"와 "저장"을 나눈다. 원본-보정본 텍스트를 화면에 **표시**할 때는 다운로드 URL을 `fetch`로 호출해 응답 본문을 문자열로 읽는다(파일명 불필요). 파일로 **저장(다운로드)**할 때는 앵커(`<a href>`)나 브라우저 내비게이션으로 직접 URL을 열어 브라우저가 서버의 `Content-Disposition` 파일명을 그대로 쓰게 한다(프런트가 파일명을 파싱하지 않음). 별도 조회 API는 만들지 않는다.

### 4.4 재시도(POST /api/jobs/{id}/retry/{fileId}) 상세

- `retry_file`은 하나의 `bool`만 반환하고 실패 사유를 구분하지 않으므로(잡 없음/처리 중/파일 없음/실패 상태 아님을 뭉침), 라우트에서 `get_job`으로 상태를 먼저 조회해 코드를 나눈다.
  1. `get_job(id)`가 `None`이면 404 `{"detail":"job not found"}`.
  2. 잡의 `files`에 `fileId`가 없으면 404 `{"detail":"file not found"}`(미존재 자원은 404 규칙 일관).
  3. `fileId`는 있으나 `retry_file`이 `False`면 409 `{"detail":"file is not retryable"}`(처리 중이거나 실패 상태가 아님).
  4. `True`면 200.

## 5. 결과 파일명 규칙

다운로드 시 사용자에게 보이는 파일 이름 규칙. 디스크 내부 저장명은 바꾸지 않는다(경로 조작 방지 목적, 상위 문서 M5 유지).

| 대상 | 파일명 형식 | 예시 |
|------|-------------|------|
| 페이지별 | `{실행일자}-{원본명}-{순번}.txt` | `2026-07-12-filename-1.txt` |
| 연속본 | `{실행일자}-{첫페이지원본명}-book.txt` | `2026-07-12-filename-book.txt` |
| 보정본 | `{실행일자}-{첫페이지원본명}-book_corrected.txt` | `2026-07-12-filename-book_corrected.txt` |
| 대조 로그 | `{실행일자}-{첫페이지원본명}-corrections.log` | `2026-07-12-filename-corrections.log` |

- 실행일자: `Job.createdAt` 앞 10자리(`YYYY-MM-DD`).
- 원본명: 원본 파일명에서 확장자를 제거한 부분(`Path(filename).stem`). 원본명은 `PageFile.filename`에 보관돼 있다(코드 확인: `create_job`이 `filename=original_name`으로 저장, 내부 안전명은 별도).
- 첫 페이지: `Job.files`는 `pageNumber` 오름차순이라 `files[0]`이 1페이지.
- 순번: 해당 페이지의 `pageNumber`(1부터).
- 헬퍼: `download_name(job, kind, page=None) -> str` 하나로 모은다(`kind` = page/book/corrected/corrections).
- 헤더 안전화: 원본명에 경로 구분자-따옴표-개행-제어문자가 있으면 제거(헤더 인젝션 방지). 정제 후 이름이 비면 `download`로 폴백하고, 지나치게 길면 잘라 상한(예: 100자)을 둔다. `Content-Disposition`에는 ASCII 폴백 `filename="..."`(비ASCII는 안전 문자로 치환)와 함께 `filename*=UTF-8''...`(RFC 5987)을 병기해 한글 이름도 최신 브라우저에서 정상 표시되고 구형 클라이언트도 깨지지 않게 한다.

## 6. 프런트 조정

- `src/main.tsx`: `enableMocking`(MSW 시작) 블록 제거, 곧바로 `createRoot` 렌더. (파일에 이미 "실제 백엔드 연결 시 이 블록 제거" TODO 존재)
- API base: 실행 시 same-origin `/api`. `src/api/client.ts`가 상대경로 `/api`를 쓰면 수정 불필요(구현 시 확인).
- 개발 편의: `vite.config.ts`에 `/api` → `localhost:8000` proxy를 둔다. `npm run dev`(핫리로드)로 화면을 고치는 동안에도 백엔드에 붙는다. 실행/배포 경로(빌드 서빙)에는 영향 없음.
- `src/api/types.ts`: `Job.phase`, `Job.correction`, `Job.correctionError`, `Job.correctedStale`, `JobOptions.backend`를 백엔드 모델과 일치시킨다.
- `UploadPage`: 백엔드 선택 UI(codex 기본/claude, 보정 켰을 때만 활성) + 표시 모델명(codex=gpt-5.5, claude=기본 모델, 읽기 전용). claude는 실측 미검증이므로 UI에 실험적임을 한 줄 표기. **요청은 `correct`와 `backend`만 보낸다 — `model`은 전송하지 않는다**(서버가 파생, 4.1). 표시 모델명은 화면 라벨용일 뿐.
- `JobPage`: 보정 단계 진행바(`correction.done`/`correction.total`). 폴링은 기존 React Query 구조를 사용하되, 종료 조건은 `status`가 `done`/`failed`면 중단한다.
- 상태 표시 규칙: `phase`로 "OCR 중 / 보정 중"을 구분, `correctionError`가 있으면 "보정 건너뜀" 경고, `correctedStale=true`면 "보정본이 최신 변환과 다를 수 있음" 경고를 띄운다.
- `ResultPage`: 원본 대 보정 비교를 책 전체(book.txt vs book_corrected.txt) 기준으로. 화면 표시는 다운로드 URL을 `fetch`로 읽어 텍스트를 얻는다(4.3). corrections.log 다운로드 추가, 페이지별 다운로드는 원본 유지.
- 다운로드 처리: 저장은 앵커(`<a href>`)/내비게이션으로 URL을 직접 열어 브라우저가 서버 `Content-Disposition` 파일명을 그대로 쓰게 하고, 화면 표시는 `fetch`로 본문만 읽는다(4.3). 프런트는 파일명을 파싱-하드코딩하지 않는다.
- 빌드 산출물: `dist/`는 `.gitignore`에 추가.

## 7. 테스트 전략 (TDD)

자동 테스트(파이프라인 모킹, CI 가능):
- FastAPI `TestClient`로 계약 흐름: 잡 생성 → 폴링(`GET`) → 다운로드. 실제 OCR/CLI 없이 파이프라인 모킹, `JobStore`는 임시 `JOBS_ROOT` 주입.
- 업로드 검증: 허용 외 확장자-MIME/매직넘버 불일치-개수 0 → 400, 용량 초과 → 413, 폼 필드 누락/타입오류 → 422(프레임워크).
- 다운로드 상태별: 처리 중 → 409, 보정 미요청/실패 → 404, 정상 → 200(4.3).
- retry: 미존재 잡 → 404, 미존재 파일 → 404, 재시도 불가 → 409, 정상 → 200(4.4).
- 파일명 규칙 단위 테스트: 페이지-연속본-보정본-로그 이름, 한글 원본명 `Content-Disposition` 인코딩, 경로 조작 파일명 안전화.
- SPA 폴백: 존재하지 않는 자산(`.js`) → 404, 화면 경로 → `index.html`(3.3).
- 토큰 절약: 세션당 핵심 테스트 10개 이내(가장 위험한 경로 우선).

수동 스모크 테스트(외부 OCR/보정 의존, CI 제외):
- 실제 이미지 업로드 → 폴링 → `book.txt` 다운로드 end-to-end(검증 기준 3).

## 8. 최종 검증 기준

1. 자동 테스트 `pytest` 전체 통과(출력 첨부).
2. `npm run build` 성공 + `uvicorn server.app:app` 기동 후 `localhost:8000`에서 SPA 로드.
3. 실제 이미지 N장 업로드 → 폴링 → `book.txt` 다운로드까지 브라우저 end-to-end 동작(수동 스모크).
4. 다운로드 파일명이 5절 규칙과 일치(페이지-연속본-보정본).
5. 보정 백엔드 미가용 시 변환 결과(book.txt) 보존 + 경고 표면화(상위 문서 승계, 기존 pipeline 로직).

## 9. 알려진 한계 / 리스크

- 한글 파일명 `Content-Disposition` 인코딩을 빠뜨리면 이름이 깨짐 → `filename` ASCII 폴백 + `filename*` 병기로 방어(5절).
- `dist/` 미빌드 상태로 기동하면 화면이 비어 보임 → 기동 시 경고 로그 + 루트 접속 안내 문구(3.3).
- 업로드는 라우트에서 바이트로 메모리에 적재 후 `create_job`에 전달 → 대용량은 상한(`UPLOAD_MAX_*`)으로 방어. 동시에 여러 큰 업로드가 들어오면 메모리가 늘 수 있으나, 상위 문서의 단일 사용자 개인용 전제 하에서는 허용 한계로 둔다(다중 사용자 전환 시 스트리밍 저장으로 개선).
- 잡 상태는 메모리라 서버 재시작 시 진행 중-과거 잡 조회-다운로드 불가(상위 문서 M1 정책 승계, 영속화는 범위 밖).
- claude 백엔드는 코드상 지원되나 실측 미검증(progress.md) → UI에 실험적 표기, 기본값은 codex 유지.
- 나머지 리스크(구독 CLI ToS, 레이트리밋, macOS 전용 OCR)는 상위 문서 11절을 승계한다.
