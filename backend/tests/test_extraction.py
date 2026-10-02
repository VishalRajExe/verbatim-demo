"""Phase 1 extraction + signature tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.extraction import extract_document
from app.services.extraction.errors import ScannedPdfError
from app.services.extraction.signatures import sniff_type
from tests.helpers import make_docx, make_scanned_pdf, make_text_pdf

TERMS = (
    "The Customer shall pay all outstanding amounts within 30 days of invoice. "
    "Late payments accrue interest at four percent per annum."
)
LIABILITY = (
    "Neither party shall be liable for indirect or consequential damages arising "
    "out of this agreement. The total liability cap is AED 100,000."
)


def test_pdf_page_level_extraction(tmp_path: Path) -> None:
    pdf = make_text_pdf(tmp_path / "a.pdf", [TERMS, LIABILITY])
    result = extract_document(pdf, ".pdf")
    assert result.page_count == 2
    assert [p.page_number for p in result.pages] == [1, 2]
    assert "30 days" in result.pages[0].text
    assert "AED 100,000" in result.pages[1].text
    assert "Liability" in result.full_text or "liability" in result.full_text


def test_scanned_pdf_raises(tmp_path: Path) -> None:
    scanned = make_scanned_pdf(tmp_path / "scan.pdf", n_pages=2)
    with pytest.raises(ScannedPdfError):
        extract_document(scanned, ".pdf")


def test_docx_multi_page_split(tmp_path: Path) -> None:
    docx = make_docx(
        tmp_path / "b.docx",
        [TERMS, LIABILITY],
        page_breaks=[0],
    )
    result = extract_document(docx, ".docx")
    assert result.page_count == 2
    assert "30 days" in result.pages[0].text
    assert "AED 100,000" in result.pages[1].text


def test_signature_validation(tmp_path: Path) -> None:
    good_pdf = make_text_pdf(tmp_path / "real.pdf", [TERMS])
    assert sniff_type(good_pdf, ".pdf") == ".pdf"

    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"this is definitely not a pdf")
    with pytest.raises(ValueError):
        sniff_type(fake, ".pdf")
