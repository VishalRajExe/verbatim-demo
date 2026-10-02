"""Clause categories and keyword cues.

Keyword lists are seeded from the clause templates and risk terms in the
reference repositories (legal-lens clause library, rag-contract-analyzer risk
terms) and reimplemented here. A category gives materiality a hint about how
consequential a change is (e.g. liability vs. notices).
"""
from __future__ import annotations

CATEGORIES: dict[str, list[str]] = {
    "liability": [
        "liability", "liable", "damages", "indemnif", "cap", "limitation of",
        "consequential", "negligence", "hold harmless",
    ],
    "payment": [
        "payment", "pay", "invoice", "fee", "amount", "price", "cost",
        "compensation", "consideration", "interest",
    ],
    "termination": [
        "terminat", "expire", "duration", "renew", "cancellation", "term of",
        "notice period", "breach",
    ],
    "indemnity": ["indemnif", "indemn", "defend", "hold harmless"],
    "governing_law": [
        "governing law", "jurisdiction", "governed by", "laws of", "venue",
        "forum", "applicable law",
    ],
    "confidentiality": [
        "confidential", "non-disclosure", "proprietary information", "secrets",
        "disclose",
    ],
    "intellectual_property": [
        "intellectual property", "ip rights", "copyright", "patent",
        "trademark", "license", "ownership",
    ],
    "warranty": ["warrant", "guarantee", "as is", "representation"],
    "dispute_resolution": [
        "arbitrat", "mediation", "dispute", "litigation", "court",
    ],
    "force_majeure": ["force majeure", "act of god", "beyond the control"],
}

# Categories where a material token change is treated as High significance.
HIGH_RISK = {"liability", "payment", "termination", "indemnity", "governing_law"}

_MODALS = ["shall not", "must not", "may not", "shall", "must", "may", "will",
           "should", "is entitled to", "agrees to"]
_NEGATIONS = ["not", "no", "never", "without", "unless", "prohibited", "restricted"]


def classify(text: str) -> str | None:
    """Return the best-matching category for a clause, or None."""
    low = text.lower()
    best: tuple[int, str] | None = None
    for cat, kws in CATEGORIES.items():
        score = sum(1 for kw in kws if kw in low)
        if score and (best is None or score > best[0]):
            best = (score, cat)
    return best[1] if best else None
