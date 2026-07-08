export default function SiteFooter() {
  return (
    <footer className="border-t border-zinc-100 dark:border-zinc-800">
      <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-zinc-400 dark:text-zinc-500">
        <p>© {new Date().getFullYear()} img2txt. 개인 프로젝트.</p>
        <p>문의: 사전 관심 등록 시 남긴 이메일로 회신드립니다.</p>
      </div>
    </footer>
  );
}
