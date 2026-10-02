"""Shared extraction result types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedPage:
    page_number: int  # 1-based
    text: str
    meta: dict = field(default_factory=dict)


@dataclass
class DocExtraction:
    """Result of extracting a whole document."""

    pages: list[ExtractedPage]
    page_count: int          # physical/logical page count for library display
    full_text: str           # pages joined with form-feed-free newlines
    total_chars: int         # non-whitespace characters (scanned-detection signal)
