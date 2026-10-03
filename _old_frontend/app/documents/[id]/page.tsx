import Link from "next/link";
import { notFound } from "next/navigation";

import { StatusBadge } from "@/components/StatusBadge";
import { PdfViewer } from "@/features/viewer/PdfViewer";
import { API_BASE, fileUrl, formatBytes } from "@/lib/api";
import type { DocumentOut, DocumentPagesOut } from "@/lib/types";

async function fetchJson(url: string): Promise<Response> {
  return fetch(url, { cache: "no-store" });
}

// Parse a "start-end,start-end" query value into canonical ranges for highlight.
function parseRanges(raw?: string): { start: number; end: number }[] {
  if (!raw) return [];
  const out: { start: number; end: number }[] = [];
  for (const part of raw.split(",")) {
    const [a, b] = part.split("-");
    const start = Number(a);
    const end = Number(b);
    if (Number.isFinite(start) && Number.isFinite(end)) out.push({ start, end });
  }
  return out;
}

export default async function DocumentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ ranges?: string }>;
}) {
  const { id } = await params;
  const { ranges: rangesRaw } = await searchParams;
  const ranges = parseRanges(rangesRaw);
  const docRes = await fetchJson(`${API_BASE}/api/documents/${id}`);
  if (docRes.status === 404) notFound();
  if (!docRes.ok) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-10 text-sm text-red-700">
        Could not reach the backend ({docRes.status}). Is it running on{" "}
        {API_BASE}?
      </div>
    );
  }
  const doc: DocumentOut = await docRes.json();

  let pages: DocumentPagesOut | null = null;
  if (doc.status === "ready") {
    const pagesRes = await fetchJson(
      `${API_BASE}/api/documents/${id}/pages`,
    );
    if (pagesRes.ok) pages = await pagesRes.json();
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-4">
        <Link href="/" className="text-sm text-brand-600 hover:underline">
          ← Back to documents
        </Link>
      </div>

      <div className="card mb-6 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">
              {doc.filename}
            </h1>
            <div className="mt-1 flex items-center gap-3 text-sm text-slate-500">
              <StatusBadge status={doc.status} />
              <span>{doc.file_type.replace(".", "").toUpperCase()}</span>
              <span>{formatBytes(doc.file_size)}</span>
              <span>{doc.page_count ?? "—"} pages</span>
            </div>
            {doc.status === "error" && doc.error_message && (
              <p className="mt-2 text-sm text-red-600">{doc.error_message}</p>
            )}
          </div>
          <a
            href={fileUrl(id)}
            target="_blank"
            rel="noreferrer"
            className="btn-secondary text-xs"
          >
            Open source file
          </a>
        </div>
      </div>

      {doc.status === "ready" && doc.file_type === ".pdf" && (
        <div className="card overflow-hidden">
          <PdfViewer docId={id} ranges={ranges} className="h-[78vh]" />
        </div>
      )}

      {doc.status === "ready" && pages && doc.file_type === ".docx" && (
        <div className="space-y-4">
          {pages.pages.map((p) => (
            <div key={p.page_number} className="card p-5">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                Page {p.page_number}
              </div>
              <div className="whitespace-pre-wrap text-sm leading-6 text-slate-700">
                {p.text}
              </div>
            </div>
          ))}
        </div>
      )}

      {doc.status !== "ready" && doc.status !== "error" && (
        <div className="card p-8 text-center text-sm text-slate-500">
          Processing… refresh in a moment.
        </div>
      )}
    </div>
  );
}
