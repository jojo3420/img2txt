# img2txt — 웹 프런트엔드

한글 책 스캔 이미지(jpg/jpeg)를 OCR로 읽고, 꼬리말 제거·문단 복원을 거쳐 읽기 좋은
텍스트로 만드는 개인용 도구의 프런트엔드입니다. 지금은 백엔드 없이 **MSW(Mock
Service Worker)**로 API를 흉내 내며 동작합니다. 실제 FastAPI 백엔드가 준비되면
`src/mocks` 를 지우고 `fetch` 대상만 바꾸면 되도록 설계했습니다.

## 실행 방법

```bash
npm install   # postinstall 스크립트가 자동으로 msw init public --save 실행
npm run dev
```

`http://localhost:5173/upload` 에서 시작합니다.

## 스택

- Vite + React 18 + TypeScript
- Tailwind CSS v3 (유틸리티 클래스, 다크 모드는 `class` 전략)
- lucide-react (아이콘)
- react-router-dom v6 (라우팅)
- @tanstack/react-query (서버 상태 + 폴링)
- msw (목 API — 실제 API 계약을 그대로 흉내)

## 라우트

| 경로 | 설명 |
|---|---|
| `/` | 랜딩 페이지 (홍보 + 결제 의사 검증용 스모크 테스트) |
| `/upload` | 이미지 업로드, 보정 옵션 선택, 변환 시작 |
| `/jobs/:jobId` | 잡 진행 상태 (2초 폴링), 실패 페이지 재시도 |
| `/jobs/:jobId/result` | 요약, 전체/페이지별 다운로드, 원본·보정본 비교 |

## 랜딩 페이지 (`/`) — 구매 의사 스모크 테스트

아직 결제 기능은 없습니다. '결제하기' 버튼은 실제 결제창 대신 이메일을 받는
사전 관심 등록 모달(`IntentModal`)을 띄우고 `POST /api/intent` 로 기록합니다.

**중요:** 이 데이터는 지금 MSW로만 처리됩니다 — MSW는 방문자의 **브라우저 안에서만**
동작하는 목 서버라, 실제로 이메일이 개발자에게 전달되지 않습니다. 게시 후 실제로
방문자의 구매 의사를 수집하려면 `/api/intent` 를 받는 진짜 백엔드(FastAPI 등)를
반드시 구현해야 합니다. 관련 코드에는 `TODO: 실제 백엔드 연동` 주석을 남겨두었습니다.

분석 이벤트(`trackIntentClick`)도 현재는 `console.log` stub이며, 실제 분석 도구
연동 지점에 TODO 주석이 있습니다.

## API 계약 (`src/api/types.ts`, `src/mocks/handlers.ts`)

- `POST /api/jobs` — multipart(files[], correct, model) → `{ id }`
- `GET /api/jobs/:id` — Job 상태 (폴링마다 목 서버가 한 틱씩 진행 시뮬레이션)
- `POST /api/jobs/:id/retry/:fileId` — 실패한 페이지 재시도
- `GET /api/jobs/:id/pages/:n` — 페이지 원본/보정본 텍스트
- `GET /api/jobs/:id/pages/:n/download` — 페이지 단위 txt 다운로드
- `GET /api/jobs/:id/download?type=book|corrected` — 전체 연속본 다운로드

목 서버는 파일 2개를 동시 처리(concurrency=2)하는 것처럼 시뮬레이션하고,
페이지 번호가 9의 배수인 파일은 1회 실패하도록 만들어 실패/재시도 UI를
데모할 수 있게 했습니다. 실제 배포 전에는 `src/mocks/handlers.ts` 의 이런
데모용 로직을 제거하세요.

## 실제 FastAPI 백엔드로 교체하기

1. `src/main.tsx` 의 `enableMocking()` 블록(및 `src/mocks/` 폴더 전체)을 삭제
2. `src/api/client.ts` 상단의 `API_BASE` 를 실제 서버 주소로 변경
   (또는 Vite 프록시 `vite.config.ts` `server.proxy` 설정)
3. 컴포넌트/라우트 코드는 그대로 둡니다 — react-query 훅이 반환하는
   `Job` / `PageDetail` 타입 계약만 백엔드가 그대로 지키면 됩니다.
4. 잡 생성 시 이미지가 많으면 업로드 자체가 오래 걸릴 수 있으니,
   실제 연동 시 업로드 진행률(progress event)을 `useCreateJob` 에 추가하는 것을
   권장합니다 (현재는 생략).

각 위치에 `TODO(실제 연동)` 주석을 남겨두었습니다.

## 폴더 구조

```
src/
  api/          types.ts(계약 타입), client.ts(react-query 훅)
  components/   재사용 UI (Button, Toggle, StatusBadge, ProgressBar, EmptyState, ErrorState, Skeleton, ...)
  lib/          naturalSort.ts(파일명 자연 정렬), format.ts(용량/시간 포맷)
  mocks/        MSW handlers + 목 데이터
  routes/       UploadPage / JobPage / ResultPage
```

## 상태 완전성

목록/데이터가 있는 세 화면 모두 로딩(스켈레톤) · 빈 상태 · 에러(재시도 버튼) ·
정상 상태를 구현했고, 일부 페이지 실패가 섞였을 때는 경고 배너를 별도로 보여줍니다.
