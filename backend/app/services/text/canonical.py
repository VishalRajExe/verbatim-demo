"""Canonical text assembly (Architecture §5d).

A document's canonical text is its per-page texts joined with a blank line. We
reconstruct it from stored pages on demand (and cache it) so verification and
locating always agree on offsets, with no extra column to keep in sync.
"""
from __future__ import annotations

from dataclasses import dataclass

PAGE_SEP = "\n\n"


@dataclass(frozen=True)
class PageRange:
    page_number: int  # 1-based
    start: int        # inclusive offset into canonical text
    end: int          # exclusive offset into canonical text


def build_canonical(pages: list[tuple[int, str]]) -> tuple[str, list[PageRange]]:
    """Join ``(page_number, text)`` pairs into canonical text + offset ranges.

    Blank pages are skipped (they would only add noise and break offsets), and
    each kept page records where its text begins and ends in the canonical
    string.
    """
    parts: list[str] = []
    ranges: list[PageRange] = []
    cursor = 0
    for page_number, text in pages:
        stripped = text.strip()
        if not stripped:
            continue
        if parts:
            cursor += len(PAGE_SEP)
        start = cursor
        end = start + len(stripped)
        ranges.append(PageRange(page_number=page_number, start=start, end=end))
        parts.append(stripped)
        cursor = end
    return PAGE_SEP.join(parts), ranges


def page_for_offset(offset: int, ranges: list[PageRange]) -> int | None:
    """Return the 1-based page number containing a canonical offset."""
    if not ranges:
        return None
    for r in ranges:
        if r.start <= offset < r.end:
            return r.page_number
    # Offsets landing in a page separator belong to the preceding page.
    for i in range(1, len(ranges)):
        if ranges[i - 1].end <= offset < ranges[i].start:
            return ranges[i - 1].page_number
    return ranges[-1].page_number if offset >= ranges[-1].end else ranges[0].page_number
