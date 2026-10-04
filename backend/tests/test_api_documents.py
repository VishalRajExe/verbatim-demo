"""Phase 1 documents API end-to-end tests (upload -> process -> store -> read)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.document import Document
from tests.helpers import make_docx, make_scanned_pdf, make_text_pdf

TERMS = (
    "The Customer shall pay all outstanding amounts within 30 days of invoice. "
    "Late payments accrue interest at four percent per annum."
)
LIABILITY = (
    "Neither party shall be liable for indirect or consequential damages arising "
    "out of this agreement. The total liability cap is AED 100,000."
)

API = "/api/documents"


def _upload(client: TestClient, name: str, data: bytes, mime: str = "application/octet-stream"):
    return client.post(f"{API}/upload", files={"file": (name, data, mime)})


def test_upload_docx_flow(client: TestClient, tmp_path: Path) -> None:
    docx = make_docx(tmp_path / "contract.docx", [TERMS, LIABILITY], page_breaks=[0])
    resp = _upload(client, "contract.docx", docx.read_bytes())
    assert resp.status_code == 202, resp.text
    doc_id = resp.json()["id"]

    try:
        detail = client.get(f"{API}/{doc_id}")
        assert detail.status_code == 200
        body = detail.json()
        # Background processing runs synchronously under TestClient.
        assert body["status"] == "ready", body
        assert body["page_count"] == 2
        assert body["file_type"] == ".docx"

        listing = client.get(API).json()
        assert any(d["id"] == doc_id for d in listing["documents"])

        pages = client.get(f"{API}/{doc_id}/pages").json()
        assert pages["total_pages"] == 2
        assert "AED 100,000" in pages["pages"][1]["text"]

        text = client.get(f"{API}/{doc_id}/text").json()
        assert "30 days" in text["text"]

        file_resp = client.get(f"{API}/{doc_id}/file")
        assert file_resp.status_code == 200
    finally:
        assert client.delete(f"{API}/{doc_id}").status_code == 204
        assert client.get(f"{API}/{doc_id}").status_code == 404


def test_upload_pdf_flow(client: TestClient, tmp_path: Path) -> None:
    pdf = make_text_pdf(tmp_path / "contract.pdf", [TERMS, LIABILITY])
    resp = _upload(client, "contract.pdf", pdf.read_bytes(), "application/pdf")
    assert resp.status_code == 202, resp.text
    doc_id = resp.json()["id"]
    try:
        body = client.get(f"{API}/{doc_id}").json()
        assert body["status"] == "ready", body
        assert body["page_count"] == 2
    finally:
        client.delete(f"{API}/{doc_id}")


def test_upload_scanned_pdf_marks_error(client: TestClient, tmp_path: Path) -> None:
    scanned = make_scanned_pdf(tmp_path / "scan.pdf")
    resp = _upload(client, "scan.pdf", scanned.read_bytes(), "application/pdf")
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    try:
        body = client.get(f"{API}/{doc_id}").json()
        assert body["status"] == "error"
        assert "scanned" in (body["error_message"] or "").lower()
    finally:
        client.delete(f"{API}/{doc_id}")


def test_reject_unsupported_extension(client: TestClient) -> None:
    resp = _upload(client, "notes.txt", b"hello world, this is a plain text file")
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_reject_content_mismatch(client: TestClient) -> None:
    # Named .pdf but not actually a PDF -> caught by signature sniffing.
    resp = _upload(client, "evil.pdf", b"PK-not-a-real-pdf-content-here")
    assert resp.status_code == 400


def test_file_and_locate_survive_ephemeral_disk_wipe(client: TestClient, tmp_path: Path) -> None:
    # Render's instance disk is wiped on redeploy/idle shutdown while the DB row
    # persists. Simulate that by deleting the on-disk upload after processing,
    # then confirm the durable copy still serves the file and citation geometry
    # instead of 404-ing until re-upload.
    pdf = make_text_pdf(tmp_path / "contract.pdf", [TERMS, LIABILITY])
    doc_id = _upload(client, "contract.pdf", pdf.read_bytes(), "application/pdf").json()["id"]
    try:
        assert client.get(f"{API}/{doc_id}").json()["status"] == "ready"
        # Sanity: while the disk copy is present, /file works and backfills the
        # durable row; then remove the disk copy to force the fallback path.
        assert client.get(f"{API}/{doc_id}/file").status_code == 200
        db = SessionLocal()
        try:
            stored = Path(db.get(Document, doc_id).file_path)
        finally:
            db.close()
        stored.unlink(missing_ok=True)
        assert not stored.exists()

        served = client.get(f"{API}/{doc_id}/file")
        assert served.status_code == 200
        assert served.content[:4] == b"%PDF", "bytes must come from the durable copy"

        # A canonical range inside the extracted text must still resolve to page
        # geometry from the persisted bytes (not SourceFileMissing -> 404).
        located = client.get(f"{API}/{doc_id}/locate", params={"ranges": "0-40"})
        assert located.status_code == 200
        assert located.json()["locations"]
    finally:
        client.delete(f"{API}/{doc_id}")
