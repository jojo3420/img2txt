import { useState } from "react";
import { useParams } from "react-router-dom";
import { ChevronDown, ChevronRight, Download, FileWarning } from "lucide-react";
import { downloadBook, downloadPage, useJob, usePage } from "../api/client";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import Button from "../components/Button";
import Spinner from "../components/Spinner";
import { SkeletonList } from "../components/Skeleton";

export default function ResultPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { data: job, isLoading, isError, error, refetch } = useJob(jobId);
  const [expanded, setExpanded] = useState<number | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-24 rounded-xl bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
        <SkeletonList rows={5} />
      </div>
    );
  }

  if (isError || !job) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : "결과를 불러오지 못했습니다."}
        onRetry={() => refetch()}
      />
    );
  }

  const summary = job.summary;
  const doneFiles = job.files
    .filter((f) => f.status === "done")
    .sort((a, b) => a.pageNumber - b.pageNumber);

  return (
    <div className="space-y-8">
      <div className="space-y-1.5">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">결과</h1>
        <p className="text-sm text-zinc-400 dark:text-zinc-500 font-mono">
          잡 ID: {job.id}
        </p>
      </div>

      {summary && summary.failedPages > 0 && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 dark:bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
          <FileWarning size={16} className="shrink-0" />
          {summary.failedPages}개 페이지는 처리에 실패해 결과에 포함되지 않았습니다.
        </div>
      )}

      {summary ? (
        <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <SummaryStat label="성공 페이지" value={summary.successPages} />
          <SummaryStat label="실패 페이지" value={summary.failedPages} tone="warn" />
          <SummaryStat label="제거한 꼬리말 줄" value={summary.removedFooterLines} />
          {job.options.correct && summary.corrected !== undefined && (
            <SummaryStat label="보정된 문단" value={summary.corrected} />
          )}
        </section>
      ) : (
        <EmptyState title="요약 정보가 없습니다" />
      )}

      {job.options.correct && summary && (
        <section className="grid grid-cols-3 gap-3 rounded-xl border border-zinc-100 dark:border-zinc-800 p-4">
          <SummaryStat label="보정" value={summary.corrected ?? 0} compact />
          <SummaryStat label="유지" value={summary.kept ?? 0} compact />
          <SummaryStat label="가드 차단" value={summary.guardBlocked ?? 0} compact />
        </section>
      )}

      <section className="flex flex-wrap gap-3">
        <Button
          variant="secondary"
          icon={<Download size={15} />}
          onClick={() => downloadBook(job.id, "book")}
        >
          book.txt (원본 연속본)
        </Button>
        {job.options.correct && (
          <Button
            icon={<Download size={15} />}
            onClick={() => downloadBook(job.id, "corrected")}
          >
            book_corrected.txt (보정본)
          </Button>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          페이지별 결과 ({doneFiles.length}장)
        </h2>
        {doneFiles.length === 0 ? (
          <EmptyState
            title="성공한 페이지가 없습니다"
            description="모든 페이지 처리가 실패했습니다."
          />
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800 rounded-xl border border-zinc-100 dark:border-zinc-800 overflow-hidden">
            {doneFiles.map((f) => (
              <PageRow
                key={f.id}
                jobId={job.id}
                pageNumber={f.pageNumber}
                previewText={f.previewText}
                hasCorrected={job.options.correct}
                expanded={expanded === f.pageNumber}
                onToggle={() =>
                  setExpanded((cur) => (cur === f.pageNumber ? null : f.pageNumber))
                }
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function SummaryStat({
  label,
  value,
  tone = "default",
  compact = false,
}: {
  label: string;
  value: number;
  tone?: "default" | "warn";
  compact?: boolean;
}) {
  return (
    <div
      className={
        compact
          ? "text-center"
          : "rounded-xl border border-zinc-100 dark:border-zinc-800 p-4"
      }
    >
      <p
        className={`text-2xl font-semibold tabular-nums ${
          tone === "warn" && value > 0
            ? "text-red-500"
            : "text-zinc-900 dark:text-zinc-50"
        }`}
      >
        {value}
      </p>
      <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-0.5">{label}</p>
    </div>
  );
}

function PageRow({
  jobId,
  pageNumber,
  previewText,
  hasCorrected,
  expanded,
  onToggle,
}: {
  jobId: string;
  pageNumber: number;
  previewText?: string;
  hasCorrected: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const [tab, setTab] = useState<"original" | "corrected">(
    hasCorrected ? "corrected" : "original"
  );
  const { data: detail, isLoading, isError, refetch } = usePage(
    jobId,
    expanded ? pageNumber : null
  );

  return (
    <li className="bg-white dark:bg-zinc-900/40">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/40 transition-colors"
      >
        {expanded ? (
          <ChevronDown size={14} className="shrink-0 text-zinc-400" />
        ) : (
          <ChevronRight size={14} className="shrink-0 text-zinc-400" />
        )}
        <span className="w-7 shrink-0 text-xs font-mono text-zinc-300 dark:text-zinc-600 text-right">
          {pageNumber}
        </span>
        <span className="flex-1 min-w-0 truncate text-sm text-zinc-500 dark:text-zinc-400">
          {previewText || "미리보기 없음"}
        </span>
        <span
          role="button"
          tabIndex={0}
          onClick={(e) => {
            e.stopPropagation();
            downloadPage(jobId, pageNumber);
          }}
          className="shrink-0 inline-flex items-center gap-1 rounded-lg border border-zinc-200 dark:border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <Download size={12} />
          page-{String(pageNumber).padStart(3, "0")}.txt
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 pl-14">
          {isLoading && (
            <div className="flex items-center gap-2 py-6 text-sm text-zinc-400">
              <Spinner size={16} />
              불러오는 중...
            </div>
          )}
          {isError && (
            <ErrorState message="페이지를 불러오지 못했습니다." onRetry={() => refetch()} />
          )}
          {detail && (
            <div className="space-y-3">
              {hasCorrected && detail.corrected && (
                <div className="inline-flex rounded-lg border border-zinc-200 dark:border-zinc-700 p-0.5 text-xs">
                  <button
                    type="button"
                    onClick={() => setTab("original")}
                    className={`rounded-md px-3 py-1 font-medium transition-colors ${
                      tab === "original"
                        ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                        : "text-zinc-500"
                    }`}
                  >
                    원본
                  </button>
                  <button
                    type="button"
                    onClick={() => setTab("corrected")}
                    className={`rounded-md px-3 py-1 font-medium transition-colors ${
                      tab === "corrected"
                        ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                        : "text-zinc-500"
                    }`}
                  >
                    보정본
                  </button>
                </div>
              )}
              <pre className="whitespace-pre-wrap break-keep rounded-lg bg-zinc-50 dark:bg-zinc-900 p-4 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300 font-sans">
                {tab === "corrected" && detail.corrected ? detail.corrected : detail.original}
              </pre>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
