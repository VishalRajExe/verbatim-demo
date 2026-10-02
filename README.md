# Legal Contract Intelligence

A single-user web application for analyzing legal contracts: upload PDF/DOCX,
chat with grounded, independently-verified citations, compare contract versions
for substantive changes, and generate real Microsoft Word tracked changes.

> Built as one unified application informed by eight reference repositories.
> **No reference code is copied**; the algorithms were reimplemented
> independently, and the GPL `ragadoc` repo was study-only.

## The core promise (and how it is enforced)

The model is **never** trusted for a quote, a page number, or an offset. Every
answer is produced by a server-side `extract → verify → compose` pipeline:

1. The model returns **quote text only** (no positions).
2. The backend re-normalises that text and searches it, word-for-word, in the
   **canonical text of the document it is attributed to** — computing the real
   character range and page from our own extraction, not the model's claim.
3. Composition receives **only verified quotes**. A streaming filter drops any
   `[Q#]` citation whose quote did not verify.
4. Every answer carries a **coverage object**; if any section could not be read,
   the answer is forbidden from stating that something is absent.

If nothing verifies, the answer is a deterministic "could not find" message — the
model is not called for composition and no content is invented.

## Stack

Next.js · React · TypeScript · Tailwind CSS  →  FastAPI · Pydantic · SQLAlchemy
→  MySQL · Google Gemini · PyMuPDF · python-docx · lxml · RapidFuzz

## Status (honest tracker — what actually runs vs. what is partial)

| Phase | Area | Status |
| --- | --- | --- |
| 0 | Env setup + library validation | ✅ Complete |
| 1 | Upload + processing + library | ✅ Complete (upload→process→store→read→delete) |
| 2 | Canonical text + quote verification | ✅ Complete + tested (keep/join/loose views, offset maps, ellipsis, occurrences, page ranges, WRONG_DOCUMENT) |
| 3 | Single-document chat + streaming | ✅ Complete + tested (offline `MockClient`) **and verified live against Gemini** (`gemini-flash-lite-latest`): streamed NDJSON answer with server-verified `[Q#]` citations |
| 4 | 150-page support (chunking + coverage) | ✅ Chunking, coverage object, partial-coverage caveats implemented + tested; **chunk extraction is parallelised** across a bounded pool (`LLM_MAX_CONCURRENCY`), DB verification stays serial; + a concurrency unit test |
| 5 | Viewer + citation highlighting | ✅ **pdf.js pixel overlay**: rendered PDF pages with server-verified quote rectangles drawn on top, auto-scrolled and centred into view (multi-line, page-break and repeated-quote handling via `/locate`); DOCX shows page + text highlight (no page geometry without a paginator) |
| 6 | Multi-document Q&A | ✅ Complete + tested (N docs, per-document verification incl. WRONG_DOCUMENT) |
| 7 | Contract comparison (clause alignment) | ✅ Engine complete + tested; API + UI wired |
| 8 | Real DOCX tracked changes (`w:ins`/`w:del`) | ✅ Engine complete + tested; API + UI wired (DOCX only) |
| 9 | Polish + honest docs | ✅ This README; **deployment not included** |

Backend test suite: **77 passing** (`pytest -q`). Frontend: `npm run build` is
clean (0 type errors); the citation overlay was confirmed in a browser (highlight
aligned on the printed line and auto-scrolled to centre).

## Running it

### Backend

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Copy backend/.env.example to backend/.env (gitignored) and set GEMINI_API_KEY, then:
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Migrations run automatically on startup (`run_migrations()` in the app lifespan).
To migrate manually: `.\.venv\Scripts\python.exe -m alembic upgrade head`.

Config loads from **`backend/.env`** (gitignored). All keys are optional and have
sane defaults:

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `mysql+pymysql://root:admin@localhost:3306/legal_contract_intelligence` | MySQL 8 |
| `GEMINI_API_KEY` | *(empty)* | Required for real answers |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | Inexpensive; any Gemini model works |
| `LLM_PROVIDER` | `gemini` | Set `mock` for a fully offline demo (no key needed) |
| `LLM_MAX_CONCURRENCY` | `2` | Bounded pool for parallel chunk extraction |
| `MAX_FILE_SIZE_MB` | `80` | |

### Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:3000  (expects backend on :8000)
```

Set `NEXT_PUBLIC_API_URL` if the backend is not on `http://127.0.0.1:8000`.

### Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Tests run against the configured MySQL database. They use the deterministic
`MockClient` (via a dependency override on `/api/ask`), so **no network or API
key is required** to prove the whole pipeline and HTTP paths.

## What works today (functional map)

- **Library** (`/`): upload PDF/DOCX, status polling, pages/text/file, delete.
- **Ask & chats** (`/chat`): select one or more ready documents, ask a question,
  watch it stream (reading progress → verified quotes → coverage → answer with
  clickable `[Q#]` citations), and reopen past conversations from the rail.
