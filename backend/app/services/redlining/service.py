"""High-level redlining service: apply tracked edits to DOCX bytes.

Turns a source ``.docx`` plus a list of ``(target, replacement)`` edits into a
new ``.docx`` carrying real ``<w:ins>``/``<w:del>`` revisions. Edits whose target
does not occur exactly once are dropped and reported, so the caller never
silently mis-edits a document (Rules §1: honest about what was applied).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from docx import Document

from app.services.redlining.tracked_changes import (
    apply_tracked_edit,
    count_tracked_changes,
)


@dataclass
class Edit:
    target: str
    replacement: str


@dataclass
class RedlineResult:
    document_bytes: bytes
    applied: list[Edit] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0


def apply_redlines(source: bytes, edits: list[Edit], author: str = "Legal AI") -> RedlineResult:
    document = Document(io.BytesIO(source))
    applied: list[Edit] = []
    dropped: list[dict] = []
    for edit in edits:
        try:
            apply_tracked_edit(document, edit.target, edit.replacement, author=author)
            applied.append(edit)
        except ValueError as exc:
            dropped.append({"target": edit.target, "reason": str(exc)})

    buf = io.BytesIO()
    document.save(buf)
    data = buf.getvalue()
    ins, dele = count_tracked_changes(data)
    return RedlineResult(
        document_bytes=data, applied=applied, dropped=dropped, insertions=ins, deletions=dele
    )
