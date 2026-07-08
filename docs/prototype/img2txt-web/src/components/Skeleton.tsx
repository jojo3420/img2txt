export default function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-zinc-100 dark:bg-zinc-800 ${className}`}
    />
  );
}

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 rounded-lg border border-zinc-100 dark:border-zinc-800 px-4 py-3"
        >
          <Skeleton className="h-4 w-8" />
          <Skeleton className="h-4 flex-1 max-w-xs" />
          <Skeleton className="h-5 w-16 rounded-full ml-auto" />
        </div>
      ))}
    </div>
  );
}
