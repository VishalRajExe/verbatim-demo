"""Phase 3-llm unit tests: tolerant JSON, retry policy, streaming cite filter,
chunking, and coverage. Pure logic, no DB or network."""
from __future__ import annotations

import pytest

from app.services.ai.json_parse import parse_json_lenient
from app.services.ai.retry import LLMError, is_retryable, retry_call
from app.services.qa.chunker import chunk_text, coverage_of
from app.services.qa.cite_filter import CitationFilter
from app.services.qa.coverage import DocumentCoverage, caveat, not_found_message


# ── json_parse ────────────────────────────────────────────────────────────────

def test_parse_plain_json():
    assert parse_json_lenient('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    raw = "Here you go:\n```json\n{\"quotes\": [{\"text\": \"hi\"}]}\n```\nDone."
    assert parse_json_lenient(raw) == {"quotes": [{"text": "hi"}]}


def test_parse_balanced_with_leading_prose():
    raw = 'Sure! The answer is {"ok": true, "nested": {"x": [1, 2]}} trust me.'
    assert parse_json_lenient(raw) == {"ok": True, "nested": {"x": [1, 2]}}


def test_parse_returns_none_on_garbage():
    assert parse_json_lenient("not json at all") is None
    assert parse_json_lenient("") is None
    assert parse_json_lenient(None) is None


def test_parse_handles_braces_inside_strings():
    raw = '{"text": "a { weird } phrase", "n": 2}'
    assert parse_json_lenient(raw) == {"text": "a { weird } phrase", "n": 2}


# ── retry ─────────────────────────────────────────────────────────────────────

def test_retry_succeeds_first_try():
    assert retry_call(lambda: 42) == 42


def test_retry_backs_off_then_succeeds():
    calls = {"n": 0}
    slept = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise LLMError(status=429, message="rate")
        return "ok"

    out = retry_call(flaky, sleep=slept.append, rng=lambda: 0.0)
    assert out == "ok"
    assert calls["n"] == 3
    assert len(slept) == 2  # two failures before success


def test_retry_honours_retry_after():
    slept = []
    state = {"n": 0}

    def fn():
        state["n"] += 1
        if state["n"] == 1:
            raise LLMError(status=503, message="unavail", retry_after=7.5)
        return 1

    retry_call(fn, sleep=slept.append, rng=lambda: 0.0)
    assert slept == [7.5]


def test_retry_does_not_retry_non_retryable_status():
    state = {"n": 0}

    def fn():
        state["n"] += 1
        raise LLMError(status=400, message="bad request")

    with pytest.raises(LLMError):
        retry_call(fn, sleep=lambda _d: None)
    assert state["n"] == 1


def test_is_retryable_classification():
    assert is_retryable(ConnectionError()) is True
    assert is_retryable(LLMError(status=None)) is True
    assert is_retryable(LLMError(status=400)) is False


# ── cite_filter ───────────────────────────────────────────────────────────────

def test_cite_filter_keeps_verified_drops_unverified():
    cf = CitationFilter({1, 2})
    out = cf.feed("See [Q1] and [Q3] here. ") + cf.flush()
    assert out == "See [Q1] and  here. "


def test_cite_filter_marker_split_across_tokens():
    cf = CitationFilter({1})
    emitted = ""
    for tok in ["Answer: ", "[", "Q", "1", "]", " done"]:
        emitted += cf.feed(tok)
    emitted += cf.flush()
    assert emitted == "Answer: [Q1] done"


def test_cite_filter_holds_partial_then_resolves_unverified():
    cf = CitationFilter({5})
    # A dangling "[Q9" that never completes as verified should not leak as a cite.
    part = cf.feed("text [Q9")
    # "[Q9" may be held (could still become [Q90]); flush resolves it. Because 9
    # is unverified, the completed marker is dropped and literal text returns.
    tail = cf.feed("] end") + cf.flush()
    joined = part + tail
    assert "[Q9]" not in joined
    assert "end" in joined


def test_cite_filter_literal_bracket_passes_through():
    cf = CitationFilter({1})
    out = cf.feed("note [bracket] here") + cf.flush()
    assert out == "note [bracket] here"


# ── chunker ───────────────────────────────────────────────────────────────────

def test_chunker_short_doc_single_chunk():
    text = "One paragraph only."
    chunks = chunk_text(text, max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].start == text.index("One")
    assert chunks[0].end == len(text)


def test_chunker_respects_budget_and_absolute_offsets():
    para = "The quick brown fox jumps over the lazy dog. " * 10
    canonical = para + "\n\n" + para
    chunks = chunk_text(canonical, max_chars=200)
    assert len(chunks) >= 2
    for c in chunks:
        # chunk.text must be the exact slice of canonical at its offsets
        assert canonical[c.start : c.end].replace("\n\n", " ").startswith(c.text.split()[0])
        assert c.end <= len(canonical)
    cov = coverage_of(chunks, len(canonical))
    assert cov["chunks"] == len(chunks)
    assert cov["coveredChars"] <= cov["canonicalChars"]


def test_chunker_oversized_paragraph_hard_splits_on_words():
    words = "alpha beta gamma delta " * 100
    chunks = chunk_text(words.strip(), max_chars=100)
    assert all(len(c.text) <= 100 for c in chunks)
    assert "".join(c.text for c in chunks).replace(" ", "") == words.replace(" ", "").replace("\n", "")


def test_chunker_empty_returns_none():
    assert chunk_text("") == []


# ── coverage ──────────────────────────────────────────────────────────────────

def _cov(total, read, failed=None):
    return DocumentCoverage(
        document_id="d1", name="Doc.pdf",
        chunks_total=total, chunks_read=read, failed_chunks=failed or [], pages=10,
    )


def test_not_found_confident_when_full_coverage():
    msg = not_found_message([_cov(3, 3)])
    assert "does not appear to be addressed" in msg


def test_not_found_hedges_when_partial():
    msg = not_found_message([_cov(4, 2, failed=[2])])
    assert "Absence is not confirmed" in msg


def test_caveat_none_when_complete():
    assert caveat([_cov(2, 2)]) is None


def test_caveat_warns_when_partial():
    assert caveat([_cov(3, 2, failed=[2])])
