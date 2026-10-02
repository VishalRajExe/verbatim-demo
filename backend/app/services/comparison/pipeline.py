"""Comparison orchestration (Architecture §10 steps 1–6, automatic-only).

This is the deterministic backbone: split both documents into clauses, align,
classify, and compute materiality floors + an automatic summary. The optional AI
pass (Phase 7 task 4) may only raise significance above the floor and enrich
summaries; it is layered on top in the API service and degrades to these
"automatic" summaries when unavailable.
"""
from __future__ import annotations

from collections import Counter

from app.services.comparison.align import Change, align
from app.services.comparison.clauses import split_clauses

_SIGNIFICANCE_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "COSMETIC": 0}


def compare_texts(a_text: str, b_text: str) -> list[Change]:
    return align(split_clauses(a_text), split_clauses(b_text))


def _counts(changes: list[Change]) -> dict:
    by_type = Counter(c.type for c in changes)
    by_sig = Counter(c.significance for c in changes)
    return {
        "total": len(changes),
        "byType": dict(by_type),
        "bySignificance": dict(by_sig),
    }


def overall_summary(changes: list[Change]) -> str:
    """Plain-language summary derived from the deterministic changes."""
    if not changes:
        return "No meaningful differences were detected between the two documents."
    ranked = sorted(
        changes, key=lambda c: _SIGNIFICANCE_RANK.get(c.significance, 0), reverse=True
    )
    high = [c for c in changes if c.significance == "HIGH"]
    parts = [f"{len(changes)} change(s) detected"]
    if high:
        parts.append(f"{len(high)} high-significance")
    top = "; ".join(f"{c.title}: {c.summary}" for c in ranked[:3])
    return ". ".join(parts) + f". Most notable \u2014 {top}."


def comparison_result(a_text: str, b_text: str) -> dict:
    changes = compare_texts(a_text, b_text)
    return {
        "changes": [_change_dict(i, c) for i, c in enumerate(changes)],
        "stats": _counts(changes),
        "summary": overall_summary(changes),
        "summarySource": "automatic",
    }


def _change_dict(order: int, c: Change) -> dict:
    return {
        "orderIdx": order,
        "type": c.type,
        "significance": c.significance,
        "category": c.category,
        "title": c.title,
        "summary": c.summary,
        "summarySource": "automatic",
        "aText": c.a_text,
        "bText": c.b_text,
        "aStart": c.a_start,
        "aEnd": c.a_end,
        "bStart": c.b_start,
        "bEnd": c.b_end,
    }
