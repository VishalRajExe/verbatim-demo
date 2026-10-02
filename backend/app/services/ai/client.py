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


_NUMS_RE = re.compile(r"(?<![A-Za-z0-9])\d{1,3}(?![A-Za-z0-9])")


class MockClient:
    """Deterministic offline stand-in. Extracts real sentences from the chunk and
    composes an answer ONLY from the verified quotes in the prompt."""

    # Generic contract words that would otherwise match every sentence and make
    # the mock's keyword scoring useless ("agreement", "party", ...).
    _STOPWORDS = {
        "what", "when", "where", "which", "who", "why", "how", "does", "doc",
        "docs", "document", "documents", "agreement", "party", "parties",
        "this", "that", "with", "from", "under", "have", "has", "had",
        "will", "shall", "are", "was", "were", "about", "into", "over",
        "them", "they", "their", "your", "been", "being", "must", "may",
    }

    def complete(self, prompt: str) -> str:
        return "\n".join(self._compose_lines(prompt))

    def stream(self, prompt: str) -> Iterator[str]:
        text = self.complete(prompt)
        for word in re.findall(r"\S+\s*", text):
            yield word

    def complete_json(self, prompt: str) -> dict | list | None:
        if "You propose MINIMAL tracked-change edits" in prompt:
            return self._propose_edits(prompt)
        q = _extract_field(prompt, "Question:")
        doc = _extract_chunk_data(prompt)
        sentences = re.split(r"(?<=[.!?])\s+", doc)
        # Hyphen-compounds (PAGE-UNIQUE-TOKEN-087) and bare numbers (page 87)
        # must both contribute keywords, or every token sentence ties on score
        # and the mock answers with the wrong page.
        keywords = {
            part.lower()
            for word in re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*", q)
            for part in word.split("-")
            if len(part) >= 4 and part.isalpha()
        }
        numbers = {n.lstrip("0") or "0" for n in _NUMS_RE.findall(q)}
        focused = keywords - self._STOPWORDS
        if focused:
            keywords = focused
        else:
            numbers = set()
        if numbers:
            # "page 87" queries: keep the word "page" so the "Page 87 of 150"
            # marker and the page's own sentences both rise to the top.
            keywords = keywords | {"page"}
        scored = []
        for s in sentences:
            s = s.strip()
            if len(s) < 25:
                continue
            slo_s = s.lower()
            nums = {n.lstrip("0") or "0" for n in _NUMS_RE.findall(slo_s)}
            hit = sum(1 for w in keywords if w in slo_s) + sum(
                1 for n in numbers if n in nums
            )
            # Exact-page signal: "Page 87" marker lines and token identifiers
            # (…-087) both contain the digits, plain filler sentences do not.
            hit += sum(1 for n in _NUMS_RE.findall(q.lower()) if n in slo_s)
            scored.append((hit, s))
        # Richer selection than top-3: multi-section answers (e.g. an incident
        # timeline split across clauses) need more candidate sentences per
        # chunk; ties fall back to the most informative (longest) sentence.
        scored.sort(key=lambda x: (-x[0], -len(x[1])))
        quotes = [{"text": s, "why": "mock relevance"} for hit, s in scored[:5] if hit > 0]
        return {"quotes": quotes}

    def _compose_lines(self, prompt: str) -> list[str]:
        refs = re.findall(r"\[(Q\d+)\]\s*\(([^)]*)\):\s*(.+)", prompt)
        if not refs:
            return ["I could not find verified passages to answer this."]
        out = ["Based on the verified quotes:"]
        for ref, _doc, text in refs:
            out.append(f"- {text.strip()} [{ref}]")
        return out

    def _propose_edits(self, prompt: str) -> dict:
        """Offline redline proposals: swap the instruction's from-value for the
        to-value wherever the from-value literally appears in this section."""
        from app.services.redlining.instructions import (
            extract_value_tokens,
            normalize_value,
            parse_instruction,
        )

        instruction = _extract_field(prompt, "Instruction:")
        data = _extract_chunk_data(prompt)
        edits = []
        for intent in parse_instruction(instruction):
            expected = intent.expected_original
            if not expected or not intent.new_value:
                continue
            want = normalize_value(expected)
            for tok in extract_value_tokens(data):
                if normalize_value(tok) == want:
                    edits.append(
                        {
                            "target": tok,
                            "replacement": intent.new_value,
                            "reason": "mock value swap",
                        }
                    )
                    break
            else:
                # Non-numeric target: locate the phrase itself, whitespace-
                # tolerant, and copy the raw text as the verbatim target.
                pattern = re.compile(
                    r"\s+".join(re.escape(w) for w in expected.split()), re.IGNORECASE
                )
                m = pattern.search(data)
                if m:
                    edits.append(
                        {
                            "target": m.group(0),
                            "replacement": intent.new_value,
                            "reason": "mock phrase swap",
                        }
                    )
        return {"edits": edits}


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
