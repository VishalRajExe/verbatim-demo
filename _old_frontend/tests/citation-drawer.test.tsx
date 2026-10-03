// Regression: citation drawer switching (document-scoped, in-place).
//
// Pins the behaviour the evaluator journey requires once the drawer is open:
//  1. clicking another citation switches the drawer's document + passage IN
//     the SAME drawer — one click, no close→reopen→click-again;
//  2. a slow, stale locate response can never overwrite the currently
//     selected citation;
//  3. the drawer is a right-side panel, not a full-screen backdrop — the old
//     `fixed inset-0` overlay intercepted the first click on every citation
//     chip behind it (the exact bug this test guards against).
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "@/features/chat/ChatView";
import type { AskEvent, DocumentOut, VerifiedQuote } from "@/lib/types";

// ── Mocked module state (vi.hoisted so factory closures can see it) ────────
const h = vi.hoisted(() => ({
  locate: vi.fn(),
  ask: vi.fn(),
  pages: {} as Record<string, { page_number: number; text: string }[]>,
}));

vi.mock("@/lib/api", () => ({
  API_BASE: "http://backend",
  listDocuments: async () => ({
    documents: [
      doc("doc-a", "Alpha.pdf", 2),
      doc("doc-b", "Beta.pdf", 5),
    ],
    total: 2,
  }),
  listConversations: async () => [],
  getConversation: async () => ({ id: "x", title: "x", messages: [] }),
  askStream: (...args: unknown[]) => h.ask(...args),
  locateRanges: (...args: unknown[]) => h.locate(...args),
  fileUrl: (id: string) => `http://backend/api/documents/${id}/file`,
}));

// The pdf.js viewer cannot run in jsdom; a stub that records the document it
// was asked to render is exactly what these tests need (the drawer must show
// the CITATION'S document, never the previously open one).
vi.mock("@/features/viewer/PdfViewer", async () => {
  const { createElement } = await import("react");
  return {
    PdfViewer: (props: { docId: string }) =>
      createElement("div", {
        "data-testid": "pdf-viewer",
        "data-doc-id": props.docId,
      }),
  };
});

vi.mock("next/link", () => ({
  default: (props: { children?: unknown }) => props.children,
}));

