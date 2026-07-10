import { useState } from "react";
import { X, Mail, CheckCircle2 } from "lucide-react";
import { trackIntentClick, useSubmitIntent } from "../api/client";
import type { IntentRequest } from "../api/types";

export default function IntentModal({
  plan,
  onClose,
}: {
  plan: IntentRequest["plan"];
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const submitIntent = useSubmitIntent();

  function validate(value: string): string | null {
    if (!value.trim()) return "이메일을 입력해주세요.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return "올바른 이메일 형식이 아니에요.";
    return null;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const err = validate(email);
    setFieldError(err);
    if (err) return;

    trackIntentClick(plan);
    submitIntent.mutate({ email, plan });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/40 dark:bg-black/60 px-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800 p-6 shadow-xl"
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-50">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-accent-50 dark:bg-accent-700/20 text-accent-600 dark:text-accent-400">
              <Mail size={15} />
            </span>
            <h3 className="font-semibold">
              {submitIntent.isSuccess ? "등록 완료" : "정식 출시 알림 받기"}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
          >
            <X size={18} />
          </button>
        </div>

        {submitIntent.isSuccess ? (
          <div className="space-y-4 text-center py-2">
            <CheckCircle2 size={32} className="mx-auto text-emerald-500" />
            <p className="text-sm text-zinc-600 dark:text-zinc-300">
              관심 감사합니다. 출시되면 이 메일로 알려드릴게요.
            </p>
            <button
              type="button"
              onClick={onClose}
              className="w-full rounded-lg bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 py-2.5 text-sm font-medium"
            >
              닫기
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              정식 출시 알림을 받고 먼저 사용해 보세요.
            </p>
            <p className="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 px-3 py-2 text-xs text-zinc-400 dark:text-zinc-500">
              지금은 사전 관심 등록 단계입니다. 실제 결제는 진행되지 않습니다.
            </p>
            <div>
              <input
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (fieldError) setFieldError(null);
                }}
                placeholder="you@example.com"
                disabled={submitIntent.isPending}
                className={`w-full rounded-lg border px-3 py-2.5 text-sm bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 outline-none focus:ring-2 focus:ring-accent-400 disabled:opacity-50 ${
                  fieldError
                    ? "border-red-300 dark:border-red-500/40"
                    : "border-zinc-200 dark:border-zinc-700"
                }`}
              />
              {fieldError && (
                <p className="mt-1 text-xs text-red-500">{fieldError}</p>
              )}
            </div>

            {submitIntent.isError && (
              <p className="text-xs text-red-500">
                {submitIntent.error instanceof Error
                  ? submitIntent.error.message
                  : "제출에 실패했습니다. 다시 시도해주세요."}
              </p>
            )}

            <button
              type="submit"
              disabled={submitIntent.isPending}
              className="w-full rounded-lg bg-accent-500 hover:bg-accent-600 text-white py-2.5 text-sm font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {submitIntent.isPending ? "제출 중..." : "알림 받기"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
