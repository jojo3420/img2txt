const ITEMS = [
  {
    q: "어떤 이미지 형식을 지원하나요?",
    a: "jpg, jpeg 형식만 지원합니다. 다른 형식은 변환 전에 jpg로 바꿔주세요.",
  },
  {
    q: "왜 이렇게 오래 걸리나요?",
    a: "로컬 LLM 보정은 문단당 평균 약 52초가 걸립니다. 책 한 권 전체를 보정하면 100분 이상 소요될 수 있어요. 변환만 하는 무료 플랜은 훨씬 빠릅니다.",
  },
  {
    q: "결과가 완벽한가요?",
    a: "아니요. OCR과 LLM 보정 모두 한계가 있습니다. 스캔 상태가 나쁘거나 문장이 애매하면 오류가 남을 수 있어요. 그래서 원문은 항상 별도로 보존하고, 보정본과 전/후 대조 로그를 함께 제공해 직접 검수할 수 있게 했습니다.",
  },
  {
    q: "내 이미지와 텍스트는 어떻게 처리되나요?",
    a: "지금은 개인용 도구로, 보정은 로컬에서 실행되는 LLM(Ollama)을 사용합니다. 랜딩 페이지의 사전 관심 등록(이메일)은 정식 서비스 알림 목적으로만 사용됩니다.",
  },
];

export default function Faq() {
  return (
    <section id="faq" className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-16 border-t border-zinc-100 dark:border-zinc-800">
      <h2 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50 mb-8">FAQ</h2>
      <div className="max-w-2xl divide-y divide-zinc-100 dark:divide-zinc-800 rounded-xl border border-zinc-100 dark:border-zinc-800">
        {ITEMS.map(({ q, a }) => (
          <details key={q} className="group px-5 py-4">
            <summary className="cursor-pointer list-none flex items-center justify-between text-sm font-medium text-zinc-800 dark:text-zinc-200">
              {q}
              <span className="ml-4 text-zinc-300 dark:text-zinc-600 group-open:rotate-45 transition-transform">
                +
              </span>
            </summary>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
              {a}
            </p>
          </details>
        ))}
      </div>
    </section>
  );
}
