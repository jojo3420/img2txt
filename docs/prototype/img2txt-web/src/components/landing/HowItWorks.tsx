import { UploadCloud, Cpu, Download } from "lucide-react";

const STEPS = [
  {
    icon: UploadCloud,
    title: "1. 업로드",
    desc: "책 스캔 이미지(jpg/jpeg) 여러 장을 한 번에 올립니다.",
  },
  {
    icon: Cpu,
    title: "2. 자동 변환 · 보정",
    desc: "OCR → 꼬리말 제거 → 문단 복원을 거치고, 원하면 LLM 오탈자 보정까지 진행합니다.",
  },
  {
    icon: Download,
    title: "3. 다운로드",
    desc: "페이지별 원본, 책 전체 연속본, 보정본을 각각 받아볼 수 있어요.",
  },
];

export default function HowItWorks() {
  return (
    <section className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-16 border-t border-zinc-100 dark:border-zinc-800">
      <h2 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50 mb-10">
        작동 방식
      </h2>
      <div className="grid sm:grid-cols-3 gap-6">
        {STEPS.map(({ icon: Icon, title, desc }) => (
          <div key={title} className="space-y-3">
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900">
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
