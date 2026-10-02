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

export function CompareView() {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<ComparisonResult[]>([]);

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

  const sortedChanges = result
    ? [...result.changes].sort(
        (x, y) => (SIGN_ORDER[y.significance] ?? 0) - (SIGN_ORDER[x.significance] ?? 0),
      )
    : [];

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
          {history.length > 0 && (
            <div className="text-xs text-slate-400">
              {history.length} prior comparison(s)
            </div>
          )}
        </div>
      </div>

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
                <Stat label="total" value={(result.stats as any).total} />
                {Object.entries(((result.stats as any).bySignificance) || {}).map(
                  ([k, v]) => (
                    <Stat key={k} label={k} value={v as number} />
                  ),
                )}
              </div>
            )}
          </div>

          <div className="space-y-3">
            {sortedChanges.length === 0 && (
              <div className="card p-6 text-center text-sm text-slate-500">
                No differences detected.
              </div>
            )}
            {sortedChanges.map((c) => (
              <ChangeCard key={c.orderIdx} change={c} />
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

function ChangeCard({ change }: { change: ComparisonChange }) {
  return (
    <div className="card p-4">
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
          <div className="mb-1 font-medium text-red-700">A · {change.type === "ADDED" ? "(absent)" : "baseline"}</div>
          <div className="whitespace-pre-wrap">{change.aText || "—"}</div>
        </div>
        <div className="rounded-lg bg-emerald-50 p-2 text-emerald-900">
          <div className="mb-1 font-medium text-emerald-700">B · {change.type === "REMOVED" ? "(absent)" : "revised"}</div>
          <div className="whitespace-pre-wrap">{change.bText || "—"}</div>
        </div>
      </div>
    </div>
  );
}
