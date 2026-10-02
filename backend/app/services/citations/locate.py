"""Locate canonical-text ranges as page rectangles (Architecture §9).

Given verified ``[start, end)`` offsets into a document's canonical text, return
per-page rectangles the viewer can highlight. For PDFs we slice the canonical
text back to each page and use PyMuPDF to find the matching words' geometry.

DOCX documents have no page geometry unless rendered to PDF first (LibreOffice),
so we return page numbers with an empty ``rects`` list and a ``noGeometry`` flag
rather than fabricating coordinates. This is reported honestly, not hidden.
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from app.models.document import Document
from app.services.citations.service import canonical_for_document

_EPS = 1.0  # tolerance when deciding if a word overlaps a page slice


def locate_ranges(
    db: Session, document_id: str, ranges: list[tuple[int, int]]
) -> list[dict]:
    canonical, page_ranges, _ = canonical_for_document(db, document_id)
    doc = db.get(Document, document_id)
    if doc is None:
        return []

    results: list[dict] = []
    if doc.file_type == ".pdf":
        pdf = fitz.open(str(Path(doc.file_path)))
        try:
            for start, end in ranges:
                results.extend(_locate_pdf(pdf, canonical, page_ranges, start, end))
        finally:
            pdf.close()
    else:
        # DOCX / anything without rendered geometry: report page numbers only.
        for start, end in ranges:
            pages = _pages_for(canonical, page_ranges, start, end)
            for pg in pages:
                results.append(
                    {
                        "pageNumber": pg,
                        "width": 0.0,
                        "height": 0.0,
                        "rects": [],
                        "noGeometry": True,
                    }
                )
    return results


def _pages_for(canonical, page_ranges, start, end) -> list[int]:
    pages: list[int] = []
    for r in page_ranges:
        if r.end > start and r.start < end and r.page_number not in pages:
            pages.append(r.page_number)
    return pages or []


def _locate_pdf(pdf, canonical, page_ranges, start, end) -> list[dict]:
    out: list[dict] = []
    for r in page_ranges:
        if r.end <= start or r.start >= end:
            continue
        s0 = max(start, r.start)
        s1 = min(end, r.end)
        needle = canonical[s0:s1].strip()
        if not needle:
            continue
        page = pdf[r.page_number - 1]
        pw, ph = page.rect.width, page.rect.height
        rects: list[dict] = []
        for instance in page.search_for(needle):
            rects.append(
                {
                    "x1": round(float(instance.x0), 2),
                    "y1": round(float(instance.y0), 2),
                    "x2": round(float(instance.x1), 2),
                    "y2": round(float(instance.y1), 2),
                }
            )
        if not rects:
            # Long phrases can miss across internal line breaks; fall back to
            # the first few words so the viewer still lands on the right spot.
            words = needle.split()
            probe = " ".join(words[: max(3, min(len(words), 6))])
            for instance in page.search_for(probe):
                rects.append(
                    {
                        "x1": round(float(instance.x0), 2),
                        "y1": round(float(instance.y0), 2),
                        "x2": round(float(instance.x1), 2),
                        "y2": round(float(instance.y1), 2),
                    }
                )
        rects = _merge_line_rects(rects)
        out.append(
            {
                "pageNumber": r.page_number,
                "width": round(float(pw), 2),
                "height": round(float(ph), 2),
                "rects": rects,
                "boundingRect": _bounding(rects),
            }
        )
    return out


def _merge_line_rects(rects: list[dict]) -> list[dict]:
    """Merge rectangles that share a text line (similar y and overlapping x)."""
    merged: list[dict] = []
    for r in sorted(rects, key=lambda x: (x["y1"], x["x1"])):
        if merged and abs(merged[-1]["y1"] - r["y1"]) < _EPS * 3 and not (
            r["x2"] < merged[-1]["x1"] or r["x1"] > merged[-1]["x2"]
        ):
            m = merged[-1]
            m["x1"] = min(m["x1"], r["x1"])
            m["x2"] = max(m["x2"], r["x2"])
            m["y1"] = min(m["y1"], r["y1"])
            m["y2"] = max(m["y2"], r["y2"])
        else:
            merged.append(dict(r))
    return merged


def _bounding(rects: list[dict]) -> dict | None:
    if not rects:
        return None
    return {
        "x1": min(r["x1"] for r in rects),
        "y1": min(r["y1"] for r in rects),
        "x2": max(r["x2"] for r in rects),
        "y2": max(r["y2"] for r in rects),
    }
