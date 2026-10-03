"use client";

import {
  Copy,
  ExternalLink,
  ShieldCheck,
  X,
} from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogClose, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { IconButton } from "@/components/ui/icon-button";
import { useToast } from "@/components/ui/toast";
import { PdfViewer } from "@/components/viewer/PdfViewer";
import { DocxViewer } from "@/components/viewer/DocxViewer";
import { API_BASE } from "@/lib/api/client";
import type { Quote } from "@/lib/types";

export function QuoteSheet({ quote, onClose }: { quote: Quote | null; onClose: () => void }) {
  return (
    <Dialog open={quote !== null} onOpenChange={(o) => (o ? undefined : onClose())}>
      {quote ? <QuoteSheetBody quote={quote} /> : null}
    </Dialog>
  );
}

function QuoteSheetBody({ quote }: { quote: Quote }) {
  const { toast } = useToast();

  // A verified quote carries server-side char offsets → pixel highlight ranges.
  const ranges =
    quote.start != null && quote.end != null ? [{ start: quote.start, end: quote.end }] : [];

  // Word documents aren't stored as PDFs, so pdf.js can't paint them; we render
  // their extracted page text and mark the cited passage by exact match instead.
  const isDocx = /\.docx$/i.test(quote.documentName);

  // Deep-link into the full document viewer, preserving highlight context.
  const viewerHref = isDocx
    ? `/documents/${quote.documentId}${quote.page ? `?page=${quote.page}` : ""}`
    : ranges.length
      ? `/documents/${quote.documentId}?ranges=${quote.start}-${quote.end}`
      : `/documents/${quote.documentId}${quote.page ? `?page=${quote.page}` : ""}`;

  const fileHref = `${API_BASE}/api/documents/${quote.documentId}/file`;

  return (
    <SheetContent aria-describedby={undefined}>
      <header className="flex items-start gap-3 border-b border-line px-5 py-4">
        <DialogTitle className="min-w-0 flex-1 truncate pt-0.5 text-[15px] font-semibold text-ink">
          {quote.ref} · {quote.documentName}
        </DialogTitle>
        <DialogClose
          aria-label="Close"
          className="grid size-8 shrink-0 place-items-center rounded-md text-ink-subtle hover:bg-line/60 hover:text-ink"
        >
          <X className="size-4" />
        </DialogClose>
      </header>

      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-3 text-sm text-ink-muted">
          {quote.page != null ? (
            <span>Page {quote.page}</span>
          ) : null}
          <Badge tone="ok">
            <ShieldCheck /> verified · {quote.matchKind ?? "exact"}
          </Badge>
          {quote.occurrences > 1 ? (
            <span className="text-xs text-ink-subtle">appears {quote.occurrences}×</span>
          ) : null}
        </div>

        <section className="px-5 pt-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">Highlighted in the document</h3>
            <Link
              href={viewerHref}
              className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
            >
              <ExternalLink className="size-3.5" /> Open full ↗
            </Link>
          </div>

          {isDocx ? (
            <div className="overflow-hidden rounded-card border border-line bg-canvas">
              <DocxViewer
                docId={quote.documentId}
                highlightText={quote.text}
                focusPage={quote.page ?? undefined}
                className="h-[320px] w-full"
              />
            </div>
          ) : ranges.length ? (
            <div className="overflow-hidden rounded-card border border-line bg-canvas">
              <PdfViewer
                docId={quote.documentId}
                ranges={ranges}
                className="h-[320px] w-full"
              />
            </div>
          ) : (
            <div className="rounded-card border border-line bg-canvas p-4 text-sm text-ink-muted">
              <p className="text-xs text-ink-subtle mb-2">
                Exact passage location unavailable — open the full document to browse it.
              </p>
              <a
                href={fileHref}
                download={quote.documentName}
                className="text-brand text-xs hover:underline"
              >
                Download original
              </a>
            </div>
          )}
        </section>

        <section className="px-5 pb-6 pt-5">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">Quoted passage</h3>
            <IconButton
              label="Copy quote"
              icon={Copy}
              onClick={() => {
                void navigator.clipboard?.writeText(quote.text);
                toast("Quote copied", "success");
              }}
            />
          </div>
          <div className="rounded-card border border-line bg-canvas p-4 text-sm leading-7 text-ink-muted">
            <p>{quote.text}</p>
          </div>
        </section>
      </div>
    </SheetContent>
  );
}
