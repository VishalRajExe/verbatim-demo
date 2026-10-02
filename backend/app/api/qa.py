"""Grounded Q&A API (Phase 3/6): a streaming NDJSON ask endpoint plus history.

The stream forwards the pipeline's events verbatim (status/quotes/coverage/
caveat/token/done) so the client renders progress live, and the assistant turn
(with its server-verified quotes) is persisted once the stream completes.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models.assistant import Conversation, Message, MessageRole, Quote
from app.models.document import Document, DocumentStatus
from app.schemas.assistant import (
    AskRequest,
    ConversationDetail,
    ConversationSummary,
)
from app.services.ai.client import LLMClient, get_llm
from app.services.qa.pipeline import ask_stream

logger = logging.getLogger(__name__)
router = APIRouter(tags=["qa"])


def get_llm_dep() -> LLMClient:
    settings = get_settings()
    return get_llm(settings.llm_provider, settings.gemini_api_key, settings.gemini_model)


def _load_ready_docs(db: Session, ids: list[str]) -> list[Document]:
    docs = []
    for did in ids:
        doc = db.get(Document, did)
        if doc is None:
            raise HTTPException(404, f"Document {did} not found.")
        if doc.status != DocumentStatus.READY:
            raise HTTPException(409, f"Document {did} is not ready.")
        docs.append(doc)
    return docs


@router.post("/ask")
def ask(
    body: AskRequest,
    llm: LLMClient = Depends(get_llm_dep),
) -> StreamingResponse:
    # Set up the conversation + user turn up front so ids exist before streaming.
    setup = SessionLocal()
    try:
        docs = _load_ready_docs(setup, body.document_ids)
        conv = (
            setup.get(Conversation, body.conversation_id)
            if body.conversation_id
            else None
        )
        if body.conversation_id and conv is None:
            raise HTTPException(404, "Conversation not found.")
        if conv is None:
            conv = Conversation(title=body.question[:120])
            setup.add(conv)
            setup.flush()
        user_msg = Message(
            conversation_id=conv.id, role=MessageRole.USER, content=body.question
        )
        setup.add(user_msg)
        setup.commit()
        conv_id = conv.id
        doc_ids = [d.id for d in docs]
    finally:
        setup.close()

    def event_stream():
        yield json.dumps({"type": "meta", "conversationId": conv_id}) + "\n"
        db = SessionLocal()
        answer_parts: list[str] = []
        quotes_payload: list[dict] = []
        unverified_payload: list[dict] = []
        coverage_payload: list[dict] = []
        status = "complete"
        stopped = False
        try:
            docs = [db.get(Document, did) for did in doc_ids]
            for event in ask_stream(db, docs, body.question, llm):
                etype = event.get("type")
                if etype == "token":
                    answer_parts.append(event["text"])
                elif etype == "quotes":
                    quotes_payload = event.get("quotes", [])
                    unverified_payload = event.get("unverified", [])
                elif etype == "coverage":
                    coverage_payload = event.get("coverage", [])
                elif etype == "done":
                    status = event.get("status", "complete")
                    stopped = event.get("stopped", False)
                elif etype == "error":
                    status = "error"
                yield json.dumps(event) + "\n"
        except Exception as exc:  # noqa: BLE001 - surface as an error event
            logger.exception("ask_stream failed")
            status = "error"
            yield json.dumps(
                {"type": "error", "message": "The request could not be completed."}
            ) + "\n"
        finally:
            try:
                _persist_assistant(
                    db, conv_id, "".join(answer_parts), status, stopped,
                    coverage_payload, quotes_payload, unverified_payload,
                )
            finally:
                db.close()

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _persist_assistant(
    db: Session, conv_id: str, content: str, status: str, stopped: bool,
    coverage: list[dict], quotes: list[dict], unverified: list[dict],
) -> None:
    msg = Message(
        conversation_id=conv_id,
        role=MessageRole.ASSISTANT,
        content=content,
        stopped=stopped or status == "error",
        coverage_json=coverage or None,
    )
    db.add(msg)
    db.flush()
    for q in quotes:
        db.add(
            Quote(
                message_id=msg.id,
                document_id=q["documentId"],
                document_name=q.get("documentName", ""),
                ref=q.get("ref"),
                ref_index=int((q.get("ref") or "Q0")[1:] or 0),
                text=q["text"],
                verified=True,
                match_kind=q.get("matchKind"),
                start=q.get("start"),
                end=q.get("end"),
                page_start=q.get("pageStart"),
                page_end=q.get("pageEnd"),
                occurrences=q.get("occurrences", 0),
            )
        )
    for u in unverified:
        db.add(
            Quote(
                message_id=msg.id,
                document_id=u["documentId"],
                document_name=u.get("documentName", ""),
                ref_index=0,
                text=u["text"],
                verified=False,
                fail_reason=u.get("failReason"),
            )
        )
    db.commit()


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationSummary]:
    convs = db.query(Conversation).order_by(Conversation.updated_at.desc()).all()
    return [ConversationSummary.model_validate(c) for c in convs]


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: str, db: Session = Depends(get_db)) -> ConversationDetail:
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found.")
    return ConversationDetail.model_validate(conv)


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, db: Session = Depends(get_db)) -> Response:
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found.")
    db.delete(conv)
    db.commit()
    return Response(status_code=204)