function doc(id: string, filename: string, page_count: number): DocumentOut {
  return {
    id,
    filename,
    file_type: "pdf",
    file_size: 1024,
    page_count,
    status: "ready",
    error_message: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

const Q1: VerifiedQuote = {
  ref: "Q1",
  documentId: "doc-a",
  documentName: "Alpha.pdf",
  text: "The Customer shall pay within thirty days.",
  verified: true,
  matchKind: "exact",
  start: 100,
  end: 150,
  pageStart: 2,
  pageEnd: 2,
  occurrences: 1,
};

const Q2: VerifiedQuote = {
  ref: "Q2",
  documentId: "doc-b",
  documentName: "Beta.pdf",
  text: "Total liability is capped at AED 100,000.",
  verified: true,
  matchKind: "exact",
  start: 300,
  end: 380,
  pageStart: 5,
  pageEnd: 5,
  occurrences: 1,
};

function located(pageNumber: number) {
  return {
    id: "loc",
    locations: [
      {
        pageNumber,
        width: 612,
        height: 792,
        rects: [{ x1: 72, y1: 100, x2: 540, y2: 112 }],
      },
    ],
  };
}

async function renderWithAnswer() {
  h.ask.mockImplementation(
    async (_params: unknown, onEvent: (e: AskEvent) => void) => {
      onEvent({ type: "meta", conversationId: "conv-1" });
      onEvent({ type: "quotes", quotes: [Q1, Q2], unverified: [] });
      onEvent({
        type: "token",
        text: "Payment is due in thirty days [Q1]; the cap is AED 100,000 [Q2].",
      });
      onEvent({ type: "done", status: "complete", stopped: false });
    },
  );

  render(<ChatView />);

  // Select both documents, ask, and wait for the citation chips.
  fireEvent.click(await screen.findByRole("button", { name: /Alpha\.pdf/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Beta\.pdf/ }));
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "payment and liability?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));

  await waitFor(() => expect(screen.getByText("Q1 · p.2")).toBeTruthy());
  expect(screen.getByText("Q2 · p.5")).toBeTruthy();
}

beforeEach(() => {
  h.pages = {
    "doc-a": [
      { page_number: 1, text: "Alpha master agreement." },
      { page_number: 2, text: "Clause 3.1 The Customer shall pay within thirty days." },
    ],
    "doc-b": [
      { page_number: 5, text: "Clause 9.2 Total liability is capped at AED 100,000." },
    ],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      const id = /documents\/([^/]+)\/pages/.exec(input)?.[1];
      return {
        ok: true,
        json: async () => ({ pages: h.pages[id ?? ""] ?? [] }),
      };
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  h.ask.mockReset();
  h.locate.mockReset();
});

describe("citation source drawer", () => {
  it("switches documents inside the SAME drawer with one click", async () => {
    h.locate.mockImplementation(async (docId: string) =>
      located(docId === "doc-a" ? 2 : 5),
    );
    await renderWithAnswer();

    // Open the drawer on Q1 (document A).
    fireEvent.click(screen.getByText("Q1 · p.2"));
    expect(await screen.findByText("Q1 · Alpha.pdf")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByTestId("pdf-viewer").getAttribute("data-doc-id")).toBe(
        "doc-a",
      ),
    );

    // ONE click on Q2 (a DIFFERENT document) switches the drawer in place.
    // Before the fix the full-screen backdrop ate this click (drawer merely
    // closed), so this asserts the whole regression in one step.
    fireEvent.click(screen.getByText("Q2 · p.5"));
    expect(await screen.findByText("Q2 · Beta.pdf")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByTestId("pdf-viewer").getAttribute("data-doc-id")).toBe(
        "doc-b",
      ),
    );
    expect(screen.queryByText("Q1 · Alpha.pdf")).toBeNull();
    // The drawer host stayed mounted the whole time.
    expect(screen.getByTestId("quote-drawer")).toBeTruthy();
  });

  it("ignores a stale locate response from a previously selected citation", async () => {
    // doc-a locate is slow; doc-b locate resolves immediately.
    h.locate.mockImplementation(async (docId: string) => {
      if (docId === "doc-a") {
        await new Promise((r) => setTimeout(r, 60));
        return located(2);
      }
      return located(5);
    });
    await renderWithAnswer();

    fireEvent.click(screen.getByText("Q1 · p.2")); // starts a slow locate
    fireEvent.click(screen.getByText("Q2 · p.5")); // user switches immediately

    expect(await screen.findByText("Q2 · Beta.pdf")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByText(/Page 5 · 1 line\(s\) matched/)).toBeTruthy(),
    );
    // Let the stale doc-a response land after the switch, then verify it did
    // not overwrite the current citation's location or header.
    await new Promise((r) => setTimeout(r, 120));
    expect(screen.getByText("Q2 · Beta.pdf")).toBeTruthy();
    expect(screen.queryByText(/Page 2 ·/)).toBeNull();
  });

  it("is a right-side panel, not a full-screen click-blocking backdrop", async () => {
    h.locate.mockImplementation(async (docId: string) =>
      located(docId === "doc-a" ? 2 : 5),
    );
    await renderWithAnswer();

    fireEvent.click(screen.getByText("Q1 · p.2"));
    const drawer = await screen.findByTestId("quote-drawer");
    const cls = drawer.className;
    // The old overlay was `fixed inset-0 ... onClick={onClose}`, covering the
    // chat and closing the drawer on the first click anywhere behind it.
    expect(cls).toContain("right-0");
    expect(cls).not.toContain("inset-0");
  });
});
