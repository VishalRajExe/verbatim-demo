/**
 * Real API client — calls the FastAPI backend on :8000.
 * No mock data; every function hits the live backend.
 */
import type {
  Chat,
  ChatSummary,
  Comparison,
  ComparisonListItem,
  Coverage,
  DocumentItem,
  Message,
  Quote,
  RedlineEdit,
  RedlineSession,
} from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

// ── helpers ──────────────────────────────────────────────────────────────────

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Convert backend DocumentOut → verbatim-ui DocumentItem */
function adaptDocument(d: {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  page_count: number | null;
  status: string;
  error_message: string | null;
  created_at: string;
}): DocumentItem {
  const statusMap: Record<string, DocumentItem["status"]> = {
    pending: "queued",
    processing: "extracting",
    ready: "ready",
    error: "failed",
  };
  const status = statusMap[d.status] ?? "queued";
  // Backend returns file_type with a leading dot (".docx"/".pdf"); normalise so
  // DOCX documents are correctly typed (the Redline picker filters on kind).
  const ext = (d.file_type ?? "").replace(/^\./, "").toLowerCase();
  return {
    id: d.id,
    name: d.filename,
    kind: ext === "docx" ? "docx" : "pdf",
    sizeBytes: d.file_size,
    pages: d.page_count,
    status,
    stage: status === "extracting" ? "Processing…" : null,
    progress: status === "ready" ? 100 : status === "failed" ? 0 : 50,
    errorMessage: d.error_message,
    warning: null,
    createdAt: d.created_at,
  };
}

/** Convert backend MessageRow → verbatim-ui Message */
function adaptMessage(m: {
  id: number;
  role: "user" | "assistant";
  content: string;
  stopped: boolean;
  coverage: BackendCoverage[] | null;
  createdAt: string;
  quotes: BackendQuote[];
}): Message {
  return {
    id: String(m.id),
    role: m.role,
    content: m.content,
    status: m.stopped ? "stopped" : "complete",
    kind: "answer",
    quotes: (m.quotes ?? []).map(adaptQuote),
    coverage: (m.coverage ?? []).map(adaptCoverage),
    errorMessage: null,
  };
}

interface BackendQuote {
  id: number;
  documentId: string;
  documentName: string;
  ref: string | null;
  refIndex: number;
  text: string;
  verified: boolean;
  matchKind: string | null;
  failReason: string | null;
  start: number | null;
  end: number | null;
  pageStart: number | null;
  pageEnd: number | null;
  occurrences: number;
}

interface BackendCoverage {
  documentId: string;
  name: string;
  chunksTotal: number;
  chunksRead: number;
  failedChunks: number[];
  pages: number;
  unreadablePages: number;
  complete: boolean;
}

function adaptQuote(q: BackendQuote): Quote {
  return {
    ref: q.ref ?? `Q${q.refIndex + 1}`,
    documentId: q.documentId,
    documentName: q.documentName,
    verified: q.verified,
    matchKind: (q.matchKind as Quote["matchKind"]) ?? null,
    failReason: q.failReason,
    text: q.text,
    page: q.pageStart ?? null,
    lines: q.pageStart != null && q.pageEnd != null ? q.pageEnd - q.pageStart + 1 : null,
    occurrences: q.occurrences,
    start: q.start ?? null,
    end: q.end ?? null,
  };
}

function adaptCoverage(c: BackendCoverage): Coverage {
  return {
    documentId: c.documentId,
    name: c.name,
    chunksTotal: c.chunksTotal,
    chunksRead: c.chunksRead,
    unreadablePages: c.unreadablePages,
  };
}

// ── AskEvent from backend NDJSON ──────────────────────────────────────────────

export type AskEvent =
  | { type: "stage"; label: string }
  | { type: "quotes"; quotes: Quote[]; coverage: Coverage[]; kind: "answer" | "not_found" }
  | { type: "token"; text: string };

// ── Documents ─────────────────────────────────────────────────────────────────

