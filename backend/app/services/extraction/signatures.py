"""File-type sniffing by magic bytes (no native dependencies).

Replaces python-magic (a Windows friction point). We verify that the uploaded
bytes actually match the claimed extension before trusting any extractor.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"
# The OOXML word-processing part inside a .docx package.
_DOCX_CONTENT_MARKER = b"wordprocessingml"


def is_pdf_bytes(head: bytes) -> bool:
    return head.startswith(PDF_MAGIC)


def is_docx_path(path: Path) -> bool:
    """A .docx is a ZIP package that contains a word/ directory or the
    wordprocessingml content type. Detect it without loading the whole file."""
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if not any(n.startswith("word/") for n in names):
                return False
            # Confirm it is a word-processing document, not just any OOXML zip.
            try:
                ct = zf.read("[Content_Types].xml")
            except KeyError:
                return False
            return _DOCX_CONTENT_MARKER in ct
    except (zipfile.BadZipFile, OSError):
        return False


def sniff_type(path: Path, claimed_ext: str) -> str:
    """Return the verified type ('.pdf'/'.docx') or raise ValueError on mismatch."""
    ext = claimed_ext.lower()
    with open(path, "rb") as fh:
        head = fh.read(8)

    if ext == ".pdf":
        if not is_pdf_bytes(head):
            raise ValueError("File content does not match the .pdf extension.")
        return ".pdf"
    if ext == ".docx":
        if not is_docx_path(path):
            raise ValueError("File content does not match the .docx extension.")
        return ".docx"
    raise ValueError(f"Unsupported extension: {ext}")
