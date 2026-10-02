"""LLM client abstraction with a Gemini provider and an offline mock.

The real provider is Google Gemini via ``google-genai`` (credentials from env,
never logged — I-8). The mock provider is used ONLY when ``LLM_PROVIDER=mock``
(tests and offline demos); in production an unconfigured key raises rather than
fabricating answers (Rules §1.5).
"""
from __future__ import annotations

import re
from typing import Iterator, Protocol

from app.services.ai.json_parse import parse_json_lenient
from app.services.ai.retry import LLMError, retry_call


class LLMClient(Protocol):
    def complete_json(self, prompt: str) -> dict | list | None: ...
    def complete(self, prompt: str) -> str: ...
    def stream(self, prompt: str) -> Iterator[str]: ...


class GeminiClient:
    def __init__(self, api_key: str, model: str, temperature: float = 0.1) -> None:
        from google import genai  # imported lazily so mock works without it

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.temperature = temperature

    def _generate(self, prompt: str) -> str:
        cfg = {"temperature": self.temperature}
        try:
            resp = self._client.models.generate_content(
                model=self.model, contents=prompt, config=cfg
            )
        except Exception as exc:  # normalise provider errors -> retryable LLMError
            raise _to_llm_error(exc) from exc
        return resp.text or ""

    def complete(self, prompt: str) -> str:
        return retry_call(lambda: self._generate(prompt))

    def complete_json(self, prompt: str) -> dict | list | None:
        data = parse_json_lenient(self.complete(prompt))
        if data is not None:
            return data
        # One repair retry asking for strict JSON.
        repair = prompt + "\n\nReturn STRICT valid JSON only, no prose."
        return parse_json_lenient(self.complete(repair))

    def stream(self, prompt: str) -> Iterator[str]:
        try:
            for chunk in self._client.models.generate_content_stream(
                model=self.model, contents=prompt, config={"temperature": self.temperature}
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as exc:  # noqa: BLE001 - normalise provider errors
            raise _to_llm_error(exc) from exc


class MockClient:
    """Deterministic offline stand-in. Extracts real sentences from the chunk and
    composes an answer ONLY from the verified quotes in the prompt."""

    def complete(self, prompt: str) -> str:
        return "\n".join(self._compose_lines(prompt))

    def stream(self, prompt: str) -> Iterator[str]:
        text = self.complete(prompt)
        for word in re.findall(r"\S+\s*", text):
            yield word

    def complete_json(self, prompt: str) -> dict | list | None:
        q = _extract_field(prompt, "Question:")
        doc = _extract_chunk_data(prompt)
        sentences = re.split(r"(?<=[.!?])\s+", doc)
        keywords = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", q)}
        scored = []
        for s in sentences:
            s = s.strip()
            if len(s) < 25:
                continue
            hit = sum(1 for w in keywords if w in s.lower())
            scored.append((hit, s))
        scored.sort(key=lambda x: -x[0])
        quotes = [{"text": s, "why": "mock relevance"} for hit, s in scored[:3] if hit > 0]
        return {"quotes": quotes}

    def _compose_lines(self, prompt: str) -> list[str]:
        refs = re.findall(r"\[(Q\d+)\]\s*\(([^)]*)\):\s*(.+)", prompt)
        if not refs:
            return ["I could not find verified passages to answer this."]
        out = ["Based on the verified quotes:"]
        for ref, _doc, text in refs:
            out.append(f"- {text.strip()} [{ref}]")
        return out


def _extract_field(prompt: str, marker: str) -> str:
    m = re.search(re.escape(marker) + r"\s*(.+)", prompt)
    return m.group(1).strip() if m else ""


def _extract_chunk_data(prompt: str) -> str:
    # Content between the untrusted-data delimiters.
    m = re.search(r"DOCUMENT_DATA>>>\s*(.*?)\s*$", prompt, re.DOTALL)
    return m.group(1) if m else prompt


_client_singleton: LLMClient | None = None


def _to_llm_error(exc: Exception) -> LLMError:
    """Map a provider exception to our LLMError, carrying the HTTP status so
    ``retry_call`` can decide transient (429/5xx) vs hard (4xx) failures."""
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(status, int):
        return LLMError(status=status, message=str(exc))
    return LLMError(status=None, message=str(exc))


def get_llm(provider: str, api_key: str, model: str) -> LLMClient:
    global _client_singleton
    if provider == "mock":
        return MockClient()
    if not api_key:
        raise LLMError(
            status=None,
            message=(
                "The language model is not configured. Set GEMINI_API_KEY (or run "
                "with LLM_PROVIDER=mock for an offline demo)."
            ),
        )
    if _client_singleton is None:
        _client_singleton = GeminiClient(api_key=api_key, model=model)
    return _client_singleton
