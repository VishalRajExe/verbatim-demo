"""Verification matrix required by Rules §8. Every listed case has a test.

These exercise the pure ``verify_in_text`` engine on synthetic canonical text, so
no database or model is involved: this is the correctness core (I-1, I-2, I-4).
"""
from __future__ import annotations

import pytest

from app.services.citations.verify_quote import (
    MAX_QUOTE_CHARS,
    NOT_FOUND,
    TOO_LONG,
    TOO_SHORT,
    verify_in_text,
)
from app.services.text.canonical import PageRange, build_canonical


def _doc(pages: list[str]) -> tuple[str, list[PageRange]]:
    return build_canonical([(i + 1, t) for i, t in enumerate(pages)])


# Long enough (>= 20 normalised chars) anchors for the length-sensitive cases.
_LONG = "The landlord shall maintain the structural integrity of the premises"


def test_exact_match():
    canonical, ranges = _doc([f"{_LONG} at all times during the term."])
    r = verify_in_text(_LONG, canonical, ranges)
    assert r.verified and r.match_kind == "exact"
    assert r.primary is not None


def test_line_break_difference_matches():
    canonical, ranges = _doc(
        ["The tenant shall pay\n\tthe rent on the first day of each month, promptly."]
    )
    r = verify_in_text(
        "The tenant shall pay the rent on the first day", canonical, ranges
    )
    assert r.verified and r.match_kind == "exact"


def test_linebreak_hyphenation_matches_via_join():
    canonical, ranges = _doc(
        ["This clause concerns the termi-\nnation of the master agreement entirely."]
    )
    r = verify_in_text("the termination of the master agreement", canonical, ranges)
    assert r.verified and r.match_kind == "exact"


def test_curly_quotes_and_dashes_match_straight_input():
    canonical, ranges = _doc(
        ["The \u201cReceiving Party\u201d shall \u2014 without exception \u2014 "
         "protect the confidential information disclosed to it."]
    )
    r = verify_in_text(
        'The "Receiving Party" shall - without exception - protect', canonical, ranges
    )
    assert r.verified and r.match_kind == "exact"


def test_ligature_matches_plain_letters():
    canonical, ranges = _doc(
        ["The finance \ufb01eld of the contract governs payment obligations fully."]
    )
    r = verify_in_text("The finance field of the contract governs", canonical, ranges)
    assert r.verified and r.match_kind == "exact"


def test_nonbreaking_space_matches():
    canonical, ranges = _doc(
        ["Neither\u00a0party shall assign this agreement to a third party without consent."]
    )
    r = verify_in_text(
        "Neither party shall assign this agreement to a third party", canonical, ranges
    )
    assert r.verified and r.match_kind == "exact"


def test_quote_split_across_two_pages_returns_both_pages():
    canonical, ranges = _doc(
        [
            "The limitation of liability provision caps aggregate damages at the",
            "total fees paid by the client during the twelve month period preceding.",
        ]
    )
    r = verify_in_text(
        "caps aggregate damages at the total fees paid by the client", canonical, ranges
    )
    assert r.verified and r.match_kind == "exact"
    assert r.primary.page_start == 1 and r.primary.page_end == 2


def test_glued_words_match_via_loose():
    # Extraction glitch glued words together; a normal-spaced quote still matches.
    canonical, ranges = _doc(["theParties agree to arbitrate disputes in Geneva."])
    r = verify_in_text("the Parties agree to arbitrate disputes", canonical, ranges)
    assert r.verified and r.match_kind == "loose"


def test_repeated_text_returns_multiple_occurrences():
    sentence = "Notice must be given in writing to each affected party hereto."
    canonical, ranges = _doc([f"{sentence} And later: {sentence}"])
    r = verify_in_text(sentence, canonical, ranges)
    assert r.verified and len(r.occurrences) == 2


def test_too_short_is_rejected():
    canonical, ranges = _doc(["A very long paragraph of contract text appears here."])
    r = verify_in_text("short quote", canonical, ranges)
    assert not r.verified and r.fail_reason == TOO_SHORT


def test_too_long_is_rejected():
    canonical, ranges = _doc(["x" * (MAX_QUOTE_CHARS + 50)])
    r = verify_in_text("y" * (MAX_QUOTE_CHARS + 10), canonical, ranges)
    assert not r.verified and r.fail_reason == TOO_LONG


def test_ellipsis_segments_verified_in_order():
    canonical, ranges = _doc(
        ["The Supplier warrants the goods. Meanwhile, the Buyer shall inspect within "
         "ten days of delivery and report defects promptly in writing to the Supplier."]
    )
    r = verify_in_text(
        "The Supplier warrants the goods ... shall inspect within ten days",
        canonical, ranges,
    )
    assert r.verified and r.match_kind == "exact"


def test_paraphrase_is_not_verified():
    canonical, ranges = _doc(
        ["The licensee may use the software for internal business purposes only."]
    )
    # Same idea, different words: must FAIL (I-4, no fuzzy/semantic).
    r = verify_in_text("The licensee can utilize the program for company use.", canonical, ranges)
    assert not r.verified and r.fail_reason == NOT_FOUND


def test_text_from_another_document_is_not_found_here():
    canonical, ranges = _doc(["This document talks about indemnification and warranties."])
    # A quote that exists only in some *other* document:
    r = verify_in_text(
        "The contractor shall provide a performance bond within days", canonical, ranges
    )
    assert not r.verified and r.fail_reason == NOT_FOUND


def test_case_sensitive_conservative():
    canonical, ranges = _doc(["The AGREEMENT is governed by the laws of Switzerland."])
    r = verify_in_text("the agreement is governed by the laws", canonical, ranges)
    assert not r.verified and r.fail_reason == NOT_FOUND


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
