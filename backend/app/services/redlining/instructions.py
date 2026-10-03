"""Deterministic parsing of plain-English redline instructions.

Safety rule the whole redline feature hangs on: if the user says
"change X to Y", the document must *actually contain X* before anything is
proposed. That precondition is checked here with pure string logic — no LLM
judgement, no guessing, no silent substitution of a different value (e.g. an
instruction "from AED 500,000" must never end up editing "AED 100,000").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# A captured value ends at sentence punctuation, end of the instruction, or the
# start of a *new* command — never at the comma inside "2,000,000" and never at
# the decimal point inside "0.5%". A new command can be introduced by a comma,
# by a bare coordinating conjunction ("... to 72 hours and change 15 days to 30
# days"), or by both (", and change"); the conjunction must be followed by a
# change verb so an ordinary "and" inside a value ("laws of England and Wales")
# can never split an intent.
_STOP = (
    r"(?=\s*(?:[;!?]|\.(?!\d)|$|"
    r"(?:,\s*(?:and\s+)?|\b(?:and|then|also)\s+)(?:change|replace|update|revise|amend|convert)\b))"
)

# An explicit "from <old> to <new>" or "replace <old> with <new>" pairing.
_FROM_TO = re.compile(
    r"\bfrom\s+(?P<from>.+?)\s+to\s+(?P<to>.+?)" + _STOP, re.IGNORECASE
)
_REPLACE_WITH = re.compile(
    r"\breplace\s+(?:the\s+)?(?P<from>.+?)\s+with\s+(?P<to>.+?)" + _STOP,
    re.IGNORECASE,
)
_CHANGE_TO = re.compile(
    r"\b(?:change|convert|update|revise|amend)\s+(?:the\s+)?(?P<from>.+?)\s+to\s+(?P<to>.+?)" + _STOP,
    re.IGNORECASE,
)

# Currency / numeric / percentage tokens used for value-level checks, e.g.
# "AED 500,000", "$250,000", "75%", "30 days", "100 USD", "12".
# Currency *codes* are case-sensitive and word-initial only (\b), so lowercase
# word tails like "thin 30" can never masquerade as a code; unit words are
# matched case-insensitively via the inline (?i:…) group.
_VALUE_TOKEN = re.compile(
    r"""(?x)
    (?:
        \b[A-Z]{2,4}\s*\$?\s*\d[\d,\.]*\s*(?:million|billion|thousand)?   # AED 500,000
      | \$\s*\d[\d,\.]*\s*(?:million|billion|thousand)?                   # $250,000
      | \d[\d,\.]*\s*(?i:%|percent|hours?|minutes?|weeks?|days?|months?|years?|quarters?|AED|USD|EUR|GBP|dirhams?|dollars?)  # 30 days / 48 hours / 1.0% / 100 USD
      | \b\d[\d,]*(?:\.\d+)?\b                                            # bare number
    )
