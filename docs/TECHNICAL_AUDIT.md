# Phase 0 — Technical Audit & Reference Mapping

This document records the study of the eight supplied reference repositories and
the design decisions for the unified **Legal Contract Intelligence** application.
Per the build brief, **no reference code is copied** — algorithms and architecture
patterns are understood here and reimplemented cleanly in our own codebase. The
GPL-licensed `ragadoc-main` was treated as read-and-study reference only.

---

## 1. Environment / toolchain decisions

| Concern | Finding | Decision |
| --- | --- | --- |
| Python | `python` on PATH is the MS Store stub; real interpreters via `py`: **3.14.6**, **3.13.3**, plus `uv`-managed 3.12.13. | Target **Python 3.13.3**. 3.14 is too new for compiled wheels (PyMuPDF/lxml/pydantic-core). |
| Package manager | `uv 0.11.21` available. | Use `uv venv` + `uv pip` for fast, reproducible installs. |
| Node | v24.19.0, npm 11.17.0. | Use for Next.js frontend. |
| MySQL | MySQL Community **9.6.0** installed locally at `C:\Program Files\MySQL\...`. | Use local MySQL for dev; `DATABASE_URL` env var for prod (Aiven/Railway). |
| File type sniffing | `legal-lens` used `python-magic`, which needs a native DLL and is a known Windows pain point. | **Avoid python-magic.** Validate by extension + magic-byte signature sniffing (PDF `%PDF`, DOCX is a ZIP `PK\x03\x04`). |

**Phase 0 gate result:** all 14 required libraries import and pass functional
smoke tests (PyMuPDF write→extract, python-docx multi-run paragraph, rapidfuzz
scoring, lxml OOXML namespace query). See `backend/scripts/validate_env.py`.

---

## 2. Reference mapping (what each repo contributes)

### legal-lens-main — PRIMARY BASE (architecture)
- **Stack in reference:** FastAPI + MongoDB (motor) + ChromaDB + sentence-transformers + React/Vite SPA. Multi-tenant, JWT auth, orgs, roles, audit log.
- **Useful patterns adopted:**
  - `core/settings.py`: `pydantic-settings` `BaseSettings` singleton via `@lru_cache`, data-dir auto-creation, `.env` loading.
  - Upload flow in `routers/documents.py`: extension whitelist → streamed size-cap (1 MB chunks) → MIME sniff → uuid filename → persist → `BackgroundTasks` processing → status transitions (`pending → processing → ready/error`) with `error_message`.
  - Layered service split: `extraction`, `chunker`, `vector_store`, `rag_engine`, `search_engine`, `ai_features`.
  - `main.py` lifespan pattern (connect on startup, close on shutdown), CORS middleware.
- **Intentionally NOT carried over:** MongoDB → **MySQL + SQLAlchemy**; multi-user auth/orgs/roles/JWT → **single-user, no auth**; ChromaDB + sentence-transformers embeddings → **deterministic lexical + fuzzy retrieval** (per brief: "deterministic retrieval before LLM reasoning", and embeddings are optional). Legacy analytics/audit/bookmarks/demo features dropped.

### rag-over-pdf-main — RAG + streaming reference
- Page-level extraction with document IDs attached to each chunk (must preserve `document_id` per chunk) — adopted.
- Token streaming of answers to the client; scanned-PDF detection (zero extractable chars → treat as failure, not empty success) — adopted as a hard rule.

### rag-contract-analyzer-main — evidence discipline reference
- Refuse when evidence insufficient ("couldn't find sufficient information"). Adopted verbatim as behavior.
- Deterministic retrieval **before** LLM reasoning; page-cited answers; comparison "significance" concept. Adopted.

### ragadoc-main — STUDY ONLY (GPL). Do not copy.
- Concept for citation→PDF-location mapping: extracted text ↔ normalized text ↔ original page spans ↔ coordinates. Reimplemented independently using PyMuPDF span rects (Phase 5).

### react-pdf-highlighter-extended-main — viewer reference (MIT-style; deps: pdfjs-dist 4.x, react-rnd)
- Reference for PDF render, text-selection, highlight-layer, page navigation. For Phase 5 we will drive **pdfjs-dist** directly and render backend-computed highlight rects, so we control exact positioning rather than trusting a library's own text search.

