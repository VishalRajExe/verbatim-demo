"use client";

import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  FileClock,
  MessageSquare,
  Trash2,
} from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
import { mutate as globalMutate } from "swr";
import { PdfViewer, type HighlightRange } from "@/components/viewer/PdfViewer";
import { DocxViewer } from "@/components/viewer/DocxViewer";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { FileIcon } from "@/components/common/file-icon";
import { Badge } from "@/components/ui/badge";
import { IconButton } from "@/components/ui/icon-button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { Tip } from "@/components/ui/tooltip";
import { API_BASE, deleteDocument } from "@/lib/api/client";
import { useDocument } from "@/lib/api/hooks";
import { isReady, type DocumentItem } from "@/lib/types";

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export function ViewerSkeleton() {
  return (
    <div className="flex h-full flex-col" aria-busy="true" aria-label="Loading document">
      <div className="flex h-14 items-center gap-3 border-b border-line bg-surface px-4">
        <Skeleton className="size-8" />
        <Skeleton className="h-4 w-56" />
      </div>
      <div className="flex flex-1 justify-center bg-canvas p-8">
        <Skeleton className="h-[640px] w-[480px] max-w-full bg-surface" />
      </div>
    </div>
  );
}

/** Parse a "start-end,start-end" query value into highlight ranges. */
function parseRanges(raw: string | null): HighlightRange[] {
  if (!raw) return [];
  const out: HighlightRange[] = [];
  for (const part of raw.split(",")) {
    const [a, b] = part.split("-");
    const start = Number(a);
    const end = Number(b);
    if (Number.isFinite(start) && Number.isFinite(end)) out.push({ start, end });
  }
  return out;
}

/** Route entry: reads the id and query, handles loading, error and not-ready states. */
export function DocumentViewer() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const { data: doc, error, isLoading, mutate } = useDocument(id);

  if (isLoading) return <ViewerSkeleton />;
  if (error) return <ErrorState className="h-full justify-center" title="Couldn't open this document" message={error.message} onRetry={() => void mutate()} />;
  if (!doc) return <ViewerSkeleton />;
  if (!isReady(doc)) {
    return (
      <EmptyState
        className="h-full justify-center"
        icon={FileClock}
        title={doc.status === "failed" ? "This document can't be opened" : "Still processing"}
        hint={doc.status === "failed" ? (doc.errorMessage ?? undefined) : "It opens as soon as processing finishes."}
      />
    );
  }
  return (
    <ViewerBody
      doc={doc}
      startPage={Number(sp.get("page")) || 1}
      ranges={parseRanges(sp.get("ranges"))}
    />
  );
}

function ViewerBody({
  doc,
  startPage,
  ranges,
}: {
  doc: DocumentItem;
  startPage: number;
  ranges: HighlightRange[];
}) {
  const router = useRouter();
  const { toast } = useToast();
  const total = doc.pages ?? 1;

  const [page, setPage] = useState(clamp(startPage, 1, total));
  const [pageInput, setPageInput] = useState(String(clamp(startPage, 1, total)));
  // When arriving without highlight ranges (e.g. a compare "go to page" link),
  // scroll straight to the requested page once the document is ready.
  const [navPage, setNavPage] = useState<number | undefined>(
    ranges.length === 0 && startPage > 1 ? clamp(startPage, 1, total) : undefined,
  );
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fileUrl = `${API_BASE}/api/documents/${doc.id}/file`;

  // Drive the pdf.js viewer to a specific page via its scroll container.
  const goTo = useCallback((n: number) => {
    const target = clamp(n, 1, total);
    setPage(target);
    setPageInput(String(target));
    setNavPage(target);
  }, [total]);

  // Viewer reports the page it actually scrolled to (citation deep-link), so the
  // toolbar counter stays in sync even when we didn't drive the navigation.
  const markActivePage = useCallback((n: number) => {
    setPage(n);
    setPageInput(String(n));
  }, []);

  async function remove() {
    setDeleting(true);
    try {
      await deleteDocument(doc.id);
      await globalMutate("documents");
      toast("Document deleted", "success");
      router.push("/documents");
    } catch {
      toast("Couldn't delete. Try again.", "error");
      setDeleting(false);
    }
  }

  return (
    <div className="flex h-full flex-col bg-canvas">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-surface px-3 py-2">
        <IconButton label="Back to documents" icon={ArrowLeft} onClick={() => router.push("/documents")} />
        <FileIcon kind={doc.kind} className="size-7" />
        <h1 className="min-w-0 max-w-[40vw] truncate text-sm font-semibold text-ink">{doc.name}</h1>
        {doc.kind === "docx" ? (
          <Tip label="Shown as extracted page text from the Word file.">
            <Badge tabIndex={0}>
              Word
            </Badge>
          </Tip>
        ) : null}

        <div className="ml-auto flex flex-wrap items-center gap-1">
          <IconButton label="Previous page" icon={ChevronLeft} disabled={page <= 1} onClick={() => goTo(page - 1)} />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const n = Number(pageInput);
              if (Number.isFinite(n)) goTo(n);
            }}
            className="flex items-center gap-1 text-sm text-ink-muted"
          >
            <input
              value={pageInput}
              onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ""))}
              inputMode="numeric"
              aria-label="Page number"
              className="h-8 w-12 rounded-md border border-line-strong bg-surface text-center text-sm tabular-nums text-ink"
            />
            <span className="tabular-nums">/ {total}</span>
          </form>
          <IconButton label="Next page" icon={ChevronRight} disabled={page >= total} onClick={() => goTo(page + 1)} />
          <span className="mx-1 hidden h-5 w-px bg-line sm:block" aria-hidden />
          <IconButton label="Ask about this document" icon={MessageSquare} onClick={() => router.push(`/chats?doc=${doc.id}`)} />
          <a href={fileUrl} download={doc.name} tabIndex={-1}>
            <IconButton label="Download" icon={Download} />
          </a>
          <IconButton label="Delete" icon={Trash2} className="text-danger hover:bg-danger-soft/60" onClick={() => setConfirmDelete(true)} />
        </div>
      </div>

      {/* Real viewer: pdf.js canvas + highlights for PDFs; extracted text for Word */}
      <div className="relative flex min-h-0 flex-1">
        {doc.kind === "docx" ? (
          <DocxViewer
            docId={doc.id}
            focusPage={navPage}
            onActivePage={markActivePage}
            className="h-full w-full"
          />
        ) : (
          <PdfViewer
            docId={doc.id}
            ranges={ranges}
            focusPage={navPage}
            onActivePage={markActivePage}
            className="h-full w-full"
          />
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this document?"
        description={`"${doc.name}" and its chats will be removed.`}
        busy={deleting}
        onConfirm={() => void remove()}
      />
    </div>
  );
}
