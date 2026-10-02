"""Extraction package public API."""
from __future__ import annotations

from pathlib import Path

from app.services.extraction.base import DocExtraction, ExtractedPage
from app.services.extraction.docx import extract_docx
from app.services.extraction.errors import UnsupportedFormatError
from app.services.extraction.pdf import extract_pdf

__all__ = [
    "DocExtraction",
    "ExtractedPage",
    "extract_pdf",
    "extract_docx",
    "extract_document",
    "UnsupportedFormatError",
]


def extract_document(path: Path, file_type: str) -> DocExtraction:
    """Dispatch to the correct extractor by verified file type."""
    ext = file_type.lower()
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    raise UnsupportedFormatError(
        f"Unsupported file type '{file_type}'. Please upload a PDF or DOCX file."
    )
