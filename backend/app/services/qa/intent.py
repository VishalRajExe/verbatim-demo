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
        # Comparative / analytical framing. Asking to "compare" or to show the
        # "evidence" for something says HOW to answer, not WHAT to look for; the
        # topic is the remaining noun ("liability"). Left in the set they dilute
        # the relevance floor until a clause mentioning only its real topic
        # ("limitation of liability") scores below the required two terms and
        # every comparison question quietly becomes a not-found.
        "compare", "compares", "compared", "comparison",
        "comparisons", "comparative", "versus", "differ", "differs",
        "differed", "differing", "difference", "differences", "different",
        "differently", "similar", "similarly", "similarity", "unlike",
        "evidence", "evidences", "evidenced", "analysis", "analyses",
        "analyse", "analysed", "analyze", "analyzed", "support", "supports",
        "supported", "supporting", "basis", "respective", "respectively",
    }
)

# Common function words that carry no topical signal.
_STOPWORDS = frozenset(
    {
        "this", "that", "with", "from", "under", "have", "has", "had",
        "will", "shall", "were", "into", "over", "them", "they", "their",
        "your", "been", "being", "must", "may", "also", "any", "all",
        "each", "other", "than", "then", "only", "just", "such",
        "these", "those", "both", "across", "among", "between",
    }
)

_WORD = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*")

# Question words that ask for a QUANTITY. A verified quote containing an actual
# number answers such a term even when the wording differs ("percentage" is
# answered by "1.0% per month"). This bridge keeps numeric legal search working
# when the document phrases the number without the question's noun.
_QUANTITY_TERMS = frozenset(
    {
        "percentage", "percent", "proportion", "ratio", "amount", "total",
        "number", "value", "figure", "cost", "price", "rate", "quantity",
        "duration", "period",
    }
)

_HAS_DIGIT = re.compile(r"\d")


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


def term_stem(term: str) -> str:
    """Crude stem used to bridge English inflection: drops up to the last three
    characters but never fewer than four, so stems stay specific ("termination"
    -> "terminat", "governs" -> "govern", "late" -> "late")."""
    return term[: max(4, len(term) - 3)]


def matches_word(text: str, term: str) -> bool:
    """True if ``text`` contains an inflection of ``term`` ("governs" matches
    "governed", "requests" matches "request").

    The stem is anchored at a WORD BOUNDARY: a raw substring test would let
    "late" match "violate" and "appl" match "applicable", which ranks unrelated
    boilerplate above the passage that actually answers the question.
    """
    lo = (text or "").lower()
    return bool(re.search(r"\b" + re.escape(term_stem(term)), lo))


def matches_term(text: str, term: str) -> bool:
    """Relevance test used by the evidence floor: an inflection of the term, OR
    — for a quantity word like "percentage"/"amount" — any quote carrying a
    real number, because documents state quantities in figures rather than
    repeating the question's noun. No value is ever hardcoded.
    """
    lo = (text or "").lower()
    if matches_word(lo, term):
        return True
    return term in _QUANTITY_TERMS and bool(_HAS_DIGIT.search(lo))


def focus_hits(text: str, focus_terms: set[str]) -> int:
    """Count distinct focus terms present in ``text`` (see ``matches_term``).

    This is the single relevance rule shared by extraction and by the
    verified-evidence floor, so the two stages can never disagree about what
    counts as "speaking to the question".
    """
    lo = (text or "").lower()
    return sum(1 for term in focus_terms if matches_term(lo, term))
