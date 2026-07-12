import { http, HttpResponse, delay } from "msw";
import type { Job, JobSummary, PageFile, PageDetail, IntentRequest } from "../api/types";
import { naturalSortByFilename } from "../lib/naturalSort";
import { makePageText, makeCorrectedParagraph } from "./data";

// ── 목 서버 내부 상태 ────────────────────────────────────────────────
// TODO: 실제 백엔드(FastAPI)로 교체 시 이 파일 전체를 제거하고
// src/api/client.ts 의 API_BASE 만 실제 서버 주소로 바꾸면 된다.

interface InternalFile extends PageFile {
  _ocrTicksLeft: number;
  _correctTicksLeft: number;
  _willFail: boolean;
  _failedOnce: boolean;
}

interface InternalJob extends Omit<Job, "files"> {
  files: InternalFile[];
}

const CONCURRENCY = 2;

const jobs = new Map<string, InternalJob>();

function publicFile(f: InternalFile): PageFile {
  const { _ocrTicksLeft, _correctTicksLeft, _willFail, _failedOnce, ...rest } = f;
  return rest;
}

function publicJob(job: InternalJob): Job {
  return { ...job, files: job.files.map(publicFile) };
}

function pageOriginalText(pageNumber: number): string {
  // convert 단계에서 이미 꼬리말이 제거된 상태로 저장된 페이지 원본 txt
  const raw = makePageText(pageNumber);
  return raw
    .split("\n\n")
    .filter((block) => !/^(- \d+ -|.*페이지$|.*\s\d+$|고요한 계절$)/.test(block.trim()))
    .join("\n\n");
}

function pageCorrectedText(pageNumber: number): string {
  return pageOriginalText(pageNumber)
    .split("\n\n")
    .map(makeCorrectedParagraph)
    .join("\n\n");
}

/** GET 폴링이 올 때마다 한 틱씩 진행 상태를 시뮬레이션한다. */
function advance(job: InternalJob) {
  if (job.status === "queued") job.status = "processing";
  if (job.status !== "processing") return;

  const inFlight = job.files.filter(
    (f) => f.status === "ocr" || f.status === "correcting"
  ).length;
  let freeSlots = CONCURRENCY - inFlight;

  // 대기 중인 파일을 빈 슬롯만큼 OCR로 진입시킨다.
  if (freeSlots > 0) {
    for (const f of job.files) {
      if (freeSlots <= 0) break;
      if (f.status === "waiting") {
        f.status = "ocr";
        freeSlots--;
      }
    }
  }

  for (const f of job.files) {
    if (f.status === "ocr") {
      f._ocrTicksLeft--;
      if (f._ocrTicksLeft <= 0) {
        if (f._willFail && !f._failedOnce) {
          f.status = "failed";
          f.error = "OCR 인식 실패: 이미지 해상도가 낮거나 손상되었습니다.";
          f._failedOnce = true;
        } else if (job.options.correct) {
          f.status = "correcting";
        } else {
          f.status = "done";
          f.previewText = pageOriginalText(f.pageNumber).slice(0, 80);
        }
      }
    } else if (f.status === "correcting") {
      f._correctTicksLeft--;
      if (f._correctTicksLeft <= 0) {
        f.status = "done";
        f.previewText = pageCorrectedText(f.pageNumber).slice(0, 80);
      }
    }
  }

  const remaining = job.files.some(
    (f) => f.status === "waiting" || f.status === "ocr" || f.status === "correcting"
  );
  if (!remaining) {
    const failedPages = job.files.filter((f) => f.status === "failed").length;
    const successPages = job.files.length - failedPages;
    job.status = successPages === 0 ? "failed" : "done";

    const summary: JobSummary = {
      successPages,
      failedPages,
      removedFooterLines: successPages * 1,
    };
    if (job.options.correct) {
      summary.corrected = Math.round(successPages * 0.6);
      summary.kept = Math.round(successPages * 0.35);
      summary.guardBlocked = successPages - summary.corrected - summary.kept;
    }
    job.summary = summary;
  }
}