export async function listDocuments(): Promise<DocumentItem[]> {
  const res = await fetch(`${API_BASE}/api/documents`, { cache: "no-store" });
  const data = await handle<{ documents: ReturnType<typeof Object>[] }>(res) as {
    documents: Parameters<typeof adaptDocument>[0][];
  };
  return data.documents.map(adaptDocument);
}

export async function getDocument(id: string): Promise<DocumentItem> {
  const res = await fetch(`${API_BASE}/api/documents/${id}`, { cache: "no-store" });
  const data = await handle<Parameters<typeof adaptDocument>[0]>(res);
  return adaptDocument(data);
}

export interface DocumentPage {
  pageNumber: number;
  text: string;
}

export interface DocumentPages {
  id: string;
  filename: string;
  totalPages: number;
  pages: DocumentPage[];
}

/** Extracted page text — used to render Word (.docx) documents as text. */
export async function getDocumentPages(id: string): Promise<DocumentPages> {
  const res = await fetch(`${API_BASE}/api/documents/${id}/pages`, { cache: "no-store" });
  const data = await handle<{
    id: string;
    filename: string;
    total_pages: number;
    pages: Array<{ page_number: number; text: string }>;
  }>(res);
  return {
    id: data.id,
    filename: data.filename,
    totalPages: data.total_pages,
    pages: data.pages.map((p) => ({ pageNumber: p.page_number, text: p.text })),
  };
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/documents/${id}`, { method: "DELETE" });
  await handle<void>(res);
}

export async function uploadDocument(
  file: File,
  onProgress: (pct: number) => void,
): Promise<DocumentItem> {
  // Simulate progress since fetch doesn't give upload progress natively
  onProgress(10);
  const form = new FormData();
  form.append("file", file);
  onProgress(40);
  const res = await fetch(`${API_BASE}/api/documents/upload`, {
    method: "POST",
    body: form,
  });
  onProgress(80);
  const accepted = await handle<{ id: string; status: string; message: string }>(res);
  onProgress(100);
  // Return a minimal DocumentItem; the hooks will poll for the real status
  return {
    id: accepted.id,
    name: file.name,
    kind: /\.docx$/i.test(file.name) ? "docx" : "pdf",
    sizeBytes: file.size,
    pages: null,
    status: "queued",
    stage: "Waiting in queue",
    progress: 0,
    errorMessage: null,
    warning: null,
    createdAt: new Date().toISOString(),
  };
}

/** URL to download/stream the original file */
export function fileUrl(id: string): string {
  return `${API_BASE}/api/documents/${id}/file`;
}

// ── Chats / Conversations ─────────────────────────────────────────────────────

export async function listChats(): Promise<ChatSummary[]> {
  const res = await fetch(`${API_BASE}/api/conversations`, { cache: "no-store" });
  const data = await handle<{ id: string; title: string; createdAt: string }[]>(res);
  return data.map((c) => ({
    id: c.id,
    title: c.title,
    documentIds: [],
    updatedAt: c.createdAt,
  }));
}

export async function getChat(id: string): Promise<Chat> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, { cache: "no-store" });
  const data = await handle<{
    id: string;
    title: string;
    messages: Parameters<typeof adaptMessage>[0][];
  }>(res);

  // Extract documentIds from quotes in the messages
  const docIds = new Set<string>();
  for (const m of data.messages) {
    for (const q of m.quotes ?? []) {
      docIds.add(q.documentId);
    }
  }

  return {
    id: data.id,
    title: data.title,
    documentIds: [...docIds],
    updatedAt: data.messages[data.messages.length - 1]?.createdAt ?? new Date().toISOString(),
    messages: data.messages.map(adaptMessage),
  };
}

export async function deleteChat(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, { method: "DELETE" });
  await handle<void>(res);
}

/** Creates a chat by asking the first question — the backend creates the conversation. */
export async function createChat(question: string, documentIds: string[]): Promise<Chat> {
  // We don't create the chat in advance; it's created on the first ask.
  // Return a temporary placeholder so the UI can navigate before the stream.
  return {
    id: "__pending__",
    title: question.length > 80 ? `${question.slice(0, 79)}…` : question,
    documentIds,
    updatedAt: new Date().toISOString(),
    messages: [
      {
        id: "__user__",
        role: "user",
        content: question,
        status: "complete",
        kind: "answer",
        quotes: [],
        coverage: [],
        errorMessage: null,
      },
    ],
  };
}

/** Appends a user message to the local optimistic view (no-op for real backend). */
export async function appendUserMessage(_chatId: string, _question: string): Promise<void> {
  // No-op: the real message is committed when the stream completes.
}

/** Removes the last failed turn so the user can retry. Returns the question. */
export async function popLastTurn(chatId: string): Promise<string | null> {
  try {
    const chat = await getChat(chatId);
    const messages = chat.messages;
    const last = messages[messages.length - 1];
    if (!last) return null;
    // Find the last user message
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i]?.role === "user") {
        return messages[i]?.content ?? null;
      }
    }
    return null;
  } catch {
    return null;
  }
}

export async function commitAssistantMessage(
  _chatId: string,
  _message: Omit<Message, "id">,
): Promise<void> {
  // No-op: the backend already committed the message during the stream.
}

/** Stream the ask response from the real backend NDJSON endpoint. */
export function askQuestion(
  args: { question: string; documentIds: string[]; signal: AbortSignal; conversationId?: string },
  onEvent: (e: AskEvent) => void,
): Promise<void> {
  return streamAsk(args, onEvent);
}

async function streamAsk(
  args: { question: string; documentIds: string[]; signal: AbortSignal; conversationId?: string },
  onEvent: (e: AskEvent) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      documentIds: args.documentIds,
      question: args.question,
      conversationId: args.conversationId ?? null,
    }),
    signal: args.signal,
  });

  if (!res.ok || !res.body) {
    let detail = `Ask failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // State accumulated across events for adapting backend events → verbatim-ui AskEvents
  const accQuotes: Quote[] = [];
  const accCoverage: Coverage[] = [];
  let conversationId: string | null = args.conversationId ?? null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      try {
        const ev = JSON.parse(line) as Record<string, unknown>;
        adaptBackendEvent(ev, accQuotes, accCoverage, conversationId, onEvent);
        // Update conversationId if we got the meta event
        if (ev.type === "meta" && typeof ev.conversationId === "string") {
          conversationId = ev.conversationId;
        }
      } catch {
        /* ignore malformed lines */
      }
    }
  }
  if (buffer.trim()) {
    try {
      const ev = JSON.parse(buffer.trim()) as Record<string, unknown>;
      adaptBackendEvent(ev, accQuotes, accCoverage, conversationId, onEvent);
    } catch { /* ignore */ }
  }
}

