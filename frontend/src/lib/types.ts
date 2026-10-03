import { z } from "zod";

/* ---------- Documents ---------- */

export const DocStatusSchema = z.enum(["queued", "converting", "extracting", "indexing", "ready", "failed"]);
export type DocStatus = z.infer<typeof DocStatusSchema>;

export const DocumentSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.enum(["pdf", "docx"]),
  sizeBytes: z.number().int().nonnegative(),
  pages: z.number().int().positive().nullable(),
  status: DocStatusSchema,
  stage: z.string().nullable(),
  progress: z.number().min(0).max(100),
  errorMessage: z.string().nullable(),
  warning: z.string().nullable(),
  createdAt: z.string(),
});
export type DocumentItem = z.infer<typeof DocumentSchema>;

export const isReady = (d: DocumentItem): boolean => d.status === "ready";
export const isWorking = (d: DocumentItem): boolean => d.status !== "ready" && d.status !== "failed";

/* ---------- Chat ---------- */

export const QuoteSchema = z.object({
  ref: z.string(),
  documentId: z.string(),
  documentName: z.string(),
  verified: z.boolean(),
  matchKind: z.enum(["exact", "loose"]).nullable(),
  failReason: z.string().nullable(),
  text: z.string(),
  page: z.number().int().nullable(),
  lines: z.number().int().nullable(),
  occurrences: z.number().int().min(0),
  start: z.number().int().nullable(),
  end: z.number().int().nullable(),
});
export type Quote = z.infer<typeof QuoteSchema>;

export const CoverageSchema = z.object({
  documentId: z.string(),
  name: z.string(),
  chunksTotal: z.number().int().positive(),
  chunksRead: z.number().int().min(0),
  unreadablePages: z.number().int().min(0),
});
export type Coverage = z.infer<typeof CoverageSchema>;
export const isCoverageComplete = (c: Coverage): boolean => c.chunksRead >= c.chunksTotal && c.unreadablePages === 0;

export const MessageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  status: z.enum(["complete", "streaming", "stopped", "error"]),
  kind: z.enum(["answer", "not_found"]),
  quotes: z.array(QuoteSchema),
  coverage: z.array(CoverageSchema),
  errorMessage: z.string().nullable(),
});
export type Message = z.infer<typeof MessageSchema>;

export const ChatSchema = z.object({
  id: z.string(),
  title: z.string(),
  documentIds: z.array(z.string()),
  updatedAt: z.string(),
  messages: z.array(MessageSchema),
});
export type Chat = z.infer<typeof ChatSchema>;
export type ChatSummary = Pick<Chat, "id" | "title" | "documentIds" | "updatedAt">;

/* ---------- Comparison ---------- */

export const SignificanceSchema = z.enum(["HIGH", "MEDIUM", "LOW", "COSMETIC"]);
export type Significance = z.infer<typeof SignificanceSchema>;
export const ChangeTypeSchema = z.enum(["ADDED", "REMOVED", "MODIFIED", "MOVED"]);
export type ChangeType = z.infer<typeof ChangeTypeSchema>;

export const SIGNIFICANCE_ORDER: Record<Significance, number> = { HIGH: 0, MEDIUM: 1, LOW: 2, COSMETIC: 3 };

export const ChangeSchema = z.object({
  id: z.string(),
  order: z.number().int(),
  clause: z.string(),
  type: ChangeTypeSchema,
  significance: SignificanceSchema,
  category: z.string(),
  summary: z.string(),
  summarySource: z.enum(["ai", "automatic"]),
  aText: z.string().nullable(),
  bText: z.string().nullable(),
  aPage: z.number().int().nullable(),
  bPage: z.number().int().nullable(),
  aStart: z.number().int().nullable(),
  aEnd: z.number().int().nullable(),
  bStart: z.number().int().nullable(),
  bEnd: z.number().int().nullable(),
});
export type Change = z.infer<typeof ChangeSchema>;

export const ComparisonSchema = z.object({
  id: z.string(),
  docAId: z.string(),
  docAName: z.string(),
  docBId: z.string(),
  docBName: z.string(),
  createdAt: z.string(),
  summary: z.string(),
  summarySource: z.enum(["ai", "automatic"]),
  unchangedCount: z.number().int().min(0),
  changes: z.array(ChangeSchema),
});
export type Comparison = z.infer<typeof ComparisonSchema>;
export type ComparisonListItem = Pick<Comparison, "id" | "docAName" | "docBName" | "createdAt"> & { total: number };

/* ---------- Redline ---------- */

export const RedlineEditSchema = z.object({
  id: z.string(),
  target: z.string(),
  replacement: z.string(),
  reason: z.string(),
  check: z.enum(["verified", "not_found", "ambiguous"]),
  note: z.string().nullable(),
  context: z.string().nullable(),
});
export type RedlineEdit = z.infer<typeof RedlineEditSchema>;

export const RedlineSessionSchema = z.object({
  id: z.string(),
  documentId: z.string(),
  documentName: z.string(),
  mode: z.enum(["plain", "manual"]),
  instruction: z.string(),
  author: z.string(),
  createdAt: z.string(),
  edits: z.array(RedlineEditSchema),
  appliedIds: z.array(z.string()),
  revisions: z.object({ ins: z.number().int().min(0), del: z.number().int().min(0) }),
});
export type RedlineSession = z.infer<typeof RedlineSessionSchema>;

export type SessionStatus = "all" | "partial" | "none";
export function sessionStatus(s: RedlineSession): SessionStatus {
  const eligible = s.edits.filter((e) => e.check === "verified").length;
  if (s.appliedIds.length === 0) return "none";
  return s.appliedIds.length >= eligible ? "all" : "partial";
}

/* ---------- Form schemas ---------- */

export const InstructionSchema = z.string().trim().min(8, "Describe the change in a full sentence.");
export const ManualEditSchema = z
  .object({
    target: z.string().trim().min(1, "Enter the original text."),
    replacement: z.string().trim().min(1, "Enter the new text."),
  })
  .refine((v) => v.target !== v.replacement, { message: "The new text matches the original.", path: ["replacement"] });
