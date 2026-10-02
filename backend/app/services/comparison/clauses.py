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
_NUMBERING = re.compile(
    r"(?:(?:^|\n)\s*(?:\d+(?:\.\d+)*\.?\s+|\([a-z0-9ivx]+\)\s+|"
    r"(?:Article|Section|Clause|Exhibit|Schedule)\s+[0-9IVXA-Z]+))",
    re.IGNORECASE,
)

_LEAD_NUM = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)*)\.?|\(([a-z0-9ivx]+)\)|"
    r"(Article|Section|Clause|Exhibit|Schedule)\s+([0-9IVXA-Z]+))\b",
    re.IGNORECASE,
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
    if not m:
        return None, None
    if m.group(1):
        return m.group(1), None
    if m.group(2):
        return f"({m.group(2)})", None
    return f"{m.group(3).title()} {m.group(4)}", None


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
    for m in _NUMBERING.finditer(text):
        pos = m.start()
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
