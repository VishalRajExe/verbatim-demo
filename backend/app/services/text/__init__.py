"""Text utilities: canonical-text normalisation and offset maps (Architecture §6)."""
from app.services.text.normalize import (
    View,
    build_views,
    canonical_span,
    normalize_str,
)

__all__ = ["View", "build_views", "canonical_span", "normalize_str"]
