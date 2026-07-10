# img2txt 웹서비스 정식 구현 설계

- 작성일: 2026-07-08
- 상태: 사용자 승인됨 (브레인스토밍 완료)
- 선행: 프런트엔드 프로토타입 `docs/prototype/img2txt-web`(Vite + React + MSW 목), 코어 로직 `img2txt/`(CLI 도구), 정식 설계 `docs/superpowers/specs/2026-07-07-korean-ocr-formal-design.md`
- 목적: MSW(Mock Service Worker) 목으로만 도는 프런트 프로토타입을 실제 백엔드(FastAPI + 기존 `img2txt` 재사용)로 연결해 개인용 웹서비스로 완성한다.

## 1. 목표

한글 책 스캔 이미지(jpg/jpeg) 여러 장을 웹에서 업로드하면, OCR 변환(꼬리말 제거 + 문단 복원)과 LLM 오탈자 보정을 거쳐 텍스트로 내려받는 개인용 웹서비스를 만든다. 프런트 프로토타입은 이미 존재하므로, 이번 작업의 본체는 프런트가 기대하는 API 계약을 그대로 구현하는 백엔드다.

기존 `img2txt` 순수 로직(scanner/ocr/layout/assembler/corrector/writer)은 거의 수정 없이 재사용하고, 그 위에 얇은 FastAPI 계층을 얹는다.

## 2. 확정된 결정사항

| 항목 | 결정 | 근거 |
|------|------|------|
| 실행 환경 | 내 Mac에서 FastAPI 실행 | OCR 엔진이 Apple Vision(`ocrmac`)이라 macOS 전용. 기존 코드 무손실 재사용, 무료-고품질 OCR 유지. 개인용/수요검증 단계에 적합 |
| 구현 범위 | 최소 (앱 end-to-end만) | 잡 상태는 메모리 + 산출물은 파일. 인증-의사수집 저장-외부 배포는 제외 (YAGNI) |
| 비동기 처리 | FastAPI 인프로세스 백그라운드 워커(ThreadPoolExecutor) | 추가 인프라 0, 단일 사용자에 적합. `img2txt` 함수를 직접 호출해 페이지별 상태 노출 가능 |
| 보정 단위 | 책 전체 (연속본을 문단 단위로) | 원래 CLI 도구 방식. 페이지 경계를 넘는 문단까지 제대로 보정, 품질 최고 |
| 보정 백엔드 | 구독 CLI 우선 (기본 `codex`, `claude` 선택 가능) | 로컬 Ollama 14B는 문단당 52초, 책 1권 107분으로 과도하게 느림. 구독 CLI는 문단당 1초대 + 배치-동시성으로 수 분. 개인 사용 전제로 사용자 승인 |
| 백엔드 선택 UI | 웹 업로드 화면에서 codex/claude 선택, 기본 codex | 사용자 지정 |
| 프런트 | 프로토타입 재사용, 최소 조정 | MSW 비활성 + Vite proxy로 실제 백엔드 연결. 보정 진행률-책 전체 비교만 조정 |

### 2.1 보정 백엔드 결정의 배경과 리스크 (ToS)

로컬 LLM 보정이 유일한 병목이다(2026-07-08 실측: qwen3:14b, 124문단 6,434초 약 107분, 문단당 평균 52초). 이를 상용 모델로 대체하는 세 경로를 조사했다.

- **정식 API (Anthropic/OpenAI 종량제)**: 약관상 완전 허용. 가장 안전-빠름-안정. 책 1권 비용 약 $0.07~0.13(문단당 입력 300 + 출력 150 토큰, Haiku 기준). 리서치 초안의 "$65"는 토큰을 1000배 오산한 오류로, 실제는 수백 원 수준.
- **구독 CLI (`claude -p`, `codex exec`)**: 벤더 자신의 공식 CLI라 로컬 개인 사용은 허용 범위. 단, 문단 대량 루프는 남용 필터-레이트리밋 위험이 있고, 남에게 파는 서비스로 쓰면 명백한 약관 위반.
- **구독-as-API 리버스 프록시**: 금지-기술 차단됨(2026년 기준 봉쇄). 제외.

결정: 개인 사용 전제이므로 구독 CLI를 우선 채택한다(사용자 승인). 경계: 이 도구가 타인 대상 유료 SaaS가 되는 시점에는 반드시 정식 API로 전환해야 한다. 백엔드를 교체 가능하게 설계해 이 전환을 저비용으로 만든다.

근거 CLI 패턴(같은 사용자의 `hermes-os` 저장소에서 검증됨):
- `codex exec -c workspace=<ws> -m gpt-5.5 --output-last-message <file> "<프롬프트>"`
- `claude -p "<프롬프트>"`