- **Citation highlight**: clicking a `[Q#]` citation opens a panel with the verified
  passage rendered on the actual PDF page via pdf.js, with a pixel-accurate yellow
  overlay auto-scrolled into view; "Open full ↗" deep-links the document viewer
  (`/documents/[id]?ranges=start-end`) to the same highlighted passage.
- **Compare** (`/compare`): pick two documents; get clause-level, significance-
  ranked differences (HIGH/MEDIUM/LOW/COSMETIC) with side-by-side clause text and
  a conservative automatic summary.
- **Redline** (`/redline`): target exact text in a DOCX and produce a downloadable
  `.docx` with real Word tracked changes. Edits whose target is not unique are
  skipped and reported, never mis-applied.

## Limitations (read before relying on this)

- **Live Gemini has been exercised** here (`gemini-flash-lite-latest`) and streamed
  verified answers, but it is quota-limited and transient errors happen: some
  models returned `429 RESOURCE_EXHAUSTED` / `503` during testing. Provider HTTP
  errors are mapped to a retryable `LLMError` (backoff on 429/5xx, clean failure on
  4xx), and a mid-stream failure surfaces as an NDJSON `error` event while the
  partial answer is still persisted — not a crash.
- **DOCX has no pixel geometry.** `/locate` returns real page rectangles for **PDFs**
  (PyMuPDF), which the pdf.js overlay renders as pixel highlights. DOCX files have no
  paginated rendering (LibreOffice is not available here), so the panel shows the
  located page and a **text** highlight rather than a bounding box. This is reported
  honestly (`noGeometry: true`), never faked.
- **Scanned/image PDFs** are rejected with a clear error (no OCR is wired).
- **No authentication / multi-user isolation** — this is a single-user workspace by
  design.
- **Deployment** (Docker, Railway/Render, CI) is **not** part of this workspace.
- **RapidFuzz** is installed but the shipped matcher uses an independent
  bigram-Dice + LIS alignment; RapidFuzz is not on the hot path.

## Design notes (how it works, where it can fail)

**Quote verification.** The model only ever returns candidate quote *text*. For each
one the server (a) normalises both the quote and the document into three aligned
views — `keep` (exact), `join` (whitespace collapsed) and `loose` (case-insensitive,
punctuation-insensitive) — with offset maps back to canonical coordinates, then (b)
searches the attributed document's canonical text word-for-word. A hit yields the
authoritative `[start, end)` range, page(s), and the number of occurrences; a miss is
labelled `NOT_FOUND`/`TOO_SHORT` and shown only as *unverified*, never as grounding.
Whitespace and line-break differences from extraction are absorbed by the `join`/`loose`
views, so genuinely-present quotes are not wrongly rejected. This can still fail when a
model *paraphrases* (words not in the document at all → correctly dropped) or quotes text
that exists only across a page/section boundary in a way the matcher can't bridge; the
answer simply loses that citation and coverage tells the user the read was partial.

**Large documents.** Canonical text is split into paragraph-aligned chunks (capped by
`CHUNK_MAX_CHARS`) that each keep absolute offsets. Extraction fans out across a bounded
thread pool (`LLM_MAX_CONCURRENCY`); each chunk returns quotes that are then verified
serially against the DB. A `DocumentCoverage` object records chunks total vs read and any
failed chunks; the `caveat()` and deterministic not-found text are derived from it, so if
only part of a 150-page contract was readable the app is **forbidden** from confidently
claiming a clause is absent — the worst-case output the brief calls out.

**Part C — Option 1 (tracked-change redlining).** Chosen because it produces a
concrete, inspectable artefact (a real `.docx`) and is fully achievable offline without
an LLM tool-loop. Edits are applied as genuine OOXML `<w:ins>`/`<w:del>` revisions via
lxml: the target run is located even when the text is split across several runs of
different formatting, run properties are preserved, and only the affected text is
touched — no full-document regeneration or renumbering. Multiple edits apply in one
pass; an edit whose target is not unique (or absent) is skipped and reported rather
than mis-applied. The hardest parts were splitting a replacement across run boundaries
while keeping the surrounding formatting, and guaranteeing the file still opens cleanly
in Word/LibreOffice.

## Layout

```
backend/app/
  api/         documents, qa (streaming ask + history), comparisons, redlines
  core/config.py
  db/session.py            engine, SessionLocal, get_db, run_migrations
  models/                  document, assistant (conversation/message/quote/comparison/redline)
  schemas/                 document, assistant (camelCase IO)
  services/
    text/                  normalize (keep/join/loose + offset maps), canonical
    citations/             verify_quote (pure), service (cache + DB), locate (page rects)
    qa/                    pipeline (extract→verify→compose), chunker, cite_filter,
                           coverage, prompts
    ai/                    client (Gemini + MockClient), retry, json_parse
    comparison/            clauses, similarity, categories, materiality, align, pipeline
    redlining/             tracked_changes (OOXML), service (apply + save)
  migrations/              alembic
frontend/
  app/                     page (library), chat, compare, redline, documents/[id]
  features/                library, chat, compare, redline, viewer (PdfViewer: pdf.js overlay)
  lib/                     api.ts (incl. NDJSON streaming), types.ts
```
