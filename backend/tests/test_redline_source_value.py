"""Redline source-value safety (§15 matrix) and session persistence.

The rule under test: an instruction "change X to Y" may only ever produce edits
whose verified target contains X. If X is not in the document, the system must
say so and propose nothing — it must never silently convert a *different* value
that happens to sit in the same clause. All deterministic checks run without
any LLM (a hostile/mock model is only used to prove targets are re-verified).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from app.api.qa import get_llm_dep
from tests.helpers import make_docx

API = "/api/documents"

CAP_P = "The total liability cap is AED 100,000 per claim year for either party."
PAY_P = "The Customer shall pay each undisputed invoice within 30 days."
LAW_P = "This Agreement is governed by the laws of England and Wales."
DUP_P = "Fee is due. Fee is due. Fee is due again here now."

VALID_INSTRUCTION = "Change the liability cap from AED 100,000 to AED 1,000,000."
INVALID_INSTRUCTION = "Change the liability cap from AED 500,000 to AED 2,000,000."
MULTIPLE_INSTRUCTION = (
    "Change the liability cap from AED 100,000 to AED 1,000,000, "
    "change the payment term from 30 days to 45 days, and "
    "replace the laws of England and Wales with the laws of France."
)


def _ready_docx(client, tmp_path: Path, paragraphs: list[str], name: str = "c.docx") -> str:
    docx = make_docx(tmp_path / name, paragraphs)
    resp = client.post(
        API + "/upload",
        files={"file": (name, docx.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    assert client.get(f"{API}/{doc_id}").json()["status"] == "ready"
    return doc_id


class ScriptedLLM:
    """Returns canned edits; records whether the model was consulted at all."""

    def __init__(self, edits: list[dict]):
        self.edits = edits
        self.called = 0

    def complete_json(self, prompt: str):
        self.called += 1
        return {"edits": self.edits}

    def complete(self, prompt: str) -> str:  # pragma: no cover
        return "{}"

    def stream(self, prompt: str):  # pragma: no cover
        yield from ()


@pytest.fixture()
def client_app(client):
    # The session client wraps the FastAPI app; expose it for dependency overrides.
    yield client.app
    client.app.dependency_overrides.clear()


def _override(app: FastAPI, llm) -> None:
    app.dependency_overrides[get_llm_dep] = lambda: llm


def _propose(client, doc_id: str, instruction: str) -> dict:
    resp = client.post(
        f"{API}/{doc_id}/redline/propose", json={"instruction": instruction}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Parser (pure, deterministic) ──────────────────────────────────────────────

def test_parser_reads_from_to_with_thousands_separators():
    from app.services.redlining.instructions import parse_instruction

    intents = parse_instruction(INVALID_INSTRUCTION)
    assert len(intents) == 1
    assert intents[0].expected_original == "AED 500,000"
    assert intents[0].new_value == "AED 2,000,000"


def test_parser_reads_multiple_changes():
    from app.services.redlining.instructions import parse_instruction

    intents = parse_instruction(MULTIPLE_INSTRUCTION)
    pairs = {(i.expected_original, i.new_value) for i in intents}
    assert ("AED 100,000", "AED 1,000,000") in pairs
    assert ("30 days", "45 days") in pairs
    assert any(i.expected_original and "England" in i.expected_original for i in intents)


def test_parser_splits_commands_joined_by_and_without_a_comma():
    # Bug #11: a compound instruction like "change A to B and change C to D"
    # (no comma before the conjunction) used to parse as ONE intent: the value
    # capture only stopped at a comma+verb, so the second edit was swallowed
    # and silently never proposed.
    from app.services.redlining.instructions import parse_instruction

    intents = parse_instruction(
        "Change 45 days to 60 days and change 15 days to 30 days."
    )
    pairs = {(i.expected_original, i.new_value) for i in intents}
    assert pairs == {("45 days", "60 days"), ("15 days", "30 days")}

    # An ordinary "and" inside a value must never split an intent.
    intents = parse_instruction(
        "replace the laws of England and Wales with the laws of France"
    )
    assert len(intents) == 1
    assert intents[0].expected_original == "laws of England and Wales"


def test_parser_keeps_decimal_values_intact():
    from app.services.redlining.instructions import parse_instruction

    intents = parse_instruction(
        "Change the late payment interest from 1.0% to 0.5%."
    )
    assert len(intents) == 1
    assert intents[0].expected_original == "1.0%"
    assert intents[0].new_value == "0.5%"


def test_similar_value_hint_respects_the_unit():
    from app.services.redlining.instructions import find_similar_value

    text = (
        "Customer will pay invoices within 30 days. The fee is AED 100,000. "
        "Curing 1 example, notice 15 days. Interest accrues at 1.0% per month."
    )
    assert find_similar_value(text, "90 days", exclude=set()) == "30 days"
    assert find_similar_value(text, "AED 500,000", exclude=set()) == "AED 100,000"
    assert find_similar_value(text, "5%", exclude=set()) == "1.0%"
    assert find_similar_value(text, "90 years", exclude=set()) is None


def test_normalize_matches_comma_variants():
    from app.services.redlining.instructions import normalize_value, value_in_text

    assert normalize_value("AED 500,000") == normalize_value("aed 500000")
    assert value_in_text("AED 100,000", "cap is aed  100000 per year")


# ── §15 case 1: VALID — original value present ───────────────────────────────

def test_valid_instruction_yields_one_verified_edit(client, client_app, tmp_path):
    doc_id = _ready_docx(client, tmp_path, [CAP_P, PAY_P, LAW_P])
    try:
        _override(client_app, ScriptedLLM([
            {"target": "AED 100,000", "replacement": "AED 1,000,000", "reason": "cap raise"},
        ]))
        out = _propose(client, doc_id, VALID_INSTRUCTION)
        assert len(out["proposed"]) == 1
        assert out["proposed"][0]["target"] == "AED 100,000"
        assert out["proposed"][0]["replacement"] == "AED 1,000,000"
        assert out["dropped"] == []
    finally:
        client.delete(f"{API}/{doc_id}")


# ── §15 case 2: INVALID — named original value absent -> honest refusal ──────

def test_invalid_source_value_refuses_without_llm(client, client_app, tmp_path):
    doc_id = _ready_docx(client, tmp_path, [CAP_P, PAY_P, LAW_P])
    try:
        llm = ScriptedLLM([
            {"target": "AED 100,000", "replacement": "AED 2,000,000", "reason": "wrong!"},
        ])
        _override(client_app, llm)
        out = _propose(client, doc_id, INVALID_INSTRUCTION)
        assert out["proposed"] == [], "must NOT silently edit a different value"
        assert len(out["dropped"]) == 1
        reason = out["dropped"][0]["reason"]
        assert "AED 500,000" in reason and "not found" in reason
        assert "AED 100,000" in reason, "should honestly show the actual value"
        assert llm.called == 0, "deterministic precondition must reject before the model"
    finally:
        client.delete(f"{API}/{doc_id}")


# ── §15 case 3: MULTIPLE — three independently verified edits ────────────────

def test_multiple_changes_verified_independently(client, client_app, tmp_path):
    doc_id = _ready_docx(client, tmp_path, [CAP_P, PAY_P, LAW_P])
    try:
        _override(client_app, ScriptedLLM([
            {"target": "AED 100,000", "replacement": "AED 1,000,000", "reason": "cap"},
            {"target": "30 days", "replacement": "45 days", "reason": "terms"},
            {"target": "laws of England and Wales", "replacement": "laws of France", "reason": "law"},
        ]))
        out = _propose(client, doc_id, MULTIPLE_INSTRUCTION)
        assert len(out["proposed"]) == 3
        targets = {e["target"] for e in out["proposed"]}
        assert targets == {"AED 100,000", "30 days", "laws of England and Wales"}
        assert out["dropped"] == []
    finally:
        client.delete(f"{API}/{doc_id}")


def test_two_changes_joined_by_and_are_both_proposed(client, client_app, tmp_path):
    # Bug #11 end-to-end: two changes joined by "and" (no comma) in one
    # instruction must each produce their own verified proposal.
    doc_id = _ready_docx(client, tmp_path, [CAP_P, PAY_P, LAW_P])
    try:
        _override(client_app, ScriptedLLM([
            {"target": "AED 100,000", "replacement": "AED 1,000,000", "reason": "cap"},
            {"target": "30 days", "replacement": "45 days", "reason": "terms"},
        ]))
        out = _propose(
            client, doc_id,
            "Change the liability cap from AED 100,000 to AED 1,000,000 "
            "and change the payment term from 30 days to 45 days.",
        )
        targets = {e["target"] for e in out["proposed"]}
        assert targets == {"AED 100,000", "30 days"}
        assert out["dropped"] == []
    finally:
        client.delete(f"{API}/{doc_id}")


# ── Hostile / sloppy model output is re-verified, never trusted ──────────────

def test_model_target_not_in_document_is_dropped(client, client_app, tmp_path):
    doc_id = _ready_docx(client, tmp_path, [CAP_P, PAY_P, LAW_P])
    try:
        _override(client_app, ScriptedLLM([
            {"target": "AED 100,000 USD", "replacement": "AED 1,000,000", "reason": "invented"},
        ]))
        out = _propose(client, doc_id, VALID_INSTRUCTION)
        assert out["proposed"] == []
        assert any("not found verbatim" in d["reason"] for d in out["dropped"])
    finally:
        client.delete(f"{API}/{doc_id}")


def test_model_edit_touching_other_value_is_dropped(client, client_app, tmp_path):
    # Instruction names AED 100,000 (present), but the model targets "30 days".
    doc_id = _ready_docx(client, tmp_path, [CAP_P, PAY_P, LAW_P])
    try:
        _override(client_app, ScriptedLLM([
            {"target": "30 days", "replacement": "AED 1,000,000", "reason": "misleading"},
        ]))
        out = _propose(client, doc_id, VALID_INSTRUCTION)
        assert out["proposed"] == []
        assert any("does not contain the original value" in d["reason"] for d in out["dropped"])
    finally:
        client.delete(f"{API}/{doc_id}")


def test_ambiguous_duplicate_target_is_dropped(client, client_app, tmp_path):
    doc_id = _ready_docx(client, tmp_path, [DUP_P])
    try:
        _override(client_app, ScriptedLLM([
            {"target": "Fee is due.", "replacement": "Amount is payable.", "reason": "x"},
        ]))
        out = _propose(client, doc_id, "Change the phrase Fee is due. wording.")
        assert out["proposed"] == []
        assert any("more than once" in d["reason"] for d in out["dropped"])
    finally:
        client.delete(f"{API}/{doc_id}")


# ── §16: sessions persist and are listable / downloadable ────────────────────

def test_redline_session_persists_instruction_and_downloads(client, client_app, tmp_path):
    doc_id = _ready_docx(client, tmp_path, [CAP_P, PAY_P, LAW_P])
    try:
        _override(client_app, ScriptedLLM([
            {"target": "AED 100,000", "replacement": "AED 1,000,000", "reason": "cap"},
        ]))
        proposal = _propose(client, doc_id, VALID_INSTRUCTION)
        edits = [{"target": e["target"], "replacement": e["replacement"]} for e in proposal["proposed"]]
        resp = client.post(
            f"{API}/{doc_id}/redline",
            json={"edits": edits, "author": "QCoder", "instruction": VALID_INSTRUCTION},
        )
        assert resp.status_code == 201, resp.text
        row = resp.json()
        assert row["instruction"] == VALID_INSTRUCTION
        assert row["insertions"] == 1 and row["deletions"] == 1

        listed = client.get(f"/api/redlines?document_id={doc_id}").json()
        assert any(r["id"] == row["id"] for r in listed)

        dl = client.get(f"/api/redlines/{row['id']}/download")
        assert dl.status_code == 200
        assert dl.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument"
        )
    finally:
        client.delete(f"{API}/{doc_id}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