## 3. 아키텍처

### 3.1 모듈 구성 (단일 책임)

```
img2txt/                       기존 순수 로직 (재사용, 수정 최소)
  scanner/ocr/layout/assembler/writer   변경 없음
  corrector.py                 보정 오케스트레이션 — 백엔드 주입 구조로 소폭 확장
  backends/                    (신규) 보정 백엔드 구현체
    base.py                    CorrectionBackend 인터페이스
    ollama.py                  로컬 HTTP (기존 request_correction 이식)
    claude_cli.py              claude -p 서브프로세스
    codex_cli.py               codex exec 서브프로세스
server/                        (신규) FastAPI 백엔드
  app.py                       FastAPI 앱 생성, CORS, 라우터 등록
  routes.py                    엔드포인트 (프런트 계약 그대로)
  models.py                    응답 스키마(Pydantic): Job/PageFile/JobSummary/PageDetail
  jobs.py                      JobStore(메모리) + 백그라운드 실행 + 상태 전이
  pipeline.py                  img2txt 조립: 업로드→OCR→레이아웃→조립→(옵션)보정→쓰기, 상태 갱신
  storage.py                   잡별 작업 디렉터리 파일 입출력
docs/prototype/img2txt-web/    기존 프런트 — MSW 끄고 Vite proxy로 localhost:8000 연결
```

핵심 경계: `pipeline.py`만 `img2txt` 함수(`collect_images`, `recognize_page`, `analyze_page`, `assemble`, `correct_paragraphs`, `write_*`)를 호출한다. `img2txt`는 웹을 모른다(낮은 결합도). `jobs.py`는 "어떻게 돌리는가"만 알고 파이프라인 내부는 모른다.

### 3.2 처리 흐름

1. 프런트가 이미지 N장을 `POST /api/jobs`로 업로드 → 백엔드가 잡 디렉터리에 저장하고 잡을 `queued`로 생성한 뒤 백그라운드에 제출, `{id}` 반환.
2. 백그라운드 워커:
   - 1단계 OCR(페이지별): 각 파일 `waiting -> ocr -> done|failed`, 완료 시 페이지 원본 미리보기.
   - 연속본 조립: `book.txt` + `pages/page-NNN.txt` 기록.
   - 2단계 보정(옵션): 책 전체를 문단 단위로 배치 보정 → `book_corrected.txt` + `corrections.log`.
   - 잡 `done|failed`.
3. 프런트가 `GET /api/jobs/:id`를 2초 폴링해 상태를 읽고, 완료 후 다운로드 엔드포인트로 파일을 받는다.

## 4. 보정 백엔드 설계

### 4.1 추상화

`CorrectionBackend` 인터페이스: `correct_batch(paragraphs: list[str], model: str) -> list[str]`. 구현체 4종:
- `ollama` — 기존 로컬 HTTP. 배치는 단건 루프. 무료 폴백.
- `claude` — `claude -p` 서브프로세스.
- `codex` — `codex exec -m gpt-5.5 --output-last-message` 서브프로세스.
- `api` — 정식 API(Anthropic/OpenAI 종량제). 이번 범위에선 인터페이스만 마련하고 실제 호출은 스텁 수준으로 둔다. 단, 환경변수 `ANTHROPIC_API_KEY`(또는 `OPENAI_API_KEY`)가 감지되면 CLI보다 우선 선택되도록 순위를 둔다. 미래 SaaS 전환 시 이 백엔드가 기본이 되어 ToS-환경 리스크를 회피한다. [리뷰 S5]

`img2txt/corrector.py`의 오케스트레이션은 "문단들을 청크로 나눠 백엔드.correct_batch 호출 → 문단별 가드 적용" 구조로 확장한다. 기존 안전장치(길이 가드, 긴 문단 스킵, 실패 폴백, `corrections.log`)는 그대로 재사용한다.

선택: `correct` CLI에 `--backend {codex,claude,ollama}` 추가. 웹 파이프라인은 잡 옵션의 `backend`로 선택. 기본 `codex`.

### 4.2 배칭 (CLI 오버헤드 상쇄)

CLI 호출은 프로세스 1회 기동 오버헤드(수 초)가 있어 문단 1개씩 124회 호출은 비효율. 문단 여러 개(기본 약 10개)를 번호 마커로 묶어 한 번에 보내고 응답을 마커로 재분리한다.

