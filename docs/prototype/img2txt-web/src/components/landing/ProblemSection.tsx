export default function ProblemSection() {
  return (
    <section className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-16 border-t border-zinc-100 dark:border-zinc-800">
      <div className="max-w-lg space-y-3 mb-8">
        <h2 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          일반 OCR 결과는 왜 읽기 힘들까요
        </h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
          범용 OCR 도구는 텍스트를 뽑아낼 뿐, 책이라는 형식은 신경 쓰지 않습니다.
          페이지 번호와 책 제목이 본문 사이사이에 섞이고, 문단은 페이지 경계에서
          뚝뚝 끊깁니다.
        </p>
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-5 space-y-2">
          <p className="text-xs font-medium text-zinc-400">일반 OCR 결과</p>
          <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-zinc-400 dark:text-zinc-500">
{`...결단코 포기하지 않겠다고
경단로 다짐했다.

고요한 계절 87

20 세기 초반의 일이었다.`}
          </pre>
        </div>
        <div className="rounded-xl border border-accent-200 dark:border-accent-700/40 p-5 space-y-2 bg-accent-50/30 dark:bg-accent-700/5">
          <p className="text-xs font-medium text-accent-600 dark:text-accent-400">
            img2txt 결과
          </p>
          <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-zinc-700 dark:text-zinc-300">
{`...결단코 포기하지 않겠다고 결단코 다짐했다. 20세기 초반의 일이었다.`}
          </pre>
        </div>
      </div>
    </section>
  );
}
