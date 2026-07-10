# Progress

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