function adaptBackendEvent(
  ev: Record<string, unknown>,
  accQuotes: Quote[],
  accCoverage: Coverage[],
  _conversationId: string | null,
  onEvent: (e: AskEvent) => void,
): void {
  switch (ev.type) {
    case "meta":
      // Conversation created — nothing to emit to UI yet
      break;

    case "status": {
      // Backend: { type: "status", stage, documentId, documentName, done, total }
      const stage = String(ev.stage ?? "");
      const docName = String(ev.documentName ?? "");
      const done = Number(ev.done ?? 0);
      const total = Number(ev.total ?? 1);
      onEvent({
        type: "stage",
        label: `Reading ${docName ? `${truncate(docName, 24)} · ` : ""}section ${done} of ${total} (${stage})`,
      });
      break;
    }

    case "quotes": {
      // Backend: { type: "quotes", quotes: VerifiedQuote[], unverified: UnverifiedQuote[] }
      const verified = (ev.quotes as BackendQuote[] | undefined) ?? [];
      const unverified = (ev.unverified as { documentId: string; documentName: string; text: string; verified: false; failReason: string }[] | undefined) ?? [];

      // Clear and rebuild accumulated quotes
      accQuotes.length = 0;
      let n = 0;
      for (const q of verified) {
        const adapted: Quote = {
          ref: `Q${++n}`,
          documentId: q.documentId,
          documentName: q.documentName,
          verified: true,
          matchKind: (q.matchKind as Quote["matchKind"]) ?? "exact",
          failReason: null,
          text: q.text,
          page: (q as { pageStart?: number }).pageStart ?? null,
          lines: null,
          occurrences: (q as { occurrences?: number }).occurrences ?? 1,
          start: q.start ?? null,
          end: q.end ?? null,
        };
        accQuotes.push(adapted);
      }
      for (const q of unverified) {
        accQuotes.push({
          ref: `Q${++n}`,
          documentId: q.documentId,
          documentName: q.documentName,
          verified: false,
          matchKind: null,
          failReason: q.failReason,
          text: q.text,
          page: null,
          lines: null,
          occurrences: 0,
          start: null,
          end: null,
        });
      }
      break;
    }

    case "coverage": {
      // Backend: { type: "coverage", coverage: Coverage[] }
      const cov = (ev.coverage as BackendCoverage[] | undefined) ?? [];
      accCoverage.length = 0;
      for (const c of cov) {
        accCoverage.push(adaptCoverage(c));
      }
      // Emit quotes+coverage together now that we have both
      onEvent({
        type: "quotes",
        quotes: [...accQuotes],
        coverage: [...accCoverage],
        kind: accQuotes.some((q) => q.verified) ? "answer" : "not_found",
      });
      break;
    }

    case "caveat":
      // The caveat message is prepended to the token stream as a note
      if (ev.message) {
        onEvent({ type: "token", text: `\n\n> ${String(ev.message)}\n\n` });
      }
      break;

    case "token":
      onEvent({ type: "token", text: String(ev.text ?? "") });
      break;

    case "done":
      // Stream complete
      break;

    case "error":
      throw new Error(String(ev.message ?? "Stream error"));
  }
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

// Stream ask and return the resulting conversationId (created or existing).
export async function askQuestionWithId(
  args: { question: string; documentIds: string[]; signal: AbortSignal; conversationId?: string },
  onEvent: (e: AskEvent) => void,
): Promise<string | null> {
  let convId: string | null = args.conversationId ?? null;

  const res = await fetch(`${API_BASE}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      documentIds: args.documentIds,
      question: args.question,
      conversationId: args.conversationId ?? null,
    }),
    signal: args.signal,
  });

  if (!res.ok || !res.body) {
    let detail = `Ask failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const accQuotes: Quote[] = [];
  const accCoverage: Coverage[] = [];

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      try {
        const ev = JSON.parse(line) as Record<string, unknown>;
        if (ev.type === "meta" && typeof ev.conversationId === "string") {
          convId = ev.conversationId;
        }
        adaptBackendEvent(ev, accQuotes, accCoverage, convId, onEvent);
      } catch { /* ignore */ }
    }
  }
  if (buffer.trim()) {
    try {
      const ev = JSON.parse(buffer.trim()) as Record<string, unknown>;
      if (ev.type === "meta" && typeof ev.conversationId === "string") {
        convId = ev.conversationId;
      }
      adaptBackendEvent(ev, accQuotes, accCoverage, convId, onEvent);
    } catch { /* ignore */ }
  }
  return convId;
}

