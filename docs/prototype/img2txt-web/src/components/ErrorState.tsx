import { AlertTriangle } from "lucide-react";

export default function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-red-100 dark:border-red-500/20 bg-red-50/60 dark:bg-red-500/5 py-16 px-6 text-center">
      <AlertTriangle size={26} className="text-red-400" />
      <p className="text-sm font-medium text-red-600 dark:text-red-400">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded-lg border border-red-200 dark:border-red-500/30 px-3 py-1.5 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-100/60 dark:hover:bg-red-500/10 transition-colors"
        >
          다시 시도
        </button>
      )}
    </div>
  );
}
