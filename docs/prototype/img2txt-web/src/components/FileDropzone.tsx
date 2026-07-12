import { useCallback, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";

const ACCEPTED = ["image/jpeg", "image/jpg", "image/png", "image/webp", "image/tiff"];

export default function FileDropzone({
  onFiles,
}: {
  onFiles: (files: File[]) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const filterImages = useCallback(
    (list: FileList | File[]) =>
      Array.from(list).filter(
        (f) => ACCEPTED.includes(f.type) || /\.(jpe?g|png|webp|tiffs?)$/i.test(f.name)
      ),
    []
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      const files = filterImages(e.dataTransfer.files);
      if (files.length) onFiles(files);
    },
    [filterImages, onFiles]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors ${
        dragOver
          ? "border-accent-400 bg-accent-50/60 dark:bg-accent-700/10"
          : "border-zinc-200 dark:border-zinc-800"
      }`}
    >
      <UploadCloud
        size={30}
        className={dragOver ? "text-accent-500" : "text-zinc-300 dark:text-zinc-700"}
      />
      <div className="space-y-1">
        <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          이미지를 이곳에 끌어다 놓으세요
        </p>
        <p className="text-xs text-zinc-400 dark:text-zinc-500">jpg, png, webp, tiff 파일 지원 (HEIC 미지원)</p>
      </div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="mt-1 rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-white hover:bg-accent-600 transition-colors"
      >
        파일 선택
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".jpg,.jpeg,.png,.webp,.tif,.tiff,image/jpeg,image/png,image/webp,image/tiff"
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files) onFiles(filterImages(e.target.files));
          e.target.value = "";
        }}
      />
    </div>
  );
}