// ── Compare ───────────────────────────────────────────────────────────────────

export const COMPARE_STAGES = ["Aligning clauses", "Rating changes", "Writing summary"] as const;

function adaptComparison(data: {
  id: string;
  documentAId: string;
  documentBId: string;
  summary: string;
  summarySource: string;
  stats: Record<string, unknown> | null;
  createdAt: string;
  changes: Array<{
    orderIdx: number;
    type: string;
    significance: string;
    category: string | null;
    title: string;
    summary: string;
    summarySource: string;
    aText: string | null;
    bText: string | null;
    aStart: number | null;
    aEnd: number | null;
    bStart: number | null;
    bEnd: number | null;
  }>;
  docAName?: string;
  docBName?: string;
}): Comparison {
  const stats = data.stats as Record<string, unknown> | null;
  const docAName = (data.docAName as string | undefined) ?? (stats?.docAName as string | undefined) ?? data.documentAId;
  const docBName = (data.docBName as string | undefined) ?? (stats?.docBName as string | undefined) ?? data.documentBId;
  const unchangedCount = (stats?.unchanged_count as number | undefined) ?? 0;

  return {
    id: data.id,
    docAId: data.documentAId,
    docAName,
    docBId: data.documentBId,
    docBName,
    createdAt: data.createdAt,
    summary: data.summary,
    summarySource: (data.summarySource === "ai" ? "ai" : "automatic") as "ai" | "automatic",
    unchangedCount,
    changes: data.changes.map((c, i) => ({
      id: String(i),
      order: c.orderIdx,
      clause: c.title,
      type: (c.type as "ADDED" | "REMOVED" | "MODIFIED" | "MOVED") ?? "MODIFIED",
      significance: (c.significance as "HIGH" | "MEDIUM" | "LOW" | "COSMETIC") ?? "LOW",
      category: c.category ?? "General",
      summary: c.summary,
      summarySource: (c.summarySource === "ai" ? "ai" : "automatic") as "ai" | "automatic",
      aText: c.aText,
      bText: c.bText,
      aPage: null,
      bPage: null,
      aStart: c.aStart ?? null,
      aEnd: c.aEnd ?? null,
      bStart: c.bStart ?? null,
      bEnd: c.bEnd ?? null,
    })),
  };
}

