"""Extraction-layer exceptions with user-facing messages (brief §41)."""
from __future__ import annotations


class ExtractionError(Exception):
    """Base error carrying a clear, safe message for the UI."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFormatError(ExtractionError):
    pass


class CorruptedFileError(ExtractionError):
    def __init__(self, message: str = "The file appears to be corrupted and could not be opened.") -> None:
        super().__init__(message)


class ScannedPdfError(ExtractionError):
    def __init__(
        self,
        message: str = (
            "This PDF does not contain extractable text. It may be scanned or "
            "image-only. Please upload a text-based PDF."
        ),
    ) -> None:
        super().__init__(message)


class EmptyDocumentError(ExtractionError):
    def __init__(self, message: str = "No readable text could be extracted from this document.") -> None:
        super().__init__(message)
