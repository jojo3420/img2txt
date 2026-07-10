import { Link } from "react-router-dom";
import { CreditCard } from "lucide-react";

export default function CtaBanner({ onOpenIntent }: { onOpenIntent: () => void }) {
  return (
    <section className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-16 border-t border-zinc-100 dark:border-zinc-800">
      <div className="rounded-2xl bg-zinc-900 dark:bg-zinc-900 border border-zinc-800 px-6 sm:px-10 py-12 text-center space-y-5">
        <h2 className="text-2xl font-semibold text-white">
          지금 바로 첫 페이지를 변환해보세요
        </h2>
        <p className="text-sm text-zinc-400 max-w-md mx-auto">
          변환은 무료입니다. 보정까지 필요하면 구독 알림을 미리 신청하세요.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/upload"
            className="rounded-lg bg-accent-500 hover:bg-accent-600 text-white px-5 py-3 text-sm font-medium transition-colors"
          >
            무료로 시작하기
          </Link>
          <button
            type="button"
            onClick={onOpenIntent}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-5 py-3 text-sm font-medium text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <CreditCard size={15} />
            결제하기
          </button>
        </div>
      </div>
    </section>
  );
}
