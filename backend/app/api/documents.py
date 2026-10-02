"""Documents API (brief §31)."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.document import Document, DocumentPage, DocumentStatus
from app.schemas.document import (
    DocumentListOut,
    DocumentOut,
    DocumentPagesOut,
    UploadAccepted,
    VerifyRequest,
)
from app.services.citations.locate import locate_ranges
from app.services.citations.service import (
    DocumentNotReadyError,
    invalidate_document,
    verify_quote,
)
from app.services.document_processing import process_document
from app.services.extraction.signatures import sniff_type

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadAccepted, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadAccepted:
    settings = get_settings()
    if not file.filename:
        raise HTTPException(400, "No filename provided.")

    ext = Path(file.filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            400,
            "Unsupported file type. Please upload a PDF or DOCX file.",
        )

    doc_id = str(uuid.uuid4())
    dest = settings.uploads_dir / f"{doc_id}{ext}"

    # Stream to disk while enforcing the size cap (supports ~150-page files).
    total = 0
    max_bytes = settings.max_file_size_bytes
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    400, f"File too large (max {settings.max_file_size_mb} MB)."
                )
            out.write(chunk)

    if total == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "The uploaded file is empty.")

    # Verify the bytes match the claimed extension before trusting an extractor.
    try:
        verified_type = sniff_type(dest, ext)
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc

    doc = Document(
        id=doc_id,
        filename=file.filename,
        file_type=verified_type,
        file_path=str(dest),
        file_size=total,
        status=DocumentStatus.PENDING,
    )
    db.add(doc)
    db.commit()

    background_tasks.add_task(process_document, doc_id)

    return UploadAccepted(
        id=doc_id,
        status=DocumentStatus.PENDING,
        message=f"Document '{file.filename}' uploaded. Processing started.",
    )


@router.get("", response_model=DocumentListOut)
def list_documents(db: Session = Depends(get_db)) -> DocumentListOut:
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return DocumentListOut(
        documents=[DocumentOut.model_validate(d) for d in docs],
        total=len(docs),
    )


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, db: Session = Depends(get_db)) -> DocumentOut:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    return DocumentOut.model_validate(doc)


@router.get("/{doc_id}/pages", response_model=DocumentPagesOut)
def get_document_pages(doc_id: str, db: Session = Depends(get_db)) -> DocumentPagesOut:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    if doc.status != DocumentStatus.READY:
        raise HTTPException(400, f"Document is not ready (status: {doc.status.value}).")
    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == doc_id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    return DocumentPagesOut(
        id=doc_id,
        filename=doc.filename,
        total_pages=doc.page_count or len(pages),
        pages=[{"page_number": p.page_number, "text": p.text} for p in pages],
    )


@router.get("/{doc_id}/text")
def get_document_text(doc_id: str, db: Session = Depends(get_db)) -> dict:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    if doc.status != DocumentStatus.READY:
        raise HTTPException(400, f"Document is not ready (status: {doc.status.value}).")
    return {"id": doc_id, "filename": doc.filename, "text": doc.extracted_text or ""}


@router.post("/{doc_id}/verify")
def verify_document_quote(
    doc_id: str, body: VerifyRequest, db: Session = Depends(get_db)
) -> dict:
    """Verify whether a quote's exact (normalised) words exist in this document."""
    try:
        result = verify_quote(db, doc_id, body.quote)
    except DocumentNotReadyError as exc:
        raise HTTPException(409, str(exc)) from exc
    return result.to_dict()


@router.get("/{doc_id}/locate")
def locate_document_ranges(
    doc_id: str, ranges: str, db: Session = Depends(get_db)
) -> dict:
    """Map canonical-text ranges (``start-end``, comma-separated) to page rects."""
    parsed: list[tuple[int, int]] = []
    for part in ranges.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            start_s, end_s = part.split("-", 1)
            parsed.append((int(start_s), int(end_s)))
        except ValueError as exc:
            raise HTTPException(400, f"Invalid range '{part}'. Use 'start-end'.") from exc
    try:
        located = locate_ranges(db, doc_id, parsed)
    except DocumentNotReadyError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": doc_id, "locations": located}


@router.get("/{doc_id}/file")
def get_document_file(doc_id: str, db: Session = Depends(get_db)) -> FileResponse:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    path = Path(doc.file_path)
    if not path.exists():
        raise HTTPException(404, "Source file not found on storage.")
    media = "application/pdf" if doc.file_type == ".pdf" else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path, media_type=media, filename=doc.filename)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, db: Session = Depends(get_db)) -> Response:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    # Remove stored file; pages cascade via FK ondelete.
    Path(doc.file_path).unlink(missing_ok=True)
    invalidate_document(doc_id)
    db.delete(doc)
    db.commit()
    return Response(status_code=204)
