"""Text similarity: character bigram Dice coefficient.

Used only for clause *alignment* (deciding which clause in B best matches a
clause in A). It is deliberately never used in the verification path (I-4).
"""
from __future__ import annotations


def _bigrams(s: str) -> set[tuple[str, str]]:
    return {(s[i], s[i + 1]) for i in range(len(s) - 1)}


def dice(a: str, b: str) -> float:
    """Dice coefficient over character bigrams of two (normalised) strings."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    ba, bb = _bigrams(a), _bigrams(b)
    total = len(ba) + len(bb)
    if total == 0:
        # Both single-character (or empty): equal only if identical.
        return 1.0 if a == b else 0.0
    inter = len(ba & bb)
    return (2 * inter) / total
