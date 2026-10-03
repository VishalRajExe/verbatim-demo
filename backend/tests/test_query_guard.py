"""Phase 10: pre-Gemini query guard.

Covers the deterministic classifier (unit) and the wired HTTP behaviour
(integration). The integration tests use a call-counting MockClient so they can
PROVE that locally-handled inputs (empty / gibberish / greeting / off-topic /
low-information) and safe answer reuse trigger ZERO model calls, while a normal
legal question still runs the existing pipeline untouched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.qa import get_llm_dep
from app.main import app
from app.services.ai.client import MockClient
from app.services.qa import dedup
from app.services.qa.dedup import build_key
from app.services.qa.guard import (
    GIBBERISH_MESSAGE,
    OFF_TOPIC_MESSAGE,
    classify_question,
    is_usable_redline_instruction,
    question_signature,
)

DOC_API = "/api/documents"
P1 = "The Customer shall pay all outstanding amounts within 30 days of invoice date."
P2 = "The total liability cap is AED 100,000 per claim year for either party."


# ── Classifier: unit ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_is_local(text):
    g = classify_question(text)
    assert g.action == "local" and g.reason == "empty"


@pytest.mark.parametrize(
    "text",
    [
        "sjsjsjsjwiais", "#)*)*#(#(", "@@@###$$$", "123123123123",
        "zxczxczxc", "asdasdasdasd", "qwertyuiopasdf", "??????",
    ],
)
def test_gibberish_is_local(text):
    g = classify_question(text)
    assert g.action == "local" and g.reason == "gibberish", text


@pytest.mark.parametrize("text", ["hi", "hello", "hey there", "thanks", "good morning"])
def test_greeting_is_local(text):
    g = classify_question(text)
    assert g.action == "local" and g.reason == "greeting", text


@pytest.mark.parametrize(
    "text",
    [
        "what is the weather?", "Who won yesterday's cricket match?",
        "tell me a joke", "give me a recipe", "write me a Python game",
    ],
)
def test_off_topic_is_local(text):
    g = classify_question(text)
    assert g.action == "local" and g.reason == "off_topic", text


@pytest.mark.parametrize("text", ["what", "who?", "how", "why?"])
def test_low_information_is_local(text):
    g = classify_question(text)
    assert g.action == "local" and g.reason == "low_information", text


@pytest.mark.parametrize(
    "text",
    [
        "What is the cap?", "Who pays?", "30 days?", "Termination?", "Insurance?",
        "summary", "liability", "What is the liability cap?", "Who is responsible?",
        "What about termination?", "How long does the customer have to pay?",
        "What is the governing law?", "Compare the termination provisions.",
    ],
)
def test_valid_passes_through_verbatim(text):
    g = classify_question(text)
    assert g.action == "continue" and g.reason == "valid", text
    # Original text must reach the pipeline untouched (no normalisation).
    assert g.question == text


def test_repeated_within_message_collapses_once():
    g = classify_question("who is that? who is that? who is that?")
    assert g.action == "continue" and g.reason == "collapse"
    assert g.question.lower().strip() == "who is that?"


# ── Redline guard: unit ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text",
    ["", "   ", "asdfgh", "#@#$%^", "change", "edit", "fix", "make it better",
     "do something"],
)
def test_redline_rejects_unusable(text):
    assert is_usable_redline_instruction(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "Change the liability cap from AED 100,000 to AED 1,000,000.",
        "Make the liability cap mutual.",
        "Change the invoice payment period from 30 days to 60 days.",
        "Make the liability clause more balanced",  # semantic, no exact value
    ],
)
def test_redline_accepts_usable(text):
    assert is_usable_redline_instruction(text) is True


# ── Signature / cache key: unit ───────────────────────────────────────────────

def test_signature_collapses_near_duplicates():
    base = question_signature("What is the liability cap?")
    for variant in [
        "what's the liability cap",
        "Can you tell me the liability cap?",
        "tell me the liability cap",
    ]:
        assert question_signature(variant) == base, variant


def test_signature_distinguishes_different_scope():
    assert question_signature("What is the cap?") != question_signature(
        "What is the liability cap?"
    )


def test_build_key_requires_scope_and_version():
    key = build_key("What is the liability cap?", ["docA"], ["v1"])
    assert key and key == build_key(
        "tell me the liability cap", ["docA"], ["v1"]
    )  # same signature + same scope
    assert key != build_key("What is the liability cap?", ["docB"], ["v1"])
    assert key != build_key("What is the liability cap?", ["docA"], ["v2"])
    # Contentless input yields an empty key (never cached).
    assert build_key("what?", ["docA"], ["v1"]) == ""


# ── Integration: local handling makes zero model calls ────────────────────────

class _CountingMock(MockClient):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def stream(self, *args, **kwargs):
        self.calls += 1
        yield from super().stream(*args, **kwargs)

    def complete_json(self, *args, **kwargs):
        self.calls += 1
        return super().complete_json(*args, **kwargs)


def _events(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _reset_cache():
    dedup.answer_cache.clear()
    yield
    dedup.answer_cache.clear()
    app.dependency_overrides.clear()


def _upload_pdf(client, tmp_path, name, pages):
    from tests.helpers import make_text_pdf

    pdf = make_text_pdf(tmp_path / name, pages)
    r = client.post(
        f"{DOC_API}/upload", files={"file": (name, pdf.read_bytes(), "application/pdf")}
    )
    assert r.status_code == 202
    return r.json()["id"]


@pytest.mark.parametrize(
    "question,reason,message",
    [
        ("   ", "empty", None),
        ("sjsjsjsjwiais", "gibberish", GIBBERISH_MESSAGE),
        ("what is the weather?", "off_topic", OFF_TOPIC_MESSAGE),
    ],
)
def test_local_paths_call_no_model(
    client: TestClient, tmp_path: Path, question, reason, message
):
    spy = _CountingMock()
    app.dependency_overrides[get_llm_dep] = lambda: spy
    doc_id = _upload_pdf(client, tmp_path, "g.pdf", [P1, P2])
    conv_id = None
    try:
        resp = client.post(
            "/api/ask", json={"documentIds": [doc_id], "question": question}
        )
        assert resp.status_code == 200, resp.text
        events = _events(resp.text)
        assert events[0]["type"] == "meta"
        conv_id = events[0]["conversationId"]
        assert events[-1]["type"] == "done"
        assert events[-1].get("guard") == reason
        # No retrieval happened: no reading status, no quotes.
        assert not [e for e in events if e["type"] == "quotes"]
        assert not [e for e in events if e.get("stage") == "reading"]
        assert spy.calls == 0
        if message:
            token = next(e for e in events if e["type"] == "token")
            assert token["text"] == message
        # Persisted so history reload shows the same local reply.
        detail = client.get(f"/api/conversations/{conv_id}").json()
        assistant = [m for m in detail["messages"] if m["role"] == "assistant"]
        assert assistant
    finally:
        app.dependency_overrides.clear()
        if conv_id:
            client.delete(f"/api/conversations/{conv_id}")
        client.delete(f"{DOC_API}/{doc_id}")


def test_valid_runs_pipeline_and_duplicate_is_reused(
    client: TestClient, tmp_path: Path
):
    spy = _CountingMock()
    app.dependency_overrides[get_llm_dep] = lambda: spy
    doc_id = _upload_pdf(client, tmp_path, "r.pdf", [P1, P2])
    conv_id = None
    try:
        q = "What is the liability cap?"
        first = _events(
            client.post(
                "/api/ask", json={"documentIds": [doc_id], "question": q}
            ).text
        )
        conv_id = first[0]["conversationId"]
        assert first[-1]["type"] == "done"
        assert not first[-1].get("cached")
        calls_after_first = spy.calls
        assert calls_after_first > 0  # the normal pipeline used the model

        # Exact repeat -> served from cache, zero additional model calls.
        second = _events(
            client.post(
                "/api/ask", json={"documentIds": [doc_id], "question": q}
            ).text
        )
        assert second[-1].get("cached") is True
        assert spy.calls == calls_after_first

        # A near-duplicate phrasing shares the signature -> also reused.
        near = _events(
            client.post(
                "/api/ask",
                json={"documentIds": [doc_id], "question": "tell me the liability cap"},
            ).text
        )
        assert near[-1].get("cached") is True
        assert spy.calls == calls_after_first

        # A DIFFERENT document scope must NOT reuse the prior answer.
        other_doc = _upload_pdf(client, tmp_path, "r2.pdf", [P2])
        try:
            changed = _events(
                client.post(
                    "/api/ask",
                    json={"documentIds": [other_doc], "question": q},
                ).text
            )
            assert not changed[-1].get("cached")
            assert spy.calls > calls_after_first
        finally:
            client.delete(f"{DOC_API}/{other_doc}")
    finally:
        app.dependency_overrides.clear()
        if conv_id:
            client.delete(f"/api/conversations/{conv_id}")
        client.delete(f"{DOC_API}/{doc_id}")
