"""Coverage tracking (Phase 4). Every answer carries one of these.

If any chunk failed or pages were unreadable, the answer must NOT state that
something does not exist (invariant I-5). The deterministic "not found" text and
the UI caveat badge are both derived from this object, so the frontend cannot
show a confident absence on a partial read.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocumentCoverage:
    document_id: str
    name: str
    chunks_total: int = 0
    chunks_read: int = 0
    failed_chunks: list[int] = field(default_factory=list)
    pages: int = 0
    unreadable_pages: int = 0

    @property
    def complete(self) -> bool:
        return not self.failed_chunks and self.chunks_read >= self.chunks_total

    def to_dict(self) -> dict:
        return {
            "documentId": self.document_id,
            "name": self.name,
            "chunksTotal": self.chunks_total,
            "chunksRead": self.chunks_read,
            "failedChunks": self.failed_chunks,
            "pages": self.pages,
            "unreadablePages": self.unreadable_pages,
            "complete": self.complete,
        }


def not_found_message(coverages: list[DocumentCoverage]) -> str:
    """Deterministic, no-model 'could not find' text honouring coverage."""
    all_complete = all(c.complete for c in coverages)
    if all_complete:
        parts = [
            f"{c.name} (all {c.chunks_total} section(s) read)" for c in coverages
        ]
        return (
            "I couldn't find a passage that answers this in "
            + ", ".join(parts)
            + ". Based on the full text I read, it does not appear to be addressed."
        )
    read = sum(c.chunks_read for c in coverages)
    total = sum(c.chunks_total for c in coverages)
    names = ", ".join(c.name for c in coverages)
    return (
        f"I couldn't find it in the sections I could read of {names} "
        f"({read} of {total} sections). Absence is not confirmed."
    )


def caveat(coverages: list[DocumentCoverage]) -> str | None:
    """A short warning shown alongside an answer, or None if coverage is full."""
    partial = [c for c in coverages if not c.complete]
    unreadable = [c for c in coverages if c.unreadable_pages > 0]
    if not partial and not unreadable:
        return None
    bits = []
    if partial:
        bits.append(
            "Some sections could not be read, so this answer may be incomplete."
        )
    if unreadable:
        bits.append("Some pages were unreadable (e.g. scanned images).")
    return " ".join(bits)
