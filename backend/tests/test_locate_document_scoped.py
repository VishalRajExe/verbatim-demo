"""Citation/viewer must be document-scoped (regression).

Guarantees the invariant behind the fix: a source range is only ever resolved
against the document it belongs to. A range that is valid in a large document
(Document B, "page 87") must NEVER resolve to a page in a smaller document
(Document A, 4 pages) — it returns nothing, so the UI shows "source not found in
this document" instead of opening the wrong document's page.

It also pins the second half of that honesty rule: a document whose stored
source file has disappeared must report THAT, not an empty location list and not
an unhandled crash.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.document import Document
from tests.helpers import make_text_pdf

API = "/api/documents"

# Document A: small (2 pages).
A1 = "Northstar Retail Technologies is the Customer under this short agreement."
A2 = "The Customer may terminate this short agreement on fifteen days written notice."

# Document B: larger (6 pages) with a distinctive clause on the last page.
_FILLER = "Operational requirements for this page include maintaining accurate records and assigning a responsible owner for every escalation path defined in the applicable statement of work."
B6 = "The supplier shall maintain commercial general liability insurance with a coverage limit of AED 5,000,000 per occurrence."


def _ready(client: TestClient, path: Path, name: str, pages: list[str]) -> str:
    pdf = make_text_pdf(path, pages)
    resp = client.post(
        f"{API}/upload",
        files={"file": (name, pdf.read_bytes(), "application/pdf")},
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    assert client.get(f"{API}/{doc_id}").json()["status"] == "ready"
    return doc_id


def _verify(client: TestClient, doc_id: str, quote: str) -> dict:
    body = client.post(f"{API}/{doc_id}/verify", json={"quote": quote}).json()
    assert body["verified"] is True, body
    return body["primary"]


def test_range_resolves_within_its_own_document(client: TestClient, tmp_path: Path) -> None:
    a_id = _ready(client, tmp_path / "a.pdf", "a.pdf", [A1, A2])
    try:
        primary = _verify(client, a_id, A2)
        located = client.get(
            f"{API}/{a_id}/locate",
            params={"ranges": f"{primary['start']}-{primary['end']}"},
        ).json()
        pages = {loc["pageNumber"] for loc in located["locations"]}
        assert pages, "a document's own range must resolve"
        # A has exactly 2 pages — resolution can never name a page beyond that.
        assert pages <= {1, 2}, pages
    finally:
        client.delete(f"{API}/{a_id}")


def test_foreign_range_never_resolves_to_another_documents_page(
    client: TestClient, tmp_path: Path
) -> None:
    a_id = _ready(client, tmp_path / "a.pdf", "a.pdf", [A1, A2])
    b_id = _ready(
        client,
        tmp_path / "b.pdf",
        "b.pdf",
        [_FILLER, _FILLER, _FILLER, _FILLER, _FILLER, B6],
    )
    try:
        # A citation from Document B's LAST page (analogous to "page 87").
        b_primary = _verify(client, b_id, B6)
        b_range = f"{b_primary['start']}-{b_primary['end']}"
        b_located = client.get(
            f"{API}/{b_id}/locate", params={"ranges": b_range}
        ).json()
        b_pages = {loc["pageNumber"] for loc in b_located["locations"]}
        assert b_pages and max(b_pages) > 2, b_pages  # resolves deep inside B

        # The SAME numeric range applied to Document A (only 2 pages) must
        # resolve to NOTHING — never to a page A does not contain.
        a_located = client.get(
            f"{API}/{a_id}/locate", params={"ranges": b_range}
        ).json()
        assert a_located["id"] == a_id
        assert a_located["locations"] == [], (
            "A foreign (out-of-bounds) range must not resolve to any page in A"
        )
    finally:
        client.delete(f"{API}/{a_id}")
        client.delete(f"{API}/{b_id}")


def test_locate_rejects_out_of_bounds_and_malformed_ranges(
    client: TestClient, tmp_path: Path
) -> None:
    a_id = _ready(client, tmp_path / "a.pdf", "a.pdf", [A1, A2])
    try:
        # Absurdly large range (beyond any small document) -> empty, not 500.
        r = client.get(f"{API}/{a_id}/locate", params={"ranges": "999999-9999999"})
        assert r.status_code == 200
        assert r.json()["locations"] == []
        # Reversed / empty range -> empty.
        r2 = client.get(f"{API}/{a_id}/locate", params={"ranges": "50-10"})
        assert r2.status_code == 200
        assert r2.json()["locations"] == []
    finally:
        client.delete(f"{API}/{a_id}")


def test_missing_source_file_is_reported_not_crashed(
    client: TestClient, tmp_path: Path
) -> None:
    # Bug #8: a document row can outlive its stored file (repo moved, storage
    # restored from another machine). The extracted text is still in the
    # database, so /locate used to call PyMuPDF on a dead path and raise a raw
    # FileNotFoundError -> HTTP 500. The browser then blamed CORS and the drawer
    # claimed the verified citation was "not found in this document".
    a_id = _ready(client, tmp_path / "a.pdf", "a.pdf", [A1, A2])
    primary = _verify(client, a_id, A2)
    db = SessionLocal()
    try:
        stored = Path(db.get(Document, a_id).file_path)
    finally:
        db.close()
    stored.rename(stored.with_suffix(".gone"))  # file disappears, row survives
    try:
        located = client.get(
            f"{API}/{a_id}/locate",
            params={"ranges": f"{primary['start']}-{primary['end']}"},
        )
        assert located.status_code == 404, located.text
        assert "Source file not found on storage" in located.text
        # Same contract as the file endpoint, which already checked this.
        assert client.get(f"{API}/{a_id}/file").status_code == 404
        # Text-based retrieval is unaffected: the quote is still verifiable.
        assert client.post(
            f"{API}/{a_id}/verify", json={"quote": A2}
        ).json()["verified"] is True
    finally:
        stored.with_suffix(".gone").rename(stored)
        client.delete(f"{API}/{a_id}")