export const handlers = [
  // ── 잡 생성 ──────────────────────────────────────────────────────
  http.post("/api/jobs", async ({ request }) => {
    await delay(400);
    const formData = await request.formData();
    const rawFiles = formData.getAll("files") as File[];
    const correct = formData.get("correct") === "true";
    const backend = (formData.get("backend") as "codex" | "claude") || "codex";
    const modelMap: Record<"codex" | "claude", string> = { codex: "gpt-5.5", claude: "claude" };
    const model = modelMap[backend];

    if (rawFiles.length === 0) {
      return HttpResponse.json(
        { message: "업로드된 이미지가 없습니다." },
        { status: 400 }
      );
    }

    const sorted = naturalSortByFilename(
      rawFiles.map((f) => ({ filename: f.name, file: f }))
    );

    const id = crypto.randomUUID();
    const files: InternalFile[] = sorted.map(({ file }, idx) => {
      const pageNumber = idx + 1;
      return {
        id: crypto.randomUUID(),
        filename: file.name,
        pageNumber,
        sizeBytes: file.size,
        status: "waiting",
        _ocrTicksLeft: 2 + (pageNumber % 2),
        _correctTicksLeft: 2 + (pageNumber % 2),
        _willFail: pageNumber % 9 === 0,
        _failedOnce: false,
      };
    });

    const job: InternalJob = {
      id,
      createdAt: new Date().toISOString(),
      options: { correct, backend, model },
      status: "queued",
      files,
      phase: "ocr",
      correction: null,
      correctionError: null,
      correctedStale: false,
    };
    jobs.set(id, job);

    return HttpResponse.json({ id }, { status: 201 });
  }),

  // ── 잡 상태 폴링 ──────────────────────────────────────────────────
  http.get("/api/jobs/:id", async ({ params }) => {
    await delay(150);
    const job = jobs.get(params.id as string);
    if (!job) {
      return HttpResponse.json({ message: "잡을 찾을 수 없습니다." }, { status: 404 });
    }
    advance(job);
    return HttpResponse.json(publicJob(job));
  }),

  // ── 실패한 페이지 재시도 ───────────────────────────────────────────
  http.post("/api/jobs/:id/retry/:fileId", async ({ params }) => {
    await delay(300);
    const job = jobs.get(params.id as string);
    if (!job) {
      return HttpResponse.json({ message: "잡을 찾을 수 없습니다." }, { status: 404 });
    }
    const file = job.files.find((f) => f.id === params.fileId);
    if (!file) {
      return HttpResponse.json({ message: "파일을 찾을 수 없습니다." }, { status: 404 });
    }
    file.status = "waiting";
    file.error = undefined;
    file._willFail = false;
    file._ocrTicksLeft = 2;
    file._correctTicksLeft = 2;
    if (job.status === "done" || job.status === "failed") job.status = "processing";
    return HttpResponse.json(publicJob(job));
  }),

  // ── 페이지 상세 (원본/보정본) ─────────────────────────────────────
  http.get("/api/jobs/:id/pages/:n", async ({ params }) => {
    await delay(200);
    const job = jobs.get(params.id as string);
    if (!job) {
      return HttpResponse.json({ message: "잡을 찾을 수 없습니다." }, { status: 404 });
    }
    const n = Number(params.n);
    const file = job.files.find((f) => f.pageNumber === n);
    if (!file) {
      return HttpResponse.json({ message: "페이지를 찾을 수 없습니다." }, { status: 404 });
    }
    const detail: PageDetail = {
      pageNumber: n,
      filename: file.filename,
      original: pageOriginalText(n),
      corrected: job.options.correct ? pageCorrectedText(n) : undefined,
    };
    return HttpResponse.json(detail);
  }),

  // ── 페이지 단위 다운로드 ───────────────────────────────────────────
  http.get("/api/jobs/:id/pages/:n/download", async ({ params }) => {
    const job = jobs.get(params.id as string);
    const n = Number(params.n);
    if (!job) return new HttpResponse(null, { status: 404 });
    const text = job.options.correct ? pageCorrectedText(n) : pageOriginalText(n);
    return new HttpResponse(text, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": `attachment; filename="page-${String(n).padStart(
          3,
          "0"
        )}.txt"`,
      },
    });
  }),

  // ── 전체 다운로드 (book.txt / book_corrected.txt) ──────────────────
  http.get("/api/jobs/:id/download", async ({ params, request }) => {
    const job = jobs.get(params.id as string);
    if (!job) return new HttpResponse(null, { status: 404 });
    const url = new URL(request.url);
    const type = url.searchParams.get("type") === "corrected" ? "corrected" : "book";

    const doneFiles = job.files
      .filter((f) => f.status === "done")
      .sort((a, b) => a.pageNumber - b.pageNumber);

    const text = doneFiles
      .map((f) =>
        type === "corrected"
          ? pageCorrectedText(f.pageNumber)
          : pageOriginalText(f.pageNumber)
      )
      .join("\n\n");

    const filename = type === "corrected" ? "book_corrected.txt" : "book.txt";
    return new HttpResponse(text, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Disposition": `attachment; filename="${filename}"`,
      },
    });
  }),

  // ── 랜딩 페이지: 구매 의사 등록 (스모크 테스트) ───────────────────
  // TODO: 실제 백엔드 연동 시 이 핸들러를 제거하고 실제 API로 교체하세요.
  // 지금은 MSW가 방문자 브라우저 안에서만 응답하므로, 실제로 이메일이
  // 개발자에게 전달되지 않습니다 — 배포 전 반드시 진짜 백엔드가 필요합니다.
  http.post("/api/intent", async ({ request }) => {
    await delay(500);
    const body = (await request.json()) as IntentRequest;
    const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body?.email ?? "");
    if (!emailValid) {
      return HttpResponse.json(
        { message: "올바른 이메일 주소를 입력해주세요." },
        { status: 400 }
      );
    }
    return HttpResponse.json({ ok: true }, { status: 200 });
  }),
];