- 프롬프트: "오탈자-잘못된 띄어쓰기만 수정, 재작성-추가-삭제-요약 금지. 각 문단을 원래 마커와 함께 그대로 반환." + 실측 오류 few-shot("경단로"→"결단코", "20 세기"→"20세기").
- 마커 개수 불일치 시: 해당 청크를 문단별 단건 재시도, 그래도 실패면 원문 유지(가드) + `corrections.log` 기록.
- 배치 크기는 구현 중 실측으로 캘리브레이션(상수 + 근거 주석).

### 4.3 동시성과 사전 점검

- 동시성: 상용 경로는 동시 호출 가능하나 구독 남용 필터 자극을 피해 개인용 기본 동시 2~3개로 낮게 시작. 배치 크기와 함께 캘리브레이션.
- 사전 점검: 시작 시 `claude`/`codex` 설치-인증 여부를 짧은 호출로 확인. Ollama는 기존 `check_server` 재사용.
- 서브프로세스 타임아웃과 좀비 방지(리뷰 M3): 모든 CLI subprocess 호출에 명시적 타임아웃(배치당 상한)을 두고, 타임아웃-예외 시 자식 프로세스를 `terminate` 후 필요 시 `kill`해 좀비가 쌓이지 않게 한다. 타임아웃 문단은 원문 유지 + 기록.
- 환경변수 전파(리뷰 M4): 백그라운드에서 subprocess를 띄울 때 호출 프로세스의 환경(`env=os.environ`, `HOME`/`PATH`/인증 토큰)을 그대로 물려준다. 안 하면 `claude`/`codex`가 인증 컨텍스트를 못 찾아 실패한다. 사전 점검도 동일 환경으로 수행한다.
- 예상 효과: 배치 약 10 + 동시성 2~3이면 124문단이 대략 1~3분(실측 필요). 로컬 107분 대비 급감.

## 5. 잡 상태 모델과 프런트 조정

### 5.1 2단계 상태 모델

- 1단계 OCR: 파일별 `waiting -> ocr -> done|failed`. 프런트의 페이지별 상태 UI에 그대로 맞음. 빠름.
- 2단계 보정(책 전체): 이제 수 분. 진행바는 "보정 중 N/총 배치(또는 문단)"로 표시. 대기 부담이 작음.

`Job`에 필드 추가: `phase: "ocr" | "correcting"`, `correction?: { done: number, total: number }`, 요약에 `correctionError?: string`(보정 스킵 사유). `JobOptions`에 `backend: "codex" | "claude"`(기본 codex) 추가.

`model`과 `backend`의 관계(리뷰 S3): v1에서 모델은 백엔드가 결정한다 — `codex`는 `gpt-5.5`, `claude`는 Claude Code 기본 모델. 프런트의 `model` 필드는 사용자 편집이 아니라 선택된 백엔드에 따라 표시만 하는 읽기 전용 값이다(사용자 직접 모델 선택은 범위 밖). 백엔드가 `ollama`일 때만 `model`이 실제 모델명(qwen3:14b)으로 쓰인다.

### 5.2 프런트 조정 (최소)

1. `src/api/types.ts`: `Job.phase`, `Job.correction`, `JobOptions.backend` 추가.
2. `UploadPage`: 백엔드 선택 UI(codex/claude, 보정 켰을 때만 활성) + 표시 모델명 백엔드 연동(codex=gpt-5.5, claude=기본 모델).
3. `JobPage`: 보정 단계 진행바 추가.
4. `ResultPage`: 원본 vs 보정본 비교를 페이지별에서 책 전체(book.txt vs book_corrected.txt)로 변경 + `corrections.log` 다운로드 추가. 페이지별 다운로드는 원본(page-NNN.txt) 유지.
5. `src/main.tsx`: MSW 활성화 제거. `vite.config.ts`에 `/api` -> `localhost:8000` proxy.

보정이 책 전체 단위라 페이지별 보정본(`PageDetail.corrected`)은 제공하지 않는다(비움). 페이지 상세는 원본만 표시.

## 6. 저장 구조

최소 범위: 잡 상태는 메모리, 산출물은 파일.

잡별 작업 디렉터리(기본 `./.data/jobs/<job_id>/`, `.gitignore` 추가):
```
uploads/                 원본 업로드 이미지 (파일명 보존 -> 자연 정렬)
output/
  pages/page-NNN.txt     페이지별 원본 (검수용)
  book.txt               연속본 (읽기용)
  book_corrected.txt     보정본 (보정 시)
  corrections.log        보정 전/후 대조 (보정 시)
```

