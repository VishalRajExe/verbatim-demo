"""Persistence models for conversations, comparisons and redlines.

These store the *server-verified* products of the pipeline: every quote keeps
the canonical offsets and page range we computed (never a model-claimed one), so
history reloads faithfully and citations remain clickable.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="New chat")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, native_enum=False, length=16),
        default=MessageRole.USER,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False, default="")
    stopped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    coverage_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    quotes: Mapped[list["Quote"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", order_by="Quote.ref_index"
    )


class Quote(Base):
    """A server-verified (or explicitly unverified) quote attached to a message."""

    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    ref: Mapped[str | None] = mapped_column(String(8), nullable=True)   # "Q1"
    ref_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fail_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    message: Mapped[Message] = relationship(back_populates="quotes")


class Comparison(Base):
    __tablename__ = "comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_a_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_b_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_source: Mapped[str] = mapped_column(String(16), nullable=False, default="automatic")
    stats_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    changes: Mapped[list["ComparisonChange"]] = relationship(
        back_populates="comparison",
        cascade="all, delete-orphan",
        order_by="ComparisonChange.order_idx",
    )


class ComparisonChange(Base):
    __tablename__ = "comparison_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("comparisons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    significance: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_source: Mapped[str] = mapped_column(String(16), nullable=False, default="automatic")
    a_text: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    b_text: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    a_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    a_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    b_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    b_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    comparison: Mapped[Comparison] = relationship(back_populates="changes")


class Redline(Base):
    __tablename__ = "redlines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author: Mapped[str] = mapped_column(String(128), nullable=False, default="Legal AI")
    applied_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    dropped_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    insertions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
