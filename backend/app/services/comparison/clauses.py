"""Clause segmentation (Architecture §10 step 1).

Splits a document's canonical text into clause/paragraph units using common
legal numbering ("1.", "1.1", "(a)", "Article 3", "Section 2") and blank-line
structure. Each unit keeps its ``[start, end)`` offset in the source text so the
comparison UI can jump straight to it in both documents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.text.normalize import normalize_str

# A clause "starts" at a blank line, or at a line whose leading token looks like
# a legal numbering marker.
#
# A bare number is only a marker when it is punctuated like one ("8.", "4.2)",
# "4:") or when the words after it read as a heading (capitalised: "8 PURPOSE").
# Without that shape test every line that happens to BEGIN with a quantity — a
# wrapped sentence such as "90 days after delivery, ...", or a table cell such
# as "60 days" — becomes a phantom clause, and a comparison then reports those
# fragments as clauses ADDED or REMOVED in documents whose text merely re-wrapped.
#
# The numeric branch is deliberately CASE-SENSITIVE: the heading test is an
# upper-vs-lowercase distinction, so a global IGNORECASE flag would cancel it.
# Word markers ("Article 3") stay case-insensitive in their own pattern.
_NUMBERING_NUMERIC = re.compile(
    r"(?:^|\n)\s*(?:\d+(?:\.\d+)*(?:[.:)\]]\s+|\s+(?=[A-Z]))|"
    r"\([A-Za-z0-9]+\)\s+)"
)
# "Article 3", "Schedule 2", "Exhibit B": the keyword is case-insensitive, but the
# label after it must look like a label (a number or an upper-case / Roman token),
# not an ordinary word. Otherwise a wrapped line such as "schedule adjustments."
# is mistaken for an exhibit heading and becomes a phantom clause.
_WORD_MARKER = re.compile(
    r"(?:^|\n)[ \t]*([A-Za-z]+)[ \t]+([^ \t\n]+)"
)
_MARKER_WORDS = frozenset(
    {"article", "section", "clause", "exhibit", "schedule", "annex", "appendix", "part"}
)


def _is_marker_label(label: str) -> bool:
    """Does the token after "Article/Schedule/…" read as a label?

    A number ("3", "3.1") or a visually distinct label ("A", "III", "2A") does.
    Trailing sentence punctuation is not part of the label.
    """
    core = label.strip(".,:;)]")
    if not core:
        return False
    return core[0].isdigit() or (core[0].isalpha() and core.isupper())


def _word_marker_positions(text: str) -> list[int]:
    return [
        m.start()
        for m in _WORD_MARKER.finditer(text)
        if m.group(1).lower() in _MARKER_WORDS and _is_marker_label(m.group(2))
    ]

_LEAD_NUM = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)*)[.:)\]]|(\d+(?:\.\d+)*)\s+(?=[A-Z])|\(([A-Za-z0-9]+)\))"
)
_LEAD_WORD = re.compile(
    r"^\s*([A-Za-z]+)[ \t]+([^ \t\n]+)"
)


@dataclass(frozen=True)
class Clause:
    number: str | None
    heading: str | None
    text: str
    start: int
    end: int

    @property
    def key(self) -> str:
        """Aggressive normalisation used to detect identical / cosmetic clauses."""
        return aggressive_normalize(self.text)


def aggressive_normalize(s: str) -> str:
    """Lowercase, drop punctuation and numbering, collapse whitespace."""
    base = normalize_str(s).lower()
    base = re.sub(r"[^a-z0-9\s]", " ", base)
    # Remove leading numbering fragments left as stray tokens.
    base = re.sub(r"\s+", " ", base).strip()
    return base


def _lead_number(text: str) -> tuple[str | None, str | None]:
    m = _LEAD_NUM.match(text)
    if m:
        if m.group(1) or m.group(2):
            return m.group(1) or m.group(2), None
        return f"({m.group(3)})", None
    w = _LEAD_WORD.match(text)
    if w and w.group(1).lower() in _MARKER_WORDS and _is_marker_label(w.group(2)):
        return f"{w.group(1).title()} {w.group(2)}", None
    return None, None


def split_clauses(text: str) -> list[Clause]:
    """Split ``text`` into ordered clause units with source offsets."""
    if not text.strip():
        return []

    boundaries = [0]
    # Break on blank lines.
    for m in re.finditer(r"\n\s*\n", text):
        pos = m.end()
        if pos < len(text):
            boundaries.append(pos)
    # Break on numbering markers.
    starts = [m.start() for m in _NUMBERING_NUMERIC.finditer(text)]
    starts += _word_marker_positions(text)
    for pos in starts:
        # Advance past a leading newline/spaces to the marker's first character
        # (the digit or word), so the number stays attached to its clause body.
        while pos < len(text) and text[pos] in " \t\n":
            pos += 1
        boundaries.append(pos)

    boundaries = sorted(set(b for b in boundaries if 0 <= b <= len(text)))

    blocks: list[tuple[int, int]] = []
    for i, b in enumerate(boundaries):
        e = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        if e > b:
            blocks.append((b, e))

    clauses: list[Clause] = []
    for start, end in blocks:
        raw = text[start:end]
        stripped = raw.strip()
        if not stripped:
            continue
        # Offsets for the trimmed body.
        lead_ws = len(raw) - len(raw.lstrip())
        a = start + lead_ws
        b = a + len(stripped)
        number, heading = _lead_number(stripped)
        clauses.append(
            Clause(number=number, heading=heading, text=stripped, start=a, end=b)
        )
    return clauses
