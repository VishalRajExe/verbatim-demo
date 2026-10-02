export type DocumentStatus = "pending" | "processing" | "ready" | "error";

export interface DocumentOut {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  page_count: number | null;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListOut {
  documents: DocumentOut[];
  total: number;
}

export interface DocumentPageOut {
  page_number: number;
  text: string;
}

export interface DocumentPagesOut {
  id: string;
  filename: string;
  total_pages: number;
  pages: DocumentPageOut[];
}

export interface UploadAccepted {
  id: string;
  status: DocumentStatus;
  message: string;
}

// ── Verified quotes & chat ──
export interface VerifiedQuote {
  ref: string;
  documentId: string;
  documentName: string;
  text: string;
  verified: boolean;
  matchKind?: string | null;
  start: number;
  end: number;
  pageStart: number;
  pageEnd: number;
  occurrences: number;
}

export interface UnverifiedQuote {
  documentId: string;
  documentName: string;
  text: string;
  verified: false;
  failReason: string;
}

export interface Coverage {
  documentId: string;
  name: string;
  chunksTotal: number;
  chunksRead: number;
  failedChunks: number[];
  pages: number;
  unreadablePages: number;
  complete: boolean;
}

export type AskEvent =
  | { type: "meta"; conversationId: string }
  | { type: "status"; stage: string; documentId: string; documentName: string; done: number; total: number }
  | { type: "quotes"; quotes: VerifiedQuote[]; unverified: UnverifiedQuote[] }
  | { type: "coverage"; coverage: Coverage[] }
  | { type: "caveat"; message: string }
  | { type: "token"; text: string }
  | { type: "done"; status: string; stopped: boolean }
  | { type: "error"; message: string };

export interface QuoteRow {
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

export interface MessageRow {
  id: number;
  role: "user" | "assistant";
  content: string;
  stopped: boolean;
  coverage: Coverage[] | null;
  createdAt: string;
  quotes: QuoteRow[];
}

export interface ConversationSummary {
  id: string;
  title: string;
  createdAt: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  messages: MessageRow[];
}

// ── Comparison ──
export interface ComparisonChange {
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
}

export interface ComparisonResult {
  id: string;
  documentAId: string;
  documentBId: string;
  summary: string;
  summarySource: string;
  stats: Record<string, unknown> | null;
  createdAt: string;
  changes: ComparisonChange[];
}

// ── Redline ──
export interface RedlineOut {
  id: string;
  documentId: string;
  author: string;
  insertions: number;
  deletions: number;
  applied: { target: string; replacement: string }[];
  dropped: { target: string; reason: string }[];
  downloadUrl: string;
  createdAt: string;
}

// ── Locate ──
// Coordinates are in PDF points, top-left origin, matching PyMuPDF's page space.
export interface PointRect {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface LocatedRect {
  pageNumber: number;
  width: number;
  height: number;
  rects: PointRect[];
  boundingRect?: PointRect | null;
  noGeometry?: boolean;
}

export interface LocateResponse {
  id: string;
  locations: LocatedRect[];
}
