import { CheckCircle2, Loader2, XCircle, Clock } from "lucide-react";
import type { FileStatus } from "../api/types";

const CONFIG: Record<
  FileStatus,
  { label: string; className: string; icon: "spin" | "clock" | "check" | "x" }
> = {
  waiting: {
    label: "대기",
    className: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
    icon: "clock",
  },
  ocr: {
    label: "OCR 처리중",
    className: "bg-accent-50 text-accent-600 dark:bg-accent-700/20 dark:text-accent-400",
    icon: "spin",
  },
  correcting: {
    label: "보정 처리중",
    className:
      "bg-violet-50 text-violet-600 dark:bg-violet-500/10 dark:text-violet-400",
    icon: "spin",
  },
  done: {
    label: "완료",
    className:
      "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400",
    icon: "check",
  },
  failed: {
    label: "실패",
    className: "bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400",
    icon: "x",
  },
};

export default function StatusBadge({ status }: { status: FileStatus }) {
  const cfg = CONFIG[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${cfg.className}`}
    >
      {cfg.icon === "spin" && <Loader2 size={12} className="animate-spin" />}
      {cfg.icon === "clock" && <Clock size={12} />}
      {cfg.icon === "check" && <CheckCircle2 size={12} />}
      {cfg.icon === "x" && <XCircle size={12} />}
      {cfg.label}
    </span>
  );
}
