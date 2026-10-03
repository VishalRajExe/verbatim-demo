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
    matches_term,
    matches_word,
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

# Adjacent-topic decoys for the relevance-floor regressions below.
Q_LATE = "A late payment incurs a penalty of 1.0% per month on the outstanding balance."
Q_EXPORT = "The Customer shall comply with applicable export control and sanctions laws at all times."
EIGHT_PAGES = SIX_PAGES + [Q_LATE, Q_EXPORT]

# Inflected wording: the clause says "governed", the question says "governs".
GOV_PAGES = SIX_PAGES + [
    "GOVERNING LAW\nThis Agreement is governed by the laws of the Republic of Cascadia, "
    "without regard to conflict-of-law principles.",
    "SERVICE METRICS\nMetric Value Owner\nReview period 6 business days Contract Manager\n"
    "Escalation target 1 business days Service Lead",
]


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


def test_focus_stems_are_word_boundary_anchored() -> None:
    # Bug #3: a raw substring stem let "late" match "violate" and "apply"
    # match "applicable", inverting the relevance floor so an unrelated quote
    # outscored the true answer. Stems may only bridge inflections of the SAME
    # word, starting at a word boundary.
    assert focus_hits("party to violate these terms", {"late"}) == 0
    assert focus_hits("a close analogy between the parties", {"liability"}) == 0
    assert focus_hits("payments due for the reply period", {"payment"}) == 1
    assert focus_hits("payment of the late fee", {"late"}) == 1
    assert focus_hits("it is applicable here", {"applicable"}) == 1
    assert focus_hits("a delayed violation", {"violation"}) == 1


def test_quantity_terms_are_answered_by_numbers() -> None:
    # "percentage" is legitimately answered by "1.0% per month" even though
    # the words differ — a generic quantity<->digit bridge, not a lookup table.
    assert focus_hits("a late payment penalty of 1.0% per month", {"percentage"}) == 1
    # But a term-less, number-less sentence gets no free bridge.
    assert focus_hits("no quantity referenced at all", {"percentage"}) == 0


def test_matchers_expose_morphology_without_the_numeric_bridge() -> None:
    # Extraction scores with matches_word only (keeps candidate ranking
    # discriminating); the evidence floor uses matches_term (adds the bridge).
    assert matches_word("the agreement is governed by cascadian law", "governs")
    assert not matches_word("party to violate these terms", "late")
    assert not matches_term("a sentence with no numbers", "amount")
    assert matches_term("a total of 42 items", "amount")


def test_comparative_framing_words_are_not_topics() -> None:
    # Bug #5: "compare" / "across" / "these" / "evidence" / "supports" describe
    # HOW to answer, not WHAT to look for. Counted as focus terms they raised
    # the relevance floor above any clause that mentions only its real topic,
    # so every comparison question degenerated into a not-found answer.
    assert specific_keywords(
        "Compare the liability-related terms across these two documents."
    ) == {"liability", "terms"}
    assert specific_keywords(
        "What evidence in each document supports the liability analysis?"
    ) == {"liability"}


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


def test_quantity_question_prefers_numeric_evidence_over_adjacent_prose(
    client: TestClient, tmp_path: Path
) -> None:
    # Bug #3 end-to-end: "What percentage applies to late payments?" was
    # answered with the export-control/sanctions quote ("applicable" matched
    # the "apply" stem, "violated" matched "late") while the true "1.0% per
    # month" quote fell below the floor. Adjacent-topic prose must never
    # outrank the quote that actually carries the requested quantity.
    doc_id = _ready(client, tmp_path / "eight.pdf", "eight.pdf", EIGHT_PAGES)
    try:
        quotes, answer = _ask(
            client, [doc_id], "What percentage applies to late payments?"
        )
        texts = " ".join(q["text"] for q in quotes)
        assert any("1.0%" in q["text"] for q in quotes), texts
        assert "sanctions" not in texts, texts
        assert "1.0%" in answer
    finally:
        client.delete(f"{API}/{doc_id}")


def test_comparison_question_answers_from_every_selected_document(
    client: TestClient, tmp_path: Path
) -> None:
    # Bug #5 end-to-end: a comparison question over two documents returned a
    # not-found refusal because its framing words counted as focus terms.
    # Each document must answer with its OWN clause and keep its own id.
    a_id = _ready(client, tmp_path / "a.pdf", "a.pdf", SIX_PAGES)
    b_pages = list(SIX_PAGES)
    b_pages[5] = (
        "The supplier maintains professional liability insurance with an "
        "aggregate liability limit of AED 750,000 per claim."
    )
    b_id = _ready(client, tmp_path / "b.pdf", "b.pdf", b_pages)
    try:
        quotes, answer = _ask(
            client,
            [a_id, b_id],
            "Compare the liability-related terms across these two documents.",
        )
        assert quotes, "a comparison question must retrieve evidence"
        by_doc = {q["documentId"] for q in quotes}
        assert by_doc == {a_id, b_id}, by_doc
        texts = " ".join(q["text"] for q in quotes)
        assert "5,000,000" in texts and "750,000" in texts, texts

        quotes2, _ = _ask(
            client,
            [a_id, b_id],
            "What evidence in each document supports the liability analysis?",
        )
        assert {q["documentId"] for q in quotes2} == {a_id, b_id}, quotes2
    finally:
        client.delete(f"{API}/{a_id}")
        client.delete(f"{API}/{b_id}")


def test_zero_relevance_quotes_never_reach_composition(
    client: TestClient, tmp_path: Path
) -> None:
    # Soft floor: with only two focus terms (below the hard floor of 3), a
    # verified quote that matches NONE of them must still be dropped from
    # the evidence handed to composition.
    doc_id = _ready(client, tmp_path / "eight.pdf", "eight.pdf", EIGHT_PAGES)
    try:
        quotes, _ = _ask(
            client, [doc_id], "What liability cap amount applies to the supplier?"
        )
        assert quotes, "the cap quote itself must survive"
        assert any("5,000,000" in q["text"] for q in quotes)
        assert not any("sanctions" in q["text"].lower() for q in quotes)
    finally:
        client.delete(f"{API}/{doc_id}")


def test_inflected_question_word_still_finds_the_clause(
    client: TestClient, tmp_path: Path
) -> None:
    # Bug #4: extraction scored candidates with raw substring equality, so the
    # question word "governs" never matched the clause's "governed" and the
    # governing-law section was unreachable — the app refused a question the
    # document plainly answers.
    doc_id = _ready(client, tmp_path / "gov.pdf", "gov.pdf", GOV_PAGES)
    try:
        quotes, answer = _ask(client, [doc_id], "Which law governs this agreement?")
        assert quotes, "the governed-by clause must be retrieved"
        assert any("Republic of Cascadia" in q["text"] for q in quotes)
        assert "Cascadia" in answer
    finally:
        client.delete(f"{API}/{doc_id}")


def test_table_labels_are_found_from_singular_or_plural_question(
    client: TestClient, tmp_path: Path
) -> None:
    # A table row labelled "Escalation target" must answer a question asking
    # for "escalation targets" (and vice versa) on the requested page.
    doc_id = _ready(client, tmp_path / "gov.pdf", "gov.pdf", GOV_PAGES)
    try:
        quotes, answer = _ask(
            client, [doc_id], "What are the escalation targets on page 8?"
        )
        assert quotes, [q["text"] for q in quotes]
        assert all(q["pageStart"] == 8 for q in quotes)
        assert "1 business days" in answer
    finally:
        client.delete(f"{API}/{doc_id}")
