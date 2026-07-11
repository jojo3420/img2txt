# 세션 핸드오프 — 2026-07-10 23:04 KST

> 모드: simple-change (git 기반. superpowers 산출물은 docs/superpowers, .superpowers/sdd 참조)
> Feature: 보정 백엔드 앱 연결 + 프런트 완성 + E2E
> 이전 세션 종결 사유: 사용자 인계 (E2E 진입 직전, 사전 조건 미충족 발견)

## 한 줄 요약

CLI 배치 보정 no-op 결함을 센티넬 프로토콜로 고쳐 PR #1을 main에 머지했으나, 새 보정 백엔드(`img2txt/backends/`)가 앱 CLI에 아직 연결 안 됐고 codex 백엔드 명령에 실제 버그가 있어, 다음 세션은 (1)버그 수정 (2)백엔드-CLI 연결 (3)프런트 완성 (4)E2E 순으로 진행해야 한다.

---

## 다음 세션이 가장 먼저 할 일

🔴 반드시:
1. 이 핸드오프 파일을 읽는다 (`docs/handoff/2026-07-10-2304-backend-wiring.md`)
2. 설계/계획 문서를 읽는다:
   - `docs/superpowers/specs/2026-07-08-img2txt-web-service-design.md` (4.1/4.2 백엔드, 6 저장구조)
   - `docs/superpowers/plans/2026-07-08-img2txt-web-service.md` (15 태스크)
   - `docs/progress.md` (세션별 진행 일지, 최신이 위)
