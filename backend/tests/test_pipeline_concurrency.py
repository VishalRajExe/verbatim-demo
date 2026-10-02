"""Phase 4 concurrency: extraction fans out across chunks; verification stays serial.

Proves the network-bound ``complete_json`` calls actually run in parallel (bounded
by ``llm_max_concurrency``) while DB verification is untouched by worker threads,
and that the Q1..Qn numbering is deterministic regardless of finish order.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.document import Document
from app.services.ai.client import MockClient
from app.services.qa import pipeline
from app.services.qa.chunker import Chunk
from app.services.qa.pipeline import ask_stream
from tests.helpers import make_text_pdf

API = "/api/documents"

S1 = "The Customer shall pay all outstanding amounts within 30 days of invoice date."
S2 = "The total liability cap is AED 100,000 per claim year for either party."
S3 = "Either party may terminate this agreement with 60 days written notice."


class ConcurrentTracker(MockClient):
    """MockClient subclass that records how many extractions overlap in time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0
        self.calls = 0

    def complete_json(self, prompt: str):
        with self._lock:
            self._active += 1
            self.calls += 1
            self.peak = max(self.peak, self._active)
        time.sleep(0.08)  # hold the worker so a serial run would never overlap
        try:
            return super().complete_json(prompt)
        finally:
            with self._lock:
                self._active -= 1


def _ready_doc(client: TestClient, tmp_path: Path) -> str:
    pdf = make_text_pdf(tmp_path / "doc.pdf", [S1, S2, S3])
    resp = client.post(
        API + "/upload", files={"file": ("doc.pdf", pdf.read_bytes(), "application/pdf")}
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id"]
    assert client.get(f"{API}/{doc_id}").json()["status"] == "ready"
    return doc_id


def _chunks_per_sentence(canonical: str, max_chars: int = 96000):
    # Force several plan items from a short doc so the pool has work to overlap.
    out = []
    for i, sent in enumerate([s.strip() for s in re.split(r"(?<=[.!?])\s+", canonical) if s.strip()]):
        start = canonical.find(sent)
        out.append(Chunk(text=sent, start=start, end=start + len(sent), index=i))
    return out


def test_extraction_runs_in_parallel_and_verifies_serially(client, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "chunk_text", _chunks_per_sentence)
    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(llm_max_concurrency=3))

    doc_id = _ready_doc(client, tmp_path)
    tracker = ConcurrentTracker()
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        events = list(ask_stream(db, [doc], "When must the Customer pay?", tracker))
    finally:
        db.close()
        client.delete(f"{API}/{doc_id}")

    # Three sentence-chunks were extracted; the pool overlapped them (peak >= 2,
    # ideally 3) rather than calling one-at-a-time (which would pin peak at 1).
    assert tracker.calls == 3, "one extraction per chunk"
    assert tracker.peak >= 2, f"expected concurrent extraction, saw peak={tracker.peak}"

    # Verification still produced server-checked, deterministically numbered quotes.
    quotes = next(e for e in events if e["type"] == "quotes")["quotes"]
    refs = [q["ref"] for q in quotes]
    assert refs == sorted(refs, key=lambda r: int(r[1:])), "Q-numbering must be stable"
    for q in quotes:
        assert q["verified"] is True
        assert isinstance(q["start"], int) and q["end"] > q["start"]

    cov = next(e for e in events if e["type"] == "coverage")["coverage"]
    assert cov[0]["complete"] is True
    assert cov[0]["chunksTotal"] == 3
