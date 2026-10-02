"""Tolerant JSON parsing for model output.

Models sometimes wrap JSON in code fences or add stray prose. We strip the
fences and extract the first balanced JSON object/array, then let the caller
validate it. Parsing never crashes: it returns None on unrecoverable input so
the pipeline can mark that chunk failed instead of erroring the whole request.
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def parse_json_lenient(raw: str) -> Any | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    # Prefer fenced content if present.
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()

    # Direct parse.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract the first balanced {...} or [...].
    start_idx = _first_of(text, "{", "[")
    if start_idx is None:
        return None
    candidate = _balanced(text, start_idx)
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _first_of(text: str, *chars: str) -> int | None:
    positions = [text.find(c) for c in chars if text.find(c) != -1]
    return min(positions) if positions else None


def _balanced(text: str, start: int) -> str | None:
    open_to_close = {"{": "}", "[": "]"}
    opener = text[start]
    closer = open_to_close.get(opener)
    if not closer:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
