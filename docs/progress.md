# Progress

## 2026-07-10 - CLI 배치 no-op 수정 + PR #1 + Codex 리뷰 반영
- 상태: 완료
- 완료한 일: (1) CLI 백엔드 `correct_batch`의 no-op 제거 — 개수 요약 마커(`[CORRECT:n,KEPT:m,GUARD:g]`) 폐기, 스펙 4.2대로 `===문단 N===` 센티넬 헤더로 응답 재분리. (2) PR #1 생성 후 Codex xhigh 리뷰 → 데이터 손실 버그 수정: CLI 실패(returncode!=0)-빈 출력-빈 세그먼트가 원문을 빈 문자열로 덮어쓰던 것을 원문 유지로 차단, Ollama 빈응답 방어, 프롬프트 `{index}` 리터럴 제거, 단건 폴백 보정 프롬프트 추가. `tests/backends/` 28개 통과.
- 커밋/PR: `5cc5b53`(no-op 수정) + `20e6926`(리뷰 반영). PR #1 https://github.com/jojo3420/img2txt/pull/1 (base main, 10커밋)
- 결정사항: (1) 재분리 구분자 고유 센티넬(A2) 채택, 개수 요약 마커 완전 폐기(모델이 자기보고 불가). (2) 리뷰 지적 C3(Ollama 길이 가드)는 무비판 수용 안 함 — 가드는 스펙 4.1/4.2상 corrector 오케스트레이션(T5) 책임이라 백엔드 대신 T5로 이관, 백엔드엔 빈응답 방어만.
- 남은 일: (1) corrector 오케스트레이션(배치+가드) 구현 — 센티넬 프로토콜 + 로컬 가드 전제, 아직 브리프 없음. (2) ⚠️ 실제 claude/codex CLI로 배치 보정 end-to-end 검증(목 테스트만으로 부족). (3) PR #1 머지.
- 관련 문서: docs/superpowers/specs/2026-07-08-img2txt-web-service-design.md (4.1/4.2), .superpowers/sdd/task-1-brief.md-task-3-brief.md (센티넬로 동기화, gitignore 미추적), Codex 리뷰 로그(세션 내)