### eula-diff-main — clause diff + redline ALGORITHMS (Go, reimplement in Python)
- **normalize**: NFKC → drop Cf/control chars (keep \n,\t) → unify curly quotes/dashes/ellipsis/nbsp → de-hyphenate line breaks → strip page furniture (`page N`, bare numbers) → collapse spaces/blank lines. Preserves paragraph structure.
- **fold**: lowercase, keep only `[a-z0-9]`, collapse whitespace → comparison key (never for display). This is the backbone of whitespace-tolerant **quote verification** (Phase 2).
- **segment.Split**: clause segmentation via numbered (`9.`/`4.2`/`12)`), lettered (`a.`), labeled (`Section 9:`/`Article IV`), ALL-CAPS banner, and title-case heading heuristics; preceding content becomes a synthetic `Preamble`.
- **align.Align**: greedy best-match pairing using blended similarity `0.4*jaccard(heading) + 0.6*jaccard(body)`, threshold `0.4`. `classify`: fold-equal + same number/order → Unchanged; fold-equal but number/order shifted → **Moved** (this is the false-positive suppression the brief demands); else Modified with a word-level redline.
- **redline.Diff**: word-level LCS (`\S+\s*|\s+` tokenizer so join == original) → merged `eq/del/ins` ops.

### compare-cli-main — clause-aware classification reference (Node/.mjs)
- `classifyDiff`: `clean` / `cosmetic` (equal after `cosmeticNormalize`) / `typographic` / `substantive`.
- `cosmeticNormalize` de-noises number formatting: `1,000`→`1000`, `5.0`→`5`, `, and`/`, or`→` and`/` or` — so `AED 100,000` vs `AED 1,000,000` is NOT cosmetic (real digit change survives normalization) while reflow/quote style is.
- Reads existing DOCX track changes (`w:ins`/`w:del`) via zip for ground truth.

### contract_comparison-main — severity + comparison UX reference
- difflib `SequenceMatcher` opcodes → change records with `category` (Textual/Formatting/Visual), `severity` (delete→High, replace→Medium, insert→Medium), old/new text, section.
- Formatting comparator over paragraph/run signatures (font, size, bold, italic, …) — informs our severity model; **not** copied (brief warns against reproducing its scoring/UI blindly).

---

## 3. Substantive-change heuristic for our comparison (Phase 7)
A change is escalated to **Substantive / High** when any of:
- a **number, money amount, or date** changes value (not just formatting — reuse `cosmeticNormalize` logic),
- a **modal/negation** flips: `shall`↔`may`, add/remove `not`, `must`, `will`,
- a **party name / defined term** changes,
- a whole clause is **added or removed**,
- duration/threshold terms change (`30 days`, `12 months`, liability caps).
Cosmetic = whitespace, line-wrap, quote/dash style, punctuation-only, numbering-only-with-same-text.

---

## 4. Target architecture (unified)

```
Next.js (frontend)  ──HTTP/SSE──▶  FastAPI (backend)  ──SQLAlchemy──▶  MySQL
        │                                  │
   pdfjs viewer                    document processing layer
   (backend-computed rects)        PyMuPDF / python-docx / lxml / rapidfuzz
                                           │
                                     Gemini (reasoning only)
```

Responsibility separation (brief §40): **Gemini = reasoning/summarize/propose**;
**Backend = source of truth**: extraction, retrieval, quote verification,
citation coordinates, comparison, DOCX manipulation. The LLM is never trusted for
quotes/pages/offsets — every citation is re-verified against stored document text.

### Canonical data model (MySQL, brief §10)
`documents`, `document_pages`, `document_chunks`, `chat_sessions`,
`chat_messages`, `citations`, `comparisons`, `comparison_items`, `redline_jobs`.

### Quote-verification pipeline (brief §11–13 — highest priority)
1. Receive AI candidate `{quote, document_id, page_hint}` (Pydantic-validated, treated as untrusted).
2. `fold()` candidate + load stored `normalized_text` for that document.
3. Exact-substring on normalized form → else rapidfuzz sliding-window ≥ threshold.
4. Map normalized match offsets back to original page text; confirm against ORIGINAL text.
5. Multiple occurrences → score by `page_hint` + surrounding context; if still ambiguous, mark `verified=false` rather than invent a location.
6. Verified → store `page_start/end`, `start_offset/end_offset`; unverified → never shown as verified.

---

## 5. Planned API surface (brief §31)
`POST /api/documents/upload`, `GET /api/documents`, `GET/DELETE /api/documents/{id}`,
`GET /api/documents/{id}/pages`, `GET /api/documents/{id}/text`,
`GET /api/documents/{id}/file`, `GET /api/documents/{id}/citations/{cid}/location`,
`POST /api/chat/stream` (SSE), `GET /api/chat/{sessionId}`,
`POST /api/compare`, `GET /api/compare/{id}`,
`POST /api/redline`, `GET /api/redline/{id}/download`.

---

## 6. Phase plan mapping (brief §36)
- P1 upload/extraction/library · P2 canonical text + quote verification ·
  P3 single-doc chat + Gemini streaming · P4 150-page retrieval + coverage ·
  P5 viewer + citation highlight · P6 multi-doc Q&A · P7 comparison ·
  P8 tracked changes (`w:ins`/`w:del`) · P9 polish + deploy.

A phase is "done" only when it **runs**, not when files exist (brief §45).
