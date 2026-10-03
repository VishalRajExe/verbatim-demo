"""Conservative, in-process answer reuse for the query guard (Phase 10).

Grounded Q&A in this product is a pure function of (question, selected
documents) — ``pipeline.ask_stream`` receives only the documents and the
question, never conversation history. That makes safe answer reuse possible:
an identical question over an identical, unchanged document scope yields an
identical verified answer, so it can be replayed without another Gemini call.

Safety rules enforced here:
- The key includes the document IDs **and** each document's ``updated_at``
  version stamp, so re-processing/replacing a document changes the key and the
  stale answer is never returned. Changing the selection changes the key.
- Only questions with a non-empty content signature are eligible (so contentless
  or gibberish input is never reused).
- The cache is bounded and time-limited; it lives only in memory and is empty
  after a restart, at which point the normal pipeline simply repopulates it.

Correctness is preferred over token savings: anything that is not an exact key
match runs the normal pipeline.
"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Iterable

from app.services.qa.guard import question_signature

_TTL_SECONDS = 30 * 60
_MAX_ENTRIES = 256


def build_key(question: str, doc_ids: Iterable[str], doc_versions: Iterable[str]) -> str:
    """Stable cache key: signature + sorted ids + sorted per-doc version stamps.

    ``doc_versions`` should be one opaque version token per document (e.g. its
    ``updated_at`` ISO string). Any change to the scope or a document's state
    produces a different key.
    """
    sig = question_signature(question)
    if not sig:
        # Not eligible for reuse. Return an empty key so callers skip caching.
        return ""
    ids = "|".join(sorted(doc_ids))
    versions = "|".join(sorted(doc_versions))
    raw = f"{sig}::{ids}::{versions}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AnswerCache:
    def __init__(self, ttl: int = _TTL_SECONDS, max_entries: int = _MAX_ENTRIES):
        self._ttl = ttl
        self._max = max_entries
        self._data: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()

    def get(self, key: str) -> dict | None:
        if not key:
            return None
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if time.monotonic() >= expires_at:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return payload

    def set(self, key: str, payload: dict) -> None:
        if not key:
            return
        self._data[key] = (time.monotonic() + self._ttl, payload)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def invalidate_document(self, doc_id: str) -> None:
        """Drop any cached answer that touched ``doc_id`` (best-effort).

        Payload stores the doc ids it was answered over; used when a document is
        deleted or reprocessed so a stale answer cannot be replayed.
        """
        doomed = [
            k for k, (_exp, payload) in self._data.items()
            if doc_id in payload.get("doc_ids", [])
        ]
        for k in doomed:
            self._data.pop(k, None)


# Process-wide singleton (bounded, in-memory only).
answer_cache = AnswerCache()
