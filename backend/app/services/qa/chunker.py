"""Document chunking (Phase 4, Architecture §8).

Splits a document's canonical text into ~``max_chars`` chunks on paragraph
boundaries (and, for oversized paragraphs, on word boundaries). Each chunk keeps
its absolute ``[start, end)`` offset in the canonical text so verified quotes can
be attributed to the chunk they came from and de-duplicated by range. Short
documents yield a single chunk.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_WORD = re.compile(r"\S+\s*")


@dataclass(frozen=True)
class Chunk:
    text: str
    start: int
    end: int
    index: int


def chunk_text(canonical: str, max_chars: int = 96000) -> list[Chunk]:
    if not canonical:
        return []
    if max_chars < 16:
        max_chars = 16

    # Paragraph units (split on blank lines) with absolute offsets.
    units: list[tuple[int, int, str]] = []
    pos = 0
    for para in re.split(r"\n[ \t]*\n", canonical):
        lead = len(para) - len(para.lstrip())
        pstart = pos + lead
        ptext = para.strip()
        pend = pstart + len(ptext)
        if ptext:
            units.append((pstart, pend, ptext))
        pos += len(para) + 2  # account for the consumed "\n\n"-style separator

    chunks: list[Chunk] = []
    cur_parts: list[str] = []
    cur_len = 0
    cur_start: int | None = None
    cur_end: int | None = None

    def flush():
        nonlocal cur_parts, cur_len, cur_start, cur_end
        if cur_start is not None and cur_parts:
            chunks.append(
                Chunk(
                    text="\n\n".join(cur_parts),
                    start=cur_start,
                    end=cur_end,
                    index=len(chunks),
                )
            )
        cur_parts, cur_len, cur_start, cur_end = [], 0, None, None

    for ustart, uend, utext in units:
        # A single oversized paragraph: emit current, then hard-split it.
        if len(utext) > max_chars:
            flush()
            for piece, pstart, pend in _hard_split(utext, ustart, max_chars):
                chunks.append(Chunk(text=piece, start=pstart, end=pend, index=len(chunks)))
            continue

        if cur_start is None:
            cur_start = ustart
        add = len(utext) + (2 if cur_parts else 0)
        if cur_len + add > max_chars and cur_parts:
            flush()
            cur_start = ustart
            add = len(utext)
        cur_parts.append(utext)
        cur_len += add
        cur_end = uend

    flush()
    return chunks


def _hard_split(text: str, base: int, max_chars: int):
    pieces = []
    i = 0
    n = len(text)
    while i < n:
        j = min(i + max_chars, n)
        if j < n:
            # Back off to a word boundary.
            while j > i and not text[j - 1].isspace() and j < n:
                j -= 1
            if j <= i:
                j = min(i + max_chars, n)
        seg = text[i:j].strip()
        if seg:
            s = text.find(seg[0], i)
            e = s + len(seg)
            pieces.append((seg, base + s, base + e))
        i = j
    return pieces


def coverage_of(chunks: list[Chunk], canonical_len: int) -> dict:
    """Sanity: total characters covered (union) vs. canonical length."""
    covered = sum(c.end - c.start for c in chunks)
    return {
        "chunks": len(chunks),
        "coveredChars": covered,
        "canonicalChars": canonical_len,
        "complete": covered <= canonical_len,
    }
