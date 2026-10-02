"use client";

import { useEffect, useMemo, useState } from "react";

import { createRedline, listDocuments, redlineDownloadUrl } from "@/lib/api";
import type { DocumentOut, RedlineOut } from "@/lib/types";

interface Row {
  target: string;
  replacement: string;
}

export function RedlineView() {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [docId, setDocId] = useState("");
  const [author, setAuthor] = useState("Legal AI");
  const [rows, setRows] = useState<Row[]>([{ target: "", replacement: "" }]);
  const [result, setResult] = useState<RedlineOut | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  // Tracked changes are DOCX-only (OOXML run tree).
  const docxReady = useMemo(
    () => docs.filter((d) => d.status === "ready" && d.file_type === ".docx"),
    [docs],
  );

  useEffect(() => {
    listDocuments()
      .then((l) => setDocs(l.documents))
      .catch(() => setDocs([]));
  }, []);

  const setRow = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  async function onApply() {
    const edits = rows
      .filter((r) => r.target.trim().length > 0)
      .map((r) => ({ target: r.target, replacement: r.replacement }));
    if (!docId || edits.length === 0) {
      setError("Select a DOCX and add at least one edit.");
      return;
    }
    setError("");
    setRunning(true);
    setResult(null);
    try {
      const res = await createRedline(docId, { edits, author });
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="mb-1 text-lg font-semibold text-slate-900">Redline (tracked changes)</h1>
      <p className="mb-6 text-sm text-slate-500">
        Produces a real <code>.docx</code> with Word tracked changes
        (<code>&lt;w:ins&gt;</code> / <code>&lt;w:del&gt;</code>). Each target must
        appear exactly once, or it is safely skipped and reported.
      </p>

      <div className="card mb-6 p-5">
        <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
              Document (DOCX only)
            </span>
            <select
              value={docId}
              onChange={(e) => setDocId(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Select…</option>
              {docxReady.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
              Author
            </span>
            <input
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
        </div>

        {docxReady.length === 0 && (
          <p className="mb-3 text-sm text-amber-700">
            No ready DOCX documents found. Upload a .docx first.
          </p>
        )}

        <div className="space-y-3">
          {rows.map((r, i) => (
            <div key={i} className="flex items-start gap-2">
              <div className="flex-1 space-y-1">
                <textarea
                  value={r.target}
                  onChange={(e) => setRow(i, { target: e.target.value })}
                  placeholder="Exact text to replace (must appear once)…"
                  rows={2}
                  className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
                <textarea
                  value={r.replacement}
                  onChange={(e) => setRow(i, { replacement: e.target.value })}
                  placeholder="Replacement text…"
                  rows={2}
                  className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </div>
              {rows.length > 1 && (
                <button
                  onClick={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
                  className="mt-1 text-slate-400 hover:text-red-500"
                  title="Remove edit"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={() => setRows((rs) => [...rs, { target: "", replacement: "" }])}
            className="btn-secondary text-xs"
          >
            + Add edit
          </button>
          <button
            onClick={onApply}
            disabled={running || !docId}
            className="btn-primary ml-auto"
          >
            {running ? "Applying…" : "Apply tracked changes"}
          </button>
        </div>
        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
      </div>

      {result && (
        <div className="card p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-800">Result</div>
            <a
              href={redlineDownloadUrl(result.id)}
              className="btn-primary text-xs"
              target="_blank"
              rel="noreferrer"
            >
              Download .docx
            </a>
          </div>
          <div className="mb-4 flex gap-4 text-sm">
            <div className="rounded-lg bg-emerald-50 px-3 py-2 text-emerald-700">
              {result.insertions} insertion(s)
            </div>
            <div className="rounded-lg bg-red-50 px-3 py-2 text-red-700">
              {result.deletions} deletion(s)
            </div>
          </div>
          <ul className="space-y-2 text-sm">
            {result.applied.map((e, i) => (
              <li key={i} className="rounded-lg bg-slate-50 p-2">
                <span className="text-red-600 line-through">{e.target}</span>{" "}
                <span className="text-slate-400">→</span>{" "}
                <span className="text-emerald-700">{e.replacement || "(deleted)"}</span>
              </li>
            ))}
          </ul>
          {result.dropped.length > 0 && (
            <div className="mt-4">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-700">
                Skipped (not applied)
              </div>
              <ul className="space-y-1 text-xs text-amber-700">
                {result.dropped.map((d, i) => (
                  <li key={i}>
                    “{d.target}” — {d.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
