"""Pydantic schemas for conversations, comparisons and redlines.

Request bodies arrive in camelCase (read via validation_alias). Response models
use camelCase field names so JSON output is camelCase, while reading ORM rows
(by their snake_case columns) through validation_alias + from_attributes.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_ids: list[str] = Field(min_length=1, validation_alias="documentIds")
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, validation_alias="conversationId")


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    documentId: str = Field(validation_alias="document_id")
    documentName: str = Field(validation_alias="document_name")
    ref: str | None
    refIndex: int = Field(validation_alias="ref_index")
    text: str
    verified: bool
    matchKind: str | None = Field(default=None, validation_alias="match_kind")
    failReason: str | None = Field(default=None, validation_alias="fail_reason")
    start: int | None
    end: int | None
    pageStart: int | None = Field(default=None, validation_alias="page_start")
    pageEnd: int | None = Field(default=None, validation_alias="page_end")
    occurrences: int


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    role: str
    content: str
    stopped: bool
    coverage: list | None = Field(default=None, validation_alias="coverage_json")
    createdAt: datetime = Field(validation_alias="created_at")
    quotes: list[QuoteOut] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    title: str
    createdAt: datetime = Field(validation_alias="created_at")


class ConversationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    title: str
    messages: list[MessageOut] = Field(default_factory=list)


# ── Comparisons ───────────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_a_id: str = Field(validation_alias="documentAId")
    document_b_id: str = Field(validation_alias="documentBId")


class ComparisonChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    orderIdx: int = Field(validation_alias="order_idx")
    type: str
    significance: str
    category: str | None
    title: str
    summary: str
    summarySource: str = Field(validation_alias="summary_source")
    aText: str | None = Field(default=None, validation_alias="a_text")
    bText: str | None = Field(default=None, validation_alias="b_text")
    aStart: int | None = Field(default=None, validation_alias="a_start")
    aEnd: int | None = Field(default=None, validation_alias="a_end")
    bStart: int | None = Field(default=None, validation_alias="b_start")
    bEnd: int | None = Field(default=None, validation_alias="b_end")


class ComparisonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    documentAId: str = Field(validation_alias="document_a_id")
    documentBId: str = Field(validation_alias="document_b_id")
    summary: str
    summarySource: str = Field(validation_alias="summary_source")
    stats: dict | None = Field(default=None, validation_alias="stats_json")
    createdAt: datetime = Field(validation_alias="created_at")
    changes: list[ComparisonChangeOut] = Field(default_factory=list)


# ── Redlines ──────────────────────────────────────────────────────────────────

class RedlineEdit(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target: str = Field(min_length=1)
    replacement: str = Field(default="")


class RedlineRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    edits: list[RedlineEdit] = Field(min_length=1)
    author: str = Field(default="Legal AI", max_length=128)
    instruction: str | None = Field(default=None, max_length=4000)


class RedlineProposeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    instruction: str = Field(min_length=3, max_length=4000)


class ProposedEditOut(BaseModel):
    target: str
    replacement: str
    reason: str = ""
    include: bool = True


class RedlineProposeOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    documentId: str
    instruction: str
    proposed: list[ProposedEditOut] = Field(default_factory=list)
    dropped: list[dict] = Field(default_factory=list)


class RedlineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    documentId: str = Field(validation_alias="document_id")
    author: str
    instruction: str | None = None
    insertions: int
    deletions: int
    applied: list = Field(default_factory=list, validation_alias="applied_json")
    dropped: list = Field(default_factory=list, validation_alias="dropped_json")
    downloadUrl: str = Field(default="", validation_alias="download_url")
    createdAt: datetime = Field(validation_alias="created_at")
