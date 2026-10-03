"""Structured question intent for retrieval (generic; no per-demo rules).

Two signals are parsed from the raw question:

* a *page constraint* — an explicit "on page 123", "from page 5", "in p. 87"
  reference. Without it the page number decays into an ordinary keyword/number
  and matches the "Page NN of 150" marker and look-alike amounts on *every*
  page (the retrieval-pollution bug this module fixes). When present, retrieval
  is constrained to those pages' canonical spans.

* *focus terms* — the substantive words the question is really about
  ("reference", "value", "insurance"). These drive a relevance floor so that
  verified-but-irrelevant evidence is never handed to composition. Questions
  that only use structural words ("what is the section on page 87 about?")
  yield an empty set, meaning "matching the page is relevance enough".

Both are derived purely from the question text — nothing about a specific
document, page number, or token is hardcoded.
"""
from __future__ import annotations

import re

# "page 123", "pages 12", "p.123", "pg 5", "pp 7", optionally a range
# ("pages 37-38", "page 10 to 12"). The number must be a standalone token.
_PAGE_REF = re.compile(
    r"(?<![A-Za-z0-9])(?:pages?|pgs?|p|pp)\.?\s*(\d{1,4})"
    r"(?:\s*(?:-|\u2013|to|through)\s*(\d{1,4}))?(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Guard against runaway ranges from malformed input.
_MAX_RANGE = 25

# Structural / question words that never, on their own, make evidence
# "relevant". Deliberately excludes real legal concepts (value, liability,
# insurance, notice, term ...) so those still drive the relevance floor.
_META_WORDS = frozenset(
    {
        "page", "pages", "section", "sections", "clause", "clauses",
        "about", "regarding", "concerning", "relate", "relates", "related",
        "refer", "refers", "referring", "reference", "references",
        "mention", "mentions", "mentioned", "describe", "describes",
        "described", "say", "says", "said", "state", "states", "stated",
        "tell", "tells", "mean", "means", "indicate", "indicates",
        "indicated", "specify", "specifies", "specified", "provide",
        "provides", "provided", "contain", "contains", "contained",
        "include", "includes", "included", "find", "show", "shows",
        "shown", "give", "gives", "want", "need", "question", "answer",
        "following", "document", "documents", "contract", "contracts",
        "text", "there", "here", "what", "when", "where", "which", "who",
        "why", "how", "does", "did", "would", "could", "should",
    }
)

# Common function words that carry no topical signal.
_STOPWORDS = frozenset(
    {
        "this", "that", "with", "from", "under", "have", "has", "had",
        "will", "shall", "were", "into", "over", "them", "they", "their",
        "your", "been", "being", "must", "may", "also", "any", "all",
        "each", "other", "than", "then", "only", "just", "such",
    }
)

_WORD = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*")


def parse_page_constraints(question: str) -> set[int]:
    """Return the explicit page numbers referenced in the question (possibly
    empty). Ranges ("pages 37-38", "page 10 to 12") expand to their members."""
    pages: set[int] = set()
    for m in _PAGE_REF.finditer(question or ""):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        if end < start:
            start, end = end, start
        end = min(end, start + _MAX_RANGE - 1)
        pages.update(range(start, end + 1))
    return pages


def specific_keywords(question: str) -> set[str]:
    """Substantive topical terms in the question, excluding structural words,
    stopwords, page numbers, and short tokens. Hyphen-compounds contribute
    their alphabetic parts ("incident-report" -> incident, report)."""
    out: set[str] = set()
    for word in _WORD.findall((question or "").lower()):
        for part in re.split(r"[-_]", word):
            if len(part) >= 4 and part.isalpha() and part not in _META_WORDS and part not in _STOPWORDS:
                out.add(part)
    return out


def focus_hits(text: str, focus_terms: set[str]) -> int:
    """Count distinct focus terms present in ``text``.

    Prefix-tolerant (a crude stem that drops up to the last three characters,
    keeping at least four): "termination" matches "terminate", "requests"
    matches "request", "liability" matches "liabilities". Morphological
    variants of the asked-about concept count as relevance; unrelated
    vocabulary does not. The four-character floor keeps stems long enough to
    stay specific while bridging common English suffixes.
    """
    lo = (text or "").lower()
    hits = 0
    for term in focus_terms:
        stem = term[: max(4, len(term) - 3)]
        if stem in lo:
            hits += 1
    return hits
