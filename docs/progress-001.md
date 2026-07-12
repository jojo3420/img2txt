# progress-001: 웹서비스화 - FastAPI HTTP 계층 + 프런트 실제 연결 (2026-07-12)

## 맥락 (왜 필요했나)
img2txt 코어(scanner/ocr/layout/assembler/corrector)와 `server/{config,models,storage,jobs,pipeline}`는 이미 있었으나 HTTP로 노출되지 않아 브라우저에서 쓸 수 없었다. 프런트 프로토타입은 MSW(Mock Service Worker) 목업으로만 동작. 이번 작업으로 얇은 HTTP 계층 + 프런트 실제 연결을 얹어 단일 프로세스 개인 웹서비스를 완성.

## 구현 요약 (무엇을 어디에)
- 신규 백엔드 모듈:
  - `server/naming.py`: 다운로드 파일명 규칙 `{createdAt[:10]}-{원본stem}-{page순번|book|book_corrected|corrections}.{txt|log}`. 연속본/보정본/로그는 첫 페이지 원본명 기준. `download_name(job, kind, page=None)`, `content_disposition(name)`(ASCII `filename=` + RFC 5987 `filename*=UTF-8''` 병기, 헤더 안전화).
  - `server/app.py`: `create_app()`, lifespan으로 단일 `JobStore`를 `app.state.job_store`에 보관 후 종료 시 `shutdown()`. 정적 서빙 catch-all `/{full_path:path}` — `/api/`는 404, `DIST_DIR` 내 파일 서빙, 확장자 있는 자산 미스는 404, 화면 경로는 `index.html` 폴백(경로 이탈 방지). 전역 예외 핸들러 500 `{"detail":"internal server error"}`(내부 노출 금지). 전역 `app`으로 `uvicorn server.app:app`.
  - `server/routes.py`: `APIRouter(prefix="/api")` + `get_store` 의존성. 엔드포인트 7종(아래).
- API 계약(계약은 상위 스펙 2026-07-08 section 7 준수):
  - `POST /api/jobs` (multipart: files[], **Form** `correct: bool`, `backend: str`). `model`은 요청으로 안 받고 서버 파생(codex→gpt-5.5, claude→claude). correct=false면 backend 무시 codex. 검증: 확장자 jpg/jpeg + content_type + JPEG 매직넘버(FF D8 FF) + 빈 파일 거절, 청크 누적 읽기로 파일당(`UPLOAD_MAX_BYTES_PER_FILE`)/전체(`UPLOAD_MAX_TOTAL_BYTES`) 상한 실시간 차단(413), 개수 상한(`UPLOAD_MAX_FILES`). 라우트는 동기 `def`(스레드풀). → 201 `CreateJobResponse`.
  - `GET /api/jobs/{id}` → `Job`, 미존재 404.
  - `POST /api/jobs/{id}/retry/{fileId}` → 잡없음 404 / 파일없음 404 / 재시도불가 409 / 성공 200.
  - `GET /api/jobs/{id}/pages/{n}` → `PageDetail`(원본만, corrected=null). n은 `PageFile.pageNumber`. 파일은 `output/pages/page-{n:03d}.txt`.
  - `GET /api/jobs/{id}/pages/{n}/download`, `GET /api/jobs/{id}/download?type=book|corrected|corrections` → `stream_file` + 파일명 규칙. 상태별: book 있으면 200/처리중 409/그외 404; corrected-corrections는 correct=false면 404("correction was not requested")/correctionError면 404/진행중 409/파일있으면 200.
  - `POST /api/intent` → 이메일 형식 검증 스텁(미저장) 200/400.
  - 오류 계약: FastAPI 자동검증 422(detail 배열), 도메인 검증은 `HTTPException(code, detail="문자열")` 400/413/404/409.
- 프런트(`docs/prototype/img2txt-web/`): `main.tsx` MSW 제거, `vite.config.ts` dev `/api` proxy(→localhost:8000), `api/types.ts` Job에 phase/correction/correctionError/correctedStale + JobOptions.backend, `api/client.ts` 요청에 model 미전송 backend 추가. UploadPage 백엔드 선택(codex/claude 실험적), JobPage 단계/진행바/경고, ResultPage 책 전체 비교(표시는 fetch, 저장은 앵커로 서버 Content-Disposition 파일명 사용) + corrections.log 버튼.

## 실행 모델 결정
단일 프로세스/단일 URL: `npm run build`로 프런트 빌드 후 `uvicorn server.app:app` 하나가 `/api`와 `dist/`를 localhost:8000에서 서빙(same-origin이라 CORS 불필요). 개발 반복만 vite dev + proxy.

## 시도와 실패 (재발 방지 - 리뷰가 잡은 실제 버그 3건)
1. `correct`/`backend`를 `Query`로 받아 프런트 FormData 값이 무시됨(항상 기본값) → `Form`으로 수정. 폼 값이 실제 `JobStore`에 전달되는지 캡처 테스트로 검증(false pass 방지).
2. 업로드 `_read_chunk`가 8192바이트만 읽어 파일이 8KB로 잘려 저장 + 상한 미발동 → `_read_limited` 청크 누적 읽기로 교체(파일당/전체 413 실시간). 축소 상한 monkeypatch로 413 테스트.
3. 페이지 다운로드가 fetch+하드코딩 파일명(`page-001.txt`)이라 서버 Content-Disposition 무시 → 앵커(`<a href download>`)로 전환, 미사용 다운로드 함수 제거.

## 기각/주의
- claude 백엔드는 factory에 있으나 실측 미검증 → UI 실험적 표기, 기본 codex.
- 잡 상태 메모리라 서버 재시작 시 과거 잡 소멸(상위 M1 정책 승계). 영속화는 범위 밖.
- 캘리브레이션(배치/동시성), 보정 품질 게이트는 다음 세션.

## 재현-검증 명령어
- 서버 테스트: `python -m pytest tests/server/ -q` (44 pass). `test_integration_ocr.py` 실패는 ocrmac 미설치 무관.
- 프런트 빌드: `cd docs/prototype/img2txt-web && npm run build`.
- 실제 OCR E2E(검증됨): `pip install ocrmac` 후 `JOBS_ROOT=... uvicorn server.app:app --port 8001`, 한글 이미지 업로드(correct=false) → 폴링 done → `GET /download?type=book` 파일명 `YYYY-MM-DD-{stem}-book.txt` + 내용 확인. Apple Vision으로 한글 인식 정확.
