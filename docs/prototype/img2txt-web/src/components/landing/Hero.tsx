import { Link } from "react-router-dom";
import { ArrowRight, CreditCard } from "lucide-react";

export default function Hero({ onOpenIntent }: { onOpenIntent: () => void }) {
  return (
    <section className="w-full max-w-5xl mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-16 grid gap-12 lg:grid-cols-2 lg:items-center">
      <div className="space-y-6">
        <span className="inline-flex items-center rounded-full bg-accent-50 dark:bg-accent-700/15 px-3 py-1 text-xs font-medium text-accent-600 dark:text-accent-400">
          한글 책 스캔 전용 변환기
        </span>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50 text-balance">
          스캔한 한글 책을
          <br />
          읽기 좋은 텍스트로
        </h1>
        <p className="text-base text-zinc-500 dark:text-zinc-400 leading-relaxed text-pretty max-w-md">
          페이지 번호·책 제목 같은 꼬리말을 자동으로 지우고, 끊긴 문단을 이어
          붙입니다. 로컬 LLM 보정까지 켜면 오탈자와 띄어쓰기도 함께 바로잡아요.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Link
            to="/upload"
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent-500 hover:bg-accent-600 text-white px-5 py-3 text-sm font-medium transition-colors"
          >
            무료로 시작하기
            <ArrowRight size={15} />
          </Link>
          <button
            type="button"
            onClick={onOpenIntent}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 px-5 py-3 text-sm font-medium text-zinc-600 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
          >
            <CreditCard size={15} />
            결제하기
          </button>
        </div>
        <p className="text-xs text-zinc-400 dark:text-zinc-500">
          지금은 사전 관심 등록 단계입니다 · 실제 결제는 진행되지 않습니다
        </p>
      </div>

      <BeforeAfterMock />
    </section>
  );
}

function BeforeAfterMock() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 p-4 space-y-2">
        <p className="text-[11px] font-medium text-zinc-400 dark:text-zinc-500">
          변환 전 (OCR 원문)
        </p>
        <pre className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-zinc-400 dark:text-zinc-500">
{`그해 겨울은 유난히 길
었다. 마당의 감나무는
잎을 다 떨구고도

- 42 -

한참을 그대로 서 있었
고, 할머니는 매일 아침
고요한 계절`}
        </pre>
      </div>
      <div className="rounded-xl border border-accent-200 dark:border-accent-700/40 bg-white dark:bg-zinc-950 p-4 space-y-2 shadow-sm">
        <p className="text-[11px] font-medium text-accent-600 dark:text-accent-400">
          변환 후 (book.txt)
        </p>
        <pre className="whitespace-pre-wrap font-sans text-[12px] leading-relaxed text-zinc-700 dark:text-zinc-300">
{`그해 겨울은 유난히 길었다. 마당의 감나무는 잎을 다 떨구고도 한참을 그대로 서 있었고, 할머니는 매일 아침...`}
        </pre>
      </div>
    </div>
  );
}
