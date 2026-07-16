# Progress

## 프로젝트 소개

한글 책을 스캔한 이미지에서 글자를 읽어(OCR, 광학 문자 인식) 텍스트 파일로 만들어 주는 도구다. 읽은 글자의 오탈자를 LLM(대규모 언어 모델)으로 교정하는 보정 단계가 있고, 명령줄(CLI)과 브라우저 업로드 방식(웹서비스) 두 가지로 쓸 수 있다. 현재는 개인용이며, 공개 서비스 전환 로드맵이 진행 중이다.

## 주요 기능

- 스캔 이미지 폴더 → 책 텍스트(book.txt) 변환 CLI (Apple Vision OCR, 한글)
- LLM 오탈자 보정 (codex/claude/ollama 백엔드, 배치 처리 + 실시간 진행률)
- 브라우저 업로드 → 텍스트 다운로드 개인용 웹서비스 (FastAPI 단일 포트)
- 입력 포맷 JPEG/PNG/WEBP/TIFF 지원
- OCR 정확도 자동 측정 도구 (`scripts/bench_ocr.py` — 정답 대비 글자/단어 오류율 CER/WER 채점, JSONL 리포트)

## 진행 기록

## 2026-07-16 - OCR 품질 자동 측정 도구(벤치 하네스) + PR #8
- 상태: 완료 (PR #8 머지 대기)
- 완료한 일: OCR 결과를 정답과 비교해 정확도를 숫자(CER 글자 오류율/WER 단어 오류율)로 자동 채점하는 도구 완성. 파이프라인 3지점(원시 OCR/조립본/보정본)을 한 번에 측정하는 CLI와 테스트 49개. GitHub PR 생성 후 Codex 리뷰 High 4건(집계 왜곡, 빈 페이지 오판, --allow-skip 버그, 전체 실패 종료코드)을 반영.
- 커밋/PR: `97d7bfe`(설계 문서)~`db440f4`(리뷰 반영), 14커밋, PR #8 https://github.com/jojo3420/img2txt/pull/8 (base main, 미머지)
- 결정사항: (1) micro CER은 정규화 길이로 가중. (2) 빈 페이지 판정은 layout.is_empty 기준. (3) 보정 지점은 스펙 7절(LLM 비교) 전까지 backend=None — corrected는 assembled와 동일. (4) levenshtein은 Sequence[T]로 일반화(WER 단어 단위 요구, str 하위 호환).
- 남은 일: (1) PR #8 머지 (사용자 결정). (2) Codex Medium 5건 follow-up — WER micro화, empty 페이지 중복 카운트, dataset glob 필터, DP 메모리 절감, segments 의미. (3) AI Hub 실제 라벨 어댑터 + 30~50페이지 실측 스모크. (4) 스펙 6절(전처리)/7절(LLM 비교) 별도 플랜.
- 관련 문서: docs/superpowers/specs/2026-07-13-ocr-llm-quality-harness-design.md, docs/superpowers/plans/2026-07-13-ocr-quality-harness.md, tobyteam/cpr-review-8-20260716-154045.md
- 상세 히스토리: 없음

## 2026-07-12 - 보정 진행률 실시간 표시 수정 (멈춘 것처럼 보이던 문제)
- 상태: 완료
- 완료한 일: 보정(LLM 오탈자 교정) 단계에서 진행률이 "0/N"에 멈춘 것처럼 보이던 문제 해결. 실제로는 백그라운드에서 정상 처리 중이었으나 UI가 중간 진행을 못 받아오는 구조였음 - 문단 묶음(배치, 10문단)마다 진행을 보고하도록 콜백을 추가해 숫자가 실시간으로 오르게 함. "남은 시간 약 0초"로 잘못 뜨던 것도 남은 보정 문단 기준으로 계산하도록 수정.
- 커밋/PR: `810ab4f` fix: 보정 진행률 배치 단위 실시간 반영 + 남은시간 추정 정확화. PR 없음 (main 직접 커밋 후 docs/web-service-design로 fast-forward 병합).
- 결정사항: `correct_paragraphs`에 선택적 `progress_callback` 인자 추가(기본값 None이라 CLI 호출은 무변경). 진행률은 배치 단위(10문단)로 갱신되어 숫자가 10씩 점프함.
- 남은 일: ⚠️ PNG/WEBP OCR 지원으로 보이는 미커밋 4개 파일(`ocr.py`/`scanner.py`/`routes.py`/`storage.py`)이 워킹트리에 남아있음 - 이 세션 밖에서 생긴 변경이라 출처 확인 후 별도 처리 필요.
- 관련 문서: 없음
- 상세 히스토리: 없음

## 2026-07-12 - 웹서비스화 (브라우저에서 이미지 올려 텍스트 다운로드)
- 상태: 완료
- 완료한 일: 이미 만든 처리 엔진에 웹 서버 계층(FastAPI HTTP API)과 화면 연결을 붙여, 브라우저에서 한글 책 스캔 이미지를 올리면 OCR(광학 문자 인식)로 텍스트를 뽑아 내려받는 개인용 웹서비스를 완성. 명령 하나(`uvicorn server.app:app`)로 뜨는 단일 주소 방식. 실제 이미지 업로드부터 `book.txt` 다운로드까지 end-to-end 동작 확인(Apple Vision OCR로 한글 인식).
- 커밋/PR: `ae4075c` feat: 웹서비스화 - FastAPI HTTP 계층 + 프런트 실제 연결 (#7). PR #7 https://github.com/jojo3420/img2txt/pull/7 (base main, squash 머지 완료)
- 결정사항: (1) 단일 프로세스-단일 URL 서빙(FastAPI가 API와 빌드된 프런트를 한 포트에서, same-origin이라 CORS 불필요). (2) 다운로드 파일명 규칙 `{실행일자}-{원본명}-{순번|book}.txt`(헤더로만, 디스크 저장명은 안전한 내부 이름 유지). (3) 보정 백엔드 `model`은 요청으로 안 받고 서버가 파생. (4) claude 백엔드는 실측 미검증이라 UI 실험적 표기, 기본 codex.
- 남은 일: (1) 배치 크기-동시성 캘리브레이션 + 보정 품질 게이트. (2) 잡 상태 영속화(현재는 서버 재시작 시 과거 잡 소멸). (3) `ocrmac`은 macOS 전용 - 서버 배포 시 대안 필요.
- 관련 문서: docs/superpowers/specs/2026-07-12-web-service-http-frontend-design.md, docs/superpowers/plans/2026-07-12-web-service-http-frontend.md, docs/review/review-result-20260712-*.md
- 상세 히스토리: progress-001.md

## 2026-07-10 - 보정 백엔드 앱 연결 (codex 버그 수정 + 배치 오케스트레이션)
- 상태: 부분 완료 (claude/ollama 백엔드는 실측 미검증 — codex만 실제 호출 확인)
- 완료한 일: (1) codex 백엔드가 실제로 동작 안 하던 버그 수정 — `codex exec`에 프롬프트를 파일 경로 옵션(`--output-last-message`)으로 잘못 넘기던 것을 위치 인자로 교정. (2) 보정 흐름을 백엔드 주입 배치 구조로 확장 — 문단을 묶어 `backend.correct_batch` 호출 후 문단별 길이 가드 적용, 긴 문단 분리 시 원위치 인덱스 정합성 보장. (3) `correct`에 `--backend {codex,claude,ollama}`(기본 codex) 선택 추가. 실제 codex로 `correct` end-to-end 성공.
- 커밋/PR: `82eaed6`(codex 버그) + `df09425`(배치 오케스트레이션) + `5a5c8b0`(Codex 리뷰 반영). PR #2 https://github.com/jojo3420/img2txt/pull/2 (base main, 3커밋, +421/-93)
- 결정사항: (1) 보정 실패(백엔드 예외/개수 불일치)를 KEPT가 아닌 FAILED로 기록 — 실패를 정상으로 위장하던 Silent Failure를 차단해 `all_requests_failed`가 전체 실패를 감지하게 함. (2) 길이 가드는 corrector 오케스트레이션 책임 유지, 백엔드는 순수 보정만.
- 남은 일: (1) claude/ollama 백엔드 실측 배치 검증. (2) 프런트 연동 (MSW 목업 → 실제 API, 스펙 7절). (3) PR #2 머지.
- 관련 문서: docs/superpowers/specs/2026-07-08-img2txt-web-service-design.md (4.1/4.2/5.1)
- 상세 히스토리: 없음

## 2026-07-10 - CLI 배치 no-op 수정 + PR #1 + Codex 리뷰 반영
- 상태: 완료
- 완료한 일: (1) CLI 백엔드 `correct_batch`의 no-op 제거 — 개수 요약 마커(`[CORRECT:n,KEPT:m,GUARD:g]`) 폐기, 스펙 4.2대로 `===문단 N===` 센티넬 헤더로 응답 재분리. (2) PR #1 생성 후 Codex xhigh 리뷰 → 데이터 손실 버그 수정: CLI 실패(returncode!=0)-빈 출력-빈 세그먼트가 원문을 빈 문자열로 덮어쓰던 것을 원문 유지로 차단, Ollama 빈응답 방어, 프롬프트 `{index}` 리터럴 제거, 단건 폴백 보정 프롬프트 추가. `tests/backends/` 28개 통과.
- 커밋/PR: `5cc5b53`(no-op 수정) + `20e6926`(리뷰 반영). PR #1 https://github.com/jojo3420/img2txt/pull/1 (base main, 10커밋)
- 결정사항: (1) 재분리 구분자 고유 센티넬(A2) 채택, 개수 요약 마커 완전 폐기(모델이 자기보고 불가). (2) 리뷰 지적 C3(Ollama 길이 가드)는 무비판 수용 안 함 — 가드는 스펙 4.1/4.2상 corrector 오케스트레이션(T5) 책임이라 백엔드 대신 T5로 이관, 백엔드엔 빈응답 방어만.
- 남은 일: (1) corrector 오케스트레이션(배치+가드) 구현 — 센티넬 프로토콜 + 로컬 가드 전제, 아직 브리프 없음. (2) ⚠️ 실제 claude/codex CLI로 배치 보정 end-to-end 검증(목 테스트만으로 부족). (3) PR #1 머지.
- 관련 문서: docs/superpowers/specs/2026-07-08-img2txt-web-service-design.md (4.1/4.2), .superpowers/sdd/task-1-brief.md-task-3-brief.md (센티넬로 동기화, gitignore 미추적), Codex 리뷰 로그(세션 내)
