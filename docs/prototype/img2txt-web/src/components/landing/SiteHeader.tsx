import { useState } from "react";
import { Link } from "react-router-dom";
import { ScanText, Menu, X } from "lucide-react";
import ThemeToggle from "../ThemeToggle";

export default function SiteHeader() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-zinc-200 dark:border-zinc-800 bg-white/80 dark:bg-zinc-950/80 backdrop-blur">
      <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2 font-semibold text-zinc-900 dark:text-zinc-50">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-accent-500 text-white">
            <ScanText size={16} />
          </span>
          img2txt
        </Link>

        <nav className="hidden sm:flex items-center gap-6 text-sm text-zinc-500 dark:text-zinc-400">
          <a href="#features" className="hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors">기능</a>
          <a href="#pricing" className="hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors">가격</a>
          <a href="#faq" className="hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors">FAQ</a>
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link
            to="/upload"
            className="hidden sm:inline-flex rounded-lg bg-accent-500 hover:bg-accent-600 text-white px-3.5 py-2 text-sm font-medium transition-colors"
          >
            무료로 시작
          </Link>
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="sm:hidden inline-flex h-9 w-9 items-center justify-center rounded-lg border border-zinc-200 dark:border-zinc-800 text-zinc-500"
            aria-label="메뉴"
          >
            {open ? <X size={16} /> : <Menu size={16} />}
          </button>
        </div>
      </div>

      {open && (
        <nav className="sm:hidden border-t border-zinc-100 dark:border-zinc-800 px-4 py-3 flex flex-col gap-3 text-sm">
          <a href="#features" onClick={() => setOpen(false)} className="text-zinc-600 dark:text-zinc-300">기능</a>
          <a href="#pricing" onClick={() => setOpen(false)} className="text-zinc-600 dark:text-zinc-300">가격</a>
          <a href="#faq" onClick={() => setOpen(false)} className="text-zinc-600 dark:text-zinc-300">FAQ</a>
          <Link
            to="/upload"
            className="rounded-lg bg-accent-500 text-white px-3.5 py-2 text-sm font-medium text-center"
          >
            무료로 시작
          </Link>
        </nav>
      )}
    </header>
  );
}
