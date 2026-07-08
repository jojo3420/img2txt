export default function ProgressBar({
  value,
  className = "",
}: {
  value: number; // 0~100
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      className={`h-2 w-full rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden ${className}`}
    >
      <div
        className="h-full rounded-full bg-accent-500 transition-all duration-500 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
