"use client";

import {
  ChevronDown,
  Copy,
  LoaderCircle,
  RotateCcw,
  SearchX,
  ShieldCheck,
  Square,
  TriangleAlert,
} from "lucide-react";
import { Fragment, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Tip } from "@/components/ui/tooltip";
import { isCoverageComplete, type Coverage, type Message, type Quote } from "@/lib/types";
import { cn, docDot } from "@/lib/utils";

export interface AssistantView {
  id: string;
  content: string;
  status: Message["status"];
  kind: Message["kind"];
  quotes: Quote[];
  coverage: Coverage[];
  errorMessage: string | null;
  stage: string | null;
}

export function UserMessage({ text }: { text: string }) {
  return <p className="text-[15px] font-semibold leading-6 text-ink">{text}</p>;
}

export function AssistantMessage({
  m,
  onOpenQuote,
  onRetry,
  onCopy,
}: {
  m: AssistantView;
  onOpenQuote: (q: Quote) => void;
  onRetry?: () => void;
  onCopy: (text: string) => void;
}) {
  const streaming = m.status === "streaming";
  const verified = m.quotes.filter((q) => q.verified);
  const unverified = m.quotes.filter((q) => !q.verified);
  const multi = new Set(m.quotes.map((q) => q.documentId)).size > 1;

  return (
    <article aria-label="Answer" className="space-y-3">
      {streaming && m.stage && !m.content ? <StageLine label={m.stage} /> : null}

      {m.content ? (
        m.kind === "not_found" ? (
          <NotFound text={m.content} streaming={streaming} />
        ) : (
          <RichAnswer text={m.content} quotes={m.quotes} streaming={streaming} onOpenQuote={onOpenQuote} />
        )
      ) : null}

      {m.status === "error" ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-card border border-danger/25 bg-danger-soft/50 px-3.5 py-3 text-sm text-danger">
          <TriangleAlert className="size-4 shrink-0" aria-hidden />
          <span className="min-w-0 flex-1">{m.errorMessage ?? "Something went wrong."}</span>
          {onRetry ? (
            <Button size="sm" onClick={onRetry}>
              <RotateCcw /> Try again
            </Button>
          ) : null}
        </div>
      ) : null}

      {m.status === "stopped" ? (
        <Badge>
          <Square className="fill-current" /> Stopped
        </Badge>
      ) : null}

      {verified.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="Verified quotes">
          {verified.map((q) => (
            <li key={q.ref}>
              <Tip label={`${q.documentName}${q.occurrences > 1 ? ` · appears ${q.occurrences} times` : ""}`}>
                <button
                  type="button"
                  onClick={() => onOpenQuote(q)}
                  className="inline-flex items-center gap-1.5 rounded-md bg-line/70 px-2 py-1 text-xs font-medium text-ink-muted transition-colors hover:bg-brand-soft hover:text-brand"
                >
                  {multi ? <span className={cn("size-2 rounded-full", docDot(q.documentId))} aria-hidden /> : null}
                  {q.ref} · p.{q.page}
                </button>
              </Tip>
            </li>
          ))}
        </ul>
      ) : null}

      {unverified.length > 0 ? (
        <details className="group rounded-card border border-warn/30 bg-warn-soft/40">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-semibold text-warn">
            <TriangleAlert className="size-3.5" aria-hidden />
            {unverified.length} couldn&apos;t be verified
            <ChevronDown className="ml-auto size-4 transition-transform group-open:rotate-180" aria-hidden />
          </summary>
          <ul className="space-y-2 border-t border-warn/20 p-3">
            {unverified.map((q) => (
              <li key={q.ref} className="rounded-md border border-dashed border-warn/40 bg-surface p-2.5 text-xs text-ink-muted">
                <p className="font-semibold text-warn">
                  {q.ref} · not found in {q.documentName}
                </p>
                <p className="mt-1 italic">&ldquo;{q.text}&rdquo;</p>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {m.coverage.length > 0 && !streaming ? <CoverageBadge coverage={m.coverage} /> : null}

      {!streaming && m.content ? (
        <div className="flex items-center gap-1 pt-0.5">
          <IconButton label="Copy answer" icon={Copy} onClick={() => onCopy(m.content)} />
        </div>
      ) : null}
    </article>
  );
}

function StageLine({ label }: { label: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-ink-subtle" role="status" aria-live="polite">
      <LoaderCircle className="size-4 animate-spin text-brand" aria-hidden />
      {label}
    </p>
  );
}

function NotFound({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <div className="flex gap-3 rounded-card border border-dashed border-line-strong bg-surface px-4 py-3.5">
      <SearchX className="mt-0.5 size-5 shrink-0 text-ink-subtle" aria-hidden />
      <p className="text-sm leading-6 text-ink-muted">
        {text}
        {streaming ? <Caret /> : null}
      </p>
    </div>
  );
}

function Caret() {
  return <span aria-hidden className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-brand align-middle" />;
}

function CoverageBadge({ coverage }: { coverage: Coverage[] }) {
  const total = coverage.reduce((n, c) => n + c.chunksTotal, 0);
  const read = coverage.reduce((n, c) => n + c.chunksRead, 0);
  const unreadable = coverage.reduce((n, c) => n + c.unreadablePages, 0);
  const complete = coverage.every(isCoverageComplete);
  const detail = coverage
    .map((c) => `${c.name}: ${c.chunksRead}/${c.chunksTotal} sections${c.unreadablePages ? `, ${c.unreadablePages} unreadable pages` : ""}`)
    .join("\n");

  if (read >= total && unreadable === 0) {
    return (
      <Tip label={detail}>
        <span tabIndex={0} className="inline-flex items-center gap-1.5 text-xs font-medium text-ok">
          <ShieldCheck className="size-4" aria-hidden />
          Read all {total} section{total === 1 ? "" : "s"}
        </span>
      </Tip>
    );
  }
  return (
    <Tip label={detail}>
      <span tabIndex={0} className="inline-flex items-center gap-1.5 text-xs font-medium text-warn">
        <TriangleAlert className="size-4" aria-hidden />
        {complete || read >= total ? `Read all sections · ${unreadable} unreadable pages` : `Read ${read} of ${total} sections · absence not confirmed`}
      </span>
    </Tip>
  );
}

/* ---------- Answer text: tiny markdown + citation chips ---------- */

function RichAnswer({
  text,
  quotes,
  streaming,
  onOpenQuote,
}: {
  text: string;
  quotes: Quote[];
  streaming: boolean;
  onOpenQuote: (q: Quote) => void;
}) {
  // Hide a half-streamed marker such as "[Q" until it completes.
  const clean = streaming ? text.replace(/\[Q?\d*$/, "") : text;
  const blocks: ReactNode[] = [];
  let list: string[] = [];

  const flush = () => {
    if (list.length === 0) return;
    const items = list;
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="list-disc space-y-1.5 pl-5">
        {items.map((li, i) => (
          <li key={i}>{renderInline(li, quotes, onOpenQuote)}</li>
        ))}
      </ul>,
    );
    list = [];
  };

  for (const line of clean.split("\n")) {
    const bullet = /^\s*[*-]\s+(.*)$/.exec(line);
    if (bullet) {
      list.push(bullet[1] ?? "");
    } else {
      flush();
      if (line.trim()) blocks.push(<p key={`p-${blocks.length}`}>{renderInline(line, quotes, onOpenQuote)}</p>);
    }
  }
  flush();

  return (
    <div className="space-y-2.5 text-[15px] leading-7 text-ink">
      {blocks}
      {streaming ? <Caret /> : null}
    </div>
  );
}

function renderInline(s: string, quotes: Quote[], onOpen: (q: Quote) => void): ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*|\[Q\d+\])/g).map((part, i) => {
    const bold = /^\*\*([^*]+)\*\*$/.exec(part);
    if (bold) return <strong key={i} className="font-semibold">{bold[1]}</strong>;
    const cite = /^\[(Q\d+)\]$/.exec(part);
    if (cite) {
      // Only verified quotes may be cited. Unknown or unverified markers are dropped.
      const q = quotes.find((x) => x.ref === cite[1] && x.verified);
      if (!q) return null;
      return (
        <Tip key={i} label={`${q.documentName} · p.${q.page}`}>
          <button
            type="button"
            onClick={() => onOpen(q)}
            className="mx-0.5 inline-flex h-5 items-center rounded bg-brand-soft px-1.5 align-baseline text-[11px] font-bold text-brand transition-colors hover:bg-brand hover:text-white"
          >
            {q.ref}
          </button>
        </Tip>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
