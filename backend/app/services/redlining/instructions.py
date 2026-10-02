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

# A captured value ends at sentence punctuation, end of the instruction, or a
# comma that starts a *new* command — never at the comma inside "2,000,000"
# and never at the decimal point inside "0.5%".
_STOP = r"(?=\s*(?:[;!?]|\.(?!\d)|$|,\s+(?:and\s+)?(?:change|replace|update|revise|amend|convert)\b))"

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
      | \d[\d,\.]*\s*(?i:%|percent|days?|months?|years?|AED|USD|EUR|GBP|dirhams?|dollars?)  # 30 days / 1.0% / 100 USD
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


def parse_instruction(instruction: str) -> list[Intent]:
    """Extract (expected_original -> new_value) intents from an instruction.

    Prefers the tightest pairing available: an explicit "from X to Y" wins over
    "replace X with Y", which wins over "change X to Y" (whose from-side may
    carry clause words instead of a bare value). Multiple pairings (one per
    requested change) are all returned, in order of appearance.
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
            intents.append(
                Intent(
                    expected_original=_expected_from_fragment(raw_from),
                    new_value=_expected_from_fragment(raw_to) or raw_to or None,
                    raw=m.group(0).strip(),
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
