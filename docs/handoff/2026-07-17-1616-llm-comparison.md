# 세션 핸드오프 — 2026-07-17 16:16 KST

> **모드**: superpowers (docs/superpowers/specs + plans)
> **Feature**: LLM 보정 가성비 비교 실험 (스펙 7절)
> **이전 세션 종결 사유**: 사용자 인계 (/handoff) — 다음 트랙 시작 위임

## 한 줄 요약

OCR 품질 하네스 3부작(PR #8 채점기, #9 전처리 인프라, #10 실측)을 모두 머지 완료했고, 전처리는 "일괄 적용 이득 없음(baseline 유지)"으로 잠정 결론냈다. 다음은 스펙 7절 = LLM 보정 모델을 gpt-5.5에서 저비용 모델로 바꿀 수 있는지 가성비를 실측하는 실험이며, 시작은 **브레인스토밍이 아니라 스펙 7절이 이미 상세 설계이므로 곧바로 writing-plans로 플랜을 쓰는 것**이다.

---

## 다음 세션이 가장 먼저 할 일

🔴 **반드시 (must)** — 컨텍스트 복원 순서:

1. **이 핸드오프 파일을 읽는다** (`docs/handoff/2026-07-17-1616-llm-comparison.md`)
2. **스펙 7절을 읽는다**: `docs/superpowers/specs/2026-07-13-ocr-llm-quality-harness-design.md` 의 7절(7.1~7.4) + 8절(미해결 확인 항목). 이것이 LLM 비교 실험의 확정 설계다.
3. **직전 실측 결론을 읽는다**: `docs/bench/2026-07-17-preprocess-ab-2010.md` (하네스 사용법 + 라벨 한계 + 재현 메타 패턴이 그대로 재사용됨)
4. **7.1 리팩터 대상 코드를 확인한다**: `img2txt/backends/cli.py:58` (모델명 하드코딩 `-m gpt-5.5`), `cli.py:36` `correct_batch(self, paragraphs, model)` — model 파라미터가 "미사용"으로 무시됨(cli.py:41 주석)
5. **git 상태 확인**: `git status && git log --oneline -6` (현재 HEAD `0672c21`, tracked clean)
6. **writing-plans 스킬로 7절 구현 플랜 작성** → 사용자 승인 → subagent-driven-development로 실행

---

## 작업 컨텍스트

### 사용자 원본 요청 (이번 세션 흐름)

1. 최신 PR/커밋/설계 문서로 진행상황 파악
2. 07-13 문서 3종 커밋 승인 + OCR 품질 하네스 subagent-driven 구현 (→ PR #8)
3. 전처리 실험 인프라 구현 (→ PR #9)
4. AI Hub 데이터 반입 + 실측 (→ PR #10)
5. 다음: "스펙 7절 LLM 비교 플랜 시작" (이 핸드오프의 대상)

### 사용자 제약-금지사항 (반드시 준수)

🔴 **반드시 (must)**:
- 커밋/푸시는 사용자가 명시 요청할 때만 (이번 세션은 매번 명시 승인받음).
- 커밋은 feature 단위 분리, `git add .`/`-A`/`-u` 금지 — 화이트리스트 스테이징.
- 스코프 밖 untracked 커밋 금지: `.idea/`, `tobyteam/`, `docs/prototype/img2txt-web/package-lock.json`, `docs/handoff/2026-07-12-0028-*`, `docs/review/pr-review-9-agy-*`(빈 파일), `bench_data/`(gitignore됨).
- 오케스트레이션: 실제 구현은 서브에이전트 위임(메인은 판단/계획/종합), 메인 코드 파일 직접 수정 턴당 2개 제한. 단 macOS Apple Vision 실OCR 실행은 컨트롤러(메인)가 직접 수행 — CI/서브에이전트에서 못 돌기 때문.
- 문서/설명은 한국어(기술 용어 영어 병기). 초급 개발자 눈높이.
- **외부 전송 컴플라이언스**: AI Hub 데이터를 외부 LLM(codex/OpenAI)에 보내는 것은 스펙 8절 확인 사항. 데이터 국외 반출 제한 문구가 약관에 있음 — LLM 비교 실험은 이 데이터로 보정 품질을 재므로, 실측 전 "AI Hub 데이터의 외부 LLM 전송 허용 여부"를 반드시 확인해야 한다 (블로커 #1).

---

## Plan / Design 인덱스

| 단계 | 문서 | 상태 |
|------|------|------|
| Spec (LLM 비교) | `docs/superpowers/specs/2026-07-13-ocr-llm-quality-harness-design.md` 7절 | ✅ 확정 설계 (플랜의 입력) |
| Plan (LLM 비교) | 없음 — **다음 세션에서 writing-plans로 작성** | ⏳ 미착수 |
| 로드맵 상위 | `docs/superpowers/specs/2026-07-12-public-service-roadmap-design.md` (서브프로젝트 B = LLM 보정 API) | 참고 |
| 직전 실측 결론 | `docs/bench/2026-07-17-preprocess-ab-2010.md` | ✅ 완료 |

---

## 코드 변경 상태 (git)

- 현재 브랜치: `main`, HEAD `0672c21`, **tracked working tree clean** (이번 세션 작업 전부 머지+푸시 완료)
- Uncommitted: 없음
- untracked: 위 "제약-금지사항"의 스코프 밖 목록만 (의도적 제외)

### 이번 세션 머지 완료 (모두 origin/main)

| SHA | 내용 |
|-----|------|
| `6357538` | PR #8 — OCR 품질 하네스 (CER/WER 3지점 채점 CLI) |
| `501cc33` | PR #9 — 전처리 인프라 (레버 3종 + 실행 메타) |
| `eb0fe00` | PR #10 — AI Hub 라벨 어댑터 + 전처리 A/B 실측 |
| `0672c21` | PR #10 리뷰 리포트 + progress 일지 |

---

## 결정 사항 (Decisions) — 뒤집지 말 것

| # | 결정 | 근거 | 누가 |
|---|------|------|------|
| 1 | 전처리 레버 3종 일괄 기본 적용 안 함, baseline 유지 | 4세트 실측: deskew는 품질 따라 개선/악화 뒤집힘(b1980 +0.71%p 악화), contrast/upscale 기각 | 합의(실측 근거) |
| 2 | 절대 CER(17~53%)은 라벨 정렬 한계로 과대추정, 상대 비교만 유효(그것도 잠정) | 원본 대조로 라벨 토큰 누락/어순 차이 확인. Codex 리뷰 반영해 "잠정 관찰"로 강등 | 합의 |
| 3 | LLM 비교는 브레인스토밍 생략, 스펙 7절이 이미 상세 설계라 바로 writing-plans | 7.1~7.4가 리팩터/구성/판정규칙/모델검증까지 확정 | 판단 |
| 4 | LLM 모델 후보: 앵커 gpt-5.5, 후보 gpt-5.6-luna / gpt-5.4-mini (실호출 검증 전 확정 아님) | 스펙 7.2/7.4. gpt-5.5-mini는 실재 안 함 | 스펙 |
| 5 | 라벨 어댑터는 Bbox id순 공백 join (줄바꿈 미복원) | normalize_strict가 공백류 접어 채점 영향 없음 | 구현 |

---

## 블로커 - 미해결 이슈 (Blockers)

| # | 이슈 | 영향 | 다음 시도 |
|---|------|------|----------|
| 1 | ⚠️ AI Hub 데이터의 외부 LLM(codex) 전송 허용 여부 미확인 | LLM 비교 실측이 이 데이터로 보정 품질을 재므로, 미확인 시 실측 착수 불가 | 스펙 8절 컴플라이언스 확인. 불가하면 보정 실험용 정답셋을 별도 확보하거나 로컬 LLM(ollama)만 사용 |
| 2 | ⚠️ 개별 모델명(gpt-5.6-luna, gpt-5.4-mini) 실재/호출 가능 여부 미검증 | 후보 확정 불가 | 플랜 7.1 리팩터 후 `codex exec -m gpt-5.6-luna` 실호출로 검증 (스펙 7.4) |
| 3 | 라벨 정렬 한계(순서 무관 지표 부재)가 절대 CER 신뢰도 병목 | 판정 정밀도 제한 | 단어 집합 기반 보조 지표 또는 bbox 좌표 재정렬 검토 (스펙 개정 필요, 별도 결정) |

---

## 다음 단계 (Next)

🔴 **MUST**:
- [ ] 블로커 #1 확인: AI Hub 데이터 외부 LLM 전송 허용 여부 (사용자 판단 필요) — **실측 착수 전 필수 게이트**
- [ ] writing-plans로 스펙 7절 구현 플랜 작성: 7.1 리팩터(cli.py 모델 파라미터화) → 하네스에 보정 backend 연결(현재 backend=None) → 탐색셋으로 허용 열화/부작용 상한 확정 → 홀드아웃 평가셋 판정 (7.3 탐색-평가 분리 준수)

🟡 **SHOULD**:
- [ ] 모델 식별자 실호출 검증 (블로커 #2) — 플랜 Task로 포함
- [ ] 부작용 지표 구현 확인: report.py에 이미 degraded_page_count 있음, 스펙 7.2가 요구하는 최악 악화폭/삭제-추가량/GUARD_BLOCKED 비율 추가 필요 여부 검토

🟢 **NICE-TO-DO**:
- [ ] 라벨 순서 무관 보조 지표 (블로커 #3)
- [ ] 나머지 세트 전처리 실측 확대 (전처리 트랙은 사실상 종료라 낮은 우선순위)

---

## 핵심 파일 경로 (Refs)

| 카테고리 | 경로 |
|---------|------|
| LLM 비교 스펙 | `docs/superpowers/specs/2026-07-13-ocr-llm-quality-harness-design.md` (7절) |
| 7.1 리팩터 대상 | `img2txt/backends/cli.py:36,58` (correct_batch model 미사용, gpt-5.5 하드코딩) |
| 보정 파이프라인 | `img2txt/corrector.py` (correct_paragraphs), `img2txt/backends/factory.py` |
| 하네스 CLI | `scripts/bench_ocr.py` (--label-format aihub, --preprocess, backend=None) |
| 채점/리포트 | `img2txt/bench/scoring.py`, `img2txt/bench/report.py` (degraded 지표) |
| 실측 데이터 | `bench_data/023.OCR 데이터(공공)/01-1.정식개방데이터/Validation/` (4세트, gitignore) |
| 직전 실측 결론 | `docs/bench/2026-07-17-preprocess-ab-2010.md` |
| SDD 원장 | `.superpowers/sdd/progress.md` (사이클별 커밋/판정 기록) |
| 핸드오프(이 파일) | `docs/handoff/2026-07-17-1616-llm-comparison.md` |

---

## 검증 상태

| 항목 | 상태 | 출처 |
|------|------|------|
| 전체 테스트 (pytest) | ✅ 205 passed, 1 skipped | 컨트롤러 직접 실행 (머지 후 main) |
| PR #8/#9/#10 | ✅ 전부 squash 머지 | gh pr merge |
| 실측 4세트 x 50p | ✅ error_status 0건, 원본 대조 1건 | bench_data/reports/ (gitignore) |
| LLM 비교 플랜 | ⚠️ 미착수 (다음 세션 MUST) | - |

---

## 재개 프롬프트 (다음 세션에 그대로 복사-붙여넣기)

```
이전 세션의 작업을 이어받습니다. 다음 핸드오프 파일을 먼저 읽고 컨텍스트를 복원해주세요:

/Users/joel.silver/Workspace/gitroom/python/img2txt/docs/handoff/2026-07-17-1616-llm-comparison.md

복원 순서:
1. 위 핸드오프 파일 전체를 읽는다
2. 스펙 7절(docs/superpowers/specs/2026-07-13-ocr-llm-quality-harness-design.md 7.1~7.4, 8절)과 직전 실측 결론(docs/bench/2026-07-17-preprocess-ab-2010.md)을 읽는다
3. git status, git log --oneline -6으로 현재 상태 확인 (HEAD 0672c21, main, clean)
4. 핸드오프의 "다음 단계 MUST"부터 시작 — 먼저 블로커 #1(AI Hub 외부 LLM 전송 허용) 확인 질문을 사용자에게 던지고, 그다음 writing-plans로 스펙 7절 구현 플랜 작성
5. 사용자 제약-금지사항(커밋 정책, 스코프 밖 파일 제외, 오케스트레이션 위임, 실OCR은 컨트롤러 직접) 준수
6. 결정 사항 표(전처리 baseline 유지, 절대 CER 과대추정, 모델 후보)는 뒤집지 않음

진행 전에 핸드오프를 읽었음을 확인하고, 블로커 #1 확인 질문부터 던져 시작해주세요.
```

---

✅ 핸드오프 메모 작성 완료. 다음 세션은 위 재개 프롬프트로 시작.
