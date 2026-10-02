"""Tests for canonical-text normalisation and offset maps (Architecture §6)."""
from __future__ import annotations

import pytest

from app.services.text.normalize import (
    build_views,
    canonical_span,
    normalize_loose,
    normalize_str,
)


def test_curly_quotes_and_dashes_fold_to_ascii():
    s = "The \u201cParty\u201d shall \u2014 not \u2014 pay A\u2013B"
    n = normalize_str(s)
    assert "\u201c" not in n and "\u201d" not in n and "\u2014" not in n
    assert '"Party"' in n  # curly double quotes folded to straight ASCII
    assert " - " in n
    assert "A-B" in n


def test_ligature_expands_to_two_letters():
    n = normalize_str("fi\u2019nance \ufb01eld")
    assert "field" in n  # \ufb01 -> "fi"


def test_whitespace_runs_collapse_and_trim():
    n = normalize_str("   hello \n\t  world\u00a0again   ")
    assert n == "hello world again"


def test_soft_hyphen_and_zero_width_removed():
    n = normalize_str("exe\u00adcute\u200b here")
    assert n == "execute here"


def test_join_view_undoes_linebreak_hyphenation():
    canonical = "the termi-\nnation of this agreement is defined"
    keep, join, _loose = build_views(canonical)
    assert "termi- nation" in keep.text
    assert "termination" in join.text


def test_real_hyphen_between_lowercase_is_preserved_in_join():
    # "brother-in-law" has no space after the hyphen, so join must not touch it.
    canonical = "the brother-in-law clause applies here"
    _keep, join, _loose = build_views(canonical)
    assert "brother-in-law" in join.text


def test_loose_view_removes_all_whitespace():
    _keep, _join, loose = build_views("the Part y splits")
    assert " " not in loose.text


def test_offset_map_round_trips_letters():
    """A match's canonical span, renormalised, equals the matched view text."""
    canonical = "The \u201cTenant\u201d shall   pay rent, in full\n\t each month."
    keep, _join, _loose = build_views(canonical)
    needle = "shall pay rent"  # normalised form of "shall   pay rent"
    j = keep.text.find(needle)
    assert j != -1
    a, b = canonical_span(keep, j, j + len(needle))
    assert normalize_str(canonical[a:b]) == needle


def test_empty_input_is_safe():
    keep, join, loose = build_views("   ")
    assert keep.text == "" and join.text == "" and loose.text == ""
    assert len(keep.map) == 1 + 0 + 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
