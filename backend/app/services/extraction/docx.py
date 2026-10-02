"""DOCX text extraction via python-docx.

Walks the document body in reading order (paragraphs and tables interleaved),
starts a new logical page on an explicit page break, and preserves paragraph
text for downstream canonical-text work.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.extraction.base import DocExtraction, ExtractedPage
from app.services.extraction.errors import CorruptedFileError, EmptyDocumentError

_WS = re.compile(r"\s+")
MIN_TOTAL_CHARS = 20


def _iter_blocks(doc: Document):
    """Yield Paragraph / Table objects in body order."""
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _has_page_break(para: Paragraph) -> bool:
    for br in para._p.findall(".//" + qn("w:br")):
        if br.get(qn("w:type")) == "page":
            return True
    return False


def _table_text(table: Table) -> list[str]:
    lines: list[str] = []
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        line = " | ".join(c for c in cells if c)
        if line:
            lines.append(line)
    return lines


def extract_docx(path: Path) -> DocExtraction:
    try:
        doc = Document(str(path))
    except Exception as exc:  # noqa: BLE001 - docx raises generic exceptions
        raise CorruptedFileError(f"The DOCX could not be opened: {exc}") from exc

    pages: list[ExtractedPage] = []
    current: list[str] = []

    def flush() -> None:
        text = "\n".join(current).strip()
        if text:
            pages.append(ExtractedPage(page_number=len(pages) + 1, text=text))
        current.clear()

    for block in _iter_blocks(doc):
        if isinstance(block, Paragraph):
            if block.text.strip():
                current.append(block.text.strip())
            # An explicit page break ends the current page after this paragraph.
            if _has_page_break(block):
                flush()
        elif isinstance(block, Table):
            current.extend(_table_text(block))
    flush()

    full_text = "\n\n".join(p.text for p in pages)
    total_chars = len(_WS.sub("", full_text))

    if total_chars < MIN_TOTAL_CHARS:
        raise EmptyDocumentError()

    return DocExtraction(
        pages=pages,
        page_count=len(pages) or 1,
        full_text=full_text,
        total_chars=total_chars,
    )
