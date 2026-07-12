export type FileStatus = "waiting" | "ocr" | "correcting" | "done" | "failed";
export type JobStatus = "queued" | "processing" | "done" | "failed";

export interface PageFile {
  id: string;
  filename: string; // 예: "page-2.jpg" — 파일명 마지막 숫자로 자연 정렬
  pageNumber: number;
  sizeBytes: number;
  status: FileStatus;
  previewText?: string; // 추출 텍스트 앞부분 (완료 시)
  error?: string; // 실패 사유 (실패 시)
}

export interface JobSummary {
  successPages: number;
  failedPages: number;
  removedFooterLines: number;
  // 보정을 켰을 때만 채워짐
  corrected?: number;
  kept?: number;
  guardBlocked?: number;
}

export interface JobOptions {
  correct: boolean; // LLM 보정까지 실행할지 여부
  backend: "codex" | "claude"; // OCR/보정 백엔드
  model: string; // 읽기 전용, 백엔드에서 파생 (예: "gpt-5.5", "claude")
}

export interface Job {
  id: string;
  createdAt: string;
  options: JobOptions;
  status: JobStatus;
  files: PageFile[];
  summary?: JobSummary;
  phase: "ocr" | "correcting";
  correction: { done: number; total: number } | null;
  correctionError: string | null;
  correctedStale: boolean;
}

export interface PageDetail {
  pageNumber: number;
  filename: string;
  original: string;
  corrected?: string;
}

export interface CreateJobResponse {
  id: string;
}

// ── 랜딩 페이지: 구매 의사(스모크 테스트) ─────────────────────────────
export interface IntentRequest {
  email: string;
  plan: "free" | "subscription";
}

export interface IntentResponse {
  ok: boolean;
}
