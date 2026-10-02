"""Comparison engine tests (Rules §8 fixture requirements)."""
from __future__ import annotations

import pytest

from app.services.comparison.clauses import split_clauses
from app.services.comparison.materiality import floor_significance
from app.services.comparison.pipeline import comparison_result

# Clause numbers are kept identical across versions so a reordering is detected
# as MOVED (same content) rather than an Added + Removed pair.
A_TEXT = """1. Definitions. Goods means the products listed in Schedule A of this agreement.

2. Payment Terms. The Client shall pay AED 100,000 within 30 days of invoice date.

3. Term. The agreement shall remain in effect for a period of two years from the date hereof.

4. Arbitration. Any dispute shall be resolved by arbitration seated in Dubai.

5. Governing Law. This agreement is governed by the laws of England and Wales."""

B_TEXT = """5. Governing Law. This agreement is governed by the laws of England and Wales.

1. Definitions. Goods means the products listed in Schedule A of this agreement.

2. Payment Terms. The Client shall pay AED 1,000,000 within 30 days of invoice date.

3. Term. The agreement shall continue in force for a period of two years from the effective date.

6. Confidentiality. The parties shall keep all pricing information strictly confidential."""


def _by_type(result: dict, t: str):
    return [c for c in result["changes"] if c["type"] == t]


def test_split_clauses_counts_and_offsets():
    clauses = split_clauses(A_TEXT)
    assert len(clauses) == 5
    first = clauses[0]
    assert first.number == "1"
    assert A_TEXT[first.start : first.end] == first.text


def test_amount_change_is_high():
    m = floor_significance(
        "The Client shall pay AED 100,000 within 30 days of invoice.",
        "The Client shall pay AED 1,000,000 within 30 days of invoice.",
    )
    assert m.significance == "HIGH"
    assert any("100,000" in t and "1,000,000" in t for t in m.changed_tokens)


def test_rewording_without_token_change_is_low():
    m = floor_significance(
        "The notice shall be delivered by mail to the registered address of the party.",
        "The notice shall be sent by post to the registered mailing address of the party.",
    )
    assert m.significance == "LOW"
    assert m.changed_tokens == []


def test_case_and_punctuation_only_is_cosmetic():
    m = floor_significance(
        "The Agreement is Binding, on the Parties hereto!",
        "the agreement is binding on the parties hereto",
    )
    assert m.significance == "COSMETIC"


def test_comparison_fixture_pair_types():
    result = comparison_result(A_TEXT, B_TEXT)
    types = {c["type"] for c in result["changes"]}
    assert {"MOVED", "MODIFIED", "ADDED", "REMOVED"} <= types

    moved = _by_type(result, "MOVED")
    assert any("Governing" in (c["title"] or "") or "governed" in (c["aText"] or "")
               for c in moved)

    # The 100k -> 1m payment change is a HIGH modification.
    modified_high = [
        c for c in _by_type(result, "MODIFIED") if c["significance"] == "HIGH"
    ]
    assert modified_high
    assert any("1,000,000" in c["summary"] or "100,000" in c["summary"]
               for c in modified_high)

    # Term clause is a pure rewording (Low), not High/Cosmetic.
    term_mods = _by_type(result, "MODIFIED")
    assert any(c["significance"] == "LOW" for c in term_mods)

    assert any("Confidentiality" in (c["bText"] or "") for c in _by_type(result, "ADDED"))
    assert any("Arbitration" in (c["aText"] or "") for c in _by_type(result, "REMOVED"))

    # Same content must never surface as both an add and a remove.
    assert not any(
        "Governing Law" in (c["aText"] or "") and c["type"] == "REMOVED"
        for c in result["changes"]
    )


def test_stats_and_summary_present():
    result = comparison_result(A_TEXT, B_TEXT)
    assert result["stats"]["total"] == len(result["changes"])
    assert result["summary"]
    assert result["summarySource"] == "automatic"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
