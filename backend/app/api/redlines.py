"""Redlining API (Phase 8): produce a real DOCX with tracked changes.

Applies ``<w:ins>``/``<w:del>`` revisions to the source ``.docx`` and stores the
result for download. Only DOCX is supported (PDF has no editable OOXML run
tree); edits that don't target exactly one occurrence are dropped and reported.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.assistant import Redline
from app.models.document import Document, DocumentStatus
from app.schemas.assistant import RedlineOut, RedlineRequest
from app.services.redlining.service import Edit, apply_redlines

router = APIRouter(tags=["redlines"])

_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _redlines_dir() -> Path:
    d = get_settings().storage_dir / "redlines"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/documents/{doc_id}/redline", response_model=RedlineOut, status_code=201)
def create_redline(
    doc_id: str, body: RedlineRequest, db: Session = Depends(get_db)
) -> RedlineOut:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    if doc.status != DocumentStatus.READY:
        raise HTTPException(409, "Document is not ready.")
    if doc.file_type != ".docx":
        raise HTTPException(
            400, "Tracked changes are only supported for DOCX documents."
        )
    src = Path(doc.file_path)
    if not src.exists():
        raise HTTPException(404, "Source file not found on storage.")

    edits = [Edit(target=e.target, replacement=e.replacement) for e in body.edits]
    try:
        result = apply_redlines(src.read_bytes(), edits, author=body.author)
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        raise HTTPException(500, "Could not generate the redlined document.") from exc

    redline_id = str(uuid.uuid4())
    out_path = _redlines_dir() / f"{redline_id}.docx"
    out_path.write_bytes(result.document_bytes)

    row = Redline(
        id=redline_id,
        document_id=doc_id,
        author=body.author,
        applied_json=[{"target": e.target, "replacement": e.replacement} for e in result.applied],
        dropped_json=result.dropped,
        insertions=result.insertions,
        deletions=result.deletions,
        output_path=str(out_path),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("/redlines", response_model=list[RedlineOut])
def list_redlines(db: Session = Depends(get_db)) -> list[RedlineOut]:
    rows = db.query(Redline).order_by(Redline.created_at.desc()).all()
    return [_to_out(r) for r in rows]


@router.get("/redlines/{redline_id}")
def get_redline(redline_id: str, db: Session = Depends(get_db)) -> RedlineOut:
    row = db.get(Redline, redline_id)
    if row is None:
        raise HTTPException(404, "Redline not found.")
    return _to_out(row)


@router.get("/redlines/{redline_id}/download")
def download_redline(redline_id: str, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(Redline, redline_id)
    if row is None:
        raise HTTPException(404, "Redline not found.")
    path = Path(row.output_path)
    if not path.exists():
        raise HTTPException(404, "Redlined file not found.")
    doc = db.get(Document, row.document_id)
    base = Path(doc.filename).stem if doc else "document"
    return FileResponse(
        path, media_type=_DOCX_MIME, filename=f"{base}.redlined.docx"
    )


def _to_out(row: Redline) -> RedlineOut:
    out = RedlineOut.model_validate(row)
    out.downloadUrl = f"{get_settings().api_prefix}/redlines/{row.id}/download"
    return out
