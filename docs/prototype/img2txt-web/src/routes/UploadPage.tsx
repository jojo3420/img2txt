import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileImage, Trash2, X } from "lucide-react";
import FileDropzone from "../components/FileDropzone";
import Toggle from "../components/Toggle";
import Button from "../components/Button";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { useCreateJob } from "../api/client";
import { naturalSortByFilename } from "../lib/naturalSort";
import { formatBytes } from "../lib/format";

const BACKEND_MODEL_DISPLAY: Record<"codex" | "claude", string> = {
  codex: "gpt-5.5",
  claude: "claude",
};

export default function UploadPage() {
  const navigate = useNavigate();
  const [files, setFiles] = useState<File[]>([]);
  const [correct, setCorrect] = useState(true);
  const [backend, setBackend] = useState<"codex" | "claude">("codex");
  const createJob = useCreateJob();

  const sortedFiles = useMemo(
    () => naturalSortByFilename(files.map((f) => ({ filename: f.name, file: f }))),
    [files]
  );

  function addFiles(newFiles: File[]) {
    setFiles((prev) => {
      const existingNames = new Set(prev.map((f) => f.name));
      const merged = [...prev];
      for (const f of newFiles) {
        if (!existingNames.has(f.name)) {
          merged.push(f);
          existingNames.add(f.name);
        }
      }
      return merged;
    });
  }

  function removeFile(name: string) {
    setFiles((prev) => prev.filter((f) => f.name !== name));
  }

  async function handleStart() {
    createJob.mutate(
      { files, correct, backend },
      {
        onSuccess: ({ id }) => navigate(`/jobs/${id}`),
      }
    );
  }

  return (
    <div className="space-y-8">
      <div className="space-y-1.5">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          이미지 업로드
        </h1>
        <p className="text-sm text-zinc-400 dark:text-zinc-500">
          책 스캔 이미지를 올리면 텍스트로 변환합니다. jpg, png, webp, tiff 지원 (HEIC 미지원).
        </p>
      </div>

      <FileDropzone onFiles={addFiles} />

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            선택된 파일 {files.length > 0 && `(${files.length}장)`}
          </h2>
          {files.length > 0 && (
            <button
              type="button"
              onClick={() => setFiles([])}
              className="inline-flex items-center gap-1 text-xs font-medium text-zinc-400 hover:text-red-500 transition-colors"
            >
              <Trash2 size={13} />
              전체 삭제
            </button>
          )}
        </div>

        {sortedFiles.length === 0 ? (
          <EmptyState
            icon={<FileImage size={26} />}
            title="선택된 파일이 없습니다"
            description="위 영역에 이미지를 끌어다 놓거나 파일 선택 버튼을 눌러주세요."
          />
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800 rounded-xl border border-zinc-100 dark:border-zinc-800 overflow-hidden">
            {sortedFiles.map(({ file }, idx) => (
              <li
                key={file.name}
                className="flex items-center gap-3 px-4 py-2.5 bg-white dark:bg-zinc-900/40"
              >
                <span className="w-7 shrink-0 text-xs font-mono text-zinc-300 dark:text-zinc-600 text-right">
                  {idx + 1}
                </span>
                <span className="truncate text-sm text-zinc-700 dark:text-zinc-300 flex-1">
                  {file.name}
                </span>
                <span className="shrink-0 text-xs text-zinc-400 dark:text-zinc-500 font-mono">
                  {formatBytes(file.size)}
                </span>
                <button
                  type="button"
                  onClick={() => removeFile(file.name)}
                  aria-label={`${file.name} 삭제`}
                  className="shrink-0 rounded p-1 text-zinc-300 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                >
                  <X size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-4 rounded-xl border border-zinc-100 dark:border-zinc-800 p-5">
        <Toggle
          checked={correct}
          onChange={setCorrect}
          label="LLM 보정까지 실행"
          description="OCR 오탈자-띄어쓰기를 LLM으로 교정합니다."
        />
        {correct && (
          <>
            <div className="space-y-2">
              <label className="block text-xs font-medium text-zinc-700 dark:text-zinc-300">
                백엔드 선택
              </label>
              <div className="flex gap-2">
                <label className="flex items-center gap-2 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-2 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors has-[:checked]:border-zinc-900 dark:has-[:checked]:border-zinc-100">
                  <input
                    type="radio"
                    name="backend"
                    value="codex"
                    checked={backend === "codex"}
                    onChange={(e) => setBackend(e.target.value as "codex")}
                    className="w-4 h-4"
                  />
                  <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                    {BACKEND_MODEL_DISPLAY.codex}
                  </span>
                </label>
                <label className="flex items-center gap-2 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-2 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors has-[:checked]:border-zinc-900 dark:has-[:checked]:border-zinc-100">
                  <input
                    type="radio"
                    name="backend"
                    value="claude"
                    checked={backend === "claude"}
                    onChange={(e) => setBackend(e.target.value as "claude")}
                    className="w-4 h-4"
                  />
                  <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                    {BACKEND_MODEL_DISPLAY.claude}{" "}
                    <span className="text-amber-600 dark:text-amber-400">실험적</span>
                  </span>
                </label>
              </div>
            </div>
            <p className="rounded-lg bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              보정을 켜면 처리 시간이 크게 늘어납니다 — 문단당 평균 약 52초, 책 1권 기준
              100분 이상 소요될 수 있어요.
            </p>
          </>
        )}
      </section>

      {createJob.isError && (
        <ErrorState
          message={
            createJob.error instanceof Error
              ? createJob.error.message
              : "변환 시작에 실패했습니다."
          }
          onRetry={handleStart}
        />
      )}

      <div className="flex justify-end">
        <Button
          onClick={handleStart}
          disabled={files.length === 0 || createJob.isPending}
        >
          {createJob.isPending ? "시작하는 중..." : "변환 시작"}
        </Button>
      </div>
    </div>
  );
}
