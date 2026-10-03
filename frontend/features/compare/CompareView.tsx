"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { createComparison, listComparisons, listDocuments } from "@/lib/api";
import type { ComparisonChange, ComparisonResult, DocumentOut } from "@/lib/types";

const SIGN_ORDER: Record<string, number> = {
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
  COSMETIC: 0,
};

const SIGN_STYLE: Record<string, string> = {
  HIGH: "bg-red-100 text-red-700 ring-red-200",
  MEDIUM: "bg-amber-100 text-amber-700 ring-amber-200",
  LOW: "bg-slate-100 text-slate-600 ring-slate-200",
  COSMETIC: "bg-slate-50 text-slate-400 ring-slate-100",
};

// Materiality levels and change types come from the server's classification;
// the UI only filters/sorts what it was given — it never re-judges materiality.
const LEVELS = ["HIGH", "MEDIUM", "LOW", "COSMETIC"];
const TYPES = ["MODIFIED", "ADDED", "REMOVED"];

type SortKey = "significance" | "significance_asc" | "document" | "category";

const SORTERS: Record<SortKey, (x: ComparisonChange, y: ComparisonChange) => number> = {
  significance: (x, y) =>
    (SIGN_ORDER[y.significance] ?? 0) - (SIGN_ORDER[x.significance] ?? 0) ||
    x.orderIdx - y.orderIdx,
  significance_asc: (x, y) =>
    (SIGN_ORDER[x.significance] ?? 0) - (SIGN_ORDER[y.significance] ?? 0) ||
    x.orderIdx - y.orderIdx,
  document: (x, y) => x.orderIdx - y.orderIdx,
  category: (x, y) =>
    (x.category ?? "").localeCompare(y.category ?? "") ||
    (SIGN_ORDER[y.significance] ?? 0) - (SIGN_ORDER[x.significance] ?? 0) ||
    x.orderIdx - y.orderIdx,
};

