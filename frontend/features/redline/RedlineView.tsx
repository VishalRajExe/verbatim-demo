"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createRedline,
  listDocuments,
  listRedlines,
  proposeRedline,
  redlineDownloadUrl,
} from "@/lib/api";
import type { DocumentOut, ProposedEdit, RedlineOut } from "@/lib/types";

interface Row {
  target: string;
  replacement: string;
}

type Mode = "instruction" | "manual";

function statusOf(r: RedlineOut): { label: string; cls: string } {
  if (r.applied.length > 0 && r.dropped.length === 0)
    return { label: "All applied", cls: "bg-emerald-50 text-emerald-700" };
  if (r.applied.length > 0)
    return { label: "Partially applied", cls: "bg-amber-50 text-amber-700" };
  return { label: "Nothing applied", cls: "bg-red-50 text-red-700" };
}

export function RedlineView() {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [docId, setDocId] = useState("");
  const [author, setAuthor] = useState("Legal AI");
  const [mode, setMode] = useState<Mode>("instruction");

  // Instruction-driven proposals (already verified against the DOCX text).
  const [instruction, setInstruction] = useState("");
  const [proposed, setProposed] = useState<ProposedEdit[]>([]);
  const [proposalDropped, setProposalDropped] = useState<
    { target: string; reason: string }[]
  >([]);
  const [proposing, setProposing] = useState(false);

  // Manual edit rows.
  const [rows, setRows] = useState<Row[]>([{ target: "", replacement: "" }]);

  const [result, setResult] = useState<RedlineOut | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  // Persisted session history (DB-backed; survives refresh).
  const [sessions, setSessions] = useState<RedlineOut[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);

  // Tracked changes are DOCX-only (OOXML run tree).
  const docxReady = useMemo(
    () => docs.filter((d) => d.status === "ready" && d.file_type === ".docx"),
    [docs],
  );
  const docNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const d of docs) m.set(d.id, d.filename);
    return m;
  }, [docs]);

  useEffect(() => {
    listDocuments()
      .then((l) => setDocs(l.documents))
      .catch(() => setDocs([]));
  }, []);

  const refreshSessions = useCallback((documentId?: string) => {
    listRedlines(documentId || undefined)
      .then(setSessions)
      .catch(() => setSessions([]));
  }, []);

  useEffect(() => refreshSessions(docId), [docId, refreshSessions]);

  const setRow = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  function resetProposal() {
    setProposed([]);
    setProposalDropped([]);
    setResult(null);
    setError("");
  }

  async function onPropose() {
    if (!docId) {
      setError("Select a DOCX first.");
      return;
    }
    if (instruction.trim().length < 3) {
      setError("Describe the change you want, e.g. \u201CChange the liability cap from AED 100,000 to AED 1,000,000.\u201D");
      return;
    }
    setError("");
    setProposing(true);
    resetProposal();
    try {
      const out = await proposeRedline(docId, instruction.trim());
      setProposed(out.proposed);
      setProposalDropped(out.dropped);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setProposing(false);
    }
  }

  async function applyEdits(
    edits: { target: string; replacement: string }[],
    instructionText: string | null,
  ) {
    if (!docId || edits.length === 0) {
      setError("Add at least one edit to apply.");
      return;
    }
    setError("");
    setRunning(true);
    setResult(null);
    try {
      const res = await createRedline(docId, {
        edits,
        author,
        instruction: instructionText,
      });
      setResult(res);
      refreshSessions(docId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  function onApplyProposal() {
    const selected = proposed.filter((e) => e.include);
    applyEdits(
      selected.map((e) => ({ target: e.target, replacement: e.replacement })),
      instruction.trim(),
    );
  }

  function onApplyManual() {
    applyEdits(
      rows
        .filter((r) => r.target.trim().length > 0)
        .map((r) => ({ target: r.target, replacement: r.replacement })),
      null,
    );
  }

  function reuseAsManual(r: RedlineOut) {
    setRows(
      r.applied.length > 0
        ? r.applied.map((e) => ({ target: e.target, replacement: e.replacement }))
        : [{ target: "", replacement: "" }],
    );
    setMode("manual");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const includedCount = proposed.filter((e) => e.include).length;

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="mb-1 text-lg font-semibold text-slate-900">Redline (tracked changes)</h1>
      <p className="mb-6 text-sm text-slate-500">
        Produces a real <code>.docx</code> with Word tracked changes
        (<code>&lt;w:ins&gt;</code> / <code>&lt;w:del&gt;</code>). Describe the change
        in plain English or edit manually — every target must appear exactly once
        in the document, or it is safely skipped and reported with the reason.
      </p>

      <div className="card mb-6 p-5">
        <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400">
              Document (DOCX only)
            </span>
            <select
              value={docId}
              onChange={(e) => {
                setDocId(e.target.value);
                resetProposal();
              }}
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

        <div className="mb-4 inline-flex rounded-lg border border-slate-200 p-0.5 text-xs">
          {(["instruction", "manual"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                setError("");
              }}
              className={`rounded-md px-3 py-1.5 font-medium ${
                mode === m
                  ? "bg-indigo-600 text-white"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              {m === "instruction" ? "In plain English" : "Manual edits"}
            </button>
          ))}
        </div>

        {mode === "instruction" ? (
          <div>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder='Describe the change, e.g. "Change the liability cap from AED 100,000 to AED 1,000,000."'
              rows={3}
              className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <div className="mt-3 flex items-center gap-3">
              <p className="text-xs text-slate-400">
                The named original value is checked against the document before
                anything is proposed.
              </p>
              <button
                onClick={onPropose}
                disabled={proposing || running || !docId}
                className="btn-primary ml-auto shrink-0"
              >
                {proposing ? "Reading document\u2026" : "Propose edits"}
              </button>
            </div>

            {proposalDropped.length > 0 && (
              <div className="mt-4 rounded-lg bg-amber-50 p-3">
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-700">
                  Not proposed
                </div>
                <ul className="space-y-1 text-xs text-amber-700">
                  {proposalDropped.map((d, i) => (
                    <li key={i}>
                      {"\u201C"}
                      {d.target}
                      {"\u201D"} — {d.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {proposed.length > 0 && (
              <div className="mt-4 space-y-2">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Verified proposals ({proposed.length}) — review before applying
                </div>
                {proposed.map((e, i) => (
                  <label
                    key={i}
                    className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm ${
                      e.include ? "border-slate-300 bg-white" : "border-slate-200 bg-slate-50 opacity-60"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={e.include}
                      onChange={(ev) =>
                        setProposed((ps) =>
                          ps.map((p, idx) =>
                            idx === i ? { ...p, include: ev.target.checked } : p,
                          ),
                        )
                      }
                      className="mt-0.5"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className="text-red-600 line-through break-words">
                          {e.target}
                        </span>
                        <span className="text-slate-400">→</span>
                        <span className="text-emerald-700 break-words">
                          {e.replacement || "(deleted)"}
                        </span>
                      </div>
                      {e.reason && (
                        <div className="mt-1 text-xs text-slate-400">{e.reason}</div>
                      )}
                    </div>
                  </label>
                ))}
                <div className="flex justify-end">
                  <button
                    onClick={onApplyProposal}
                    disabled={running || proposing || includedCount === 0}
                    className="btn-primary"
                  >
                    {running
                      ? "Applying\u2026"
                      : `Apply ${includedCount} selected edit${includedCount === 1 ? "" : "s"}`}
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div>
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
                      {"\u2715"}
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
                onClick={onApplyManual}
                disabled={running || proposing || !docId}
                className="btn-primary ml-auto"
              >
                {running ? "Applying\u2026" : "Apply tracked changes"}
              </button>
            </div>
          </div>
        )}
        {error && <div className="mt-3 text-sm text-red-600">{error}</div>}
      </div>

      {result && (
        <div className="card mb-6 p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-800">Latest result</div>
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
                    {"\u201C"}
                    {d.target}
                    {"\u201D"} — {d.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ── Session history (persisted; reloads after refresh) ── */}
      <div className="card p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-sm font-semibold text-slate-800">
            Redline sessions{docId ? ` for ${docNameById.get(docId) ?? "this document"}` : ""}
          </div>
          <button
            onClick={() => refreshSessions(docId)}
            className="btn-secondary text-xs"
          >
            Refresh
          </button>
        </div>
        {sessions.length === 0 && (
          <p className="text-sm text-slate-400">
            No redline sessions yet. Propose or apply edits above and they will be
            recorded here.
          </p>
        )}
        <ul className="space-y-2">
          {sessions.map((s) => {
            const st = statusOf(s);
            const open = expanded === s.id;
            return (
              <li key={s.id} className="rounded-lg border border-slate-200">
                <button
                  onClick={() => setExpanded(open ? null : s.id)}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm"
                >
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${st.cls}`}>
                    {st.label}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-slate-700">
                    {s.instruction || `${s.applied.length} manual edit(s)`}
                  </span>
                  {!docId && (
                    <span className="hidden shrink-0 text-xs text-slate-400 sm:inline">
                      {docNameById.get(s.documentId) ?? "document"}
                    </span>
                  )}
                  <span className="shrink-0 text-xs text-slate-400">
                    {new Date(s.createdAt).toLocaleString()}
                  </span>
                  <span className="shrink-0 text-xs text-slate-400">{open ? "\u25B4" : "\u25BE"}</span>
                </button>
                {open && (
                  <div className="border-t border-slate-100 px-3 py-3 text-sm">
                    <div className="mb-2 flex flex-wrap gap-3 text-xs text-slate-500">
                      <span>Author: {s.author}</span>
                      <span>{s.insertions} insertion(s)</span>
                      <span>{s.deletions} deletion(s)</span>
                    </div>
                    {s.applied.length > 0 && (
                      <ul className="mb-2 space-y-1">
                        {s.applied.map((e, i) => (
                          <li key={i} className="rounded bg-slate-50 p-1.5 text-xs">
                            <span className="text-red-600 line-through">{e.target}</span>{" "}
                            <span className="text-slate-400">→</span>{" "}
                            <span className="text-emerald-700">
                              {e.replacement || "(deleted)"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {s.dropped.length > 0 && (
                      <ul className="mb-2 space-y-1 text-xs text-amber-700">
                        {s.dropped.map((d, i) => (
                          <li key={i}>
                            Skipped {"\u201C"}
                            {d.target}
                            {"\u201D"} — {d.reason}
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="mt-2 flex gap-2">
                      <a
                        href={redlineDownloadUrl(s.id)}
                        className="btn-primary text-xs"
                        target="_blank"
                        rel="noreferrer"
                      >
                        Download .docx
                      </a>
                      <button
                        onClick={() => reuseAsManual(s)}
                        className="btn-secondary text-xs"
                      >
                        Reuse edits
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
