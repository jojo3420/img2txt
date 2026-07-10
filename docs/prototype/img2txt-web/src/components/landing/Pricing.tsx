import { Link } from "react-router-dom";
import { Check } from "lucide-react";

export default function Pricing({ onOpenIntent }: { onOpenIntent: () => void }) {
  return (
    <section id="pricing" className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-16 border-t border-zinc-100 dark:border-zinc-800">
      <div className="max-w-lg space-y-3 mb-10">
        <h2 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">가격</h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          변환은 무료입니다. 오탈자 보정까지 필요할 때만 구독하세요.
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-5 max-w-2xl">
        {/* 무료 플랜 */}
        <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 p-6 space-y-5">
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">무료</h3>
            <p className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">
              0원
            </p>
          </div>
          <ul className="space-y-2 text-sm text-zinc-500 dark:text-zinc-400">
            <li className="flex items-center gap-2">
              <Check size={14} className="text-accent-500 shrink-0" />
              이미지 → 텍스트 변환
            </li>
            <li className="flex items-center gap-2">
              <Check size={14} className="text-accent-500 shrink-0" />
              꼬리말 제거 · 문단 복원
            </li>
            <li className="flex items-center gap-2">
              <Check size={14} className="text-accent-500 shrink-0" />
              페이지별 + 연속본 다운로드
            </li>
          </ul>
          <Link
            to="/upload"
            className="block w-full text-center rounded-lg border border-zinc-200 dark:border-zinc-700 py-2.5 text-sm font-medium text-zinc-700 dark:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
          >
            무료로 시작
          </Link>
        </div>

        {/* 구독 플랜 */}
        <div className="relative rounded-2xl border-2 border-accent-500 p-6 space-y-5">
          <span className="absolute -top-3 left-6 rounded-full bg-accent-500 text-white text-xs font-medium px-3 py-1">
            추천
          </span>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
              구독
            </h3>
            <p className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">
              월 4,900원
            </p>
          </div>
          <ul className="space-y-2 text-sm text-zinc-500 dark:text-zinc-400">
            <li className="flex items-center gap-2">
              <Check size={14} className="text-accent-500 shrink-0" />
              무료 플랜의 모든 기능
            </li>
            <li className="flex items-center gap-2">
              <Check size={14} className="text-accent-500 shrink-0" />
              로컬 LLM(qwen3:14b) 오탈자·띄어쓰기 보정
            </li>
            <li className="flex items-center gap-2">
              <Check size={14} className="text-accent-500 shrink-0" />
              보정본 + 전/후 대조 로그
            </li>
          </ul>
          <button
            type="button"
            onClick={onOpenIntent}
            className="block w-full text-center rounded-lg bg-accent-500 hover:bg-accent-600 text-white py-2.5 text-sm font-medium transition-colors"
          >
            결제하기
          </button>
        </div>
      </div>
    </section>
  );
}
