/**
 * Regression tests for the Compare view's materiality filters, sorting and
 * both-side source links (evaluator journey steps 18-20). The bug class these
 * guard: a comparison result that cannot be filtered/sorted buries the one
 * commercially significant change (liability cap AED 100,000 -> AED 1,000,000)
 * among cosmetic rows, and a UI that re-judged materiality would silently
 * override the server's classification.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  createComparison: vi.fn(),
  listComparisons: vi.fn<() => Promise<unknown[]>>(() => Promise.resolve([])),
}));

vi.mock("@/lib/api", () => ({
  listDocuments: vi.fn(async () => ({
    documents: [
      { id: "doc-a", filename: "contract_v1.pdf", status: "ready" },
      { id: "doc-b", filename: "contract_v2.pdf", status: "ready" },
    ],
  })),
  listComparisons: () => h.listComparisons(),
  createComparison: (...args: unknown[]) => h.createComparison(...args),
}));

import { CompareView } from "@/features/compare/CompareView";

function change(orderIdx: number, significance: string, type: string, title: string) {
  return {
    orderIdx,
    type,
    significance,
    category: "liability",
    title,
    summary: `${title} summary`,
    summarySource: "automatic",
    aText: `A text for ${title}`,
    bText: type === "REMOVED" ? null : `B text for ${title}`,
    aStart: 100 + orderIdx,
    aEnd: 200 + orderIdx,
    bStart: 300 + orderIdx,
    bEnd: 400 + orderIdx,
  };
}

const RESULT = {
  id: "cmp-1",
  documentAId: "doc-a",
  documentBId: "doc-b",
  summary: "4 change(s) detected.",
  summarySource: "automatic",
  stats: { total: 4, bySignificance: { HIGH: 1, MEDIUM: 1, LOW: 1, COSMETIC: 1 } },
  createdAt: "2026-10-03T00:00:00Z",
  // Deliberately NOT in significance order, so sorting is observable.
  changes: [
    change(3, "HIGH", "MODIFIED", "Liability cap"),
    change(0, "LOW", "MODIFIED", "Whitespace only"),
    change(1, "COSMETIC", "ADDED", "Heading punctuation"),
    change(2, "MEDIUM", "REMOVED", "Audit clause"),
  ],
};

async function compare() {
  // The document list loads asynchronously; the pickers are empty until it lands.
  await waitFor(() =>
    expect(screen.getAllByRole("combobox")[0].querySelectorAll("option").length).toBe(3),
  );
  const selects = screen.getAllByRole("combobox");
  fireEvent.change(selects[0], { target: { value: "doc-a" } });
  fireEvent.change(selects[1], { target: { value: "doc-b" } });
  const button = screen.getByRole("button", { name: /compare/i });
  expect(button.hasAttribute("disabled")).toBe(false);
  fireEvent.click(button);
  await waitFor(() => expect(screen.queryAllByTestId("change-card").length).toBe(4));
}

function cards() {
  // queryAll (not getAll): several assertions deliberately expect zero rows.
  return screen.queryAllByTestId("change-card");
}

beforeEach(() => {
  h.createComparison.mockResolvedValue(RESULT);
  h.listComparisons.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Compare materiality filter / sort", () => {
  it("shows the server's materiality verbatim and sorts it highest-first", async () => {
    render(<CompareView />);
    await compare();
    const sigs = cards().map((c) => c.getAttribute("data-significance"));
    expect(sigs).toEqual(["HIGH", "MEDIUM", "LOW", "COSMETIC"]);
    // The liability-cap row keeps the server's HIGH verdict: no UI re-judging.
    expect(cards()[0].textContent).toContain("Liability cap");
    expect(screen.getByTestId("change-count").textContent).toContain("Showing 4 of 4");
  });

  it("filtering by materiality actually removes rows", async () => {
    render(<CompareView />);
    await compare();
    fireEvent.click(screen.getByTestId("filter-HIGH"));
    await waitFor(() => expect(cards().length).toBe(3));
    expect(cards().map((c) => c.getAttribute("data-significance"))).not.toContain("HIGH");
    expect(screen.getByTestId("change-count").textContent).toContain("Showing 3 of 4");
    fireEvent.click(screen.getByTestId("filter-HIGH"));
    await waitFor(() => expect(cards().length).toBe(4));
  });

  it("filters by change type", async () => {
    render(<CompareView />);
    await compare();
    fireEvent.change(screen.getByTestId("filter-type"), { target: { value: "MODIFIED" } });
    await waitFor(() => expect(cards().length).toBe(2));
    expect(cards().map((c) => c.getAttribute("data-type"))).toEqual(["MODIFIED", "MODIFIED"]);
  });

  it("sorting by document order reorders rows", async () => {
    render(<CompareView />);
    await compare();
    fireEvent.change(screen.getByTestId("sort-key"), { target: { value: "document" } });
    await waitFor(() =>
      expect(cards().map((c) => Number(c.getAttribute("data-order")))).toEqual([0, 1, 2, 3]),
    );
  });

  it("links each side of a change to its own document and range", async () => {
    render(<CompareView />);
    await compare();
    const links = screen.getAllByRole("link", { name: /open source/i });
    const hrefs = links.map((l) => l.getAttribute("href") ?? "");
    // The HIGH row is the liability-cap change (orderIdx 3): A range 103-203.
    expect(hrefs).toContain("/documents/doc-a?ranges=103-203");
    expect(hrefs.filter((h2) => h2.startsWith("/documents/doc-b")).length).toBeGreaterThan(0);
    // A REMOVED change has no B-side text, so it must offer exactly one link
    // (its A side) rather than a fake B source.
    const removed = cards().find((c) => c.getAttribute("data-type") === "REMOVED");
    expect(removed?.querySelectorAll("a").length).toBe(1);
    const added = cards().find((c) => c.getAttribute("data-type") === "ADDED");
    expect(added?.querySelectorAll("a").length).toBe(1);
  });

  it("says so when a filter hides everything", async () => {
    render(<CompareView />);
    await compare();
    for (const lvl of ["HIGH", "MEDIUM", "LOW", "COSMETIC"]) {
      fireEvent.click(screen.getByTestId(`filter-${lvl}`));
    }
    await waitFor(() => expect(cards().length).toBe(0));
    expect(screen.getByText(/No changes match the current filter/)).toBeTruthy();
  });

  it("reopens a persisted comparison without re-running the server", async () => {
    // Bug #12: comparisons were saved to the database and counted as dead
    // text ("N prior comparison(s)"), so a session reloaded after a refresh
    // could never be shown again. Persisted results must be reopenable.
    h.listComparisons.mockResolvedValue([RESULT]);
    render(<CompareView />);
    const button = await screen.findByTestId("reopen-comparison");
    expect(screen.queryAllByTestId("change-card").length).toBe(0);
    fireEvent.click(button);
    await waitFor(() => expect(cards().length).toBe(4));
    // The stored server verdict is displayed verbatim (HIGH first).
    expect(cards()[0].getAttribute("data-significance")).toBe("HIGH");
    // Reopening must NOT recompute anything on the server.
    expect(h.createComparison).not.toHaveBeenCalled();
  });
});
