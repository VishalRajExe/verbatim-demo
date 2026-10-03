"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PdfViewer } from "@/features/viewer/PdfViewer";
import {
  API_BASE,
  askStream,
  getConversation,
  listConversations,
  listDocuments,
  locateRanges,
} from "@/lib/api";
import type {
  AskEvent,
  ConversationSummary,
  Coverage,
  DocumentOut,
  UnverifiedQuote,
  VerifiedQuote,
} from "@/lib/types";

interface Turn {
  question: string;
  answer: string;
  quotes: VerifiedQuote[];
  unverified: UnverifiedQuote[];
  coverage: Coverage[];
  caveat?: string;
  status?: string;
}

export function ChatView() {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [activeConv, setActiveConv] = useState<string | null>(null);
  const [activeQuote, setActiveQuote] = useState<VerifiedQuote | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const ready = useMemo(() => docs.filter((d) => d.status === "ready"), [docs]);

  const refresh = useCallback(async () => {
    const [list, hist] = await Promise.all([listDocuments(), listConversations()]);
    setDocs(list.documents);
    setHistory(hist);
  }, []);

  useEffect(() => {
    refresh().catch(() => setDocs([]));
  }, [refresh]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });

  async function onAsk() {
    if (!question.trim() || selected.size === 0) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setProgress("Starting…");
    const draft: Turn = {
      question,
      answer: "",
      quotes: [],
      unverified: [],
      coverage: [],
    };
    setTurns((t) => [...t, draft]);
    const patch = (fn: (d: Turn) => Turn) =>
      setTurns((t) => {
        const copy = [...t];
        copy[copy.length - 1] = fn(copy[copy.length - 1]);
        return copy;
      });

    const onEvent = (e: AskEvent) => {
      if (e.type === "meta") {
        setActiveConv(e.conversationId); // follow-ups continue this conversation
      } else if (e.type === "status") {
        setProgress(`Reading ${e.documentName} (${e.done}/${e.total})…`);
      } else if (e.type === "quotes") {
        patch((d) => ({ ...d, quotes: e.quotes, unverified: e.unverified }));
      } else if (e.type === "coverage") {
        patch((d) => ({ ...d, coverage: e.coverage }));
      } else if (e.type === "caveat") {
        patch((d) => ({ ...d, caveat: e.message }));
      } else if (e.type === "token") {
        patch((d) => ({ ...d, answer: d.answer + e.text }));
      } else if (e.type === "done") {
        patch((d) => ({ ...d, status: e.status }));
      } else if (e.type === "error") {
        patch((d) => ({ ...d, answer: d.answer || `⚠ ${e.message}`, status: "error" }));
      }
    };

    try {
      await askStream(
        { documentIds: [...selected], question, conversationId: activeConv ?? undefined },
        onEvent,
        controller.signal,
      );
    } catch (err) {
      // A user-initiated Stop aborts the fetch mid-stream: that is an expected
      // outcome, not a failure, so keep the partial answer and mark it stopped
      // instead of surfacing the raw "BodyStreamBuffer was aborted" text.
      const e = err as Error;
      const aborted =
        controller.signal.aborted ||
        e?.name === "AbortError" ||
        /aborted/i.test(e?.message || "");
      if (aborted) {
        patch((d) => ({ ...d, status: d.status || "stopped" }));
      } else {
        patch((d) => ({ ...d, answer: d.answer || `⚠ ${e.message}`, status: "error" }));
      }
    } finally {
      setRunning(false);
      setProgress("");
      setQuestion("");
      refresh();
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  async function openConversation(id: string) {
    setActiveQuote(null); // never show a drawer from the previous conversation
    let detail;
    try {
      detail = await getConversation(id);
    } catch (err) {
      setProgress(`Could not load chat: ${(err as Error).message}`);
      return;
    }
    const rebuilt: Turn[] = [];
    let lastQuestion = "";
    for (const m of detail.messages) {
      if (m.role === "user") lastQuestion = m.content;
      else
        rebuilt.push({
          question: lastQuestion,
          answer: m.content,
          quotes: m.quotes
            .filter((q) => q.verified && q.start != null)
            .map((q) => ({
              ref: q.ref || "Q?",
              documentId: q.documentId,
              documentName: q.documentName,
              text: q.text,
              verified: true,
              matchKind: q.matchKind,
              start: q.start as number,
              end: q.end as number,
              pageStart: q.pageStart ?? 0,
              pageEnd: q.pageEnd ?? 0,
              occurrences: q.occurrences,
            })),
          unverified: m.quotes
            .filter((q) => !q.verified)
            .map((q) => ({
              documentId: q.documentId,
              documentName: q.documentName,
              text: q.text,
              verified: false,
              failReason: q.failReason || "NOT_FOUND",
            })),
          coverage: m.coverage || [],
          status: m.stopped ? "stopped" : "complete",
        });
    }
    setTurns(rebuilt);
    setActiveConv(id);
    // Re-scope the picker to the documents that conversation actually used,
    // otherwise a follow-up silently asks different documents.
    const used = new Set(
      detail.messages.flatMap((m) => (m.quotes || []).map((q) => q.documentId)),
    );
    if (used.size) setSelected(used);
  }

  function newChat() {
    abortRef.current?.abort();
    setTurns([]);
    setActiveConv(null);
    setActiveQuote(null);
  }

  return (
    <div className="flex h-full">
      {/* History rail */}
      <div className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex">
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-sm font-semibold text-slate-700">Recent chats</span>
          <button
            onClick={newChat}
            className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
          >
            + New chat
          </button>
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto px-2">
          {history.length === 0 && (
            <div className="px-3 py-2 text-xs text-slate-400">No chats yet.</div>
          )}
          {history.map((h) => (
            <button
              key={h.id}
              onClick={() => openConversation(h.id)}
              className={`block w-full truncate rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                activeConv === h.id
                  ? "bg-brand-50 font-medium text-brand-700"
                  : "text-slate-600"
              }`}
            >
              {h.title}
            </button>
          ))}
        </div>
      </div>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-slate-200 bg-white px-6 py-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
            Ask across documents ({ready.length} ready)
          </div>
          {ready.length === 0 ? (
            <p className="text-sm text-slate-500">
              Upload and process documents first, then select them here.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {ready.map((d) => (
                <button
                  key={d.id}
                  onClick={() => toggle(d.id)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    selected.has(d.id)
                      ? "border-brand-500 bg-brand-50 text-brand-700"
                      : "border-slate-300 text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {selected.has(d.id) ? "✓ " : ""}
                  {d.filename}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
          {turns.map((t, i) => (
            <TurnBlock
              key={i}
              turn={t}
              isLast={i === turns.length - 1}
              onCite={setActiveQuote}
            />
          ))}
          {turns.length === 0 && (
            <div className="text-sm text-slate-400">
              Answers are grounded only in your documents, and every quoted line
              is verified word-for-word before it is shown.
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 bg-white px-6 py-4">
          {progress && (
            <div
              className={`mb-2 text-xs ${
                running ? "text-brand-600" : "text-red-600"
              }`}
            >
              {progress}
            </div>
          )}
          <div className="flex items-end gap-2">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onAsk();
                }
              }}
              placeholder="Ask a question about the selected documents…"
              rows={2}
              className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500"
            />
            {running ? (
              <button onClick={stop} className="btn-danger">
                Stop
              </button>
            ) : (
              <button
                onClick={onAsk}
                disabled={!question.trim() || selected.size === 0}
                className="btn-primary"
              >
                Ask
              </button>
            )}
          </div>
        </div>
      </div>

      {activeQuote && (
        // Same-instance drawer: switching citations updates the quote in place
        // (no remount, no close→reopen→click-again). QuotePanel's effect is
        // keyed on `quote` and guards stale async responses, and PdfViewer
        // fully resets when docId changes, so document scoping is preserved.
        <QuotePanel quote={activeQuote} onClose={() => setActiveQuote(null)} />
      )}
    </div>
  );
}

function TurnBlock({
  turn,
  isLast,
  onCite,
}: {
  turn: Turn;
  isLast: boolean;
  onCite: (q: VerifiedQuote) => void;
}) {
  const byRef = new Map(turn.quotes.map((q) => [q.ref, q]));
  return (
    <div>
      <div className="mb-1 text-sm font-semibold text-slate-800">{turn.question}</div>
      <div className="whitespace-pre-wrap text-sm leading-6 text-slate-700">
        <AnswerText answer={turn.answer} byRef={byRef} onCite={onCite} />
      </div>
      {turn.caveat && (
        <div className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
          {turn.caveat}
        </div>
      )}
      {turn.unverified.length > 0 && (
        <div className="mt-2 text-xs text-slate-400">
          {turn.unverified.length} candidate quote(s) were rejected as not found —
          never shown as grounding.
        </div>
      )}
      {turn.quotes.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {turn.quotes.map((q) => (
            <button
              key={q.ref}
              onClick={() => onCite(q)}
              className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600 hover:bg-brand-50 hover:text-brand-700"
              title={q.text}
            >
              {q.ref} · p.{q.pageStart}
            </button>
          ))}
        </div>
      )}
      {turn.coverage.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
          {turn.coverage.map((c) => (
            <span key={c.documentId} className="rounded bg-slate-50 px-1.5 py-0.5">
              {c.name}: read {c.chunksRead}/{c.chunksTotal} chunks
              {c.pages ? ` · ${c.pages} pp` : ""}
              {c.complete
                ? " · full coverage"
                : ` · ${c.failedChunks.length} chunk(s) failed`}
              {c.unreadablePages ? ` · ${c.unreadablePages} unreadable page(s)` : ""}
            </span>
          ))}
        </div>
      )}
      {isLast && turn.status === "stopped" && (
        <div className="mt-2 text-xs text-red-500">Answer stopped early.</div>
      )}
    </div>
  );
}

function AnswerText({
  answer,
  byRef,
  onCite,
}: {
  answer: string;
  byRef: Map<string, VerifiedQuote>;
  onCite: (q: VerifiedQuote) => void;
}) {
  const parts = answer.split(/(\[Q\d+\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[(Q\d+)\]$/);
        if (m && byRef.has(m[1])) {
          const q = byRef.get(m[1])!;
          return (
            <button
              key={i}
              onClick={() => onCite(q)}
              className="mx-0.5 rounded bg-brand-50 px-1 text-xs font-medium text-brand-700 hover:bg-brand-100"
            >
              {p}
            </button>
          );
        }
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

function QuotePanel({
  quote,
  onClose,
}: {
  quote: VerifiedQuote;
  onClose: () => void;
}) {
  const [pages, setPages] = useState<{ page_number: number; text: string }[]>([]);
  const [location, setLocation] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  // A verified quote whose document has lost its stored source file is NOT the
  // same failure as a quote that is absent from the document. Keep them apart so
  // the drawer never implies a verified citation is bogus.
  const [sourceMissing, setSourceMissing] = useState(false);

  // Close the drawer with Escape; clicking another citation while it is open
  // switches in place instead of requiring a close + reopen.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setNotFound(false);
    setSourceMissing(false);
    setLocation("");
    setPages([]);
    (async () => {
      try {
        // 1. Load the CITATION'S OWN document (never the currently-open one).
        const res = await fetch(`${API_BASE}/api/documents/${quote.documentId}/pages`, {
          cache: "no-store",
        });
        if (!res.ok) {
          if (alive) setNotFound(true);
          return;
        }
        const data = await res.json();
        const docPages: { page_number: number; text: string }[] = data.pages || [];
        if (alive) setPages(docPages);

        // 2. Resolve the source range AGAINST THIS DOCUMENT ONLY.
        const loc = await locateRanges(quote.documentId, [
          { start: quote.start, end: quote.end },
        ]);
        const locatedPages = (loc.locations || []).map((l) => l.pageNumber);

        // 3. The cited page must actually exist in this document, and the range
        //    must resolve to a page within it. Otherwise it is NOT found here —
        //    we must never fall back to another document's page.
        const pageExistsHere = docPages.some((p) => p.page_number === quote.pageStart);
        const resolvedHere =
          locatedPages.length > 0 &&
          locatedPages.every((pg) => docPages.some((p) => p.page_number === pg));
        const found = (pageExistsHere || resolvedHere) && locatedPages.length > 0;

        if (!alive) return;
        if (!found) {
          // The text is stored in the database, so a range that resolves to no
          // geometry at all can also mean the source file went missing; the
          // typed 404 above is the authority, this is the fallback.
          setNotFound(true);
          return;
        }
        const l = loc.locations[0];
        setLocation(
          l.noGeometry
            ? `Page ${l.pageNumber} (exact text position available; pixel geometry is PDF-only)`
            : `Page ${l.pageNumber} · ${l.rects.length} line(s) matched`,
        );
      } catch (err) {
        if (!alive) return;
        if ((err as Error).message.includes("Source file not found on storage")) {
          setSourceMissing(true);
          return;
        }
        setNotFound(true);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [quote]);

  const pageText =
    pages.find((p) => p.page_number === quote.pageStart)?.text || "";
  const isPdf = quote.documentName.toLowerCase().endsWith(".pdf");

  return (
    // Side drawer pinned to the right edge. It intentionally does NOT cover
    // the whole screen: a full-screen backdrop used to swallow the first
    // click on another citation chip, forcing close→reopen→click again.
    <div
      data-testid="quote-drawer"
      className="fixed inset-y-0 right-0 z-40 flex w-[34rem] max-w-[92vw] flex-col border-l border-slate-200 bg-white shadow-xl"
    >
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <div className="text-sm font-semibold text-slate-800">
            {quote.ref} · {quote.documentName}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            ✕
          </button>
        </div>
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-500">
          {loading ? "Locating…" : location || `Page ${quote.pageStart}`}
          {quote.matchKind && (
            <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-700">
              verified · {quote.matchKind}
            </span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {!loading && notFound ? (
            <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              Source not found in this document.
              <div className="mt-1 text-xs text-amber-700">
                The cited passage could not be located in {quote.documentName} at
                page {quote.pageStart}. It may belong to a different document, so
                no other document was opened.
              </div>
            </div>
          ) : (
          <>
          {!loading && sourceMissing && (
            <div
              data-testid="source-missing"
              className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700"
            >
              The stored source file for {quote.documentName} is missing on the
              server, so page geometry cannot be shown.
              <div className="mt-1 text-xs text-slate-500">
                The quote below was still verified against this document&rsquo;s
                extracted text; re-upload the file to restore highlighting.
              </div>
            </div>
          )}
          {isPdf && !sourceMissing && (
            <div className="mb-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                  Highlighted in the document
                </span>
                <Link
                  href={`/documents/${quote.documentId}?ranges=${quote.start}-${quote.end}`}
                  target="_blank"
                  className="text-xs text-brand-600 hover:underline"
                >
                  Open full ↗
                </Link>
              </div>
              <div className="overflow-hidden rounded-lg ring-1 ring-slate-200">
                <PdfViewer
                  docId={quote.documentId}
                  ranges={[{ start: quote.start, end: quote.end }]}
                  className="h-72"
                />
              </div>
            </div>
          )}
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
            Quoted passage
          </div>
          <p className="rounded-lg border border-brand-200 bg-brand-50/50 p-3 text-sm leading-6 text-slate-700">
            {highlight(pageText, quote.text) || quote.text}
          </p>
          {pageText && (
            <>
              <div className="mt-4 mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                In context (page {quote.pageStart})
              </div>
              <p className="text-sm leading-6 text-slate-600">
                {highlight(pageText, quote.text)}
              </p>
            </>
          )}
          </>
          )}
        </div>
    </div>
  );
}

// Loosely find `quote` inside `text` (ignoring whitespace differences) and wrap
// the matched run in <mark>. Falls back to the raw text if not found.
function highlight(text: string, quote: string) {
  if (!text) return null;
  const tw = text.split(/(\s+)/);
  const qw = quote.trim().split(/\s+/);
  // Build a whitespace-stripped index map.
  const tokens: { w: string; idx: number }[] = [];
  tw.forEach((t, idx) => {
    if (t.trim()) tokens.push({ w: t.toLowerCase(), idx });
  });
  let pos = 0;
  let found = false;
  for (let i = 0; i <= tokens.length - qw.length; i++) {
    let ok = true;
    for (let j = 0; j < qw.length; j++) {
      if (tokens[i + j].w !== qw[j].toLowerCase()) {
        ok = false;
        break;
      }
    }
    if (ok) {
      pos = i;
      found = true;
      break;
    }
  }
  if (!found) return <>{text}</>;
  const startTok = tokens[pos].idx;
  const endTok = tokens[pos + qw.length - 1].idx;
  const before = tw.slice(0, startTok).join("");
  const mid = tw.slice(startTok, endTok + 1).join("");
  const after = tw.slice(endTok + 1).join("");
  return (
    <>
      {before}
      <mark className="rounded bg-yellow-200 px-0.5">{mid}</mark>
      {after}
    </>
  );
}
