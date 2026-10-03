"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import { StatusBadge } from "@/components/StatusBadge";
import {
  deleteDocument,
  formatBytes,
  listDocuments,
  uploadDocument,
} from "@/lib/api";
import type { DocumentOut } from "@/lib/types";

const POLL_MS = 1500;

export function DocumentLibrary() {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshed, setRefreshed] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await listDocuments();
      setDocs(res.documents);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load.
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll only while at least one document is still processing.
  const hasActive = docs.some(
    (d) => d.status === "pending" || d.status === "processing",
  );
  useEffect(() => {
    if (!hasActive) return;
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [hasActive, refresh]);

  async function onFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadDocument(file);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function onDelete(doc: DocumentOut) {
    if (!confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return;
    try {
      await deleteDocument(doc.id);
      setDocs((prev) => prev.filter((d) => d.id !== doc.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed.");
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Documents</h1>
          <p className="text-sm text-slate-500">
            Upload PDF or DOCX contracts to analyse them.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-secondary"
            onClick={() => {
              setRefreshed((n) => n + 1);
              refresh();
            }}
            title="Refresh list"
          >
            Refresh
          </button>
          <button
            className="btn-primary"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
          >
            {uploading ? "Uploading…" : "Upload document"}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={onFileSelected}
          />
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="card overflow-hidden">
        {loading ? (
          <div className="px-6 py-16 text-center text-sm text-slate-500">
            Loading documents…
          </div>
        ) : docs.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <p className="text-sm font-medium text-slate-600">
              No documents yet
            </p>
            <p className="mt-1 text-sm text-slate-400">
              Upload a PDF or DOCX to get started.
            </p>
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Size</th>
                <th className="px-4 py-3 font-medium">Pages</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {docs.map((doc) => (
                <DocumentRow
                  key={`${doc.id}-${refreshed}`}
                  doc={doc}
                  onDelete={() => onDelete(doc)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function DocumentRow({
  doc,
  onDelete,
}: {
  doc: DocumentOut;
  onDelete: () => void;
}) {
  const ready = doc.status === "ready";
  return (
    <tr className="hover:bg-slate-50/60">
      <td className="max-w-[22rem] px-4 py-3">
        <div className="truncate font-medium text-slate-800">
          {doc.filename}
        </div>
        {doc.status === "error" && doc.error_message && (
          <div className="mt-0.5 truncate text-xs text-red-600">
            {doc.error_message}
          </div>
        )}
        <div className="text-xs text-slate-400">
          {new Date(doc.created_at).toLocaleString()}
        </div>
      </td>
      <td className="px-4 py-3 uppercase text-slate-500">
        {doc.file_type.replace(".", "")}
      </td>
      <td className="px-4 py-3 text-slate-500">{formatBytes(doc.file_size)}</td>
      <td className="px-4 py-3 text-slate-500">{doc.page_count ?? "—"}</td>
      <td className="px-4 py-3">
        <StatusBadge status={doc.status} />
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-1.5">
          <Link
            href={`/documents/${doc.id}`}
            aria-disabled={!ready}
            className={`btn-secondary !px-2.5 !py-1 text-xs ${
              ready ? "" : "pointer-events-none opacity-50"
            }`}
          >
            Open
          </Link>
          <button
            className="btn-secondary !px-2.5 !py-1 text-xs"
            disabled
            title="Coming in Phase 3"
          >
            Chat
          </button>
          <button
            className="btn-secondary !px-2.5 !py-1 text-xs"
            disabled
            title="Coming in Phase 7"
          >
            Compare
          </button>
          <button
            onClick={onDelete}
            className="btn-danger !px-2.5 !py-1 text-xs"
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  );
}