"""
)

_QUOTES = re.compile(r'^[\'"“”‘’]+|[\'"“”‘’]+$')
# Trailing sentence punctuation to trim from captured fragments — but never a
# decimal point that is part of the value itself ("0.5%", "1.0%").
_TRAILING = re.compile(r"(?<![0-9])[.,;:!?]+\s*$|^\s*[.,;:!?]+")


@dataclass
class Intent:
    """One requested change parsed from the instruction, best-effort."""

    expected_original: str | None  # the value/text the doc must already contain
    new_value: str | None          # the value/text to write instead
    raw: str                       # the instruction fragment it came from
    concept: str = ""              # clause descriptor when there is no literal original


def normalize_value(text: str) -> str:
    """Casefold, collapse whitespace, and drop thousands separators in numbers
    so "AED 500,000" matches "aed  500000"."""
    t = text.casefold().strip()
    t = _QUOTES.sub("", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)  # 500,000 -> 500000
    return t


def value_in_text(value: str, text: str) -> bool:
    """Normalized containment of ``value`` anywhere in ``text``."""
    v = normalize_value(value)
    if not v:
        return False
    return v in normalize_value(text)


# Leading imperative / article words stripped from a clause descriptor so
# "Change the liability cap" reduces to the concept "liability cap".
_CONCEPT_LEAD = re.compile(
    r"^(?:\s*(?:change|convert|update|revise|amend|set|modify|increase|decrease|"
    r"make|the|to|of)\b)+",
    re.IGNORECASE,
)


def _clean_concept(text: str) -> str:
    return _CONCEPT_LEAD.sub("", (text or "").strip()).strip(" .,;:").strip()


def _has_value(fragment: str) -> bool:
    return bool(extract_value_tokens(fragment))


def parse_instruction(instruction: str) -> list[Intent]:
    """Extract (expected_original -> new_value) intents from an instruction.

    Prefers the tightest pairing available: an explicit "from X to Y" wins over
    "replace X with Y", which wins over "change X to Y". A "change <concept> to
    <value>" whose from-side is a clause descriptor rather than a literal value
    ("change the payment period to 60 days") carries no expected_original: the
    clause is located by its concept and the value already there is replaced.
    Multiple pairings (one per requested change) are all returned, in order.
    """
    intents: list[Intent] = []
    consumed: list[tuple[int, int]] = []

    for pattern in (_FROM_TO, _REPLACE_WITH, _CHANGE_TO):
        for m in pattern.finditer(instruction):
            span = m.span()
            if any(span[0] < e and span[1] > s for s, e in consumed):
                continue  # an earlier, tighter pattern already covered this
            consumed.append(span)
            raw_from = _TRAILING.sub("", m.group("from").strip()).strip(" \t'\"“”‘’")
            raw_to = _TRAILING.sub("", m.group("to").strip()).strip(" \t'\"“”‘’")
            new_value = _expected_from_fragment(raw_to) or raw_to or None
            if pattern is _CHANGE_TO and not _has_value(raw_from):
                expected = None
                concept = _clean_concept(raw_from)
            else:
                expected = _expected_from_fragment(raw_from)
                if pattern is _FROM_TO:
                    # The descriptor is the clause noun right before "from", i.e.
                    # the text after the LAST change verb: "... change payment
                    # terms from 30 days ..." -> "payment terms". Giving each
                    # change its own concept lets a multi-change instruction
                    # disambiguate its repeated values independently.
                    lead = re.split(
                        r"\b(?:change|convert|update|revise|amend|replace|set|modify)\b",
                        instruction[: span[0]],
                        flags=re.IGNORECASE,
                    )[-1]
                    concept = _clean_concept(lead)
                else:
                    concept = ""
            intents.append(
                Intent(
                    expected_original=expected,
                    new_value=new_value,
                    raw=m.group(0).strip(),
                    concept=concept,
                )
            )
    return intents


def _expected_from_fragment(fragment: str) -> str | None:
    """Reduce a captured fragment to the value the document must contain.

    "the liability cap from AED 500,000" -> "AED 500,000" when a currency token
    is present; otherwise the whole cleaned fragment ("governing law of England").
    """
    tokens = extract_value_tokens(fragment)
    if tokens:
        return tokens[0]
    fragment = fragment.strip()
    return fragment or None


def extract_value_tokens(text: str) -> list[str]:
    """All currency/number/percent tokens in ``text``, in order, de-duplicated."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _VALUE_TOKEN.finditer(text):
        tok = m.group(0).strip().rstrip(".")  # don't swallow the sentence period
        key = normalize_value(tok)
        if key and key not in seen:
            seen.add(key)
            out.append(tok)
    return out


def find_similar_value(text: str, value: str, exclude: set[str]) -> str | None:
    """Best-effort: a token in ``text`` of the same shape as ``value`` but not in
    ``exclude`` — used to say *"the document contains X instead"* honestly.

    "Same shape" means the same unit: a leading currency code (AED/USD/$) or the
    same trailing unit word/percent sign (days, %, years). Without that, the
    hint could latch onto an unrelated number anywhere in the document.
    """
    wanted = normalize_value(value)
    lead = re.match(r"^([a-z]{2,4}|\$)", wanted)
    trail = re.search(r"([a-z%]{1,7})$", wanted)
    for tok in extract_value_tokens(text):
        norm = normalize_value(tok)
        if norm in exclude or norm == wanted:
            continue
        if lead and not norm.startswith(lead.group(1)):
            continue
        if not lead and trail:
            unit = trail.group(1)
            if unit == "%":
                if not norm.endswith("%"):
                    continue
            elif not re.search(re.escape(unit) + r"s?$", norm):
                continue
        return tok
    return None