잡 메타데이터(status/files/options/summary)는 `JobStore`(메모리 dict). 재시작 정책(리뷰 M1): 서버 재시작 시 잡 메타데이터가 소멸하며 과거 잡은 조회-다운로드 모두 불가하다(단순-일관). 재시작 후에도 산출물을 받게 하려면 잡 메타데이터 JSON 영속화가 필요하나 범위 밖이다. 즉 "재시작 후 다운로드 가능"을 표방하지 않는다(디스크 산출물 파일 자체는 남지만 UI 진입점이 없다). 자동 정리는 생략(수동).

페이지 번호: 업로드 파일을 `uploads/`에 저장 후 `collect_images`로 자연 정렬(기존 scanner 재사용). 번호는 `extract_page_number(path) or 순번`(CLI `run_convert`와 동일).

## 7. API 계약 매핑과 에러 처리

프런트 계약(`docs/prototype/img2txt-web/src/api/types.ts`)을 그대로 구현하고 필드만 확장한다.

- `POST /api/jobs` (multipart: files[], correct, model, backend): 업로드 검증 -> 저장 -> 잡 생성(queued) -> 백그라운드 제출 -> `{id}`(201). 업로드 검증(리뷰 M5): 확장자 jpg/jpeg + MIME 확인, 파일당 상한(기본 20MB), 한 잡 최대 장수(기본 100장), 전체 상한(기본 500MB), 저장 시 파일명을 내부 안전 이름(`page-<index>-<uuid>.jpg`)으로 변환해 경로 조작(디렉터리 트래버설)을 차단하고 원본 파일명은 정렬-표시용 메타로만 보관. 위반 시 400(개수 0 포함).
- `GET /api/jobs/:id`: 스토어의 `Job`(+phase, correction 진행률). 미존재 404.
- `POST /api/jobs/:id/retry/:fileId`: 실패 페이지 재-OCR (리뷰 M2). v1 재조립 범위: 재-OCR 성공 후 해당 페이지의 `pages/page-NNN.txt`와 연속본 `book.txt`를 재생성한다. 보정본(`book_corrected.txt`)-`corrections.log`는 자동 재생성하지 않으며 보정 재실행은 별도 명시 동작(추후)으로 둔다. retry는 변환 산출물까지만 최신화한다.
- `GET /api/jobs/:id/pages/:n`: `PageDetail`(원본). corrected는 비움.
- `GET /api/jobs/:id/pages/:n/download`: `page-NNN.txt`.
- `GET /api/jobs/:id/download?type=book|corrected`: `book.txt` / `book_corrected.txt`.
- `POST /api/intent`: 이번 범위 밖. 이메일 형식만 검증하는 간단 스텁(미저장, 200).

에러 처리(기존 `img2txt` 방침 재사용):
- OCR 1장 실패 -> 파일 `failed` + error, 계속. 빈 OCR -> 연속본 제외 + `[페이지 N 누락]`. 전체 OCR 실패 -> 잡 `failed`.
- 보정 백엔드 미설치/미인증(사전점검 실패): 변환은 이미 성공했으므로 버리지 않고 보정만 건너뛰며 `summary.correctionError`에 사유를 남기고 잡 `done`. (변환 결과 보존 우선)
- 문단 보정 실패/타임아웃/가드 초과 -> 원문 유지 + 기록. 전체 보정 실패(정상 응답 0건) -> 보정 경고, `book.txt`는 제공.
- HTTP 400(입력 오류)/404(미존재)/500(예외). 잡 처리 중 실패는 HTTP가 아니라 잡 `status`/`summary`로 표면화.

### 7.1 응답 스키마 (리뷰 S1, 스펙에 고정)

프런트 `types.ts`와 동일하되 확장 필드 포함. 실제 JSON 예시:

```json
// GET /api/jobs/:id
{
  "id": "b1f2...",
  "createdAt": "2026-07-08T22:00:00Z",
  "options": { "correct": true, "model": "gpt-5.5", "backend": "codex" },
  "status": "processing",
  "phase": "correcting",
  "correction": { "done": 40, "total": 124 },
  "files": [
    {
      "id": "f1",
      "filename": "page-2.jpg",
      "pageNumber": 1,
      "sizeBytes": 812345,
      "status": "done",
      "previewText": "첫 줄 미리보기...",
      "error": null
    }
  ],
  "summary": {
    "successPages": 30, "failedPages": 1, "removedFooterLines": 30,
    "corrected": 78, "kept": 42, "guardBlocked": 3,
    "correctionError": null
  }
}

// GET /api/jobs/:id/pages/:n
{ "pageNumber": 1, "filename": "page-2.jpg", "original": "페이지 원본 전체...", "corrected": null }
```

