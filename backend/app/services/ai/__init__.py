"""AI provider abstraction (Gemini + offline mock) with tolerant JSON and retry."""
from app.services.ai.client import (
    GeminiClient,
    LLMClient,
    MockClient,
    get_llm,
)
from app.services.ai.json_parse import parse_json_lenient
from app.services.ai.retry import LLMError, is_retryable, retry_call

__all__ = [
    "LLMClient",
    "GeminiClient",
    "MockClient",
    "get_llm",
    "parse_json_lenient",
    "LLMError",
    "retry_call",
    "is_retryable",
]
