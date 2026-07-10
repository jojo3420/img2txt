# Progress

## 2026-07-10 - CLI 배치 보정 no-op 결함 수정 (센티넬 재분리 프로토콜)
- 상태: 완료
- 완료한 일: CLI 백엔드 `correct_batch`가 교정 결과를 응답에서 추출 못 해 원문을 그대로 반환하던 no-op을 제거. 개수 요약 마커(`[CORRECT:n,KEPT:m,GUARD:g]`)를 폐기하고 스펙 4.2대로 `===문단 N===` 센티넬 헤더로 응답을 재분리하는 방식으로 교체. `tests/backends/` 18개 통과.
- 커밋/PR: `a35b429` fix: cli 배치 no-op 제거 — 센티넬 재분리 프로토콜(스펙 4.2). PR 없음
- 결정사항: 재분리 구분자로 고유 센티넬(A2) 채택. 스펙 문구 그대로 번호 마커 재사용(A1)은 본문에 번호 섞이면 오분리 위험이라 기각. 개수 요약 마커는 모델이 자기보고할 수 없는 값(가드 판정은 corrector.py 로컬 책임)이라 유지 안 하고 완전 폐기 — escalation 원안(개수 마커 가드용 유지)과 갈린 지점.
- 남은 일: (1) corrector 오케스트레이션(배치+가드) 구현 — 이 센티넬 프로토콜 + 로컬 가드 전제, 아직 브리프 없음. (2) 원격 푸시 여부 결정.
- 관련 문서: docs/superpowers/specs/2026-07-08-img2txt-web-service-design.md (4.2 배칭), .superpowers/sdd/task-1-brief.md-task-3-brief.md (센티넬로 동기화 완료, gitignore 대상이라 미추적)
