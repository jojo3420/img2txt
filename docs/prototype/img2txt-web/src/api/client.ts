import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CreateJobResponse, IntentRequest, IntentResponse, Job, PageDetail } from "./types";

// TODO(실제 연동): 아래 API_BASE 를 FastAPI 서버 주소로 교체하세요.
// 지금은 MSW(src/mocks)가 이 상대 경로 요청을 가로채 목 데이터로 응답합니다.
const API_BASE = "/api";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `요청이 실패했습니다 (${res.status})`;
    try {
      const body = await res.json();
      if (body?.message) message = body.message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return res.json();
}

export interface CreateJobInput {
  files: File[];
  correct: boolean;
  backend: "codex" | "claude";
}

async function createJob(input: CreateJobInput): Promise<CreateJobResponse> {
  const formData = new FormData();
  input.files.forEach((f) => formData.append("files", f));
  formData.append("correct", String(input.correct));
  formData.append("backend", input.backend);

  const res = await fetch(`${API_BASE}/jobs`, { method: "POST", body: formData });
  return jsonOrThrow<CreateJobResponse>(res);
}

export function useCreateJob() {
  return useMutation({ mutationFn: createJob });
}

async function fetchJob(jobId: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  return jsonOrThrow<Job>(res);
}

const ACTIVE_STATUSES = new Set(["queued", "processing"]);

export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => fetchJob(jobId as string),
    enabled: !!jobId,
    // 처리 중일 때만 2초 간격으로 폴링, 완료/실패하면 폴링 중지
    refetchInterval: (query) => {
      const data = query.state.data as Job | undefined;
      if (!data) return 2000;
      return ACTIVE_STATUSES.has(data.status) ? 2000 : false;
    },
  });
}

async function retryFile(jobId: string, fileId: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/retry/${fileId}`, {
    method: "POST",
  });
  return jsonOrThrow<Job>(res);
}

export function useRetryFile(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (fileId: string) => retryFile(jobId, fileId),
    onSuccess: (job) => {
      queryClient.setQueryData(["job", jobId], job);
    },
  });
}

async function fetchPage(jobId: string, pageNumber: number): Promise<PageDetail> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/pages/${pageNumber}`);
  return jsonOrThrow<PageDetail>(res);
}

export function usePage(jobId: string, pageNumber: number | null) {
  return useQuery({
    queryKey: ["job", jobId, "page", pageNumber],
    queryFn: () => fetchPage(jobId, pageNumber as number),
    enabled: pageNumber !== null,
  });
}

// ── 랜딩 페이지: 구매 의사 등록 (스모크 테스트) ───────────────────────
// TODO: 실제 분석 도구(GA, Amplitude 등) 연결.
export function trackIntentClick(_plan: IntentRequest["plan"]) {
  // Stub for analytics integration
}

async function submitIntent(input: IntentRequest): Promise<IntentResponse> {
  const res = await fetch(`${API_BASE}/intent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return jsonOrThrow<IntentResponse>(res);
}

export function useSubmitIntent() {
  return useMutation({ mutationFn: submitIntent });
}
