import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

export default function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-zinc-200 dark:border-zinc-800 py-16 px-6 text-center">
      <div className="text-zinc-300 dark:text-zinc-700">{icon ?? <Inbox size={28} />}</div>
      <div className="space-y-1">
        <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">{title}</p>
        {description && (
          <p className="text-sm text-zinc-400 dark:text-zinc-500">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}
