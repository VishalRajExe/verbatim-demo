"""PDF text extraction via PyMuPDF (fitz).

Produces page-level text and detects scanned/image-only PDFs (brief §8): a PDF
that yields no meaningful text is a FAILURE, not an empty success.
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF

from app.services.extraction.base import DocExtraction, ExtractedPage
from app.services.extraction.errors import CorruptedFileError, ScannedPdfError

# Below this many non-whitespace characters, a PDF is treated as image-only.
MIN_TOTAL_CHARS = 50

_WS = re.compile(r"\s+")


def extract_pdf(path: Path) -> DocExtraction:
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001 - fitz raises generic RuntimeError
        raise CorruptedFileError(f"The PDF could not be opened: {exc}") from exc

    try:
        physical_pages = doc.page_count
        pages: list[ExtractedPage] = []
        for i, page in enumerate(doc):
            raw = page.get_text("text") or ""
            text = raw.strip()
            if text:
                pages.append(ExtractedPage(page_number=i + 1, text=text))
    finally:
        doc.close()

    full_text = "\n".join(p.text for p in pages)
    total_chars = len(_WS.sub("", full_text))

    if total_chars < MIN_TOTAL_CHARS:
        raise ScannedPdfError()

    return DocExtraction(
        pages=pages,
        page_count=physical_pages,
        full_text=full_text,
        total_chars=total_chars,
    )
