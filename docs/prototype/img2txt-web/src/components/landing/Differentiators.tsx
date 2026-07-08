import { Eraser, Link2, SpellCheck2, Layers } from "lucide-react";

const ITEMS = [
  {
    icon: Eraser,
    title: "꼬리말 자동 제거",
    desc: "페이지 번호, 책 제목처럼 본문 사이에 섞여 들어오는 꼬리말을 알아서 지웁니다.",
  },
  {
    icon: Link2,
    title: "문단·문장 이어붙이기",
    desc: "줄바꿈으로 쪼개진 문단을 복원하고, 페이지 경계를 넘는 문장을 자연스럽게 연결합니다.",
  },
  {
    icon: SpellCheck2,
    title: "로컬 LLM 오탈자 보정",
    desc: "qwen3:14b로 OCR 오탈자와 띄어쓰기를 교정합니다. (예: 경단로 → 결단코)",
  },
  {
    icon: Layers,
    title: "페이지별 + 한 권 전체",
    desc: "이미지 여러 장을 한 번에 올리고, 페이지별 원본과 책 한 권짜리 연속본을 함께 받아요.",
  },
];

export default function Differentiators() {
  return (
    <section id="features" className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-16 border-t border-zinc-100 dark:border-zinc-800">
      <div className="max-w-lg space-y-3 mb-10">
        <h2 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          한글 책 스캔에 특화된 이유
        </h2>
      </div>
      <div className="grid sm:grid-cols-2 gap-4">
        {ITEMS.map(({ icon: Icon, title, desc }) => (
          <div
            key={title}
            className="rounded-xl border border-zinc-100 dark:border-zinc-800 p-5 space-y-3"
          >
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-accent-50 dark:bg-accent-700/15 text-accent-600 dark:text-accent-400">
              <Icon size={17} />
            </span>
            <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
              {title}
            </h3>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
              {desc}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
