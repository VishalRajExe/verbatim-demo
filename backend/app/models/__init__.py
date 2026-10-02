"""ORM model registry. Importing this package registers every table on Base."""
from app.models.document import Document, DocumentPage, DocumentStatus
from app.models.assistant import (
    Comparison,
    ComparisonChange,
    Conversation,
    Message,
    MessageRole,
    Quote,
    Redline,
)

__all__ = [
    "Document",
    "DocumentPage",
    "DocumentStatus",
    "Conversation",
    "Message",
    "MessageRole",
    "Quote",
    "Comparison",
    "ComparisonChange",
    "Redline",
]
