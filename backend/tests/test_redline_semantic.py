"""Plain-English redlining: semantic instructions and repeated-value
disambiguation, exercised end-to-end against the deterministic offline model
(``MockClient``). This is the behaviour the reference (Antigravity) product
exhibits and that regressed to "No exact match".

The invariant under test: a natural-language instruction becomes a *verified*,
precisely-targeted tracked change. A value that repeats across clauses (the same
figure in the fee clause and the liability clause) is edited only in the clause
the instruction points at; the other occurrence is left byte-for-byte intact.
An instruction naming an original value that is absent, or one pointing at an
already-mutual clause, must propose nothing rather than guess.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from docx import Document
from fastapi import FastAPI

from app.api.qa import get_llm_dep
from app.services.ai.client import MockClient
from app.services.redlining.tracked_changes import count_tracked_changes
from tests.helpers import make_docx

API = "/api/documents"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Mirrors .journey/verbatim_redline_test_contract.docx with the liability cap
# made UNILATERAL. Note AED 100,000 (fee + liability) and 30 days (invoice +
# cure period) BOTH repeat, so every edit must be pinned to the right clause.
FIXTURE_PARAS = [
    "MASTER SERVICES AGREEMENT - REDLINE TEST",
    "1. Fees and Payment",
    "Customer will pay undisputed invoices within 30 days of receipt. "
    "The implementation fee is AED 100,000. Late undisputed amounts may "
    "accrue interest at 1.0% per month.",
    "2. Limitation of Liability",
    "Except for liability that cannot lawfully be limited, Supplier\u2019s "
    "aggregate liability arising out of or relating to this Agreement will not "
    "exceed AED 100,000. Neither party will be liable for indirect, incidental, "
    "special, consequential or punitive damages.",
    "4. Security Incident Notice",
    "Supplier shall notify Customer of a confirmed security incident affecting "
    "Customer Data within 48 hours after confirmation.",
    "5. Termination",
    "Either party may terminate for material breach if the breach is not cured "
    "within 30 days after written notice.",
]


@pytest.fixture()
def client_app(client):
    yield client.app
    client.app.dependency_overrides.clear()


def _use_mock(app: FastAPI) -> None:
    app.dependency_overrides[get_llm_dep] = lambda: MockClient()


def _ready_docx(client, tmp_path: Path, paragraphs: list[str], name: str = "fixture.docx") -> str:
    path = make_docx(tmp_path / name, paragraphs)
    resp = client.post(
        API + "/upload",
        files={
            "file": (
                name,
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    assert client.get(f"{API}/{doc_id}").json()["status"] == "ready"
    return doc_id


def _propose(client, doc_id: str, instruction: str) -> dict:
    resp = client.post(f"{API}/{doc_id}/redline/propose", json={"instruction": instruction})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _apply(client, doc_id: str, proposed: list[dict], instruction: str) -> dict:
    resp = client.post(
        f"{API}/{doc_id}/redline",
        json={
            "edits": [
                {"target": e["target"], "replacement": e["replacement"], "context": e.get("context", "")}
                for e in proposed
            ],
            "author": "Legal AI",
            "instruction": instruction,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _download(client, redline_id: str) -> bytes:
    resp = client.get(f"/api/redlines/{redline_id}/download")
    assert resp.status_code == 200
    return resp.content


def _all_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def _del_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        from lxml import etree

        root = etree.fromstring(z.read("word/document.xml"))
    return "".join(t.text or "" for t in root.iter(f"{{{W}}}delText"))


def _ins_text(data: bytes) -> str:
    # python-docx's ``paragraph.text`` ignores runs nested inside w:ins/w:del, so
    # inserted text must be read from the XML directly.
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        from lxml import etree

        root = etree.fromstring(z.read("word/document.xml"))
    return "".join(
        t.text or ""
        for ins in root.iter(f"{{{W}}}ins")
        for t in ins.iter(f"{{{W}}}t")
    )


# ── The seven required redline instructions ───────────────────────────────────

def test_1_semantic_make_mutual_proposes_and_applies(client, client_app, tmp_path):
    _use_mock(client_app)
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    ins = "Make the liability cap mutual."
    try:
        out = _propose(client, doc_id, ins)
        assert out["proposed"], "semantic instruction must produce a real proposal"
        edit = out["proposed"][0]
        assert edit["target"] == "Supplier\u2019s"
        assert edit["replacement"] == "each party\u2019s"
        assert edit["verified"] is True

        applied = _apply(client, doc_id, out["proposed"], ins)
        data = _download(client, applied["id"])
        ins_ct, del_ct = count_tracked_changes(data)
        assert (ins_ct, del_ct) == (1, 1)
        assert "Supplier\u2019s" in _del_text(data)
        assert "each party\u2019s" in _ins_text(data)
        # the mutual edit does not touch any amount: both AED 100,000 figures
        # remain as ordinary text in the document.
        assert _all_text(data).count("AED 100,000") == 2
    finally:
        client.delete(f"{API}/{doc_id}")


def test_2_explicit_value_swap_targets_only_the_liability_occurrence(client, client_app, tmp_path):
    _use_mock(client_app)
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    ins = "Change the liability cap from AED 100,000 to AED 1,000,000."
    try:
        out = _propose(client, doc_id, ins)
        assert len(out["proposed"]) == 1
        edit = out["proposed"][0]
        assert edit["target"] == "AED 100,000"
        assert edit["replacement"] == "AED 1,000,000"
        assert edit["occurrences"] == 2  # repeated value, disambiguated by context

        applied = _apply(client, doc_id, out["proposed"], ins)
        data = _download(client, applied["id"])
        assert count_tracked_changes(data) == (1, 1)
        # exactly one AED 100,000 deleted, replaced by the new cap in the
        # liability clause; the fee line keeps its figure as ordinary text.
        assert "AED 100,000" in _del_text(data)
        assert "AED 1,000,000" in _ins_text(data)
        body = _all_text(data)
        assert "implementation fee is AED 100,000" in body
    finally:
        client.delete(f"{API}/{doc_id}")


def test_3_wrong_original_value_is_rejected(client, client_app, tmp_path):
    _use_mock(client_app)
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    ins = "Change the liability cap from AED 500,000 to AED 2,000,000."
    try:
        out = _propose(client, doc_id, ins)
        assert out["proposed"] == []
        assert out["dropped"]
        reason = " ".join(d["reason"] for d in out["dropped"])
        assert "AED 500,000" in reason and "not found" in reason
    finally:
        client.delete(f"{API}/{doc_id}")


def test_4_invoice_payment_days_disambiguated_from_cure_period(client, client_app, tmp_path):
    _use_mock(client_app)
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    ins = "Change the invoice payment period from 30 days to 60 days."
    try:
        out = _propose(client, doc_id, ins)
        assert len(out["proposed"]) == 1
        edit = out["proposed"][0]
        assert edit["target"] == "30 days" and edit["replacement"] == "60 days"
        assert edit["occurrences"] == 2

        applied = _apply(client, doc_id, out["proposed"], ins)
        data = _download(client, applied["id"])
        assert count_tracked_changes(data) == (1, 1)
        body = _all_text(data)
        # the termination/cure period's 30 days must survive untouched
        assert "cured within 30 days" in body
        assert "AED 100,000" in body
    finally:
        client.delete(f"{API}/{doc_id}")


def test_5_security_notice_hours(client, client_app, tmp_path):
    _use_mock(client_app)
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    ins = "Change the security incident notification period from 48 hours to 24 hours."
    try:
        out = _propose(client, doc_id, ins)
        assert len(out["proposed"]) == 1
        edit = out["proposed"][0]
        assert edit["target"] == "48 hours" and edit["replacement"] == "24 hours"
        applied = _apply(client, doc_id, out["proposed"], ins)
        assert count_tracked_changes(_download(client, applied["id"])) == (1, 1)
    finally:
        client.delete(f"{API}/{doc_id}")


def test_6_mutual_and_payment_produce_two_edits(client, client_app, tmp_path):
    _use_mock(client_app)
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    ins = "Make the liability cap mutual and change the payment period to 60 days."
    try:
        out = _propose(client, doc_id, ins)
        targets = {e["target"] for e in out["proposed"]}
        assert targets == {"Supplier\u2019s", "30 days"}
        applied = _apply(client, doc_id, out["proposed"], ins)
        assert count_tracked_changes(_download(client, applied["id"])) == (2, 2)
    finally:
        client.delete(f"{API}/{doc_id}")


def test_7_two_explicit_changes_target_correct_clauses(client, client_app, tmp_path):
    _use_mock(client_app)
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    ins = (
        "Change the liability cap from AED 100,000 to AED 1,000,000 and change "
        "payment terms from 30 days to 60 days."
    )
    try:
        out = _propose(client, doc_id, ins)
        pairs = {(e["target"], e["replacement"]) for e in out["proposed"]}
        assert pairs == {("AED 100,000", "AED 1,000,000"), ("30 days", "60 days")}
        applied = _apply(client, doc_id, out["proposed"], ins)
        data = _download(client, applied["id"])
        assert count_tracked_changes(data) == (2, 2)
        body = _all_text(data)
        assert "implementation fee is AED 100,000" in body  # fee AED not touched
        assert "cured within 30 days" in body  # cure period not touched
    finally:
        client.delete(f"{API}/{doc_id}")


# ── Ambiguity / already-satisfied safety ──────────────────────────────────────

def test_already_mutual_clause_is_not_fabricated(client, client_app, tmp_path):
    _use_mock(client_app)
    paras = list(FIXTURE_PARAS)
    paras[4] = paras[4].replace("Supplier\u2019s", "each party\u2019s")  # already mutual
    doc_id = _ready_docx(client, tmp_path, paras)
    try:
        out = _propose(client, doc_id, "Make the liability cap mutual.")
        assert out["proposed"] == []
        assert out["dropped"]  # honest report, no invented edit
    finally:
        client.delete(f"{API}/{doc_id}")


def _scripted(client_app: FastAPI, edits) -> None:
    class ScriptedLLM:
        def __init__(self, edits):
            self.edits = edits

        def complete_json(self, prompt):
            return {"edits": self.edits}

        def complete(self, prompt):
            return "{}"

        def stream(self, prompt):
            yield from ()

    client_app.dependency_overrides[get_llm_dep] = lambda: ScriptedLLM(edits)


def test_repeated_target_without_context_resolves_by_concept(
    client, client_app, tmp_path
):
    """A strong model may return just the bare repeated value with no anchor.

    The engine must still pin the RIGHT clause from the instruction's concept
    ("liability cap"), rather than dropping a clearly-intended edit as
    ambiguous - the failure that made plain-language redlining look broken."""
    _scripted(client_app, [
        {"target": "AED 100,000", "replacement": "AED 999", "reason": "no context"}
    ])
    ins = "Change the liability cap from AED 100,000 to AED 999."
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    try:
        out = _propose(client, doc_id, ins)
        assert len(out["proposed"]) == 1, out["dropped"]
        edit = out["proposed"][0]
        assert edit["target"] == "AED 100,000"
        assert edit["occurrences"] == 2  # repeats in the fee and liability clauses
        assert "aggregate liability" in edit["context"]  # pinned to liability

        applied = _apply(client, doc_id, out["proposed"], ins)
        data = _download(client, applied["id"])
        assert count_tracked_changes(data) == (1, 1)
        assert _del_text(data) == "AED 100,000"
        assert "AED 999" in _ins_text(data)
        # Only the fee clause still states AED 100,000 verbatim: the liability
        # occurrence was the one edited, the fee one survives untouched.
        assert _all_text(data).count("AED 100,000") == 1
    finally:
        client.delete(f"{API}/{doc_id}")


def test_repeated_target_with_no_concept_stays_ambiguous(
    client, client_app, tmp_path
):
    """Safety: when the instruction names no concept that distinguishes the two
    occurrences, the engine must NOT guess - the edit is dropped as ambiguous."""
    _scripted(client_app, [
        {"target": "AED 100,000", "replacement": "AED 999", "reason": "no context"}
    ])
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    try:
        out = _propose(client, doc_id, "Change AED 100,000 to AED 999.")
        assert out["proposed"] == []
        assert any("more than once" in d["reason"] for d in out["dropped"])
    finally:
        client.delete(f"{API}/{doc_id}")


def test_session_persists_with_context(client, client_app, tmp_path):
    _use_mock(client_app)
    doc_id = _ready_docx(client, tmp_path, FIXTURE_PARAS)
    ins = "Change the liability cap from AED 100,000 to AED 1,000,000."
    try:
        out = _propose(client, doc_id, ins)
        applied = _apply(client, doc_id, out["proposed"], ins)
        rows = client.get(f"/api/redlines?document_id={doc_id}").json()
        row = next(r for r in rows if r["id"] == applied["id"])
        assert row["instruction"] == ins
        assert row["applied"][0]["context"]  # anchor stored for safe reuse
        assert row["insertions"] == 1 and row["deletions"] == 1
    finally:
        client.delete(f"{API}/{doc_id}")