# ── Semantic (natural-language) edit operations ───────────────────────────────
# Not every instruction names a literal "from X to Y". Some describe a desired
# STATE the clause should end up in ("make the liability cap mutual"), with no
# original text quoted at all. Those are handled here as a small, principled set
# of *generic drafting operations*: each is defined by the state word that
# triggers it and a transformation applied to whatever the located clause
# actually says. Nothing about a specific clause, party name, currency or
# document is baked in — the same rule broadens a one-sided liability cap in any
# contract to whichever party that contract happens to name.

_STATE_OPERATIONS = {
    "mutual": "make_mutual",
    "mutually": "make_mutual",
    "reciprocal": "make_mutual",
    "reciprocally": "make_mutual",
}

# Words that already make a provision apply to both sides; a clause carrying one
# of these governing the obligation is *already* mutual and must be left alone
# (report honestly rather than fabricate an edit).
_MUTUAL_MARKERS = ("each party", "both parties", "either party", "the parties")

# A one-sided obligation owned by a single capitalised party noun, e.g.
# "Supplier's aggregate liability" (possessive) or "the Supplier shall" (subject
# + modal). "party"/"parties" are never owners — that phrasing is already
# bilateral. Imperative verbs stripped from the instruction to recover the
# concept the user is pointing at.
_UNILATERAL_POSSESSIVE = re.compile(r"\b([A-Z][A-Za-z]{2,})['\u2019]s\b")
_UNILATERAL_SUBJECT = re.compile(
    r"\b(?:the\s+)?([A-Z][A-Za-z]{2,})\s+(?:shall|may|will|must|agrees|undertakes)\b"
)
_COMMAND_VERBS = re.compile(
    r"\b(?:make|change|revise|amend|update|convert|replace|set|modify|ensure|all|to)\b",
    re.IGNORECASE,
)


@dataclass
class SemanticIntent:
    """A state-change instruction with no literal from/to (e.g. \u201cmutual\u201d)."""

    operation: str  # "make_mutual"
    concept: str    # the noun phrase being pointed at, e.g. "liability cap"
    raw: str


def parse_semantic_instruction(instruction: str) -> list[SemanticIntent]:
    """Detect state-word instructions (\u201cmake X mutual\u201d) that carry no explicit
    original value. Returns [] for ordinary from/to instructions so the two
    paths never overlap."""
    if not instruction:
        return []
    low = instruction.lower()
    operation = None
    for word, op in _STATE_OPERATIONS.items():
        if re.search(r"\b" + word + r"\b", low):
            operation = op
            break
    if not operation:
        return []
    # Scope the concept to the clause the state word applies to. In the common
    # "make <clause> <state>" ordering the descriptor sits *before* the state
    # word, so cutting at the state word keeps a compound instruction ("make the
    # liability cap mutual and change the payment period to 60 days") pointed at
    # the liability clause rather than drifting onto the payment clause.
    m = re.search(
        r"\b(" + "|".join(_STATE_OPERATIONS) + r")\b", instruction, re.IGNORECASE
    )
    before = instruction[: m.start()] if m else instruction
    concept = _COMMAND_VERBS.sub(" ", before)
    concept = re.sub(r"\s+", " ", concept).strip(" .,;:")
    concept = _clean_concept(concept)
    return [SemanticIntent(operation=operation, concept=concept, raw=instruction.strip())]


def make_mutual_edit(clause: str) -> tuple[str, str] | None:
    """Return ``(target, replacement)`` that broadens a one-sided clause to both
    parties, or ``None`` when the clause is already mutual or names no single
    owner. The target is the exact unilateral reference found in the clause, so
    it is always a verbatim substring of the authoritative text."""
    if not clause:
        return None
    low = clause.lower()
    pos = _UNILATERAL_POSSESSIVE.search(clause)
    if pos and pos.group(1).lower() not in ("party", "parties"):
        # Already mutual? A mutual marker governing the same obligation means
        # there is nothing honest to change.
        if any(marker in low for marker in _MUTUAL_MARKERS):
            return None
        return pos.group(0), "each party\u2019s"
    subj = _UNILATERAL_SUBJECT.search(clause)
    if subj and subj.group(1).lower() not in ("party", "parties"):
        if any(marker in low for marker in _MUTUAL_MARKERS):
            return None
        # Rebuild the matched "[the] Owner modal" span with a bilateral subject.
        matched = subj.group(0)
        rebuilt = re.sub(r"^(?:the\s+)?[A-Z][A-Za-z]{2,}", "each party", matched, count=1)
        return matched, rebuilt
    return None
