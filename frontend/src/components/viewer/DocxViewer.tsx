"use client";

import { useEffect, useRef } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useDocumentPages } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

interface DocxViewerProps {
  docId: string;
  className?: string;
  /** A verified quote's exact text to mark within the page it appears on. */
  highlightText?: string | null;
  /** Page to scroll into view (from a citation deep link). */
  focusPage?: number;
  /** Reports the page the viewer scrolled to, so the toolbar counter can sync. */
  onActivePage?: (page: number) => void;
}

/**
 * Renders a Word (.docx) document as its server-extracted page text. The stored
 * source is not a PDF, so pdf.js can't paint it; instead we show readable pages
 * and highlight a cited passage by exact text match on the page it lives on.
 */
export function DocxViewer({ docId, className = "", highlightText, focusPage, onActivePage }: DocxViewerProps) {
  const { data, error, isLoading } = useDocumentPages(docId);
  const containerRef = useRef<HTMLDivElement>(null);

  // Scroll the requested page into view once the text has rendered.
  useEffect(() => {
    if (!data || !focusPage) return;
    const cont = containerRef.current;
    if (!cont) return;
    const el = cont.querySelector<HTMLElement>(`[data-page="${focusPage}"]`);
    if (el) {
      const contBox = cont.getBoundingClientRect();
      const elBox = el.getBoundingClientRect();
      cont.scrollTo({
        top: cont.scrollTop + (elBox.top - contBox.top) - cont.clientHeight / 2 + elBox.height / 2,
        behavior: "smooth",
      });
      onActivePage?.(focusPage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, focusPage]);

  if (isLoading) {
    return (
      <div className={cn("grid place-items-center bg-canvas p-8", className)}>
        <Skeleton className="h-[640px] w-[480px] max-w-full bg-surface" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className={cn("grid place-items-center bg-canvas", className)}>
        <p className="max-w-sm text-center text-sm text-danger">
          {error?.message || "Couldn't load the document text."}
        </p>
      </div>
    );
  }

  const target = (highlightText ?? "").trim();

  return (
    <div ref={containerRef} className={cn("scroll-thin overflow-y-auto bg-canvas", className)}>
      <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
        {data.pages.map((p) => (
          <article
            key={p.pageNumber}
            data-page={p.pageNumber}
            className="rounded-card bg-white p-8 shadow-card ring-1 ring-line"
          >
            <DocPageText text={p.text} highlight={target} />
            <div className="mt-6 text-center text-[11px] tabular-nums text-ink-subtle">
              {p.pageNumber}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

/** Renders page text, wrapping an exact-match passage in a highlighted <mark>. */
function DocPageText({ text, highlight }: { text: string; highlight: string }) {
  if (!highlight) return <p className="whitespace-pre-line text-sm leading-7 text-ink">{text}</p>;
  const idx = text.indexOf(highlight);
  if (idx === -1) return <p className="whitespace-pre-line text-sm leading-7 text-ink">{text}</p>;
  return (
    <p className="whitespace-pre-line text-sm leading-7 text-ink">
      {text.slice(0, idx)}
      <mark className="rounded-sm bg-mark px-0.5 animate-mark">{highlight}</mark>
      {text.slice(idx + highlight.length)}
    </p>
  );
}
