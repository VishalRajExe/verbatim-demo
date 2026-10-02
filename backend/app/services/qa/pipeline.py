"""The question-answering pipeline (Architecture §8): extract -> verify -> compose.

This generator is the whole product's spine and enforces the invariants:
 - the model returns quote TEXT only; we verify it against the attributed
   document's canonical text on the server (I-1, I-2, I-7);
 - compose sees ONLY verified quotes (I-3);
 - every answer carries a coverage object and never overclaims absence (I-5).

It yields NDJSON-ready event dicts; the route turns them into a stream and the
persistence layer stores messages/quotes.
"""
from __future__ import annotations

import re
from typing import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.services.ai.client import LLMClient
from app.services.citations.service import verify_quote
from app.services.qa.chunker import chunk_text
from app.services.qa.cite_filter import CitationFilter
from app.services.qa.coverage import DocumentCoverage, caveat, not_found_message
from app.services.qa.prompts import compose_prompt, extract_prompt

# On very large documents the extract phase can surface hundreds of verified
# quotes. Compose is capped to the top-N most relevant to the question
# (deterministic word-overlap ranking, original order as tie-break) so answers
# stay focused and the prompt stays bounded.
_MAX_COMPOSE_QUOTES = 24


def _rank_quotes(verified: list[dict], question: str) -> list[dict]:
    # Always sort by relevance (stable, original order as tie-break), then
    # cap the list. On small sets this merely moves exact matches forward.
    qlo = question.lower()
    terms = {
        p for w in re.findall(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*", qlo)
        for p in w.split("-") if len(p) >= 4 and p.isalpha()
    }
    numbers = {n.lstrip("0") or "0" for n in re.findall(r"(?<![a-z0-9])\d{1,3}(?![a-z0-9])", qlo)}
    scored = []
    for i, v in enumerate(verified):
        slo = v["text"].lower()
        parts = {
            p for w in re.findall(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*", slo)
            for p in w.split("-")
        }
        nums = {n.lstrip("0") or "0" for n in re.findall(r"(?<![a-z0-9])\d{1,3}(?![a-z0-9])", slo)}
        hit = sum(1 for t in terms if t in parts) + sum(1 for n in numbers if n in nums)
        scored.append((-hit, i, v))
    scored.sort()
    return [v for _, _, v in scored[:_MAX_COMPOSE_QUOTES]]


def ask_stream(
    db: Session,
    documents: list[Document],
    question: str,
    llm: LLMClient,
) -> Iterator[dict]:
    coverages: list[DocumentCoverage] = []
    verified: list[dict] = []          # will be numbered Q1..Qn
    unverified: list[dict] = []
    seen_ranges: set[tuple[str, int, int]] = set()

    # ── EXTRACT ──────────────────────────────────────────────────────────────
    # Network-bound LLM extraction runs concurrently across chunks; the DB-backed
    # verification is deliberately serial because a SQLAlchemy Session is not
    # thread-safe (I-1..I-7 hold unchanged). Plan order is preserved so Q1..Qn
    # numbering is stable regardless of the order chunks finish in.
    plan: list[dict] = []
    for doc in documents:
        canonical, _page_ranges, _ = _canonical(db, doc)
        chunks = chunk_text(canonical) or []
        cov = DocumentCoverage(
            document_id=doc.id, name=doc.filename,
            chunks_total=len(chunks), chunks_read=0, pages=doc.page_count or 0,
        )
        coverages.append(cov)
        for ci, chunk in enumerate(chunks):
            plan.append({"cov": cov, "ci": ci, "doc": doc, "chunk": chunk})

    total = len(plan)
    raw_by_index: dict[int, list] = {}
    concurrency = max(1, int(get_settings().llm_max_concurrency))
    if total:
        pool = ThreadPoolExecutor(max_workers=min(concurrency, total))
        try:
            futures = {
                pool.submit(
                    _extract_one, llm, item["doc"].filename, question,
                    item["chunk"].text,
                ): i
                for i, item in enumerate(plan)
            }
            done = 0
            for fut in as_completed(futures):
                i = futures[fut]
                item = plan[i]
                done += 1
                try:
                    raw_by_index[i] = fut.result()
                    item["cov"].chunks_read += 1
                except Exception:  # noqa: BLE001 - one failed chunk lowers coverage
                    item["cov"].failed_chunks.append(item["ci"])
                yield {
                    "type": "status", "stage": "reading", "documentId": item["doc"].id,
                    "documentName": item["doc"].filename, "done": done, "total": total,
                }
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    for i, item in enumerate(plan):
        doc = item["doc"]
        chunk = item["chunk"]
        for rq in raw_by_index.get(i, []):
            text = (rq.get("text") or "").strip() if isinstance(rq, dict) else str(rq)
            if not text:
                continue
            res = verify_quote(
                db, doc.id, text, chunk_hint=(chunk.start, chunk.end)
            )
            if res.verified and res.primary:
                key = (doc.id, res.primary.start, res.primary.end)
                if key in seen_ranges:
                    continue
                seen_ranges.add(key)
                verified.append(
                    {
                        "documentId": doc.id, "documentName": doc.filename,
                        "text": text, "verified": True,
                        "matchKind": res.match_kind,
                        "start": res.primary.start, "end": res.primary.end,
                        "pageStart": res.primary.page_start,
                        "pageEnd": res.primary.page_end,
                        "occurrences": len(res.occurrences),
                    }
                )
            else:
                unverified.append(
                    {
                        "documentId": doc.id, "documentName": doc.filename,
                        "text": text, "verified": False,
                        "failReason": res.fail_reason,
                    }
                )

    # Number verified quotes and emit the quote + coverage events.
    verified = _rank_quotes(verified, question)
    for i, v in enumerate(verified, start=1):
        v["ref"] = f"Q{i}"
    yield {
        "type": "quotes",
        "quotes": [
            {
                "ref": v["ref"], "documentId": v["documentId"],
                "documentName": v["documentName"], "text": v["text"],
                "verified": True, "matchKind": v["matchKind"],
                "start": v["start"], "end": v["end"],
                "pageStart": v["pageStart"], "pageEnd": v["pageEnd"],
                "occurrences": v["occurrences"],
            }
            for v in verified
        ],
        "unverified": unverified,
    }
    yield {"type": "coverage", "coverage": [c.to_dict() for c in coverages]}

    warn = caveat(coverages)
    if warn:
        yield {"type": "caveat", "message": warn}

    # ── COMPOSE ──────────────────────────────────────────────────────────────
    verified_ids = {int(v["ref"][1:]) for v in verified}
    cf = CitationFilter(verified_ids)

    if not verified:
        # Deterministic, no model call. Never invents content.
        yield {"type": "token", "text": not_found_message(coverages)}
        yield {"type": "done", "status": "complete", "stopped": False}
        return

    prompt = compose_prompt(question, verified, multi=len(documents) > 1)
    stopped = False
    try:
        for tok in llm.stream(prompt):
            safe = cf.feed(tok)
            if safe:
                yield {"type": "token", "text": safe}
    except GeneratorExit:
        stopped = True
        raise
    tail = cf.flush()
    if tail:
        yield {"type": "token", "text": tail}
    yield {"type": "done", "status": "stopped" if stopped else "complete",
           "stopped": stopped}


def _extract_one(llm: LLMClient, filename: str, question: str, text: str) -> list:
    """Run one network-bound extraction for a chunk. Raises on provider error so
    the caller can lower that document's coverage; touches no shared DB state."""
    payload = llm.complete_json(extract_prompt(filename, question, text)) or {}
    return payload.get("quotes", []) if isinstance(payload, dict) else []


def _canonical(db: Session, doc: Document):
    # Local import to avoid a cycle with the citations service on package init.
    from app.services.citations.service import canonical_for_document

    return canonical_for_document(db, doc.id)
