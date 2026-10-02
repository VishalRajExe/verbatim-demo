"""DB-backed wrapper around the pure verifier, plus canonical-text caching.

Verification always runs against the *document the quote is attributed to*
(invariant I-7). For multi-document questions the caller passes the set of
candidate documents; a quote that is absent from its attributed document but
present in another is reported ``WRONG_DOCUMENT`` rather than verified.
"""
from __future__ import annotations

from collections import OrderedDict

from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPage, DocumentStatus
from app.services.citations.verify_quote import (
    WRONG_DOCUMENT,
    VerifyResult,
    verify_in_text,
)
from app.services.text.canonical import PageRange, build_canonical

# Small in-process cache of (canonical, ranges) keyed by document id. Legal
# documents are immutable once READY, so entries never need explicit eviction
# beyond a bounded LRU.
_CACHE: "OrderedDict[str, tuple[str, list[PageRange], int]]" = OrderedDict()
_CACHE_MAX = 32


def canonical_for_document(db: Session, document_id: str) -> tuple[str, list[PageRange], int]:
    """Return ``(canonical_text, page_ranges, version)`` for a READY document."""
    cached = _CACHE.get(document_id)
    if cached is not None:
        _CACHE.move_to_end(document_id)
        return cached

    doc = db.get(Document, document_id)
    if doc is None or doc.status != DocumentStatus.READY:
        raise DocumentNotReadyError(document_id)

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    canonical, ranges = build_canonical([(p.page_number, p.text) for p in pages])

    _CACHE[document_id] = (canonical, ranges, doc.page_count or 0)
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return _CACHE[document_id]


def invalidate_document(document_id: str) -> None:
    _CACHE.pop(document_id, None)


class DocumentNotReadyError(Exception):
    def __init__(self, document_id: str) -> None:
        super().__init__(f"Document {document_id} is missing or not ready.")
        self.document_id = document_id


def verify_quote(
    db: Session,
    document_id: str,
    quote: str,
    chunk_hint: tuple[int, int] | None = None,
) -> VerifyResult:
    """Verify a quote against a single attributed document."""
    canonical, ranges, _ = canonical_for_document(db, document_id)
    return verify_in_text(quote, canonical, ranges, chunk_hint=chunk_hint)


def verify_quote_multi(
    db: Session,
    attributed_document_id: str,
    quote: str,
    candidate_document_ids: list[str],
    chunk_hint: tuple[int, int] | None = None,
) -> VerifyResult:
    """Verify against the attributed doc; tag WRONG_DOCUMENT if only elsewhere."""
    result = verify_quote(db, attributed_document_id, quote, chunk_hint)
    if result.verified or not result.fail_reason:
        return result
    # Only re-classify a NOT_FOUND (not TOO_SHORT / TOO_LONG) as wrong-document.
    if result.fail_reason != "NOT_FOUND":
        return result
    for other_id in candidate_document_ids:
        if other_id == attributed_document_id:
            continue
        other = verify_quote(db, other_id, quote)
        if other.verified:
            return VerifyResult(
                False, result.normalized, fail_reason=WRONG_DOCUMENT
            )
    return result