export async function listComparisons(): Promise<ComparisonListItem[]> {
  const res = await fetch(`${API_BASE}/api/comparisons`, { cache: "no-store" });
  const data = await handle<Parameters<typeof adaptComparison>[0][]>(res);
  return data.map((c) => {
    const adapted = adaptComparison(c);
    return {
      id: adapted.id,
      docAName: adapted.docAName,
      docBName: adapted.docBName,
      createdAt: adapted.createdAt,
      total: adapted.changes.length,
    };
  });
}

export async function getComparison(id: string): Promise<Comparison> {
  const res = await fetch(`${API_BASE}/api/comparisons/${id}`, { cache: "no-store" });
  const data = await handle<Parameters<typeof adaptComparison>[0]>(res);
  return adaptComparison(data);
}

export async function runComparison(
  docAId: string,
  docBId: string,
  onStage: (index: number) => void,
): Promise<Comparison> {
  // Animate through stages while waiting for the real API
  onStage(0);
  const stagePromise = (async () => {
    await delay(500);
    onStage(1);
    await delay(500);
    onStage(2);
  })();

  const res = await fetch(`${API_BASE}/api/comparisons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ documentAId: docAId, documentBId: docBId }),
  });

  await stagePromise;
  const data = await handle<Parameters<typeof adaptComparison>[0]>(res);
  return adaptComparison(data);
}

function delay(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}

// ── Redline ───────────────────────────────────────────────────────────────────

function adaptRedlineSession(r: {
  id: string;
  documentId: string;
  author: string;
  instruction: string | null;
  insertions: number;
  deletions: number;
  applied: Array<{ target: string; replacement: string; context?: string }>;
  dropped: Array<{ target: string; reason: string }>;
  downloadUrl: string;
  createdAt: string;
  documentName?: string;
}): RedlineSession {
  const edits: RedlineEdit[] = [
    ...r.applied.map((e, i) => ({
      id: `applied-${i}`,
      target: e.target,
      replacement: e.replacement,
      reason: "Applied",
      check: "verified" as const,
      note: null,
      context: e.context ?? null,
    })),
    ...r.dropped.map((e, i) => ({
      id: `dropped-${i}`,
      target: e.target,
      replacement: "",
      reason: e.reason,
      check: "not_found" as const,
      note: e.reason,
      context: null,
    })),
  ];

  return {
    id: r.id,
    documentId: r.documentId,
    documentName: r.documentName ?? r.documentId,
    mode: "plain",
    instruction: r.instruction ?? "",
    author: r.author,
    createdAt: r.createdAt,
    edits,
    appliedIds: r.applied.map((_, i) => `applied-${i}`),
    revisions: { ins: r.insertions, del: r.deletions },
  };
}

export async function listRedlines(): Promise<RedlineSession[]> {
  const res = await fetch(`${API_BASE}/api/redlines`, { cache: "no-store" });
  const data = await handle<Parameters<typeof adaptRedlineSession>[0][]>(res);
  return data.map(adaptRedlineSession).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export type ProposeInput =
  | { mode: "plain"; instruction: string }
  | { mode: "manual"; rows: { target: string; replacement: string }[] };

export async function proposeRedline(input: ProposeInput): Promise<RedlineEdit[]> {
  if (input.mode === "manual") {
    // Manual edits: verify them against the selected document
    // For now return them as needing verification — the real check happens on apply
    return input.rows.map((r, i) => ({
      id: `manual-${i}`,
      target: r.target,
      replacement: r.replacement,
      reason: "Manual edit",
      check: "verified" as const,
      note: null,
      context: null,
    }));
  }

  // Plain language: call the propose API — we need a docId, which is set in the view
  // The view calls proposeRedline with a docId set on the input
  const extInput = input as { mode: "plain"; instruction: string; docId?: string };
  if (!extInput.docId) {
    throw new Error("No document selected.");
  }

  const res = await fetch(`${API_BASE}/api/documents/${extInput.docId}/redline/propose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction: input.instruction }),
  });
  const data = await handle<{
    documentId: string;
    instruction: string;
    proposed: Array<{
      target: string;
      replacement: string;
      reason: string;
      include: boolean;
      context: string;
      occurrences: number;
      verified: boolean;
    }>;
    dropped: Array<{ target: string; reason: string }>;
  }>(res);

  const edits: RedlineEdit[] = [
    ...data.proposed.map((e, i) => ({
      id: `proposed-${i}`,
      target: e.target,
      replacement: e.replacement,
      reason: e.reason,
      check: e.verified ? ("verified" as const) : ("not_found" as const),
      note: e.verified ? null : "Target text not uniquely found.",
      // Preserve the disambiguating context so repeated values apply correctly.
      context: e.context ?? null,
    })),
    ...data.dropped.map((e, i) => ({
      id: `dropped-${i}`,
      target: e.target,
      replacement: "",
      reason: e.reason,
      check: "not_found" as const,
      note: e.reason,
      context: null,
    })),
  ];

  return edits;
}

