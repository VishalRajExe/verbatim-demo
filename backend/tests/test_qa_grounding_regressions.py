"""Regression tests for generic QA-correctness fixes found during live QA.

These are provider-independent (deterministic functions + MockClient), so they
run offline and would fail if the underlying logic regressed:

1. Compose must GROUND the page it names: the verified page (resolved
   server-side) is passed into the compose prompt label, so the model cites a
   real page instead of inventing one (live bug: a page-148 answer said "page 150").
2. Extraction must ask for EVERY relevant passage, not just the headline clause
   (live bug: an incident deadline on one page was dropped when another page's
   timeline was the "most prominent" match).
3. Broad (unpage-constrained) questions must chunk a large document into
   multiple, attendable extraction windows rather than one ~96k megachunk, which
   silently under-returned scattered facts.
4. Compound questions must keep EACH part's evidence: the relevance floor used
   to demand two focus terms from the whole question, so the liability-cap
   clause in "what is the cap AND the payment term?" scored 1, was gated out,
   and the second half of every compound question became "the quotes are
   silent" (also: short topics like "cap"/"fee"/"law" were below the keyword
   length floor and never counted at all).
5. A page reference must scope only to the sub-question that made it. In a
   multi-document compound question ("the token on page 4 of the 150-page
   contract, AND the liability cap in the other document") the global page
   filter discarded the OTHER document's page-1 liability clause because it
   was not on page 4 - so the non-page part became "the quotes are silent".
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.document import Document
from app.services.ai.client import MockClient
from app.services.qa.intent import (
    specific_keywords,
    subquestion_groups,
    subquestion_page_parts,
)
from app.services.qa.pipeline import _BROAD_CHUNK_CHARS, ask_stream
from app.services.qa.prompts import compose_prompt, extract_prompt
from tests.helpers import make_text_pdf

API = "/api/documents"


def _collect(gen) -> list[dict]:
    return list(gen)


# ── 1. compose page grounding ────────────────────────────────────────────────

def test_compose_prompt_grounds_verified_page_metadata() -> None:
    quotes = [
        {"ref": "Q1", "documentName": "d.pdf", "text": "Line one.", "pageStart": 5, "pageEnd": 5},
        {"ref": "Q2", "documentName": "d.pdf", "text": "Line two.", "pageStart": 12, "pageEnd": 14},
    ]
    prompt = compose_prompt("What applies?", quotes, multi=False)
    # The authoritative page rides on the label so the model never guesses.
    assert "[Q1] (d.pdf, page 5):" in prompt
    assert "[Q2] (d.pdf, pages 12-14):" in prompt


def test_compose_prompt_omits_location_when_pages_absent() -> None:
    quotes = [{"ref": "Q1", "documentName": "d.pdf", "text": "Only text.", "pageStart": None, "pageEnd": None}]
    prompt = compose_prompt("q?", quotes, multi=False)
    # No spurious ", page" when a quote carries no resolved location.
    assert "[Q1] (d.pdf): Only text." in prompt


# ── 2. extraction completeness ───────────────────────────────────────────────

def test_extract_prompt_demands_every_relevant_passage() -> None:
    prompt = extract_prompt("d.pdf", "What is the timeline and deadline?", "some data")
    assert "EVERY passage" in prompt
    assert "EACH part" in prompt


# ── 3. broad-question multi-window recall ────────────────────────────────────

def test_broad_question_chunks_large_document_into_multiple_windows(
    client: TestClient, tmp_path: Path
) -> None:
    filler = (
        "This standard operational clause sets out routine obligations for "
        "records, assigned owners, and notification of any material deviation. "
    ) * 6
    pages = [filler for _ in range(40)]
    pdf = make_text_pdf(tmp_path / "big.pdf", pages)
    resp = client.post(
        API + "/upload", files={"file": ("big.pdf", pdf.read_bytes(), "application/pdf")}
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        canon_len = len(doc.extracted_text or "")
        assert canon_len > 2 * _BROAD_CHUNK_CHARS, canon_len
        events = _collect(
            ask_stream(db, [doc], "What are the routine obligations?", MockClient())
        )
    finally:
        db.close()
        client.delete(f"{API}/{doc_id}")

    cov = next(e for e in events if e["type"] == "coverage")["coverage"]
    # A single megachunk would report chunksTotal == 1; the bounded broad path
    # must split it and (with the mock) read every window completely.
    assert cov[0]["chunksTotal"] >= 2, cov
    assert cov[0]["chunksRead"] == cov[0]["chunksTotal"], cov


# ── 4. compound-question evidence floor ──────────────────────────────────────

def test_short_legal_topics_count_as_focus_terms() -> None:
    # "cap" (3 letters) is the question's actual subject; the old length floor
    # of 4 discarded it, so no cap quote could ever earn a second term match.
    assert "cap" in specific_keywords("What is the liability cap?")
    assert "fee" in specific_keywords("What implementation fee applies?")
    # Grammar never becomes a topic.
    assert not specific_keywords("What is it in?")


def test_subquestion_groups_partition_compound_questions() -> None:
    groups = subquestion_groups(
        "What is the liability cap and how long does the Customer have to pay "
        "undisputed invoices?"
    )
    assert any({"cap", "liability"} <= g for g in groups), groups
    assert any({"pay", "invoices"} <= g or {"undisputed", "invoices"} <= g for g in groups), groups
    # A single-part question stays a single group.
    assert subquestion_groups("What is the liability cap?") == [{"cap", "liability"}]


def test_compound_question_keeps_evidence_for_both_parts(
    client: TestClient, tmp_path: Path
) -> None:
    pages = [
        "MERGER TERMS\nEach party's aggregate liability is capped at AED 100,000 per claim year.",
        "PAYMENT TERMS\nThe Customer shall pay each undisputed invoice within 30 days after receipt.",
        "UNRELATED\nThe cafeteria menu is reviewed quarterly by the office manager.",
    ]
    pdf = make_text_pdf(tmp_path / "compound.pdf", pages)
    resp = client.post(
        API + "/upload", files={"file": ("compound.pdf", pdf.read_bytes(), "application/pdf")}
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        events = _collect(
            ask_stream(
                db, [doc],
                "What is the liability cap and how long does the Customer have "
                "to pay undisputed invoices?",
                MockClient(),
            )
        )
    finally:
        db.close()
        client.delete(f"{API}/{doc_id}")

    quotes = next(e for e in events if e["type"] == "quotes")["quotes"]
    texts = " ".join(q["text"].lower() for q in quotes)
    assert "liability" in texts and "capped" in texts, quotes  # part 1 survives
    assert "invoice" in texts and "30 days" in texts, quotes    # part 2 survives
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    assert "100,000" in answer and "30 days" in answer, answer


# ── 5. per-sub-question page scoping (multi-document compound) ───────────────

def test_page_parts_scope_page_ref_to_its_own_subquestion() -> None:
    parts = subquestion_page_parts(
        "What is the unique test token on page 2 of the second document, and "
        "what is the liability cap in the first document?"
    )
    term_parts = [(t, p) for (t, p) in parts if t]
    assert len(term_parts) == 2, parts
    # Exactly one part carries the page reference; the liability part names none.
    assert sum(1 for _t, p in term_parts if p) == 1, term_parts
    assert any({"cap", "liability"} <= t for t, _p in term_parts), term_parts


def test_page_reference_does_not_starve_other_document(
    client: TestClient, tmp_path: Path
) -> None:
    # The liability cap sits on page 1, the page-referenced token on page 2.
    # A global page filter keyed to "page 2" would drop the page-1 liability
    # clause - exactly the multi-document bug, reproduced within one document
    # so the assertion is deterministic. The page reference belongs only to the
    # token sub-question; the liability sub-question names no page.
    pages = [
        "PAYMENT\nExcept for liability that cannot lawfully be limited, each "
        "party's aggregate liability will not exceed AED 100,000.",
        "APPENDIX\nThe internal test identifier PAGE-UNIQUE-TOKEN-002 is "
        "embedded on this page for retrieval checks.",
        "ADMIN\nRoutine administrative provisions follow in this unrelated part.",
    ]
    pdf = make_text_pdf(tmp_path / "scoped.pdf", pages)
    resp = client.post(
        API + "/upload", files={"file": ("scoped.pdf", pdf.read_bytes(), "application/pdf")}
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        events = _collect(
            ask_stream(
                db, [doc],
                "What is the unique test token on page 2, and what is the "
                "liability cap?",
                MockClient(),
            )
        )
    finally:
        db.close()
        client.delete(f"{API}/{doc_id}")

    quotes = next(e for e in events if e["type"] == "quotes")["quotes"]
    texts = " ".join(q["text"].lower() for q in quotes)
    assert "page-unique-token-002" in texts, quotes  # page-referenced part
    assert "100,000" in texts, quotes                # non-page part survives

