"""Document processing pipeline: extraction -> persist pages -> status.

Runs as a background task, so it opens its own DB session rather than reusing
the request-scoped session.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.db.session import SessionLocal
from app.models.document import Document, DocumentPage, DocumentStatus
from app.services.citations.service import invalidate_document
from app.services.extraction import extract_document
from app.services.extraction.errors import ExtractionError

logger = logging.getLogger(__name__)


def process_document(document_id: str) -> None:
    """Extract and store a document's text, updating its processing status."""
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            logger.warning("process_document: document %s vanished", document_id)
            return

        doc.status = DocumentStatus.PROCESSING
        doc.error_message = None
        db.commit()

        path = Path(doc.file_path)
        result = extract_document(path, doc.file_type)

        # Replace any prior pages (safe for reprocessing).
        db.query(DocumentPage).filter(DocumentPage.document_id == document_id).delete()
        for page in result.pages:
            db.add(
                DocumentPage(
                    document_id=document_id,
                    page_number=page.page_number,
                    text=page.text,
                    metadata_json=page.meta or None,
                )
            )

        doc.extracted_text = result.full_text
        doc.page_count = result.page_count
        doc.status = DocumentStatus.READY
        db.commit()
        invalidate_document(document_id)  # pages changed; drop cached canonical
        logger.info(
            "Document %s processed: %d pages, %d chars",
            document_id, result.page_count, result.total_chars,
        )

    except ExtractionError as exc:
        db.rollback()
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = DocumentStatus.ERROR
            doc.error_message = exc.message
            db.commit()
        logger.info("Document %s failed extraction: %s", document_id, exc.message)
    except Exception as exc:  # noqa: BLE001 - unexpected → generic safe message
        db.rollback()
        logger.exception("Unexpected error processing %s", document_id)
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = DocumentStatus.ERROR
            doc.error_message = (
                "An unexpected error occurred while processing this document."
            )
            db.commit()
    finally:
        db.close()
