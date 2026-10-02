"""Citation / quote-verification package."""
from app.services.citations.service import (
    canonical_for_document,
    verify_quote,
    verify_quote_multi,
)
from app.services.citations.verify_quote import (
    MAX_OCCURRENCES,
    Occurrence,
    VerifyResult,
    verify_in_text,
)

__all__ = [
    "Occurrence",
    "VerifyResult",
    "verify_in_text",
    "verify_quote",
    "verify_quote_multi",
    "canonical_for_document",
    "MAX_OCCURRENCES",
]
