"""Regression: repeated values are only editable when the model supplies context.

Bug #4 (live Gemini): a value like "30 days" appears in both the payment clause
and the termination clause. The disambiguation machinery (propose.py keeps an
ambiguous edit only when a verbatim unique ``context`` pins one occurrence) was
dead in production because ``propose_prompt`` never asked the model for a
``context`` field — the real LLM therefore never supplied one, and every
repeated-value edit was dropped as "ambiguous". The offline MockClient
self-supplied context, which is why the existing suite stayed green.

These tests pin both halves of the fix:
  1. the prompt must demand a verbatim ``context`` and show it in the JSON
     schema (so model output carries the field);
  2. an edit whose context uniquely pins one occurrence must be proposed and
     applied to the RIGHT clause. When the model omits the anchor, the engine
     falls back to locating the clause from the instruction's own concept, so a
     distinguishable repeated value still resolves; only a genuinely
     unanchorable target (no concept tells the clauses apart) is dropped as
     ambiguous rather than guessed.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.api.qa import get_llm_dep
from app.services.redlining.tracked_changes import count_tracked_changes
from tests.helpers import make_docx

API = "/api/documents"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

PAY_P = "Customer will pay undisputed invoices within 30 days of receipt."
TERM_P = "Either party may terminate for material breach if the breach is not " \
         "cured within 30 days after written notice."
INSTRUCTION = "Change the payment term from 30 days to 60 days."


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
    """Returns canned edits — exactly what a real LLM would emit for the prompt."""

    def __init__(self, edits: list[dict]):
        self.edits = edits

    def complete_json(self, prompt: str):
        return {"edits": self.edits}

    def complete(self, prompt: str) -> str:  # pragma: no cover
        return "{}"

    def stream(self, prompt: str):  # pragma: no cover
        yield from ()


@pytest.fixture()
def client_app(client):
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


def _del_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        from lxml import etree

        root = etree.fromstring(z.read("word/document.xml"))
        return "".join(t.text or "" for t in root.iter(f"{{{W}}}delText"))


def _para_texts(data: bytes) -> list[str]:
    """Full text of each paragraph, including content inside tracked edits."""
    from lxml import etree

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.iter(f"{{{W}}}p"):
        parts = []
        for node in p.iter():
            if node.tag in (f"{{{W}}}t", f"{{{W}}}delText"):
                parts.append(node.text or "")
        out.append("".join(parts))
    return out


# ── 1. The prompt itself must require the context field ──────────────────────

def test_propose_prompt_requires_verbatim_context():
    from app.services.redlining.prompts import propose_prompt

    prompt = propose_prompt("c.docx", INSTRUCTION, "some document data")
    lowered = prompt.lower()
    assert "'context' must also be copied exactly" in lowered, (
        "the model must be told to return a verbatim context passage"
    )
    assert '"context"' in prompt, "context must appear in the JSON schema the model copies"


# ── 2a. Without context, a distinguishable target resolves by its concept ─────

def test_repeated_target_without_context_resolves_by_concept(
    client, client_app, tmp_path
):
    """The model returns only the bare repeated value ("30 days"), no anchor.

    The engine must still pin the payment clause from the instruction's concept
    ("invoice payment period") rather than drop a clearly-intended edit."""
    doc_id = _ready_docx(client, tmp_path, [PAY_P, TERM_P])
    try:
        _override(client_app, ScriptedLLM([
            {"target": "30 days", "replacement": "60 days", "reason": "terms"},
        ]))
        ins = "Change the invoice payment period from 30 days to 60 days."
        out = _propose(client, doc_id, ins)
        assert len(out["proposed"]) == 1, out["dropped"]
        edit = out["proposed"][0]
        assert edit["target"] == "30 days"
        assert edit["occurrences"] == 2
        assert "undisputed invoices" in edit["context"]  # pinned to the payment clause

        applied = client.post(
            f"{API}/{doc_id}/redline",
            json={
                "edits": [{
                    "target": edit["target"],
                    "replacement": edit["replacement"],
                    "context": edit["context"],
                }],
                "author": "QCoder",
                "instruction": ins,
            },
        )
        assert applied.status_code == 201, applied.text
        data = client.get(f"/api/redlines/{applied.json()['id']}/download").content
        assert count_tracked_changes(data) == (1, 1)
        paras = _para_texts(data)
        payment = next(t for t in paras if "undisputed invoices" in t)
        termination = next(t for t in paras if "terminate for material breach" in t)
        assert "60 days" in payment
        assert "30 days" in termination, "the cure period must survive untouched"
    finally:
        client.delete(f"{API}/{doc_id}")


def test_repeated_target_with_no_concept_is_dropped(client, client_app, tmp_path):
    """Safety: with no concept to tell the two clauses apart, the engine must
    not guess - the ambiguous edit is still dropped."""
    doc_id = _ready_docx(client, tmp_path, [PAY_P, TERM_P])
    try:
        _override(client_app, ScriptedLLM([
            {"target": "30 days", "replacement": "60 days", "reason": "terms"},
        ]))
        out = _propose(client, doc_id, "Change 30 days to 60 days.")
        assert out["proposed"] == []
        assert any("more than once" in d["reason"] for d in out["dropped"])
    finally:
        client.delete(f"{API}/{doc_id}")


# ── 2b. With unique context the edit is proposed and lands on the right clause ─

def test_repeated_target_with_context_resolves_to_correct_clause(
    client, client_app, tmp_path
):
    doc_id = _ready_docx(client, tmp_path, [PAY_P, TERM_P])
    try:
        _override(client_app, ScriptedLLM([
            {
                "target": "30 days",
                "replacement": "60 days",
                "reason": "payment terms",
                "context": PAY_P,  # the whole sentence the target sits in
            },
        ]))
        out = _propose(client, doc_id, INSTRUCTION)
        assert len(out["proposed"]) == 1, out["dropped"]
        edit = out["proposed"][0]
        assert edit["target"] == "30 days"
        assert edit["occurrences"] == 2  # repeats globally...
        assert edit["context"] == PAY_P  # ...but the anchor uniquely pins it

        applied = client.post(
            f"{API}/{doc_id}/redline",
            json={
                "edits": [{
                    "target": edit["target"],
                    "replacement": edit["replacement"],
                    "context": edit["context"],
                }],
                "author": "QCoder",
                "instruction": INSTRUCTION,
            },
        )
        assert applied.status_code == 201, applied.text
        data = client.get(f"/api/redlines/{applied.json()['id']}/download").content
        assert count_tracked_changes(data) == (1, 1)
        # only the target itself is wrapped in w:del; "30 days" repeats, so the
        # del count proves exactly ONE occurrence was touched — and it must be
        # the payment sentence's (checked via paragraph text below).
        assert _del_text(data) == "30 days"
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            assert z.read("word/document.xml").count(b"<w:del ") == 1
        paras = _para_texts(data)
        payment = next(t for t in paras if "undisputed invoices" in t)
        assert "AED" not in payment  # sanity: picked the right paragraph
        termination = next(t for t in paras if "terminate for material breach" in t)
        assert "60 days" in payment
        assert "30 days" in termination, "the cure period must survive untouched"
    finally:
        client.delete(f"{API}/{doc_id}")


def test_llm_failure_returns_clean_message_not_raw_blob(client, client_app, tmp_path):
    """A provider error (e.g. Gemini 429 quota) must surface as a short, safe
    message — never the raw provider payload dumped into the UI."""
    from app.services.ai.retry import LLMError

    class ExplodingLLM:
        def complete_json(self, prompt):
            raise LLMError(
                status=429,
                message="429 RESOURCE_EXHAUSTED. {'error': {'message': "
                "'You exceeded your current quota'}}",
            )

        def complete(self, prompt):  # pragma: no cover
            return "{}"

        def stream(self, prompt):  # pragma: no cover
            yield from ()

    client_app.dependency_overrides[get_llm_dep] = lambda: ExplodingLLM()
    doc_id = _ready_docx(client, tmp_path, [PAY_P, TERM_P])
    try:
        resp = client.post(
            f"{API}/{doc_id}/redline/propose",
            json={"instruction": INSTRUCTION},
        )
        assert resp.status_code == 503, resp.text
        detail = resp.json()["detail"]
        assert "RESOURCE_EXHAUSTED" not in detail  # no internal leak
        assert "{" not in detail
        assert "quota" in detail.lower() or "rate-limit" in detail.lower()
    finally:
        client.delete(f"{API}/{doc_id}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
