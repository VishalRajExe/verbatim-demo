"""Contract comparison API (Phase 7): clause-aware, deterministic comparison.

Runs the comparison engine over two READY documents, persists the resulting
changes, and returns them. The engine only ever reports *differences*; the
materiality floor is computed server-side and never lowered by the model.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.assistant import Comparison, ComparisonChange
from app.models.document import Document, DocumentStatus
from app.schemas.assistant import CompareRequest, ComparisonOut
from app.services.comparison.pipeline import comparison_result

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


def _ready_text(db: Session, doc_id: str) -> str:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, f"Document {doc_id} not found.")
    if doc.status != DocumentStatus.READY:
        raise HTTPException(409, f"Document {doc_id} is not ready.")
    return doc.extracted_text or ""


@router.post("", response_model=ComparisonOut, status_code=201)
def create_comparison(
    body: CompareRequest, db: Session = Depends(get_db)
) -> ComparisonOut:
    a_text = _ready_text(db, body.document_a_id)
    b_text = _ready_text(db, body.document_b_id)
    result = comparison_result(a_text, b_text)

    comp = Comparison(
        document_a_id=body.document_a_id,
        document_b_id=body.document_b_id,
        summary=result["summary"],
        summary_source=result["summarySource"],
        stats_json=result["stats"],
    )
    db.add(comp)
    db.flush()
    for change in result["changes"]:
        db.add(
            ComparisonChange(
                comparison_id=comp.id,
                order_idx=change["orderIdx"],
                type=change["type"],
                significance=change["significance"],
                category=change.get("category"),
                title=change.get("title", ""),
                summary=change.get("summary", ""),
                summary_source=change.get("summarySource", "automatic"),
                a_text=change.get("aText"),
                b_text=change.get("bText"),
                a_start=change.get("aStart"),
                a_end=change.get("aEnd"),
                b_start=change.get("bStart"),
                b_end=change.get("bEnd"),
            )
        )
    db.commit()
    db.refresh(comp)
    return ComparisonOut.model_validate(comp)


@router.get("", response_model=list[ComparisonOut])
def list_comparisons(db: Session = Depends(get_db)) -> list[ComparisonOut]:
    comps = db.query(Comparison).order_by(Comparison.created_at.desc()).all()
    return [ComparisonOut.model_validate(c) for c in comps]


@router.get("/{comparison_id}", response_model=ComparisonOut)
def get_comparison(comparison_id: str, db: Session = Depends(get_db)) -> ComparisonOut:
    comp = db.get(Comparison, comparison_id)
    if comp is None:
        raise HTTPException(404, "Comparison not found.")
    return ComparisonOut.model_validate(comp)
