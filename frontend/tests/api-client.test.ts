// Regression suite for the real-backend API adapters in src/lib/api/client.ts.
// Guards the wiring fixes made when integrating verbatim-ui into the live app:
//   • verified quotes carry server char offsets (start/end) → pixel highlighting
//   • redline context is threaded propose → apply (repeated values disambiguate)
//   • comparison changes carry their clause offsets for deep-link highlighting
//   • /locate builds the canonical "start-end,start-end" ranges query
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import {
  applyRedline,
  getChat,
  getComparison,
  listDocuments,
  locateRanges,
  proposeRedline,
} from "@/lib/api/client";

type FetchCall = { url: string; init?: RequestInit };
const calls: FetchCall[] = [];

function jsonResponse(payload: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => payload,
  } as unknown as Response;
}

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({ url, init });
      // Per-test responses are installed by mocking fetchResolved directly below.
      return jsonResponse(fetchResolved.value);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// A tiny indirection so each test can set the payload the mocked fetch returns.
const fetchResolved = { value: {} as unknown };

function respondWith(payload: unknown): void {
  fetchResolved.value = payload;
}

function lastBody<T = unknown>(): T {
  const init = calls[calls.length - 1]?.init;
  return JSON.parse(String(init?.body)) as T;
}

/* ── Quotes: verified offsets survive adaptation ─────────────────────────── */

it("getChat maps backend quote char offsets onto the Quote type", async () => {
  respondWith({
    id: "c1",
    title: "Liability chat",
    messages: [
      {
        id: 1,
        role: "assistant",
        content: "The cap is AED 100,000.",
        stopped: false,
        createdAt: "2026-01-01T00:00:00Z",
        coverage: null,
        quotes: [
          {
            id: 10,
            documentId: "doc-1",
            documentName: "contract.pdf",
            ref: "Q1",
            refIndex: 0,
            text: "liability will not exceed AED 100,000",
            verified: true,
            matchKind: "exact",
            failReason: null,
            start: 1200,
            end: 1248,
            pageStart: 4,
            pageEnd: 4,
            occurrences: 1,
          },
        ],
      },
    ],
  });

  const chat = await getChat("c1");
  const q = chat.messages[0].quotes[0];
  expect(q.start).toBe(1200);
  expect(q.end).toBe(1248);
  expect(q.page).toBe(4);
  expect(q.verified).toBe(true);
});

/* ── Locate: canonical ranges query ──────────────────────────────────────── */

it("locateRanges joins ranges as start-end pairs", async () => {
  respondWith({ id: "doc-1", locations: [] });
  await locateRanges("doc-1", [
    { start: 103, end: 203 },
    { start: 500, end: 610 },
  ]);
  expect(calls[0].url).toContain("/api/documents/doc-1/locate?ranges=103-203%2C500-610");
});

/* ── Redline: context threaded propose → apply ───────────────────────────── */

it("proposeRedline preserves the disambiguating context on verified edits", async () => {
  respondWith({
    documentId: "doc-1",
    instruction: "Change the liability cap.",
    proposed: [
      {
        target: "AED 100,000",
        replacement: "AED 1,000,000",
        reason: "Raise the cap.",
        include: true,
        context: "Except for liability ... will not exceed AED 100,000.",
        occurrences: 2,
        verified: true,
      },
    ],
    dropped: [],
  });

  const edits = await proposeRedline({
    mode: "plain",
    instruction: "Change the liability cap.",
    docId: "doc-1",
  } as never);

  expect(edits[0].check).toBe("verified");
  expect(edits[0].note).toBeNull();
  expect(edits[0].context).toBe("Except for liability ... will not exceed AED 100,000.");
});

it("applyRedline sends the edit context (not the note) to the backend", async () => {
  respondWith({
    id: "r-1",
    documentId: "doc-1",
    author: "Legal AI",
    instruction: "x",
    insertions: 1,
    deletions: 1,
    applied: [],
    dropped: [],
    downloadUrl: "http://backend/api/redlines/r-1/download",
    createdAt: "2026-01-01T00:00:00Z",
  });

  await applyRedline({
    documentId: "doc-1",
    mode: "plain",
    instruction: "Change the liability cap.",
    author: "Legal AI",
    includeIds: ["proposed-0"],
    edits: [
      {
        id: "proposed-0",
        target: "AED 100,000",
        replacement: "AED 1,000,000",
        reason: "Raise the cap.",
        check: "verified",
        note: null,
        context: "will not exceed AED 100,000.",
      },
    ],
  });

  const body = lastBody<{ edits: Array<{ target: string; replacement: string; context?: string }> }>();
  expect(body.edits[0]).toEqual({
    target: "AED 100,000",
    replacement: "AED 1,000,000",
    context: "will not exceed AED 100,000.",
  });
});

/* ── Documents: backend ".docx" (leading dot) must normalise to kind "docx" ── */

it("listDocuments maps the dotted file_type extension onto the correct kind", async () => {
  respondWith({
    total: 2,
    documents: [
      {
        id: "d-1",
        filename: "contract.docx",
        file_type: ".docx",
        file_size: 10,
        page_count: 1,
        status: "ready",
        error_message: null,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "d-2",
        filename: "report.pdf",
        file_type: ".pdf",
        file_size: 20,
        page_count: 4,
        status: "ready",
        error_message: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
  });

  const docs = await listDocuments();
  // Guards the Redline picker, which filters on kind === "docx": a leading dot
  // in the backend value must not silently mislabel Word files as PDFs.
  expect(docs[0].kind).toBe("docx");
  expect(docs[1].kind).toBe("pdf");
});

/* ── Comparison: clause offsets for highlighting ─────────────────────────── */

it("getComparison maps backend clause offsets onto the change", async () => {
  respondWith({
    id: "cmp-1",
    documentAId: "doc-a",
    documentBId: "doc-b",
    summary: "One change.",
    summarySource: "automatic",
    stats: { unchanged_count: 5 },
    createdAt: "2026-01-01T00:00:00Z",
    changes: [
      {
        orderIdx: 1,
        type: "MODIFIED",
        significance: "HIGH",
        category: "Liability",
        title: "Liability cap",
        summary: "Cap raised.",
        summarySource: "automatic",
        aText: "AED 100,000",
        bText: "AED 1,000,000",
        aStart: 103,
        aEnd: 203,
        bStart: 310,
        bEnd: 420,
      },
    ],
  });

  const cmp = await getComparison("cmp-1");
  const change = cmp.changes[0];
  expect(change.aStart).toBe(103);
  expect(change.aEnd).toBe(203);
  expect(change.bStart).toBe(310);
  expect(change.bEnd).toBe(420);
});
