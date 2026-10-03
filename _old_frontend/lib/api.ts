import type {
  AskEvent,
  ComparisonResult,
  ConversationDetail,
  ConversationSummary,
  DocumentListOut,
  DocumentOut,
  DocumentPagesOut,
  LocateResponse,
  RedlineOut,
  RedlineProposeOut,
  UploadAccepted,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function fileUrl(id: string): string {
  return `${API_BASE}/api/documents/${id}/file`;
}

export async function listDocuments(): Promise<DocumentListOut> {
  const res = await fetch(`${API_BASE}/api/documents`, { cache: "no-store" });
  return handle<DocumentListOut>(res);
}

export async function getDocument(id: string): Promise<DocumentOut> {
  const res = await fetch(`${API_BASE}/api/documents/${id}`, { cache: "no-store" });
  return handle<DocumentOut>(res);
}

export async function getDocumentPages(id: string): Promise<DocumentPagesOut> {
  const res = await fetch(`${API_BASE}/api/documents/${id}/pages`, {
    cache: "no-store",
  });
  return handle<DocumentPagesOut>(res);
}

export async function uploadDocument(file: File): Promise<UploadAccepted> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/documents/upload`, {
    method: "POST",
    body: form,
  });
  return handle<UploadAccepted>(res);
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/documents/${id}`, { method: "DELETE" });
  await handle<void>(res);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

// ── Conversations / ask ──
export async function listConversations(): Promise<ConversationSummary[]> {
  const res = await fetch(`${API_BASE}/api/conversations`, { cache: "no-store" });
  return handle<ConversationSummary[]>(res);
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, { cache: "no-store" });
  return handle<ConversationDetail>(res);
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, { method: "DELETE" });
  await handle<void>(res);
}

// Streams the NDJSON ask response, invoking onEvent for each parsed event.
export async function askStream(
  params: { documentIds: string[]; question: string; conversationId?: string },
  onEvent: (event: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      documentIds: params.documentIds,
      question: params.question,
      conversationId: params.conversationId ?? null,
    }),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`Ask failed (${res.status})`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) {
        try {
          onEvent(JSON.parse(line) as AskEvent);
        } catch {
          /* ignore a malformed line */
        }
      }
    }
  }
  if (buffer.trim()) {
    try {
      onEvent(JSON.parse(buffer.trim()) as AskEvent);
    } catch {
      /* ignore */
    }
  }
}

// ── Compare ──
export async function createComparison(
  body: { documentAId: string; documentBId: string },
): Promise<ComparisonResult> {
  const res = await fetch(`${API_BASE}/api/comparisons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<ComparisonResult>(res);
}

export async function listComparisons(): Promise<ComparisonResult[]> {
  const res = await fetch(`${API_BASE}/api/comparisons`, { cache: "no-store" });
  return handle<ComparisonResult[]>(res);
}

// ── Redline ──
export async function proposeRedline(
  docId: string,
  instruction: string,
): Promise<RedlineProposeOut> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/redline/propose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
  return handle<RedlineProposeOut>(res);
}

export async function listRedlines(documentId?: string): Promise<RedlineOut[]> {
  const q = documentId ? `?document_id=${encodeURIComponent(documentId)}` : "";
  const res = await fetch(`${API_BASE}/api/redlines${q}`, { cache: "no-store" });
  return handle<RedlineOut[]>(res);
}

export async function createRedline(
  docId: string,
  body: {
    edits: { target: string; replacement: string; context?: string }[];
    author?: string;
    instruction?: string | null;
  },
): Promise<RedlineOut> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/redline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<RedlineOut>(res);
}

export function redlineDownloadUrl(id: string): string {
  return `${API_BASE}/api/redlines/${id}/download`;
}

// ── Locate ──
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
