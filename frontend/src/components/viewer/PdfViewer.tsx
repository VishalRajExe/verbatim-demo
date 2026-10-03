"use client";

/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useRef, useState } from "react";

import { fileUrl, locateRanges, type LocatedRect } from "@/lib/api/client";

export interface HighlightRange {
  start: number;
  end: number;
}

interface PdfViewerProps {
  docId: string;
  /** Server-verified quote char ranges to overlay as pixel highlights. */
  ranges?: HighlightRange[];
  /** Scroll to this page even when there is no highlight (e.g. compare links). */
  focusPage?: number;
  /** Reports the page the viewer scrolled to, so the toolbar counter can sync. */
  onActivePage?: (page: number) => void;
  className?: string;
}

/**
 * Renders a PDF via pdf.js and overlays server-verified quote rectangles as
 * pixel highlights, scrolling the first matched passage into view. Pages render
 * lazily (IntersectionObserver) so 150-page contracts stay responsive.
 */
export function PdfViewer({ docId, ranges = [], focusPage, onActivePage, className = "" }: PdfViewerProps) {
  const [pdfDoc, setPdfDoc] = useState<any>(null);
  const [error, setError] = useState("");
  const [numPages, setNumPages] = useState(0);
  const [highlights, setHighlights] = useState<Record<number, LocatedRect>>({});
  const [flashPage, setFlashPage] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Centre the target page (or its highlight) in the scroll container. Retries
  // for a few seconds so it stays correct while lazy pages change layout height
  // and canvases finish painting.
  const scrollToElement = useCallback((pageNumber: number, useFlash = true) => {
    const cont = containerRef.current;
    if (!cont) return;
    let attempts = 0;
    const tick = () => {
      attempts += 1;
      const pageEl = cont.querySelector<HTMLElement>(`[data-page="${pageNumber}"]`);
      const el = useFlash
        ? cont.querySelector<HTMLElement>(`[data-page="${pageNumber}"] .quote-flash`)
        : pageEl;
      const target = el && el.offsetHeight > 0 ? el : pageEl;
      if (target && target.offsetHeight > 0) {
        const contBox = cont.getBoundingClientRect();
        const elBox = target.getBoundingClientRect();
        const targetTop =
          cont.scrollTop + (elBox.top - contBox.top) - cont.clientHeight / 2 + elBox.height / 2;
        cont.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
      }
      if (attempts < 25) setTimeout(tick, 150);
    };
    tick();
  }, []);

  // Load the pdf.js engine + document bytes (browser-only; no SSR).
  // Reset ALL viewer state whenever the document identity changes so a page
  // from a previously-open document can never linger (document-scoped view).
  useEffect(() => {
    let cancelled = false;
    let doc: any = null;
    setError("");
    setPdfDoc(null);
    setHighlights({});
    setNumPages(0);
    setFlashPage(null);
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";
        const resp = await fetch(fileUrl(docId));
        if (!resp.ok) throw new Error(`Could not load the PDF (HTTP ${resp.status}).`);
        const buf = await resp.arrayBuffer();
        doc = await pdfjs.getDocument({ data: new Uint8Array(buf) }).promise;
        if (cancelled) {
          doc.destroy();
          return;
        }
        setPdfDoc(doc);
        setNumPages(doc.numPages);
      } catch (e) {
        if (!cancelled) setError((e as Error).message || "Failed to render PDF.");
      }
    })();
    return () => {
      cancelled = true;
      doc?.destroy?.();
    };
  }, [docId]);

  const rangesKey = JSON.stringify(ranges);

  // Fetch pixel geometry for the requested ranges, then jump to the first page.
  useEffect(() => {
    if (!pdfDoc || ranges.length === 0) {
      setHighlights({});
      return;
    }
    let alive = true;
    (async () => {
      try {
        const loc = await locateRanges(docId, ranges);
        if (!alive) return;
        const map: Record<number, LocatedRect> = {};
        for (const l of loc.locations) {
          const cur = map[l.pageNumber];
          if (cur) cur.rects = [...cur.rects, ...(l.rects || [])];
          else map[l.pageNumber] = { ...l, rects: [...(l.rects || [])] };
        }
        setHighlights(map);
        const first = loc.locations.find((l) => (l.rects?.length ?? 0) > 0) || loc.locations[0];
        if (first) {
          setFlashPage(first.pageNumber);
          scrollToElement(first.pageNumber);
          onActivePage?.(first.pageNumber);
        }
      } catch {
        /* geometry is best-effort; page numbers still show */
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdfDoc, rangesKey]);

  // Explicit navigation: scroll a page into view (compare "go to page", or the
  // viewer's prev/next controls). Independent of quote highlighting.
  useEffect(() => {
    if (pdfDoc && focusPage) {
      scrollToElement(focusPage, false);
      onActivePage?.(focusPage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdfDoc, focusPage]);

  if (error) {
    return (
      <div className={`grid place-items-center bg-canvas ${className}`}>
        <p className="max-w-sm text-center text-sm text-danger">{error}</p>
      </div>
    );
  }
  if (!pdfDoc) {
    return (
      <div className={`grid place-items-center bg-canvas ${className}`}>
        <p className="text-sm text-ink-subtle">Loading document…</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={`scroll-thin overflow-y-auto bg-canvas ${className}`}>
      <div className="mx-auto flex flex-col items-center gap-4 p-4">
        {Array.from({ length: numPages }, (_, i) => i + 1).map((p) => (
          <PdfPage
            key={`${docId}-${p}`}
            pdfDoc={pdfDoc}
            pageNumber={p}
            containerRef={containerRef}
            highlight={highlights[p]}
            flash={flashPage === p}
          />
        ))}
      </div>
    </div>
  );
}

function PdfPage({
  pdfDoc,
  pageNumber,
  containerRef,
  highlight,
  flash,
}: {
  pdfDoc: any;
  pageNumber: number;
  containerRef: { current: HTMLDivElement | null };
  highlight?: LocatedRect;
  flash: boolean;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderedRef = useRef(false);
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  const [pageWidth, setPageWidth] = useState(720);

  // Reserve correct layout size (points at scale 1) before rendering.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const page = await pdfDoc.getPage(pageNumber);
        const vp = page.getViewport({ scale: 1 });
        if (alive) setDims({ w: vp.width, h: vp.height });
      } catch {
        /* ignore */
      }
    })();
    return () => {
      alive = false;
    };
  }, [pdfDoc, pageNumber]);

  // Fit pages to the container width.
  useEffect(() => {
    const host = containerRef.current;
    if (!host || !dims) return;
    const compute = () => {
      const inner = host.clientWidth - 32; // padding
      setPageWidth(Math.max(320, Math.min(inner, 900)));
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(host);
    return () => ro.disconnect();
  }, [containerRef, dims]);

  const fitScale = dims ? pageWidth / dims.w : 1;

  // Render the page to a canvas only when it scrolls near the viewport.
  useEffect(() => {
    if (!dims || renderedRef.current || !wrapRef.current) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          io.disconnect();
          (async () => {
            try {
              const dpr = window.devicePixelRatio || 1;
              const page = await pdfDoc.getPage(pageNumber);
              const viewport = page.getViewport({ scale: fitScale * dpr });
              const canvas = canvasRef.current;
              if (!canvas) return;
              canvas.width = Math.floor(viewport.width);
              canvas.height = Math.floor(viewport.height);
              canvas.style.width = `${viewport.width / dpr}px`;
              canvas.style.height = `${viewport.height / dpr}px`;
              const ctx = canvas.getContext("2d");
              if (!ctx) return;
              await page.render({ canvasContext: ctx, viewport }).promise;
              renderedRef.current = true;
            } catch {
              /* render failures degrade to a blank page box */
            }
          })();
        }
      },
      { rootMargin: "300px 0px" },
    );
    io.observe(wrapRef.current);
    return () => io.disconnect();
  }, [dims, pdfDoc, pageNumber, fitScale]);

  const cssW = dims ? dims.w * fitScale : pageWidth;
  const cssH = dims ? dims.h * fitScale : 900;

  return (
    <div
      ref={wrapRef}
      data-page={pageNumber}
      className="relative bg-white shadow-card ring-1 ring-line"
      style={{ width: `${cssW}px`, height: `${cssH}px` }}
    >
      <canvas ref={canvasRef} className="block h-full w-full" />
      {highlight?.rects?.map((r, i) => (
        <div
          key={i}
          className={`pointer-events-none absolute rounded-sm ${flash ? "quote-flash" : ""}`}
          style={{
            left: `${r.x1 * fitScale}px`,
            top: `${r.y1 * fitScale}px`,
            width: `${Math.max(0, r.x2 - r.x1) * fitScale}px`,
            height: `${Math.max(0, r.y2 - r.y1) * fitScale}px`,
            background: "rgba(253, 224, 71, 0.45)",
            outline: "1px solid rgba(180, 83, 9, 0.7)",
          }}
        />
      ))}
      <div className="absolute bottom-1 right-2 text-[10px] text-ink-subtle tabular-nums">
        {pageNumber}
      </div>
    </div>
  );
}
