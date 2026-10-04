# ⚖️ Legal Contract Intelligence

**A grounded, citation-verified workspace for legal contracts.** Upload PDF/DOCX,
ask questions that are answered *only* from independently-verified passages,
compare two contract versions clause-by-clause, and generate a real Microsoft
Word document with native tracked changes.

> The model is **never** trusted for a quote, a page number, or an offset. Every
> citation is re-found word-for-word in the document server-side before it can
> appear in an answer. If nothing verifies, the app says so — it does not invent.

| | |
|---|---|
| **Live demo** | https://verbatim-demo.onrender.com  ·  health: https://verbatim-demo.onrender.com/health |
| **Stack** | Next.js · React · TypeScript · Tailwind → FastAPI · Pydantic · SQLAlchemy → MySQL · Google Gemini · PyMuPDF · python-docx · lxml |
| **Tests** | Backend **233 passing** (`pytest -q`) · Frontend `npm run build` clean (0 type errors) |

---

## Table of contents

- [What the app does](#-what-the-app-does)
- [Screenshots](#-screenshots)
- [Architecture](#-architecture)
- [How grounding works (the core promise)](#-how-grounding-works-the-core-promise)
- [Feature flows](#-feature-flows)
- [Running it locally](#-running-it-locally)
- [Configuration](#-configuration)
- [What is finished vs. not](#-what-is-finished-vs-not)
- [Limitations](#-limitations)
- [Project layout](#-project-layout)
- [Deployment](#-deployment)

---

## 🧭 What the app does

Four pillars, all built on the same extract → verify → compose guarantee:

1. **📚 Document library** — upload PDF/DOCX, watch it process (extract →
   canonicalise → store), browse pages/text, delete.
2. **💬 Grounded Q&A** — select one or more documents and ask questions. Answers
   stream in with clickable `[Q#]` citations that jump to the exact, verified
   passage on the real PDF page. Every answer carries a **coverage** report so a
   partial read can never masquerade as "the contract doesn't say".
3. **🔀 Contract comparison** — pick two versions; get clause-level differences
   ranked by materiality (HIGH / MEDIUM / LOW / COSMETIC) with side-by-side text
   and a conservative automatic summary.
4. **✍️ Redlining (tracked changes)** — describe an edit in plain English (or
   specify it manually) and get a downloadable `.docx` with **real Word
   `<w:ins>` / `<w:del>` revisions**. Any edit whose target isn't found exactly
   once is safely skipped and reported — never mis-applied.

---

## 🖼️ Screenshots

### Grounded answers with verified citations
Each answer quotes the document verbatim and cites `[Q1]` with the source page.
When a passage genuinely isn't in the document, the app says so instead of guessing.

![Grounded Q&A answers](docs/screenshots/qa-grounded-answers.png)

### Citation → pixel-accurate highlight on the PDF page
Clicking a citation opens a panel showing the located page with the quoted
sentence highlighted, plus the full surrounding context.

![Citation highlight panel](docs/screenshots/citation-highlight-panel.png)

### Multi-document comparison with per-quote highlighting
Compare liability caps across documents; each quote resolves to its exact page
(`verified · exact`) in the side panel.

![Compare with citation highlight](docs/screenshots/compare-citation-highlight-p56.png)

### Clause-aware comparison view
Materiality filters, a significance-ranked summary, and side-by-side baseline vs
revised clauses.

![Compare view](docs/screenshots/compare-view.png)

### Coverage & full-document reading
Every answer reports how much of the document was actually read
(`read 1/1 chunks · 150 pp · full coverage`), so confidence is never overstated.

![Coverage footer](docs/screenshots/qa-coverage.png)

### Plain-English redlining with tracked-change preview
Describe the change; each target is verified against the document before it is
proposed, then applied as a real Word revision.

![Redline proposals](docs/screenshots/redline-proposals.png)

---

## 🏗️ Architecture

```mermaid
flowchart LR
  subgraph Client["Browser"]
    UI["Next.js (App Router)<br/>/ · /chats · /compare · /redline · /documents/[id]"]
  end

  subgraph Backend["FastAPI backend"]
    DOC["Documents API<br/>upload · process · list · delete"]
    QA["QA API<br/>streaming ask + history"]
    CMP["Compare API"]
    RDL["Redline API"]
    PIPE["Grounded pipeline<br/>extract → verify → compose"]
    LLM["AI client<br/>Gemini · MockClient"]
    EXT["Extraction<br/>PyMuPDF · python-docx"]
  end

  DB[("MySQL<br/>SQLAlchemy + Alembic")]
  FS[("Local storage<br/>STORAGE_DIR")]
  G[("Google Gemini")]

  UI -->|"HTTPS / NDJSON"| DOC
  UI --> QA
  UI --> CMP
  UI --> RDL
  QA --> PIPE --> LLM --> G
  PIPE --> EXT
  DOC --> EXT --> FS
  DOC --> DB
  QA --> DB
  CMP --> DB
  RDL --> DB
```

**Routers mount under `/api`** (e.g. `/api/documents`, `/api/ask`); the health
check lives at the root `/health`.

---

## 🛡️ How grounding works (the core promise)

The single most important design rule: **the model may only copy text; the server
decides whether that text is really there.**

```mermaid
flowchart TD
  A["Question + selected documents"] --> B["Split canonical text into<br/>paragraph-aligned chunks"]
  B --> C["Per chunk (parallel, bounded):<br/>LLM returns quote TEXT only<br/>(no positions)"]
  C --> D["Server re-normalises the quote and<br/>searches it word-for-word in the<br/>canonical text of the attributed document"]
  D -->|hit| E["Verified quote<br/>real start/end + page(s) + occurrences"]
  D -->|miss| F["Unverified<br/>NOT_FOUND / TOO_SHORT / WRONG_DOCUMENT"]
  E --> G["Compose answer using ONLY verified quotes"]
  G --> H["Streaming filter drops any [Q#]<br/>whose quote did not verify"]
  H --> I["Answer + clickable citations + coverage object"]
  F --> I
```

- **Three aligned views** (`keep` exact · `join` whitespace-collapsed · `loose`
  case/punctuation-insensitive) with offset maps back to canonical coordinates, so
  extraction whitespace never wrongly rejects a real quote.
- **Coverage object** records chunks total vs read and any failures; if only part
  of a 150-page contract was readable, the answer is **forbidden** from claiming a
  clause is absent.
- If nothing verifies, the result is a deterministic "could not find" — the model
  is not even called for composition.

---

## 🔎 Feature flows

### Contract comparison

```mermaid
flowchart LR
  A["Document A + Document B"] --> B["Extract + clause segmentation"]
  B --> C["Align clauses<br/>(bigram-Dice similarity + LIS ordering)"]
  C --> D["Classify materiality<br/>HIGH / MEDIUM / LOW / COSMETIC"]
  D --> E["Side-by-side diff + conservative summary"]
```

### Redlining (tracked changes)

```mermaid
flowchart TD
  A["Plain-English instruction"] --> B{"Deterministic source-value check<br/>BEFORE any LLM call"}
  B -->|named original value absent| C["Drop · report 'not found'"]
  B -->|ok| D["LLM proposes minimal verbatim edits"]
  D --> E["Verify each target against the full DOCX run tree<br/>(paragraphs AND table cells)"]
  E -->|exactly once| F["Accept"]
  E -->|repeats · unique context pins one| F
  E -->|ambiguous / absent| G["Skip · report the reason"]
  F --> H["Apply real OOXML w:ins / w:del revisions"]
  H --> I["Downloadable .docx"]
```

The redline walks the **entire document body in reading order — including table
cells** — so the text it verifies and edits is the same content the viewer shows.

---

## 🚀 Running it locally

### Prerequisites

- **Python 3.12+** and **Node 18+**
- A **MySQL 8/9** database (or use the offline mock mode below with any local MySQL)
- A **Google Gemini API key** for real answers — *optional*: `LLM_PROVIDER=mock`
  gives a fully offline, deterministic demo with **no key and no network**.

### 1 · Backend

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Create backend/.env (gitignored). Minimum: DATABASE_URL (+ GEMINI_API_KEY for live answers).
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Migrations run automatically on startup (`run_migrations()` in the app lifespan).
Manual: `.\.venv\Scripts\python.exe -m alembic upgrade head`.

**Fully offline demo** (no Gemini key, deterministic answers):

```powershell
$env:LLM_PROVIDER = "mock"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### 2 · Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:3000  (expects the backend on :8000)
```

The frontend reads its API base from `NEXT_PUBLIC_API_URL`
(falling back to `http://127.0.0.1:8000`). Put it in `frontend/.env.local`.

### 3 · Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q      # 233 passing, no network/key needed
```

Frontend checks:

```powershell
cd frontend
npm run typecheck
npm run build
```

---

## ⚙️ Configuration

Backend config loads from **`backend/.env`** via `app/core/config.py`
(pydantic-settings). Every key has a sane default.

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `mysql+pymysql://root:admin@localhost:3306/legal_contract_intelligence` | `mysql://…` is auto-normalised to `mysql+pymysql://…` |
| `DB_CONNECT_TIMEOUT` | `10` | Fail fast on an unreachable DB instead of hanging startup |
| `GEMINI_API_KEY` | *(empty)* | Required for live answers |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | Any Gemini model works |
| `LLM_PROVIDER` | `gemini` | `mock` = offline deterministic demo (no key) |
| `LLM_MAX_CONCURRENCY` | `2` | Bounded pool for parallel chunk extraction |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Must include your frontend origin |
| `STORAGE_DIR` | `backend/data` | Writable dir for uploads + redlines |
| `MAX_FILE_SIZE_MB` | `80` | Upload cap |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | **Build-time** backend base URL (frontend) |

---

## ✅ What is finished vs. not

### Finished & tested

| Area | State |
| --- | --- |
| Env setup, config, library validation | ✅ Complete |
| Upload → process → store → read → delete (PDF/DOCX) | ✅ Complete |
| Canonical text + quote verification (keep/join/loose, offsets, page ranges, occurrences, `WRONG_DOCUMENT`) | ✅ Complete + tested |
| Single-document chat + NDJSON streaming | ✅ Complete, verified live against Gemini **and** offline via `MockClient` |
| 150-page support: chunking, coverage, partial-coverage caveats, parallel extraction | ✅ Complete + tested |
| PDF viewer + pixel-accurate citation overlay (pdf.js) + deep links | ✅ Complete |
| Multi-document Q&A with per-document verification | ✅ Complete + tested |
| Clause-aware comparison (engine + API + UI) | ✅ Complete + tested |
| Real DOCX tracked changes incl. table cells (engine + API + UI) | ✅ Complete + tested |
| Plain-English redline disambiguation + honest drop reporting | ✅ Complete + tested |
| Test suite (233 backend), typecheck, production build | ✅ Green |
| Deployment (Docker/Render + external MySQL + Vercel), live demo | ✅ Documented & running |

### Not finished / intentionally out of scope

| Area | State |
| --- | --- |
| Authentication / multi-user isolation | ❌ By design single-user |
| OCR for scanned/image PDFs | ❌ Rejected with a clear message; no OCR wired |
| DOCX pixel-geometry highlights (bounding boxes) | ⚠️ Text highlight + located page only (no paginator); PDFs get full pixel overlay |
| Gemini free-tier reliability | ⚠️ Quota-limited; transient `429/503` handled with retry + clean errors, not eliminated |
| RapidFuzz on the hot path | ⚠️ Installed but the shipped matcher is an independent bigram-Dice + LIS alignment |

---

## ⚠️ Limitations (read before relying on this)

- **DOCX has no pixel geometry.** `/locate` returns real page rectangles for
  **PDFs** (PyMuPDF), rendered as pixel highlights. DOCX has no paginated
  rendering here, so the panel shows the located page + a **text** highlight —
  reported honestly (`noGeometry: true`), never faked.
- **Live Gemini is quota-limited.** Provider HTTP errors map to a retryable
  `LLMError` (backoff on 429/5xx, clean failure on 4xx); a mid-stream failure
  surfaces as an NDJSON `error` event while the partial answer is still persisted.
- **Single-user, no auth.** No accounts, roles, or per-user data isolation.
- **Shared-DB file paths.** Uploaded files are stored on the server's local disk
  and referenced by absolute path; a document uploaded on one host isn't readable
  from another (relevant when a shared DB points at a different machine's disk).

---

## 📁 Project layout

```
backend/app/
  api/            documents · qa (streaming ask + history) · comparisons · redlines
  core/config.py
  db/session.py   engine, SessionLocal, get_db, run_migrations
  models/         document · assistant (conversation/message/quote/comparison/redline)
  schemas/        document · assistant (camelCase IO)
  services/
    text/         normalize (keep/join/loose + offset maps) · canonical
    citations/    verify_quote (pure) · service (cache + DB) · locate (page rects)
    qa/           pipeline (extract→verify→compose) · chunker · cite_filter · coverage · prompts · intent · guard
    ai/           client (Gemini + MockClient) · retry · json_parse
    comparison/   clauses · similarity · categories · materiality · align · pipeline
    redlining/    instructions · propose · tracked_changes (OOXML) · service
    extraction/   docx (body incl. tables) · pdf · signatures
  migrations/     alembic

frontend/src/
  app/            page (library) · chats · compare · redline · documents · documents/[id]
  components/     library · chat · compare · redline · viewer (PdfViewer overlay, DocxViewer) · shell · ui · common
  lib/            api/client.ts (NDJSON streaming) · types.ts
```

---

## ☁️ Deployment

Full step-by-step (Docker, Render backend, external MySQL, Vercel frontend,
offline mode) is in **[DEPLOYMENT.md](DEPLOYMENT.md)**. The public demo runs on
Render: <https://verbatim-demo.onrender.com>.

---

*Built as one unified application informed by eight reference repositories. No
reference code is copied; the algorithms were reimplemented independently.*
