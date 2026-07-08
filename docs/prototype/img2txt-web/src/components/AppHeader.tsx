import { Link, useLocation } from "react-router-dom";
import { ScanText } from "lucide-react";
import ThemeToggle from "./ThemeToggle";

export default function AppHeader() {
  const location = useLocation();
  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800">
      <div className="w-full max-w-4xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link
          to="/upload"
          className="flex items-center gap-2 font-semibold text-zinc-900 dark:text-zinc-50"
        >
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-accent-500 text-white">
            <ScanText size={16} />
          </span>
          <span>img2txt</span>
          <span className="hidden sm:inline text-xs font-normal text-zinc-400 dark:text-zinc-500">
            책 스캔 → 텍스트 변환
          </span>
        </Link>
        <div className="flex items-center gap-3">
          <span className="hidden sm:inline text-xs text-zinc-400 dark:text-zinc-500 font-mono">
            {location.pathname}
          </span>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