3. `git status && git log --oneline -8`로 상태 확인. ⚠️ 로컬 `main`은 원격 머지분(PR #1) 미반영 — `git checkout main && git pull` 필요.
4. 아래 "다음 단계 → MUST"부터 시작.

---

## 작업 컨텍스트

### 사용자 원본 요청 (이번 인계)

> 새 보정 백엔드(img2txt/backends/)는 아직 앱 CLI(img2txt correct)에 연결 진행 및 프런트 목업에서 실제로 완성도 있게 구현 필요. @docs/prototype/img2txt-web 프로토타입 확인하여 완성도 있게 다음 세션에서 구현 필요함. 그 이후에 E2E 테스트 진행 후 전체 파이프라인 검증해야 한다.

### 이번 세션에서 한 일 (완료)

- CLI 배치 보정 no-op 제거: 개수 요약 마커 폐기 → `===문단 N===` 센티넬 재분리 프로토콜(스펙 4.2). 커밋 `5cc5b53`.
- Codex 2회 리뷰 + 데이터 손실 버그 수정(CLI 실패/빈 출력/빈 세그먼트가 원문을 ""로 덮어씀 방지, Ollama 빈응답 방어, 프롬프트 `{index}` 리터럴 제거, 단건 폴백 보정 프롬프트). 커밋 `20e6926`.
- PR #1 생성 → main 머지 완료(원격 머지 커밋 `5a13195`).

### 사용자 제약-금지사항 (반드시 준수)

🔴 반드시:
- 오케스트레이션 게이트: 메인 에이전트 코드 파일 직접 수정은 턴당 2개까지. 3개+는 서브에이전트(default-worker 등) 위임.
- 길이 가드(LENGTH_GUARD_RATIO 등)는 백엔드에 넣지 말 것 — 스펙 4.1/4.2상 corrector 오케스트레이션(T5) 책임. 백엔드는 빈응답 방어만.
- TDD: 화이트리스트 대상은 테스트 동시 작성. 커밋은 Conventional Commit.

---

## 결정 사항 (Decisions) — 뒤집지 말 것

| # | 결정 | 근거 |
|---|------|------|
| 1 | 배치 재분리 구분자 = 고유 센티넬 `===문단 N===` (A2) | 번호 마커 재사용(A1)은 본문 번호와 오분리 위험 |
| 2 | 개수 요약 마커 `[CORRECT:n,KEPT:m,GUARD:g]` 완전 폐기 | 모델이 자기보고 불가(가드는 로컬 책임), 재분리에도 무용 |
| 3 | 길이 가드는 corrector 오케스트레이션(T5)에, 백엔드엔 빈응답 방어만 | 스펙 레이어링. Codex C3 지적 부분만 수용 |
| 4 | Ollama 백엔드는 단건 루프 유지(배치 아님) | 스펙 "ollama 배치는 단건 루프" |

---

## 블로커 - 미해결 이슈 (Blockers)

| # | 이슈 | 영향 | 상태 |
|---|------|------|------|
| 1 | ✅ codex 백엔드 명령 버그 (`img2txt/backends/cli.py:53`) | CodexBackend가 실제 codex CLI에서 작동 안 함 | 코드+`codex exec --help`로 확인. 미수정 |
| 2 | ✅ 새 backends가 앱 CLI에 미연결 (`img2txt/cli.py:94` run_correct) | `img2txt correct`는 여전히 구 Ollama 경로(check_server+correct_paragraphs) | 확인됨. corrector 오케스트레이션(T5) 필요 |
| 3 | ✅ 프런트(`docs/prototype/img2txt-web`) MSW 목업 전용 | 실제 백엔드 미연동, 브라우저 E2E 대상 아님 | `src/main.tsx:21` worker.start 확인 |
| 4 | ⚠️ 실제 claude/codex CLI 배치 보정 미검증 | 목 테스트만 존재(28 passed) | Codex 잔여 리스크 |

### 블로커 #1 상세 (codex 버그)

`cli.py:53` 현재: `["codex","exec","-m","gpt-5.5","--output-last-message", prompt]`
- `codex exec --help`: `-o, --output-last-message <FILE>`는 파일 경로 인자, 프롬프트는 위치 인자 `[PROMPT]`.
- 지금은 prompt가 출력 파일명으로 소비되고 실제 지시가 전달 안 됨.
- 수정 방향: prompt를 위치 인자로 넘기고, `--output-last-message`는 제거하거나 실제 임시 파일 경로 지정. claude 명령(`["claude","-p",prompt]`)은 정상.

---

## 다음 단계 (Next)

🔴 MUST (진행 차단):
- [ ] 블로커 #1: codex 백엔드 명령어 수정 + 실제 codex CLI로 1회 스모크 검증
- [ ] 블로커 #2: corrector 오케스트레이션(배치+가드) 구현 — 문단 청크 → `backend.correct_batch` → 문단별 로컬 가드. `img2txt correct`에 `--backend {codex,claude,ollama}` 추가(기본 codex). 센티넬 프로토콜 + 로컬 가드 전제
- [ ] 위 연결 후 실제 CLI로 `img2txt correct` end-to-end 1회 검증

🟡 SHOULD (완성도):
- [ ] 프런트 `docs/prototype/img2txt-web` 완성 — 프로토타입 확인 후 실제 백엔드 연동(현재 MSW 목업). package.json/vite/api 클라이언트 점검
- [ ] E2E 테스트: 백엔드 파이프라인(Python) + 프런트(연동 후 Playwright). 현재 Playwright 미설치
- [ ] 리뷰 잔여 Low 2건: 프롬프트 인젝션 방어(`<text>` 래핑), CLI 엣지 테스트(returncode!=0+stdout, 부분 폴백)

🟢 NICE-TO-DO:
- [ ] `tobyteam/`(Codex 리뷰 산출물) `.gitignore` 추가 검토
- [ ] `.superpowers/sdd/task-1,3-brief.md`는 센티넬로 동기화됨(gitignore 미추적)

---

## 핵심 파일 경로 (Refs)

| 카테고리 | 경로 |
|---------|------|
| 설계 스펙 | `docs/superpowers/specs/2026-07-08-img2txt-web-service-design.md` |
| 구현 계획 | `docs/superpowers/plans/2026-07-08-img2txt-web-service.md` |
| 앱 CLI (연결 대상) | `img2txt/cli.py:94` (run_correct) |
| 보정 백엔드 (완료) | `img2txt/backends/base.py`, `cli.py`, `ollama.py` |
| codex 버그 위치 | `img2txt/backends/cli.py:53` |
| 구 보정 로직 | `img2txt/corrector.py` (correct_paragraphs, 가드 로직) |
| 프런트 프로토타입 | `docs/prototype/img2txt-web/` (src/main.tsx MSW) |
| 백엔드 테스트 | `tests/backends/` (28 passed) |
| 진행 일지 | `docs/progress.md` |
| 핸드오프 (이 파일) | `docs/handoff/2026-07-10-2304-backend-wiring.md` |

---

## 검증 상태

| 항목 | 상태 | 비고 |
|------|------|------|
| backends 단위 테스트 | ✅ 28 passed | `.venv/bin/pytest tests/backends/ -v` |
| 전체 pytest | ⚠️ ocrmac 미설치로 1건 실패 | `tests/test_integration_ocr.py` 환경 이슈, 리뷰 대상 밖 |
| 실제 CLI E2E | ⚠️ 미실행 | 블로커 #1 수정 후 가능 |
| 프런트 빌드/구동 | ⚠️ 미확인 | Playwright 미설치 |
| PR #1 | ✅ MERGED (remote 5a13195) | 로컬 main 미동기화 |

---

## 재개 프롬프트 (다음 세션에 그대로 복사-붙여넣기)

```
이전 세션의 작업을 이어받습니다. 다음 핸드오프 파일을 먼저 읽고 컨텍스트를 복원해주세요:

/Users/joel.silver/Workspace/gitroom/python/img2txt/docs/handoff/2026-07-10-2304-backend-wiring.md

복원 순서:
1. 위 핸드오프 파일 전체를 읽는다
2. Plan/Design 문서(docs/superpowers/specs, plans)와 docs/progress.md를 읽는다
3. git checkout main && git pull 로 PR #1 머지분 동기화, git status 확인
4. 핸드오프 "다음 단계 → MUST" 항목부터 시작 (블로커 #1 codex 명령 버그 우선)
5. 사용자 제약 준수: 길이 가드는 백엔드 아닌 corrector 오케스트레이션(T5)에, 오케스트레이션 게이트(코드 수정 턴당 2개) 준수
6. 결정 사항 표(센티넬 프로토콜, 개수 마커 폐기 등)는 뒤집지 않음

진행 전 핸드오프를 읽었음을 확인하고, MUST 중 어디부터 시작할지 한 줄로 보고해주세요.
```

---

✅ 핸드오프 작성 완료.
