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
        # Local import: app.services.qa's package __init__ imports the pipeline,
        # which imports this module — a top-level import would be circular.
        from app.services.qa.intent import matches_term

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
            # Score with the product's own relevance definition (see
            # app.services.qa.intent): an inflection of the question word
            # "governs" finds "governed", "late" does NOT find "violate", and a
            # quantity word ("percentage") is answered by a sentence carrying a
            # real number. Raw substring equality here made answering clauses
            # unreachable, and ranking without the numeric bridge let longer
            # boilerplate outrank the sentence that actually answers.
            hit = sum(1 for w in keywords if matches_term(slo_s, w)) + sum(
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
        """Offline redline proposals. Two kinds of instruction are understood:

        * explicit "from X to Y" / "replace X with Y" -- swap the from-value for
          the to-value, choosing the sentence that best matches the instruction's
          concept so a value that repeats across clauses is disambiguated, and
          returning that sentence as a verification anchor (``context``).
        * semantic state instructions ("make the liability cap mutual") -- locate
          the clause the concept points at and apply the matching generic
          drafting operation to whatever that clause actually says.

        In every case the returned ``target`` is copied verbatim from this
        section; the caller re-verifies it against the authoritative DOCX."""
        from app.services.redlining.instructions import (
            extract_value_tokens,
            find_similar_value,
            make_mutual_edit,
            normalize_value,
            parse_instruction,
            parse_semantic_instruction,
        )
        from app.services.qa.intent import (
            focus_hits,
            matches_word,
            specific_keywords,
        )

        instruction = _extract_field(prompt, "Instruction:")
        data = _extract_chunk_data(prompt)
        # Split on paragraph boundaries (newlines) first, then on sentence
        # terminals within each line. A verification anchor must live inside one
        # DOCX paragraph -- the deterministic checks match per paragraph -- so a
        # heading line must never be glued onto the clause beneath it.
        sentences = []
        for line in data.splitlines():
            for s in re.split(r"(?<=[.!?])\s+", line):
                s = s.strip()
                if s:
                    sentences.append(s)
        edits = []

        def lex_hits(sentence: str, kws: set[str]) -> int:
            """Count concept words the sentence speaks to in WORDS, not merely in
            digits.

            ``matches_word`` covers inflection; a shared four-letter prefix adds
            a light morphology bridge so "payment" reaches "pay" and "invoices"
            stays distinct from a bare numeric period. The quantity<->digit
            bridge in ``focus_hits`` is deliberately left out of this score: a
            clause that only matches because it happens to contain a number is a
            weaker locator than one that names the concept."""
            words = re.findall(r"[a-z]+", sentence.lower())
            total = 0
            for term in kws:
                if matches_word(sentence, term):
                    total += 1
                    continue
                t = term[:4]
                if any(len(w) >= 3 and (w.startswith(t) or term.startswith(w[:4])) for w in words):
                    total += 1
            return total

        def clause_key(sentence: str, kws: set[str]) -> tuple:
            """Ranking key: real-word concept match first, then the broad
            relevance score (so numeric-only clauses still rank), then the more
            substantive (longer) sentence -- so a short heading loses to the
            clause beneath it."""
            return (
                -lex_hits(sentence, kws),
                -(focus_hits(sentence, kws) if kws else 0),
                -len(sentence),
            )

        def nearest_concept_distance(sentence: str, target: str, kws: set[str]) -> int:
            """Characters between ``target`` and the closest concept word in the
            sentence (huge if none). A value that repeats across clauses is most
            likely meant by the clause whose wording sits right next to it."""
            low = sentence.lower()
            tpos = low.find(target.lower())
            if tpos < 0:
                return 10**9
            best = 10**9
            for m in re.finditer(r"[a-z]+", low):
                w = m.group(0)
                for term in kws:
                    if matches_word(w, term) or (
                        len(w) >= 3 and (w.startswith(term[:4]) or term.startswith(w[:4]))
                    ):
                        best = min(best, abs(m.start() - tpos))
                        break
            return best

        def rank_clauses(concept: str) -> list[str]:
            """Sentences matching ``concept``, best first; those with no signal
            at all are excluded."""
            kws = specific_keywords(concept or instruction)
            if not kws:
                return []
            ranked = sorted(sentences, key=lambda s: clause_key(s, kws))
            return [s for s in ranked if lex_hits(s, kws) or focus_hits(s, kws)]

        def anchor_for(target: str, concept: str) -> str:
            """The sentence containing ``target`` that best matches ``concept``.

            Ordering puts the real-word concept match first, then the distance
            from the value to that concept word (so "change the payment terms
            from 30 days" picks the clause that talks about paying near the
            figure, not another clause that merely also contains "30 days"),
            then the broader relevance score, then substance."""
            kws = specific_keywords(concept or instruction)
            want = normalize_value(target)
            candidates = [s for s in sentences if not want or want in normalize_value(s)]
            if not candidates:
                return ""
            if not kws:
                return candidates[0]
            return min(
                candidates,
                key=lambda s: (
                    -lex_hits(s, kws),
                    nearest_concept_distance(s, target, kws),
                    -(focus_hits(s, kws) if kws else 0),
                    -len(s),
                ),
            )

        # ── Type A: explicit from/to, or "change <concept> to <value>" ────────
        for intent in parse_instruction(instruction):
            new_value = intent.new_value
            if not new_value:
                continue
            expected = intent.expected_original
            if expected:
                want = normalize_value(expected)
                target = None
                for tok in extract_value_tokens(data):
                    if normalize_value(tok) == want:
                        target = tok
                        break
                if target is None:
                    # Non-numeric phrase: locate it whitespace-tolerantly.
                    pattern = re.compile(
                        r"\s+".join(re.escape(w) for w in expected.split()), re.IGNORECASE
                    )
                    m = pattern.search(data)
                    target = m.group(0) if m else None
                if target:
                    edits.append(
                        {
                            "target": target,
                            "replacement": new_value,
                            "reason": "mock value swap",
                            "context": anchor_for(target, intent.concept or instruction),
                        }
                    )
            elif intent.concept:
                # No literal original: find the clause by concept and replace the
                # value already sitting in it ("change the payment period to 60
                # days" -> the 30 days in the payment clause becomes 60 days).
                # Walk the concept-matched clauses best-first and stop at the
                # first that actually states a value, so a clause that merely
                # mentions the concept word ("subject to payment of fees") without
                # a figure never shadows the clause that does.
                for clause in rank_clauses(intent.concept):
                    existing = find_similar_value(clause, new_value, set())
                    if existing:
                        edits.append(
                            {
                                "target": existing,
                                "replacement": new_value,
                                "reason": "mock value swap",
                                "context": clause,
                            }
                        )
                        break

        # ── Type B: semantic state change (no literal from/to) ────────────────
        for sintent in parse_semantic_instruction(instruction):
            if sintent.operation != "make_mutual":
                continue
            # Walk the concept-matched clauses best-first and take the first one
            # that is actually one-sided; this skips section headings and clauses
            # that are already mutual rather than fabricating an edit.
            result = None
            clause = ""
            for candidate in rank_clauses(sintent.concept):
                found = make_mutual_edit(candidate)
                if found:
                    result, clause = found, candidate
                    break
            if not result:
                continue
            target, replacement = result
            edits.append(
                {
                    "target": target,
                    "replacement": replacement,
                    "reason": "Extend the provision to apply to both parties.",
                    "context": clause,
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
