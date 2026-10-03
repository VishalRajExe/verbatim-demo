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
        # Interrogative degree framing: "how long" asks for a duration but
        # "long" itself names no topic, and counting it as one inflates the
        # number of substantive parts in a question.
        "long", "much", "many",
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
        # Three-letter function words - dropped alongside the rest so lowering
        # the length floor below cannot admit grammar instead of topics.
        "and", "but", "not", "for", "the", "has", "one", "can", "way",
        "too", "own", "two", "three", "five",
    }
)

_WORD = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*")

# Question words that ask for a QUANTITY. A verified quote containing an actual
# number answers such a term even when the wording differs ("percentage" is
# answered by "1.0% per month"). This bridge keeps numeric legal search working
# when the document phrases the number without the question's noun. It is
# deliberately limited to unambiguous "how much?" nouns: adding a word that can
# also be a common noun/verb ("cap", "limit") would make EVERY figure-bearing
# clause match it, letting an unrelated numeric line masquerade as evidence.
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
    their alphabetic parts ("incident-report" -> incident, report).

    The length floor is 3, not 4: real legal topics are short ("cap", "fee",
    "law"), and dropping them breaks compound questions - a quote that matches
    every long term except the short one used to fail the two-term relevance
    floor and never reach composition (the question's own "capped at AED
    100,000" clause was silently discarded because "cap" was too short to
    count). Matching is word-boundary anchored, so short terms cannot leak as
    substrings; generic three-letter function words are filtered as stopwords.
    """
    out: set[str] = set()
    for word in _WORD.findall((question or "").lower()):
        for part in re.split(r"[-_]", word):
            if len(part) >= 3 and part.isalpha() and part not in _META_WORDS and part not in _STOPWORDS:
                out.add(part)
    return out


def term_stem(term: str) -> str:
    """Crude stem used to bridge English inflection: drops up to the last three
    characters but never fewer than four, so stems stay specific ("termination"
    -> "terminat", "governs" -> "govern", "late" -> "late").

    Terms of five characters or fewer are kept WHOLE: truncating "analysis" to
    "anal" or "compare" to "compa" would invent a second, spurious topic that
    matches nothing in the evidence. A short term still reaches its inflections
    through the word-boundary anchor in ``matches_word`` ("cap" matches
    "capped" and "caps", whole-prefix, without matching "capability").
    """
    if len(term) <= 5:
        return term
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


# Separators between sub-questions inside one prompt. "that" is excluded so
# relative clauses ("the document that has one") do not count as a new part.
_SUBQ_SPLIT = re.compile(r"[.?;]|\band\b|\bor\b|how|what|which|who|where|when")


def subquestion_groups(question: str) -> list[set[str]]:
    """Focus terms partitioned by the sub-question they belong to.

    A compound question ("what is the cap AND how long is payment?") asks
    several things; evidence for one part legitimately mentions only THAT
    part's terms. Judging every quote against the union of all terms punishes
    precisely the partial evidence a complete answer must combine. Grouping
    lets the relevance floor require coverage of each asked part, per quote,
    without demanding that one quote answer everything.
    """
    parts = [p for p in _SUBQ_SPLIT.split((question or "").lower()) if p.strip()]
    groups = [g for g in (specific_keywords(p) for p in parts) if g]
    if groups:
        return groups
    whole = specific_keywords(question)
    return [whole] if whole else []


def relevant_to_group(text: str, terms: set[str]) -> bool:
    """Whether ``text`` speaks to ONE sub-question's terms.

    Two ways to qualify: match two of the terms (the strict floor), or match
    the group's single MOST SPECIFIC term - the longest, which is the least
    incidental ("liability", not "cap"). A clause that answers the part in the
    document's own words ("aggregate liability ... will not exceed AED 100,000")
    names the part's distinctive noun even when it never uses the question's
    short synonym, so it must not be discarded for want of a second word - yet
    boilerplate that only echoes a common verb ("applicable" for "applies") does
    not touch the distinctive noun and stays excluded.
    """
    if not terms:
        return False
    if focus_hits(text, terms) >= min(2, len(terms)):
        return True
    primary = max(terms, key=lambda w: (len(w), w))
    return matches_term(text, primary)


def relevant_to_groups(text: str, groups: list[set[str]]) -> bool:
    """Whether ``text`` speaks to at least one sub-question (see
    ``relevant_to_group``)."""
    return any(relevant_to_group(text, g) for g in groups)


def subquestion_page_parts(question: str) -> list[tuple[set[str], set[int]]]:
    """Each sub-question paired with the page numbers IT references.

    A page number constrains only the part that asked for it. In "the token on
    page 4, and the liability cap in the other document" the page reference
    belongs to the token part; the liability part names no page, so its
    evidence must never be discarded by a global page filter. Returning terms
    and pages per part lets the pipeline scope page filtering to the part a
    quote actually answers. Derived entirely from the question text.
    """
    parts = [p for p in _SUBQ_SPLIT.split((question or "").lower()) if p.strip()]
    result: list[tuple[set[str], set[int]]] = []
    for p in parts:
        terms = specific_keywords(p)
        pages = parse_page_constraints(p)
        if terms or pages:
            result.append((terms, pages))
    if result:
        return result
    whole = specific_keywords(question)
    pages = parse_page_constraints(question)
    return [(whole, pages)] if (whole or pages) else []

