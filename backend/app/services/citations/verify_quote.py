"""Quote verification (Architecture §7) — the core of the product.

`verify_in_text` is a pure function so it can be tested without a database or a
model. It answers one question and nothing else: *do these exact (normalised)
words occur in this document's canonical text?* It never uses fuzzy or semantic
matching (invariant I-4) and never trusts positions reported by a model (I-2):
the only offsets produced are derived here from real matches.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.text.canonical import PageRange, page_for_offset
from app.services.text.normalize import (
    build_views,
    canonical_span,
    normalize_loose,
    normalize_str,
)

MIN_QUOTE_CHARS = 20
MAX_QUOTE_CHARS = 2000
MAX_OCCURRENCES = 50

_ELLIPSIS_MARKERS = ("\u2026", "...", "[...]")

# Failure reasons (stable strings, mirrored by the API layer).
TOO_SHORT = "TOO_SHORT"
TOO_LONG = "TOO_LONG"
NOT_FOUND = "NOT_FOUND"
WRONG_DOCUMENT = "WRONG_DOCUMENT"


@dataclass(frozen=True)
class Occurrence:
    start: int
    end: int
    page_start: int | None
    page_end: int | None


@dataclass
class VerifyResult:
    verified: bool
    normalized: str
    match_kind: str | None = None          # "exact" | "loose" | None
    fail_reason: str | None = None         # TOO_SHORT | TOO_LONG | NOT_FOUND | WRONG_DOCUMENT
    occurrences: list[Occurrence] = field(default_factory=list)
    primary: Occurrence | None = None

    def to_dict(self) -> dict:
        return {
            "verified": self.verified,
            "normalized": self.normalized,
            "matchKind": self.match_kind,
            "failReason": self.fail_reason,
            "occurrences": [
                {
                    "start": o.start,
                    "end": o.end,
                    "pageStart": o.page_start,
                    "pageEnd": o.page_end,
                }
                for o in self.occurrences
            ],
            "primary": (
                None
                if self.primary is None
                else {
                    "start": self.primary.start,
                    "end": self.primary.end,
                    "pageStart": self.primary.page_start,
                    "pageEnd": self.primary.page_end,
                }
            ),
        }


def _find_all(haystack: str, needle: str, cap: int = MAX_OCCURRENCES) -> list[int]:
    positions: list[int] = []
    start = haystack.find(needle)
    while start != -1 and len(positions) < cap:
        positions.append(start)
        start = haystack.find(needle, start + 1)
    return positions


def _split_ellipsis(q: str) -> list[str]:
    parts = [q]
    for marker in _ELLIPSIS_MARKERS:
        parts = [seg for p in parts for seg in p.split(marker)]
    return [p.strip() for p in parts if p.strip()]


def _occurrences_from_positions(
    view_positions: list[int], view, ranges: list[PageRange]
) -> list[Occurrence]:
    out: list[Occurrence] = []
    length = len(view_positions[0][1]) if view_positions else 0
    for j, _ in view_positions:
        a, b = canonical_span(view, j, j + length)
        out.append(
            Occurrence(
                start=a,
                end=b,
                page_start=page_for_offset(a, ranges),
                page_end=page_for_offset(max(b - 1, a), ranges),
            )
        )
    return out


def _pick_primary(
    occurrences: list[Occurrence], chunk_hint: tuple[int, int] | None
) -> Occurrence | None:
    if not occurrences:
        return None
    if chunk_hint:
        c0, c1 = chunk_hint
        for o in occurrences:
            if c0 <= o.start and o.end <= c1:
                return o
    return occurrences[0]


def verify_in_text(
    quote: str,
    canonical: str,
    ranges: list[PageRange],
    chunk_hint: tuple[int, int] | None = None,
) -> VerifyResult:
    """Verify a single quote against one document's canonical text."""
    q = normalize_str(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return VerifyResult(False, q, fail_reason=TOO_SHORT)
    if len(q) > MAX_QUOTE_CHARS:
        return VerifyResult(False, q, fail_reason=TOO_LONG)

    # Ellipsis: every segment must be present, in order.
    segments = _split_ellipsis(q)
    if len(segments) > 1:
        return _verify_segments(segments, canonical, ranges, q)

    keep, join, loose = build_views(canonical)

    # Exact search over the keep and join views (join catches hyphen line breaks).
    for view in (keep, join):
        positions = [(j, q) for j in _find_all(view.text, q)]
        if positions:
            occ = _occurrences_from_positions(positions, view, ranges)
            return VerifyResult(
                True, q, match_kind="exact", occurrences=occ,
                primary=_pick_primary(occ, chunk_hint),
            )

    # Loose fallback: whitespace-insensitive, still no character-level fuzz.
    ql = normalize_loose(q)
    if ql:
        positions = [(j, ql) for j in _find_all(loose.text, ql)]
        if positions:
            occ = _occurrences_from_positions(positions, loose, ranges)
            return VerifyResult(
                True, q, match_kind="loose", occurrences=occ,
                primary=_pick_primary(occ, chunk_hint),
            )

    return VerifyResult(False, q, fail_reason=NOT_FOUND)


def normalize_loose_to_keep(quote: str) -> str:
    return normalize_str(quote)


def _verify_segments(
    segments: list[str],
    canonical: str,
    ranges: list[PageRange],
    q: str,
) -> VerifyResult:
    """Every ellipsis segment must be present, in order, in one of the views."""
    keep, join, _loose = build_views(canonical)
    for view in (keep, join):
        occ = _segments_span(view, segments, ranges)
        if occ is not None:
            return VerifyResult(
                True, q, match_kind="exact", occurrences=[occ], primary=occ
            )
    return VerifyResult(False, q, fail_reason=NOT_FOUND)


def _segments_span(view, segments, ranges) -> Occurrence | None:
    """Find segments in order within a view; return the combined canonical span."""
    cursor = 0
    first_start = None
    last_end = None
    for seg in segments:
        j = view.text.find(seg, cursor)
        if j == -1:
            return None
        a, b = canonical_span(view, j, j + len(seg))
        if first_start is None:
            first_start = a
        last_end = b
        cursor = j + len(seg)
    return Occurrence(
        first_start,
        last_end,
        page_for_offset(first_start, ranges),
        page_for_offset(max(last_end - 1, first_start), ranges),
    )
