"""Phase 3/7/8 API integration tests: ask (streaming), comparisons, redlines.

The ask route is exercised with the offline MockClient via a dependency
override, so no network or Gemini key is needed while still proving the whole
HTTP path (NDJSON stream + persistence + history reload).
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.qa import get_llm_dep
from app.main import app
from app.services.ai.client import MockClient

DOC_API = "/api/documents"

P1 = "The Customer shall pay all outstanding amounts within 30 days of invoice date."
P2 = "The total liability cap is AED 100,000 per claim year for either party."


def _parse_ndjson(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _upload_pdf(client, tmp_path, name, pages):
    from tests.helpers import make_text_pdf

    pdf = make_text_pdf(tmp_path / name, pages)
    r = client.post(
        f"{DOC_API}/upload", files={"file": (name, pdf.read_bytes(), "application/pdf")}
    )
    assert r.status_code == 202
    return r.json()["id"]


def _upload_docx(client, tmp_path, name, paragraphs):
    from tests.helpers import make_docx

    docx = make_docx(tmp_path / name, paragraphs)
    r = client.post(f"{DOC_API}/upload", files={"file": (name, docx.read_bytes())})
    assert r.status_code == 202
    return r.json()["id"]


# ── Ask / conversations ───────────────────────────────────────────────────────

def test_ask_stream_and_history(client: TestClient, tmp_path: Path):
    app.dependency_overrides[get_llm_dep] = lambda: MockClient()
    doc_id = _upload_pdf(client, tmp_path, "c.pdf", [P1, P2])
    conv_id = None
    try:
        resp = client.post(
            "/api/ask",
            json={"documentIds": [doc_id], "question": "When must the Customer pay?"},
        )
        assert resp.status_code == 200, resp.text
        events = _parse_ndjson(resp.text)
        types = [e["type"] for e in events]
        assert types[0] == "meta"
        conv_id = events[0]["conversationId"]
        assert "quotes" in types and "token" in types and types[-1] == "done"

        quotes = next(e for e in events if e["type"] == "quotes")["quotes"]
        assert quotes and quotes[0]["verified"] is True

        # History reload shows the persisted, server-verified turn.
        detail = client.get(f"/api/conversations/{conv_id}").json()
        assert detail["title"].startswith("When must")
        assistant = [m for m in detail["messages"] if m["role"] == "assistant"]
        assert assistant and assistant[-1]["content"].strip()
        verified = [q for q in assistant[-1]["quotes"] if q["verified"]]
        assert verified and verified[0]["pageStart"] >= 1
        assert verified[0]["start"] is not None
    finally:
        app.dependency_overrides.clear()
        if conv_id:
            client.delete(f"/api/conversations/{conv_id}")
        client.delete(f"{DOC_API}/{doc_id}")


def test_ask_unknown_document_404(client: TestClient):
    app.dependency_overrides[get_llm_dep] = lambda: MockClient()
    try:
        resp = client.post(
            "/api/ask", json={"documentIds": ["nope"], "question": "hi there friend"}
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_session_list_followup_and_reopen_persists(client: TestClient, tmp_path: Path):
    """Sessions regression: a conversation must appear in the list exactly
    once, follow-ups must append to the same conversation (not fork a new
    one), and reopening by id must return every persisted, verified turn —
    the API contract the UI relies on across browser refreshes."""
    app.dependency_overrides[get_llm_dep] = lambda: MockClient()
    doc_id = _upload_pdf(client, tmp_path, "s.pdf", [P1, P2])
    conv_id = None
    try:
        r1 = client.post(
            "/api/ask",
            json={"documentIds": [doc_id], "question": "When must the Customer pay?"},
        )
        assert r1.status_code == 200
        conv_id = _parse_ndjson(r1.text)[0]["conversationId"]

        # The session is listed for the history rail.
        listed = client.get("/api/conversations").json()
        match = [c for c in listed if c["id"] == conv_id]
        assert len(match) == 1, "conversation must appear exactly once in the list"

        # A follow-up continues the SAME conversation, not a new one.
        before = len(client.get("/api/conversations").json())
        r2 = client.post(
            "/api/ask",
            json={
                "documentIds": [doc_id],
                "question": "What is the liability cap?",
                "conversationId": conv_id,
            },
        )
        assert r2.status_code == 200
        meta2 = _parse_ndjson(r2.text)[0]
        assert meta2["conversationId"] == conv_id
        assert len(client.get("/api/conversations").json()) == before

        # Reopen (simulates browser refresh + click on the old session).
        detail = client.get(f"/api/conversations/{conv_id}").json()
        roles = [m["role"] for m in detail["messages"]]
        assert roles.count("user") == 2 and roles.count("assistant") == 2
        assistants = [m for m in detail["messages"] if m["role"] == "assistant"]
        assert all(m["content"].strip() for m in assistants)
        # Reopened quotes keep document scoping: ids/pages are persisted.
        for m in assistants:
            for q in m["quotes"]:
                if q["verified"]:
                    assert q["documentId"] == doc_id
                    assert q["pageStart"] >= 1
    finally:
        app.dependency_overrides.clear()
        if conv_id:
            client.delete(f"/api/conversations/{conv_id}")
        client.delete(f"{DOC_API}/{doc_id}")


# ── Comparisons ───────────────────────────────────────────────────────────────

def test_create_and_read_comparison(client: TestClient, tmp_path: Path):
    a = _upload_docx(
        client, tmp_path, "a.docx",
        ["Payment. The Customer shall pay within 30 days.",
         "Liability. The total liability cap is AED 100,000 per year."],
    )
    b = _upload_docx(
        client, tmp_path, "b.docx",
        ["Payment. The Customer shall pay within 45 days.",
         "Liability. The total liability cap is AED 250,000 per year."],
    )
    comp_ids = []
    try:
        resp = client.post(
            "/api/comparisons", json={"documentAId": a, "documentBId": b}
        )
        assert resp.status_code == 201, resp.text
        comp = resp.json()
        comp_ids.append(comp["id"])
        assert comp["changes"], "expected detected changes"
        assert comp["summarySource"] == "automatic"
        # A change should flag the differing numbers somewhere as non-cosmetic.
        assert any(
            c["significance"] in ("HIGH", "MEDIUM") for c in comp["changes"]
        ), comp["changes"]

        listed = client.get("/api/comparisons").json()
        assert any(c["id"] == comp["id"] for c in listed)
        one = client.get(f"/api/comparisons/{comp['id']}").json()
        assert one["id"] == comp["id"]
    finally:
        client.delete(f"{DOC_API}/{a}")
        client.delete(f"{DOC_API}/{b}")


# ── Redlines ──────────────────────────────────────────────────────────────────

def test_redline_produces_downloadable_tracked_docx(client: TestClient, tmp_path: Path):
    target = "The total liability cap is AED 100,000 per year."
    replacement = "The total liability cap is AED 50,000 per year."
    doc_id = _upload_docx(
        client, tmp_path, "r.docx",
        ["Liability. " + target, "Governing law is the UAE."],
    )
    try:
        resp = client.post(
            f"{DOC_API}/{doc_id}/redline",
            json={
                "edits": [{"target": target, "replacement": replacement}],
                "author": "Test Counsel",
            },
        )
        assert resp.status_code == 201, resp.text
        out = resp.json()
        assert out["insertions"] >= 1 and out["deletions"] >= 1
        assert out["applied"] and not out["dropped"]

        dl = client.get(f"/api/redlines/{out['id']}/download")
        assert dl.status_code == 200
        # A .docx is a zip; the tracked-changes markup must be present.
        from app.services.redlining.tracked_changes import count_tracked_changes

        ins, dele = count_tracked_changes(dl.content)
        assert ins >= 1 and dele >= 1
    finally:
        client.delete(f"{DOC_API}/{doc_id}")


def test_redline_drops_ambiguous_edit(client: TestClient, tmp_path: Path):
    # Target appears twice -> cannot safely place a tracked edit -> dropped.
    doc_id = _upload_docx(
        client, tmp_path, "dup.docx",
        ["Fee is AED 500.", "Fee is AED 500. is stated twice."],
    )
    try:
        resp = client.post(
            f"{DOC_API}/{doc_id}/redline",
            json={"edits": [{"target": "Fee is AED 500.", "replacement": "Fee is AED 700."}]},
        )
        assert resp.status_code == 201
        out = resp.json()
        assert out["applied"] == []
        assert out["dropped"] and "exactly once" in out["dropped"][0]["reason"]
    finally:
        client.delete(f"{DOC_API}/{doc_id}")


def test_redline_rejects_pdf(client: TestClient, tmp_path: Path):
    doc_id = _upload_pdf(client, tmp_path, "p.pdf", [P1, P2])
    try:
        resp = client.post(
            f"{DOC_API}/{doc_id}/redline",
            json={"edits": [{"target": P1, "replacement": "nope"}]},
        )
        assert resp.status_code == 400
    finally:
        client.delete(f"{DOC_API}/{doc_id}")
