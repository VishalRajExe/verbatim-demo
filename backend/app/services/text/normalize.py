"""Canonical-text normalisation with offset maps (Architecture §6).

Verification never touches the raw extracted bytes; it works on *views* of the
canonical text. A view is a normalised string plus a ``map`` where ``map[i]`` is
the offset, in the original canonical text, of the source code point that
produced ``view.text[i]``. A final sentinel entry marks the end.

Every normalisation step is applied identically to a view and to a candidate
quote, so a substring search in a view is a *normalised exact* match. No fuzzy
matching happens here (invariant I-4).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# Characters removed outright: soft hyphen and zero-width code points.
_DROP = {0x00AD, 0x200B, 0x200C, 0x200D, 0xFEFF}

# Code-point level replacements applied after NFKC, mapping to ASCII.
_REPLACE = {
    0x2018: "'",   # left single quote
    0x2019: "'",   # right single quote
    0x201A: "'",
    0x201B: "'",
    0x201C: '"',   # left double quote
    0x201D: '"',   # right double quote
    0x201E: '"',
    0x201F: '"',
    0x2013: "-",   # en dash
    0x2014: "-",   # em dash
    0x2010: "-",   # hyphen
    0x2011: "-",   # non-breaking hyphen
    0x2212: "-",   # minus sign
    0x00A0: " ",   # non-breaking space -> plain space (also a whitespace run)
}


def _is_ws(ch: str) -> bool:
    return ch.isspace()


@dataclass(frozen=True)
class View:
    """A normalised string plus its offset map back into the canonical text.

    ``map`` has exactly ``len(text) + 1`` entries; ``map[i]`` is the canonical
    offset of ``text[i]`` and ``map[-1]`` is the end sentinel.
    """

    text: str
    map: list[int]


def canonical_span(view: View, start: int, end: int) -> tuple[int, int]:
    """Convert a ``[start, end)`` match in ``view.text`` to canonical offsets."""
    return view.map[start], view.map[end]


def _normalize_char(ch: str) -> str:
    """Apply NFKC + code-point replacements to a single source character."""
    cp = ord(ch)
    if cp in _DROP:
        return ""
    nfkc = unicodedata.normalize("NFKC", ch)
    out = []
    for c in nfkc:
        r = ord(c)
        out.append(_REPLACE.get(r, c))
    return "".join(out)


def _keep_view(canonical: str) -> View:
    """Build the *keep* view: normalise, collapse whitespace runs, trim.

    Each produced output character records the canonical index of the single
    source code point that generated it (NFKC expansions such as ligatures map
    every produced character back to the same source index).
    """
    chars: list[str] = []
    srcs: list[int] = []
    pending_ws = False
    for idx, ch in enumerate(canonical):
        norm = _normalize_char(ch)
        if norm == "":
            continue
        if norm.isspace():
            # A run of whitespace collapses to one space anchored at its first
            # source code point; skip the rest of the run.
            if not pending_ws and chars:  # leading whitespace is trimmed away
                chars.append(" ")
                srcs.append(idx)
                pending_ws = True
            continue
        pending_ws = False
        chars.append(norm)
        srcs.append(idx)

    # Trim trailing whitespace (leading was already avoided: a space is only
    # emitted once a non-whitespace character has already been kept).
    while chars and chars[-1] == " ":
        chars.pop()
        srcs.pop()

    text = "".join(chars)
    if srcs:
        offset_map = srcs + [srcs[-1] + 1]
    else:
        offset_map = [0, 0]
    return View(text=text, map=offset_map)


def _join_view(keep: View) -> View:
    """Build the *join* view: also undo line-break hyphenation.

    A hyphen followed by whitespace, sitting between a letter and a lowercase
    letter, is a soft hyphenation from a line break ("termi-\\nnation"). Remove
    the hyphen and the space so the word rejoins. Offsets follow the kept view.
    """
    text = keep.text
    kmap = keep.map
    out_chars: list[str] = []
    out_srcs: list[int] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if (
            ch == "-"
            and 0 < i < n - 2
            and text[i - 1].isalpha()
            and text[i + 1] == " "
            and text[i + 2].islower()
        ):
            # Skip the hyphen and the following space; keep their offsets out.
            i += 2
            continue
        out_chars.append(ch)
        out_srcs.append(kmap[i])
        i += 1
    if out_srcs:
        offset_map = out_srcs + [out_srcs[-1] + 1]
    else:
        offset_map = [0, 0]
    return View(text="".join(out_chars), map=offset_map)


def _loose_view(keep: View) -> View:
    """Build the *loose* key: all whitespace removed (catches glued/split words)."""
    out_chars: list[str] = []
    out_srcs: list[int] = []
    for i, ch in enumerate(keep.text):
        if ch == " ":
            continue
        out_chars.append(ch)
        out_srcs.append(keep.map[i])
    if out_srcs:
        offset_map = out_srcs + [out_srcs[-1] + 1]
    else:
        offset_map = [0, 0]
    return View(text="".join(out_chars), map=offset_map)


def build_views(canonical: str) -> tuple[View, View, View]:
    """Return the (keep, join, loose) views for a canonical text."""
    keep = _keep_view(canonical)
    return keep, _join_view(keep), _loose_view(keep)


def normalize_str(s: str) -> str:
    """Normalise a bare string (e.g. a candidate quote) with the *keep* rules."""
    return _keep_view(s).text


def normalize_loose(s: str) -> str:
    """Normalise a bare string with keep rules, then remove all whitespace."""
    return _loose_view(_keep_view(s)).text
