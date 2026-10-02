"""Pydantic schemas for document API responses."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    file_size: int = Field(ge=0)
    page_count: int | None = None
    status: DocumentStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]
    total: int


class DocumentPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_number: int
    text: str


class DocumentPagesOut(BaseModel):
    id: str
    filename: str
    total_pages: int
    pages: list[DocumentPageOut]


class UploadAccepted(BaseModel):
    id: str
    status: DocumentStatus
    message: str


class VerifyRequest(BaseModel):
    quote: str = Field(min_length=1, max_length=8000)
