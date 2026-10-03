"""Page-constrained retrieval regression tests.

Guards the fix for the pollution bug: "What is the reference value on page
123?" returned 15 verified quotes across 12 pages because the page number was
treated as a generic keyword. An explicit page reference is now a STRUCTURED
constraint (numeric page metadata, never substring matching), and verified-but-
irrelevant evidence is dropped by a separate relevance floor. All fixtures are
synthetic — no demo file, page number, or token from the bug report is
hardcoded in production logic.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.document import Document
from app.services.ai.client import MockClient
from app.services.qa.intent import (
    focus_hits,
    parse_page_constraints,
    specific_keywords,
)
from app.services.qa.pipeline import ask_stream
from tests.helpers import make_text_pdf

API = "/api/documents"

P1 = "Master Services Agreement between Northstar Retail Technologies and BluePeak Software Solutions."
P2 = "The Customer may request an audit of the Supplier's records once per year with fourteen days notice."
P3 = "The reference value for this page is REF-003-XL and it identifies the governing schedule."
P4 = "Financial baseline for the vendor program is AED 122,500 per quarter reviewed by the finance lead."
P5 = "Either party may terminate this agreement by giving sixty days written notice to the other party."
P6 = "The supplier maintains commercial general liability insurance with a coverage limit of AED 5,000,000 per occurrence."
SIX_PAGES = [P1, P2, P3, P4, P5, P6]


# ── intent parsing (pure) ────────────────────────────────────────────────────

def test_page_reference_is_a_structured_constraint() -> None:
    assert parse_page_constraints("What is the reference value on page 123?") == {123}
    assert parse_page_constraints("what is in p.87?") == {87}
    assert parse_page_constraints("from page 5 please") == {5}
    # Ranges expand numerically.
    assert parse_page_constraints("compare pages 37-38") == {37, 38}
    assert parse_page_constraints("page 10 to 12") == {10, 11, 12}


def test_legal_numbers_are_never_page_constraints() -> None:
    # §4: normal numeric search must not be affected.
    assert parse_page_constraints("What is the liability cap of AED 100,000?") == set()
    assert parse_page_constraints("Must payment occur within 30 days?") == set()
    assert parse_page_constraints("What does section 4.2 say?") == set()


def test_page_numbers_match_exactly_not_by_substring() -> None:
    # §5: "page 1" must never be satisfied by pages 10/11/100.
    pages = parse_page_constraints("the token on page 1")
    assert pages == {1} and 10 not in pages and 100 not in pages


def test_focus_terms_separate_substance_from_structure() -> None:
    assert specific_keywords("What is the reference value on page 123?") == {"value"}
    assert specific_keywords(
        "What insurance coverage limit is specified on page 123?"
    ) == {"insurance", "coverage", "limit"}
    # Purely structural question: page match alone is relevance enough.
    assert specific_keywords("What is the section on page 87 about?") == set()
    # Morphology-tolerant hits.
    assert focus_hits("Either party may terminate on notice.", {"termination", "notice"}) == 2
    assert focus_hits("unrelated sentence about logistics.", {"termination", "notice"}) == 0


# ── pipeline behavior ────────────────────────────────────────────────────────

def _ready(client: TestClient, path: Path, name: str, pages: list[str]) -> str:
    pdf = make_text_pdf(path, pages)
    resp = client.post(
        f"{API}/upload", files={"file": (name, pdf.read_bytes(), "application/pdf")}
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    assert client.get(f"{API}/{doc_id}").json()["status"] == "ready"
    return doc_id


def _ask(client: TestClient, doc_ids: list[str], question: str) -> tuple[list[dict], str]:
    db = SessionLocal()
    try:
        docs = [db.get(Document, d) for d in doc_ids]
        events = list(ask_stream(db, docs, question, MockClient()))
    finally:
        db.close()
    quotes = next(e for e in events if e["type"] == "quotes")["quotes"]
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    return quotes, answer


def test_page_question_retrieves_only_that_pages_evidence(client: TestClient, tmp_path: Path) -> None:
    doc_id = _ready(client, tmp_path / "six.pdf", "six.pdf", SIX_PAGES)
    try:
        quotes, answer = _ask(client, [doc_id], "What is the reference value on page 3?")
        assert quotes, "the target page must answer its own question"
        assert all(q["pageStart"] == 3 for q in quotes), [q["pageStart"] for q in quotes]
        assert "REF-003-XL" in answer
    finally:
        client.delete(f"{API}/{doc_id}")


def test_page_1_does_not_pull_pages_10_11_or_100(client: TestClient, tmp_path: Path) -> None:
    pages = [
        f"Reference value marker on this page is VAL-PAGE-{n:03d} and it is unique to this page."
        for n in range(1, 13)
    ]
    doc_id = _ready(client, tmp_path / "twelve.pdf", "twelve.pdf", pages)
    try:
        quotes, answer = _ask(client, [doc_id], "What is the reference value on page 1?")
        assert quotes and all(q["pageStart"] == 1 for q in quotes)
        assert "VAL-PAGE-001" in answer
        assert "VAL-PAGE-010" not in answer and "VAL-PAGE-011" not in answer
    finally:
        client.delete(f"{API}/{doc_id}")


def test_page_beyond_document_is_honest_not_found(client: TestClient, tmp_path: Path) -> None:
    doc_id = _ready(client, tmp_path / "six.pdf", "six.pdf", SIX_PAGES)
    try:
        quotes, answer = _ask(client, [doc_id], "What is the reference value on page 99?")
        assert quotes == []
        assert "do not contain page 99" in answer
    finally:
        client.delete(f"{API}/{doc_id}")


def test_verified_but_irrelevant_page_evidence_is_excluded(client: TestClient, tmp_path: Path) -> None:
    # Page 6 genuinely contains the insurance limit; page 3 does not. Asking
    # for insurance ON PAGE 3 must NOT borrow page 6's verified evidence.
    doc_id = _ready(client, tmp_path / "six.pdf", "six.pdf", SIX_PAGES)
    try:
        quotes, answer = _ask(
            client, [doc_id], "What insurance coverage limit is specified on page 3?"
        )
        assert quotes == [], [q["text"] for q in quotes]
        assert "5,000,000" not in answer
        assert "couldn't find" in answer.lower()
    finally:
        client.delete(f"{API}/{doc_id}")


def test_unconstrained_legal_number_question_still_works(client: TestClient, tmp_path: Path) -> None:
    doc_id = _ready(client, tmp_path / "six.pdf", "six.pdf", SIX_PAGES)
    try:
        quotes, answer = _ask(
            client, [doc_id], "What insurance coverage does the supplier maintain?"
        )
        assert quotes, "no page constraint: the whole document remains searchable"
        assert any("insurance" in q["text"].lower() for q in quotes)
        assert all(q["pageStart"] == 6 for q in quotes)  # the clause's real page
    finally:
        client.delete(f"{API}/{doc_id}")


def test_cross_page_question_still_spans_pages(client: TestClient, tmp_path: Path) -> None:
    # §11: no page reference -> legitimately multi-page evidence survives.
    doc_id = _ready(client, tmp_path / "six.pdf", "six.pdf", SIX_PAGES)
    try:
        quotes, _ = _ask(
            client,
            [doc_id],
            "What notice requirements apply to termination and to audit requests?",
        )
        pages = {q["pageStart"] for q in quotes}
        assert {2, 5} <= pages, pages  # audit page AND termination page
    finally:
        client.delete(f"{API}/{doc_id}")


def test_multi_document_page_attribution_is_per_document(client: TestClient, tmp_path: Path) -> None:
    # Doc A has 2 pages, Doc B has 6. "page 3" exists only in B; every quote
    # must keep its own documentId + page and A must contribute nothing.
    a_id = _ready(client, tmp_path / "a.pdf", "a.pdf", SIX_PAGES[:2])
    b_id = _ready(client, tmp_path / "b.pdf", "b.pdf", SIX_PAGES)
    try:
        quotes, _ = _ask(client, [a_id, b_id], "What is the reference value on page 3?")
        assert quotes
        assert all(q["documentId"] == b_id and q["pageStart"] == 3 for q in quotes)

        # "page 2" exists in BOTH: each document answers with its OWN page 2.
        quotes2, _ = _ask(
            client,
            [a_id, b_id],
            "What audit notice requirements apply to records requests?",
        )
        by_doc = {q["documentId"] for q in quotes2}
        assert by_doc == {a_id, b_id}, by_doc
        assert all(q["pageStart"] == 2 for q in quotes2)
    finally:
        client.delete(f"{API}/{a_id}")
        client.delete(f"{API}/{b_id}")
