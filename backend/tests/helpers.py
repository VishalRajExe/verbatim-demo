"""Helpers to build real sample PDF/DOCX files for tests."""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
from docx import Document
from docx.enum.text import WD_BREAK


def make_text_pdf(path: Path, pages: list[str]) -> Path:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        # Wrap long text so PyMuPDF stores multiple lines.
        page.insert_textbox(fitz.Rect(50, 50, 550, 780), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def make_scanned_pdf(path: Path, n_pages: int = 2) -> Path:
    """A PDF with image-only pages and no extractable text."""
    doc = fitz.open()
    for _ in range(n_pages):
        page = doc.new_page()
        # Draw filled rectangles (visual content) but insert no text.
        page.draw_rect(fitz.Rect(100, 100, 400, 300), color=(0, 0, 0), fill=(0.8, 0.8, 0.8))
    doc.save(str(path))
    doc.close()
    return path


def make_docx(path: Path, paragraphs: list[str], page_breaks: list[int] | None = None) -> Path:
    doc = Document()
    page_breaks = set(page_breaks or [])
    for i, text in enumerate(paragraphs):
        para = doc.add_paragraph(text)
        if i in page_breaks:
            para.add_run().add_break(WD_BREAK.PAGE)
    doc.save(str(path))
    return path
