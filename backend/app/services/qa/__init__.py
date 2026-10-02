"""Grounded QA pipeline package: chunking, coverage, citation filtering, prompts."""
from app.services.qa.chunker import Chunk, chunk_text, coverage_of
from app.services.qa.cite_filter import CitationFilter
from app.services.qa.coverage import (
    DocumentCoverage,
    caveat,
    not_found_message,
)
from app.services.qa.pipeline import ask_stream
from app.services.qa.prompts import compose_prompt, extract_prompt

__all__ = [
    "Chunk",
    "chunk_text",
    "coverage_of",
    "CitationFilter",
    "DocumentCoverage",
    "caveat",
    "not_found_message",
    "ask_stream",
    "extract_prompt",
    "compose_prompt",
]
