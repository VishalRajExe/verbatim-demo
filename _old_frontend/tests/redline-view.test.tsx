// Regression: the plain-English Redline view must render verified proposals and
// thread the disambiguating context through to the apply call. Guards the fix
// for "Make the liability cap mutual." returning "No exact match", and for a
// repeated value (AED 100,000 in two clauses) being applied to the wrong one.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  propose: vi.fn(),
  create: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  API_BASE: "http://backend",
  listDocuments: async () => ({
    documents: [
      {
        id: "doc-1",
        filename: "contract.docx",
        file_type: ".docx",
        file_size: 10,
        page_count: 1,
        status: "ready",
        error_message: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
    total: 1,
  }),
  listRedlines: async () => [],
  proposeRedline: (...a: unknown[]) => h.propose(...a),
  createRedline: (...a: unknown[]) => h.create(...a),
  redlineDownloadUrl: (id: string) => `http://backend/api/redlines/${id}/download`,
}));

import { RedlineView } from "@/features/redline/RedlineView";

beforeEach(() => {
  h.propose.mockReset();
  h.create.mockReset();
});
afterEach(() => cleanup());

async function selectDocAndPropose(instruction: string) {
  render(<RedlineView />);
  const select = await screen.findByLabelText(/Document \(DOCX only\)/i);
  fireEvent.change(select, { target: { value: "doc-1" } });
  const box = await screen.findByPlaceholderText(/Describe the change/i);
  fireEvent.change(box, { target: { value: instruction } });
  fireEvent.click(screen.getByRole("button", { name: /Propose edits/i }));
}

it("renders a verified semantic proposal with revision number and badge", async () => {
  h.propose.mockResolvedValue({
    documentId: "doc-1",
    instruction: "Make the liability cap mutual.",
    proposed: [
      {
        target: "Supplier\u2019s",
        replacement: "each party\u2019s",
        reason: "Extend the provision to apply to both parties.",
        include: true,
        context: "Supplier\u2019s aggregate liability ...",
        occurrences: 1,
        verified: true,
      },
    ],
    dropped: [],
  });

  await selectDocAndPropose("Make the liability cap mutual.");

  // findByText throws if the element is absent, so resolving is the assertion.
  expect(await screen.findByText("Verified")).toBeTruthy();
  expect(screen.getByText("#1")).toBeTruthy();
  // No single-occurrence pill when the target is already globally unique.
  expect(screen.queryByText(/Single occurrence via context/)).toBeNull();
});

it("flags a repeated value as single-occurrence via context and sends context on apply", async () => {
  const proposal = {
    target: "AED 100,000",
    replacement: "AED 1,000,000",
    reason: "mock value swap",
    include: true,
    context: "Except for liability ... will not exceed AED 100,000.",
    occurrences: 2,
    verified: true,
  };
  h.propose.mockResolvedValue({
    documentId: "doc-1",
    instruction: "Change the liability cap from AED 100,000 to AED 1,000,000.",
    proposed: [proposal],
    dropped: [],
  });
  h.create.mockResolvedValue({
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

  await selectDocAndPropose(
    "Change the liability cap from AED 100,000 to AED 1,000,000.",
  );
  expect(
    await screen.findByText(/Single occurrence via context \(2 in doc\)/),
  ).toBeTruthy();

  fireEvent.click(
    screen.getByRole("button", { name: /Apply 1 selected edit/i }),
  );
  await waitFor(() => expect(h.create).toHaveBeenCalled());
  const body = h.create.mock.calls[0][1];
  expect(body.edits[0]).toEqual({
    target: "AED 100,000",
    replacement: "AED 1,000,000",
    context: proposal.context,
  });
});

it("shows the honest not-found reason for a pure-semantic miss", async () => {
  h.propose.mockResolvedValue({
    documentId: "doc-1",
    instruction: "Make the liability cap mutual.",
    proposed: [],
    dropped: [
      {
        target: "Make the liability cap mutual.",
        reason:
          "No clause clearly matching the requested change was found, or it already satisfies the instruction. Nothing was proposed.",
      },
    ],
  });
  await selectDocAndPropose("Make the liability cap mutual.");
  expect(
    await screen.findByText(/already satisfies the instruction/i),
  ).toBeTruthy();
});
