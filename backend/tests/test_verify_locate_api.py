"""Phase 2 verify + locate endpoints, end-to-end on a real PDF."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers import make_text_pdf

API = "/api/documents"

P1 = "The Customer shall pay all outstanding amounts within 30 days of invoice date."
P2 = "The total liability cap is AED 100,000 per claim year for either party."


def _ready_pdf(client: TestClient, tmp_path: Path) -> str:
    pdf = make_text_pdf(tmp_path / "c.pdf", [P1, P2])
    resp = client.post(
        f"{API}/upload", files={"file": ("c.pdf", pdf.read_bytes(), "application/pdf")}
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    assert client.get(f"{API}/{doc_id}").json()["status"] == "ready"
    return doc_id


def test_verify_found_and_paraphrase_not_found(client: TestClient, tmp_path: Path) -> None:
    doc_id = _ready_pdf(client, tmp_path)
    try:
        good = client.post(f"{API}/{doc_id}/verify", json={"quote": P1}).json()
        assert good["verified"] is True
        assert good["matchKind"] == "exact"
        assert good["primary"]["pageStart"] == 1

        paraphrase = client.post(
            f"{API}/{doc_id}/verify",
            json={"quote": "The client must remit payment inside a month of the bill."},
        ).json()
        assert paraphrase["verified"] is False
        assert paraphrase["failReason"] == "NOT_FOUND"

        short = client.post(f"{API}/{doc_id}/verify", json={"quote": "hi"}).json()
        assert short["failReason"] == "TOO_SHORT"
    finally:
        client.delete(f"{API}/{doc_id}")


def test_locate_returns_page_rectangles_for_verified_quote(
    client: TestClient, tmp_path: Path
) -> None:
    doc_id = _ready_pdf(client, tmp_path)
    try:
        good = client.post(f"{API}/{doc_id}/verify", json={"quote": P2}).json()
        assert good["verified"] is True
        start = good["primary"]["start"]
        end = good["primary"]["end"]

        located = client.get(f"{API}/{doc_id}/locate", params={"ranges": f"{start}-{end}"}).json()
        assert located["id"] == doc_id
        assert located["locations"], "expected at least one located rectangle"
        first = located["locations"][0]
        assert first["pageNumber"] == 2
        # A located page exposes its pixel size and a non-empty bounding box.
        assert first["width"] > 0 and first["height"] > 0
        if not first.get("noGeometry"):
            assert first["boundingRect"] is not None
            assert first["rects"], "PDF locate should yield rects"
    finally:
        client.delete(f"{API}/{doc_id}")