값 도메인: `status` = queued|processing|done|failed, `phase` = ocr|correcting, `files[].status` = waiting|ocr|correcting|done|failed. `correction`은 보정 단계에서만, `summary`는 완료 시, `summary`의 corrected/kept/guardBlocked는 보정 시에만 채워진다. `PageDetail.corrected`는 책 전체 보정 방침상 항상 null(페이지 상세는 원본만). 다운로드 엔드포인트는 `text/plain; charset=utf-8` + `Content-Disposition`으로 파일을 스트리밍한다.

## 8. 테스트 전략 (TDD)

- 기존 `img2txt` 단위 테스트 재사용(scanner/layout/assembler/corrector).
- 신규 핵심:
  1. CLI 백엔드 배치 파싱: 마커 분리, 개수 불일치 시 단건 폴백, 실패 시 원문 유지 (subprocess 모킹).
  2. 파이프라인: OCR 실패 폴백, 빈 페이지 누락 표식, 보정 백엔드 미가용 시 변환 결과 보존.
  3. retry 재조립: 실패 페이지 재-OCR 후 `book.txt` 재생성, 보정본 미재생성 확인. [리뷰 M2]
  4. 업로드 검증: 허용 외 확장자-용량 초과-장수 초과 거절, 파일명 안전화(경로조작 차단). [리뷰 M5]
  5. `JobStore`: 상태 전이(queued→processing→done|failed), 재시도.
  6. API: FastAPI `TestClient`로 엔드포인트 계약(생성->폴링->다운로드), 파이프라인 모킹(실제 OCR/CLI 없이).
- 통합(marker `macos`, CI 제외): 실제 이미지 1장 OCR + 실제 codex/claude 1회 보정.
- 토큰 절약: 세션당 핵심 테스트 10개 이내로 집중.

## 9. 구현 분해 (작은 문제 단위)

병렬-순차로 처리 가능한 독립 단위. 앞선 문제 분해(P2~P9)와 대응한다.

1. 보정 백엔드 인터페이스 + Ollama 이식(`img2txt/backends/`). (P3)
2. `codex`/`claude` CLI 백엔드 구현 + 사전 점검. (P2)
3. `corrector.py` 오케스트레이션을 배치+가드 구조로 확장. (P3, P6)
4. 배치 크기-동시성 캘리브레이션 + 목표 시간 검증. (P4, P5)
5. 상용 백엔드 품질 게이트(샘플 3문단, 과교정-의미변경 없음 확인). (P7)
6. `server/` FastAPI: models/storage/jobs/pipeline/routes. (핵심)
7. 프런트 조정(타입/UploadPage 백엔드 선택/JobPage 진행바/ResultPage 책 전체 비교/MSW 제거/proxy).
8. 비용-상한-폴백 로깅. (P8, P9)

## 10. 최종 검증 기준

1. 전체 단위 테스트 통과 (`pytest` 출력 첨부).
2. 실제 책 스캔 N장 업로드 -> 웹에서 잡 생성 -> 폴링 -> `book.txt` 다운로드까지 end-to-end 동작.
3. 보정(기본 codex) 켠 잡이 실제로 완료되고 `corrections.log`의 변경 문단 표본 5개가 실제 오류 수정이면서 원문 의미 변형이 없음.
4. 보정 소요 시간이 목표(예: 5분 이내, 캘리브레이션으로 확정) 안에 들어옴.
5. 보정 백엔드 미가용 상황에서 변환 결과(book.txt)가 보존되고 경고가 표면화됨.

## 11. 알려진 한계 / 리스크

- OCR은 macOS(Apple Vision) 전용. 서버 배포-타 OS는 이번 범위 밖.
- 구독 CLI 보정은 개인 사용 전제. 타인 대상 유료 서비스로 전환 시 정식 API로 교체 필수(약관). 백엔드 추상화로 교체 비용 최소화.
- 잡 상태는 메모리라 서버 재시작 시 진행 중-과거 잡 모두 조회-다운로드 불가(리뷰 M1로 정책 확정, 최소 범위 허용). 영속화는 범위 밖.
- CLI 에이전트는 출력이 장황할 수 있어, 엄격한 "결과만 반환" 프롬프트 + 마커 검증 + 가드로 방어. 실패 시 원문 유지.
- 구독 레이트리밋-남용 필터로 대량 처리 시 실패 가능 -> 동시성 낮춤 + 실패 폴백 + Ollama 폴백.
- 배치 병합이 문단 경계를 흐트러뜨릴 위험 -> 마커 정렬-개수 검증으로 차단, 불일치 시 단건 폴백.
