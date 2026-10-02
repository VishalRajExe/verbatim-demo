"""Phase 3 pipeline end-to-end: the extract -> verify -> compose spine.

Runs ask_stream against a real, processed document with the deterministic
MockClient, and with a hostile fake LLM that invents text, to prove the
invariants: only verified quotes are ever composed, and invented quotes are
dropped (never cited, never shown as grounding).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.document import Document
from app.services.ai.client import MockClient
from app.services.qa.pipeline import ask_stream
from tests.helpers import make_text_pdf

API = "/api/documents"

P1 = "The Customer shall pay all outstanding amounts within 30 days of invoice date."
P2 = "The total liability cap is AED 100,000 per claim year for either party."


def _ready_doc(client: TestClient, tmp_path: Path) -> str:
    pdf = make_text_pdf(tmp_path / "doc.pdf", [P1, P2])
    resp = client.post(
        API + "/upload", files={"file": ("doc.pdf", pdf.read_bytes(), "application/pdf")}
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    assert client.get(f"{API}/{doc_id}").json()["status"] == "ready"
    return doc_id


def _collect(gen) -> list[dict]:
    return list(gen)


class InventingLLM:
    """Returns a quote that is NOT in the document plus one real sentence."""

    def complete_json(self, prompt: str):
        return {
            "quotes": [
                {"text": "The vendor guarantees unlimited liability forever.", "why": "fabricated"},
            ]
        }

    def complete(self, prompt: str) -> str:  # pragma: no cover - not used here
        return "unused"

    def stream(self, prompt: str):
        # Should never be reached because there will be no verified quotes.
        yield "SHOULD-NOT-APPEAR"


def test_mock_stream_produces_verified_quotes_and_cited_answer(client, tmp_path):
    doc_id = _ready_doc(client, tmp_path)
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        events = _collect(ask_stream(db, [doc], "When must the Customer pay?", MockClient()))
    finally:
        db.close()
        client.delete(f"{API}/{doc_id}")

    types = [e["type"] for e in events]
    assert "status" in types
    assert "quotes" in types
    assert "coverage" in types
    assert "token" in types
    assert types[-1] == "done"

    quotes_event = next(e for e in events if e["type"] == "quotes")
    verified = quotes_event["quotes"]
    assert verified, "expected at least one verified quote for the payment question"
    # Every emitted verified quote carries server-computed positions.
    for v in verified:
        assert v["verified"] is True
        assert isinstance(v["start"], int) and v["end"] > v["start"]
        assert v["pageStart"] >= 1
        assert v["ref"].startswith("Q")

    answer = "".join(e["text"] for e in events if e["type"] == "token")
    assert answer.strip(), "compose should stream a non-empty answer"

    cov = next(e for e in events if e["type"] == "coverage")["coverage"]
    assert cov[0]["complete"] is True


def test_invented_quote_is_never_composed_or_cited(client, tmp_path):
    doc_id = _ready_doc(client, tmp_path)
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        events = _collect(ask_stream(db, [doc], "Anything about liability?", InventingLLM()))
    finally:
        db.close()
        client.delete(f"{API}/{doc_id}")

    quotes_event = next(e for e in events if e["type"] == "quotes")
    assert quotes_event["quotes"] == []  # nothing verified
    assert quotes_event["unverified"], "the fabricated line should be reported unverified"
    assert quotes_event["unverified"][0]["failReason"] in ("NOT_FOUND", "TOO_SHORT")

    answer = "".join(e["text"] for e in events if e["type"] == "token")
    # The invented text must never leak into the answer, and the hostile token
    # stream is never reached (no verified quotes -> deterministic not-found).
    assert "SHOULD-NOT-APPEAR" not in answer
    assert "unlimited liability forever" not in answer
    assert answer.strip()  # deterministic not-found message present


def test_multi_document_question_verifies_per_attributed_doc(client, tmp_path):
    # Two docs; ask a question whose answer lives only in the second one.
    pdf1 = make_text_pdf(tmp_path / "one.pdf", [P1])
    pdf2 = make_text_pdf(tmp_path / "two.pdf", [P2])
    id1 = client.post(API + "/upload", files={"file": ("one.pdf", pdf1.read_bytes(), "application/pdf")}).json()["id"]
    id2 = client.post(API + "/upload", files={"file": ("two.pdf", pdf2.read_bytes(), "application/pdf")}).json()["id"]
    db = SessionLocal()
    try:
        docs = [db.get(Document, id1), db.get(Document, id2)]
        events = _collect(ask_stream(db, docs, "What is the liability cap?", MockClient()))
    finally:
        db.close()
        client.delete(f"{API}/{id1}")
        client.delete(f"{API}/{id2}")

    quotes = next(e for e in events if e["type"] == "quotes")["quotes"]
    # The liability sentence lives in doc id2; the verified quote must be
    # attributed to the document that actually contains it (invariant I-7).
    assert any(q["documentId"] == id2 and "liability cap" in q["text"].lower() for q in quotes)
