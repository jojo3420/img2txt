import { FileText, BookOpen, SpellCheck2, GitCompare } from "lucide-react";

const OUTPUTS = [
  {
    icon: FileText,
    title: "페이지별 원본",
    desc: "page-001.txt, page-002.txt … 검수하기 좋은 페이지 단위 파일.",
  },
  {
    icon: BookOpen,
    title: "연속본 (book.txt)",
    desc: "페이지 경계 없이 이어지는, 읽기용 한 권짜리 파일.",
  },
  {
    icon: SpellCheck2,
    title: "보정본 (book_corrected.txt)",
    desc: "LLM으로 오탈자·띄어쓰기를 교정한 별도 파일. 원문은 건드리지 않아요.",
  },
];

export default function ResultsShowcase() {
  return (
    <section className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-16 border-t border-zinc-100 dark:border-zinc-800">
      <div className="max-w-lg space-y-3 mb-10">
        <h2 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          결과물은 이렇게 나와요
        </h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
          원문은 절대 훼손하지 않습니다. 보정본은 항상 별도 파일로 제공하고,
          바뀐 문단은 전/후 대조 로그로 확인할 수 있어요.
        </p>
      </div>

      <div className="grid sm:grid-cols-3 gap-4 mb-6">
        {OUTPUTS.map(({ icon: Icon, title, desc }) => (
          <div
            key={title}
            className="rounded-xl border border-zinc-100 dark:border-zinc-800 p-5 space-y-3"
          >
            <Icon size={18} className="text-accent-500" />
            <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
              {title}
            </h3>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
              {desc}
            </p>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-zinc-100 dark:border-zinc-800 p-5">
        <div className="flex items-center gap-2 mb-3">
          <GitCompare size={15} className="text-zinc-400" />
          <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">
            전/후 대조 로그 예시
          </p>
        </div>
        <div className="space-y-2 font-mono text-xs">
          <p className="text-red-500/80 dark:text-red-400/80">
            − 경단로 다짐했다. 20 세기 초반의 일이었다.
          </p>
          <p className="text-emerald-600 dark:text-emerald-400">
            + 결단코 다짐했다. 20세기 초반의 일이었다.
          </p>
        </div>
      </div>
    </section>
  );
}
