"""Instruction-driven redline proposals with deterministic source-value safety.

Flow (mirrors the QA pipeline's trust model):
 1. Parse the instruction with pure string logic. If it names an original value
    ("from AED 500,000") that is NOT in the authoritative DOCX text, stop right
    there with an honest reason — the LLM is never even consulted, so a wrong
    value can never be silently swapped for a nearby one.
 2. Otherwise ask the model for *minimal verbatim edits* per chunk (text only,
    never positions).
 3. Verify every proposed target deterministically against the real DOCX run
    tree: exactly-one-occurrence or drop with a reason; and when the instruction
    named an original value, the surviving target must actually contain it.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from docx import Document as DocxDocument
from sqlalchemy.orm import Session

from app.models.document import Document
from app.services.ai.client import LLMClient
from app.services.qa.chunker import chunk_text
from app.services.redlining.instructions import (
    Intent,
    find_similar_value,
    normalize_value,
    parse_instruction,
    value_in_text,
)
from app.services.redlining.prompts import propose_prompt
from app.services.redlining.tracked_changes import count_occurrences


@dataclass
class ProposedEdit:
    target: str
    replacement: str
    reason: str = ""
    include: bool = True
    context: str = ""      # verbatim anchor that pins a repeated target to one clause
    occurrences: int = 1   # how many times the bare target occurs in the document
    verified: bool = True


@dataclass
class ProposeResult:
    instruction: str
    proposed: list[ProposedEdit] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "instruction": self.instruction,
            "proposed": [
                {
                    "target": e.target,
                    "replacement": e.replacement,
                    "reason": e.reason,
                    "include": e.include,
                    "context": e.context,
                    "occurrences": e.occurrences,
                    "verified": e.verified,
                }
                for e in self.proposed
            ],
            "dropped": self.dropped,
        }


def _docx_paragraph_text(source: bytes) -> tuple[DocxDocument, str]:
    document = DocxDocument(io.BytesIO(source))
    text = "\n".join(p.text for p in document.paragraphs)
    return document, text


def propose_redline(
    db: Session, doc: Document, instruction: str, llm: LLMClient, source: bytes
) -> ProposeResult:
    """Turn a plain-English instruction into verified, reviewable edit proposals."""
    from app.services.citations.service import canonical_for_document

    trimmed = instruction.strip()
    result = ProposeResult(instruction=trimmed)
    document, docx_text = _docx_paragraph_text(source)
    intents = parse_instruction(trimmed)

    # ── 1. Deterministic source-value precondition (no LLM involved) ─────────
    # An instruction naming several changes is screened intent by intent: an
    # intent whose original value is absent is rejected up front, while the
    # remaining intents still get a chance to produce verified proposals.
    satisfied: list[Intent] = []
    for intent in intents:
        expected = intent.expected_original
        if expected and not value_in_text(expected, docx_text):
            actual = find_similar_value(docx_text, expected, exclude=set())
            msg = (
                f'The specified original value "{expected}" was not found in '
                "the document."
            )
            if actual:
                msg += f' For example, the document contains "{actual}".'
            msg += " No changes were proposed for it."
            result.dropped.append({"target": expected, "reason": msg})
        else:
            satisfied.append(intent)
    if intents and not satisfied:
        return result

    # ── 2. Model proposes minimal verbatim edits, chunk by chunk ─────────────
    canonical, _ranges, _ = canonical_for_document(db, doc.id)
    raw_edits: list[dict] = []
    for chunk in chunk_text(canonical) or []:
        payload = llm.complete_json(
            propose_prompt(doc.filename, trimmed, chunk.text)
        ) or {}
        edits = payload.get("edits", []) if isinstance(payload, dict) else []
        for e in edits:
            if isinstance(e, dict):
                raw_edits.append(e)

    seen: set[tuple[str, str]] = set()
    for e in raw_edits:
        target = (e.get("target") or "").strip()
        replacement = (e.get("replacement") or "").strip()
        reason = (e.get("reason") or "").strip()
        context = (e.get("context") or "").strip()
        if not context:
            before = (e.get("contextBefore") or "").strip()
            after = (e.get("contextAfter") or "").strip()
            if before or after:
                context = f"{before}{target}{after}".strip()
        if not target:
            continue

        # ── 3. Deterministic verification against the authoritative DOCX ────
        try:
            occ = count_occurrences(document, target)
        except Exception:  # noqa: BLE001 - malformed model text is a drop, not a crash
            occ = 0
        if occ == 0:
            result.dropped.append(
                {
                    "target": target,
                    "reason": "The proposed target text was not found verbatim "
                    "in the document. Nothing was changed.",
                }
            )
            continue

        # A value that repeats across clauses (e.g. the same figure in the fee
        # clause and the liability clause) is only safe to edit when a verbatim
        # surrounding passage pins exactly one occurrence. That anchor is itself
        # re-verified to be unique; without it the edit stays ambiguous and is
        # dropped rather than guessed (never the first match).
        resolved_context = ""
        if occ > 1:
            if context and count_occurrences(document, context) == 1:
                resolved_context = context
            else:
                result.dropped.append(
                    {
                        "target": target,
                        "reason": "The target text appears more than once, so the "
                        "edit is ambiguous. Nothing was changed.",
                    }
                )
                continue
        if (target, resolved_context) in seen:
            result.dropped.append(
                {"target": target, "reason": "Duplicate of an earlier proposal."}
            )
            continue
        if replacement and replacement == target:
            result.dropped.append(
                {"target": target, "reason": "No-op: replacement equals the target."}
            )
            continue
        if not _matches_intents(target, satisfied):
            expected_label = next(
                (i.expected_original for i in satisfied if i.expected_original), ""
            )
            result.dropped.append(
                {
                    "target": target,
                    "reason": f"The proposed edit does not contain the original "
                    f'value "{expected_label}" named in the instruction. '
                    "Nothing was changed.",
                }
            )
            continue
        seen.add((target, resolved_context))
        result.proposed.append(
            ProposedEdit(
                target=target,
                replacement=replacement,
                reason=reason,
                context=resolved_context,
                occurrences=occ,
                verified=True,
            )
        )

    if not result.proposed and not result.dropped:
        if intents or any(i.new_value for i in intents):
            reason = (
                "No exact match for the requested change was found in the "
                "document. Nothing was proposed."
            )
        else:
            reason = (
                "No clause clearly matching the requested change was found, or it "
                "already satisfies the instruction. Nothing was proposed."
            )
        result.dropped.append({"target": trimmed, "reason": reason})
    return result


def _matches_intents(target: str, intents: list[Intent]) -> bool:
    """When the instruction named original value(s), the target must contain one.

    Instructions without an explicit from-value (e.g. "delete the arbitration
    clause") impose no containment requirement — they are still bound by the
    exactly-once verification.
    """
    named = [i.expected_original for i in intents if i.expected_original]
    if not named:
        return True
    norm_target = normalize_value(target)
    return any(normalize_value(v) in norm_target for v in named)