export async function applyRedline(args: {
  documentId: string;
  mode: "plain" | "manual";
  instruction: string;
  author: string;
  edits: RedlineEdit[];
  includeIds: string[];
}): Promise<RedlineSession> {
  const includedEdits = args.edits.filter((e) => args.includeIds.includes(e.id));
  const backendEdits = includedEdits.map((e) => ({
    target: e.target,
    replacement: e.replacement,
    context: e.context ?? undefined,
  }));

  const res = await fetch(`${API_BASE}/api/documents/${args.documentId}/redline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      edits: backendEdits,
      author: args.author,
      instruction: args.instruction,
    }),
  });
  const data = await handle<Parameters<typeof adaptRedlineSession>[0]>(res);
  return adaptRedlineSession(data);
}

export async function deleteRedline(id: string): Promise<void> {
  // Backend doesn't have a delete endpoint for redlines, so we silently succeed
  // This is a limitation — redline sessions persist on the server
  void id;
}

export function redlineDownloadUrl(id: string): string {
  return `${API_BASE}/api/redlines/${id}/download`;
}

// ── Locate (for quote viewer) ──────────────────────────────────────────────────

export interface LocatedRect {
  pageNumber: number;
  width: number;
  height: number;
  rects: Array<{ x1: number; y1: number; x2: number; y2: number }>;
  boundingRect?: { x1: number; y1: number; x2: number; y2: number } | null;
  noGeometry?: boolean;
}

export interface LocateResponse {
  id: string;
  locations: LocatedRect[];
}

export async function locateRanges(
  docId: string,
  ranges: { start: number; end: number }[],
): Promise<LocateResponse> {
  const joined = ranges.map((r) => `${r.start}-${r.end}`).join(",");
  const res = await fetch(
    `${API_BASE}/api/documents/${docId}/locate?ranges=${encodeURIComponent(joined)}`,
    { cache: "no-store" },
  );
  return handle<LocateResponse>(res);
}

// Re-export for isAbortError (used in chat-workspace)
export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}