export function CompareView() {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<ComparisonResult[]>([]);
  const [levels, setLevels] = useState<Record<string, boolean>>(
    Object.fromEntries(LEVELS.map((l) => [l, true])),
  );
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("significance");

  const ready = useMemo(() => docs.filter((d) => d.status === "ready"), [docs]);

  const refresh = useCallback(async () => {
    const [list, hist] = await Promise.all([listDocuments(), listComparisons()]);
    setDocs(list.documents);
    setHistory(hist);
  }, []);

  useEffect(() => {
    refresh().catch(() => setDocs([]));
  }, [refresh]);

  async function onCompare() {
    if (!a || !b || a === b) {
      setError("Choose two different documents to compare.");
      return;
    }
    setError("");
    setRunning(true);
    try {
      const res = await createComparison({ documentAId: a, documentBId: b });
      setResult(res);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const counts = useMemo(() => {
    const byLevel: Record<string, number> = {};
    for (const c of result?.changes ?? []) {
      byLevel[c.significance] = (byLevel[c.significance] ?? 0) + 1;
    }
    return byLevel;
  }, [result]);

  // Filter and sort happen on the server-classified data; nothing here decides
  // materiality, it only selects which already-classified rows are visible.
  const visibleChanges = useMemo(() => {
    const all = result?.changes ?? [];
    const kept = all.filter(
      (c) => (levels[c.significance] ?? true) && (typeFilter === "ALL" || c.type === typeFilter),
    );
    return [...kept].sort(SORTERS[sortKey]);
  }, [result, levels, typeFilter, sortKey]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="mb-1 text-lg font-semibold text-slate-900">Compare contracts</h1>
      <p className="mb-6 text-sm text-slate-500">
        Clause-aware comparison. Materiality is computed on the server; the
        summary below is automatic and conservative.
      </p>

      <div className="card mb-6 p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
              Document A (baseline)
            </span>
            <select
              value={a}
              onChange={(e) => setA(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Select…</option>
              {ready.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
              Document B (revised)
            </span>
            <select
              value={b}
              onChange={(e) => setB(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Select…</option>
              {ready.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={onCompare}
            disabled={running || !a || !b}
            className="btn-primary"
          >
            {running ? "Comparing…" : "Compare"}
          </button>
        </div>
      </div>

      {/* ── Persisted comparisons (DB-backed; reopen without re-running) ── */}
      {history.length > 0 && (
        <div className="card mb-6 p-5">
          <div className="mb-2 text-sm font-semibold text-slate-800">
            Prior comparisons ({history.length})
          </div>
          <ul className="space-y-1">
            {history.map((h) => (
              <li key={h.id}>
                <button
                  type="button"
                  data-testid="reopen-comparison"
                  onClick={() => {
                    // Show the stored result verbatim and restore its two
                    // document selections; nothing is recomputed or judged here.
                    setResult(h);
                    setA(h.documentAId);
                    setB(h.documentBId);
                    setError("");
                  }}
                  className="flex w-full items-center gap-3 rounded-lg border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50"
                >
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                    {h.changes.length} change(s)
                  </span>
                  <span className="min-w-0 flex-1 truncate text-slate-700">
                    {h.summary}
                  </span>
                  <span className="shrink-0 text-xs text-slate-400">
                    {new Date(h.createdAt).toLocaleString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result && (
        <>
          <div className="card mb-6 p-5">
            <div className="mb-1 flex items-center justify-between">
              <div className="text-sm font-semibold text-slate-800">Summary</div>
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                {result.summarySource}
              </span>
            </div>
            <p className="text-sm leading-6 text-slate-700">{result.summary}</p>
            {result.stats && (
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                <Stat
                  label="total"
                  value={(result.stats as { total?: number }).total ?? 0}
                />
                {Object.entries(
                  (result.stats as { bySignificance?: Record<string, number> })
                    .bySignificance ?? {},
                ).map(([k, v]) => (
                  <Stat key={k} label={k} value={v} />
                ))}
              </div>
            )}
          </div>

          <div className="card mb-6 p-4">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                  Materiality
                </span>
                {LEVELS.map((l) => (
                  <button
                    key={l}
                    type="button"
                    data-testid={`filter-${l}`}
                    onClick={() => setLevels((prev) => ({ ...prev, [l]: !prev[l] }))}
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
                      levels[l]
                        ? SIGN_STYLE[l]
                        : "bg-white text-slate-300 ring-slate-200 line-through"
                    }`}
                  >
                    {l} ({counts[l] ?? 0})
                  </button>
                ))}
              </div>
              <label className="flex items-center gap-2 text-xs text-slate-500">
                Type
                <select
                  data-testid="filter-type"
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="rounded-lg border border-slate-300 px-2 py-1 text-xs"
                >
                  <option value="ALL">All</option>
                  {TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-500">
                Sort
                <select
                  data-testid="sort-key"
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value as SortKey)}
                  className="rounded-lg border border-slate-300 px-2 py-1 text-xs"
                >
                  <option value="significance">Significance (high → low)</option>
                  <option value="significance_asc">Significance (low → high)</option>
                  <option value="document">Document order</option>
                  <option value="category">Clause / category</option>
                </select>
              </label>
              <span className="ml-auto text-xs text-slate-400" data-testid="change-count">
                Showing {visibleChanges.length} of {result.changes.length} change(s)
              </span>
            </div>
          </div>

          <div className="space-y-3" data-testid="change-list">
            {visibleChanges.length === 0 && (
              <div className="card p-6 text-center text-sm text-slate-500">
                {result.changes.length === 0
                  ? "No differences detected."
                  : "No changes match the current filter."}
              </div>
            )}
            {visibleChanges.map((c) => (
              <ChangeCard
                key={c.orderIdx}
                change={c}
                docAId={result.documentAId}
                docBId={result.documentBId}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <span className="rounded-lg bg-slate-50 px-2 py-1 ring-1 ring-slate-200">
      {label}: <span className="font-semibold text-slate-700">{value}</span>
    </span>
  );
}

function ChangeCard({
  change,
  docAId,
  docBId,
}: {
  change: ComparisonChange;
  docAId: string;
  docBId: string;
}) {
  // "Open source" jumps to the exact character range of that side's clause in
  // its own document, so both sides of every change stay verifiable.
  const sourceHref = (docId: string, start: number | null, end: number | null) =>
    start === null || end === null
      ? `/documents/${docId}`
      : `/documents/${docId}?ranges=${start}-${end}`;

  return (
    <div
      className="card p-4"
      data-testid="change-card"
      data-significance={change.significance}
      data-type={change.type}
      data-order={change.orderIdx}
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
            SIGN_STYLE[change.significance] || SIGN_STYLE.LOW
          }`}
        >
          {change.significance}
        </span>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {change.type}
        </span>
        {change.category && (
          <span className="text-xs text-slate-400">{change.category}</span>
        )}
        <span className="ml-auto text-sm font-semibold text-slate-800">
          {change.title}
        </span>
      </div>
      <p className="mb-2 text-sm text-slate-600">{change.summary}</p>
      <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
        <div className="rounded-lg bg-red-50 p-2 text-red-900">
          <div className="mb-1 flex items-center justify-between font-medium text-red-700">
            <span>A · {change.type === "ADDED" ? "(absent)" : "baseline"}</span>
            {change.type !== "ADDED" && (
              <a
                href={sourceHref(docAId, change.aStart, change.aEnd)}
                className="text-[11px] font-normal text-red-600 hover:underline"
              >
                open source ↗
              </a>
            )}
          </div>
          <div className="whitespace-pre-wrap">{change.aText || "—"}</div>
        </div>
        <div className="rounded-lg bg-emerald-50 p-2 text-emerald-900">
          <div className="mb-1 flex items-center justify-between font-medium text-emerald-700">
            <span>B · {change.type === "REMOVED" ? "(absent)" : "revised"}</span>
            {change.type !== "REMOVED" && (
              <a
                href={sourceHref(docBId, change.bStart, change.bEnd)}
                className="text-[11px] font-normal text-emerald-600 hover:underline"
              >
                open source ↗
              </a>
            )}
          </div>
          <div className="whitespace-pre-wrap">{change.bText || "—"}</div>
        </div>
      </div>
    </div>
  );
}
