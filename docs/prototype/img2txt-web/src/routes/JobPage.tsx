import { useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useJob, useRetryFile } from "../api/client";
import ProgressBar from "../components/ProgressBar";
import StatusBadge from "../components/StatusBadge";
import ErrorState from "../components/ErrorState";
import Button from "../components/Button";
import { SkeletonList } from "../components/Skeleton";
import { formatBytes, formatDuration } from "../lib/format";

const SECONDS_PER_FILE_OCR = 20;
const SECONDS_PER_FILE_CORRECT = 60;
const CONCURRENCY = 2;

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { data: job, isLoading, isError, error, refetch } = useJob(jobId);
  const retry = useRetryFile(jobId ?? "");

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="h-5 w-40 rounded bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
          <div className="h-2 w-full rounded-full bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
        </div>
        <SkeletonList rows={5} />
      </div>
    );
  }

  if (isError || !job) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : "잡 정보를 불러오지 못했습니다."}
        onRetry={() => refetch()}
      />
    );
  }

  const total = job.files.length;
  const doneCount = job.files.filter((f) => f.status === "done").length;
  const failedCount = job.files.filter((f) => f.status === "failed").length;
  const remaining = job.files.filter(
    (f) => f.status === "waiting" || f.status === "ocr" || f.status === "correcting"
  ).length;
  const percent = total === 0 ? 0 : ((doneCount + failedCount) / total) * 100;

  const perFileSeconds = job.options.correct
    ? SECONDS_PER_FILE_OCR + SECONDS_PER_FILE_CORRECT
    : SECONDS_PER_FILE_OCR;
  const estRemainingSeconds = (remaining / CONCURRENCY) * perFileSeconds;

  const isFinished = job.status === "done" || job.status === "failed";
  const canViewResult = job.status === "done" && doneCount > 0;

  return (
    <div className="space-y-8">
      <div className="space-y-1.5">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">처리 중</h1>
        <p className="text-sm text-zinc-400 dark:text-zinc-500 font-mono">
          잡 ID: {job.id}
        </p>
      </div>

      <section className="space-y-3 rounded-xl border border-zinc-100 dark:border-zinc-800 p-5">
        <div className="flex items-baseline justify-between">
          <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            {total}개 중 {doneCount}개 완료
            {failedCount > 0 && (
              <span className="text-red-500"> · {failedCount}개 실패</span>
            )}
          </p>
          {!isFinished && (
            <p className="text-xs text-zinc-400 dark:text-zinc-500">
              남은 시간 {formatDuration(estRemainingSeconds)}
            </p>
          )}
        </div>
        <ProgressBar value={percent} />
      </section>

      {failedCount > 0 && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 dark:bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
          <AlertTriangle size={16} className="shrink-0" />
          {failedCount}개 페이지 처리에 실패했습니다. 아래 목록에서 재시도할 수 있어요.
        </div>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          페이지별 상태
        </h2>
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800 rounded-xl border border-zinc-100 dark:border-zinc-800 overflow-hidden">
          {job.files.map((f) => (
            <li
              key={f.id}
              className="flex items-center gap-3 px-4 py-3 bg-white dark:bg-zinc-900/40"
            >
              <span className="w-7 shrink-0 text-xs font-mono text-zinc-300 dark:text-zinc-600 text-right">
                {f.pageNumber}
              </span>
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm text-zinc-700 dark:text-zinc-300">
                  {f.filename}
                </p>
                {f.status === "failed" && f.error && (
                  <p className="truncate text-xs text-red-500 mt-0.5">{f.error}</p>
                )}
              </div>
              <span className="shrink-0 text-xs text-zinc-400 dark:text-zinc-500 font-mono hidden sm:inline">
                {formatBytes(f.sizeBytes)}
              </span>
              <StatusBadge status={f.status} />
              {f.status === "failed" && (
                <button
                  type="button"
                  onClick={() => retry.mutate(f.id)}
                  disabled={retry.isPending}
                  className="shrink-0 inline-flex items-center gap-1 rounded-lg border border-zinc-200 dark:border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-600 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors disabled:opacity-40"
                >
                  <RefreshCw size={12} />
                  재시도
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <div className="flex justify-end">
        <Button disabled={!canViewResult} onClick={() => navigate(`/jobs/${job.id}/result`)}>
          결과 보기
        </Button>
      </div>
    </div>
  );
}
