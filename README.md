# ⚖️ Verbatim — Legal Contract Intelligence

**A grounded, citation-verified AI workspace for legal contracts.** Upload complex PDF and DOCX agreements, ask multi-clause questions answered *strictly* from independently verified passages, compare contract versions clause-by-clause with materiality scoring, and generate Microsoft Word redlines with native OpenXML (`<w:ins>` / `<w:del>`) tracked changes.

> **The Grounding Invariant:** The language model is **never** trusted for a quote, a page number, or an offset coordinate. Every citation is located and re-verified word-for-word against the canonical document on the server before it is permitted into an answer. If evidence cannot be deterministically verified, the system explicitly reports absence—it never hallucinates.

| | |
|---|---|
| **Live Demo** | [https://verbatim-demo.onrender.com](https://verbatim-demo.onrender.com) |
| **Tech Stack** | Next.js 14 · React 18 · TypeScript · Tailwind CSS → FastAPI · Pydantic v2 · SQLAlchemy 2.0 → MySQL 8/9 · Google Gemini API · PyMuPDF (fitz) · python-docx · lxml |
| **Test Suite** | Backend **233 passing** (`pytest -q`, 24 test suites) · Frontend `npm run build` clean (0 type errors, 0 ESLint warnings) |
| **Repository** | [https://github.com/VishalRajExe/verbatim-demo.git](https://github.com/VishalRajExe/verbatim-demo.git) |

---

## 📑 Table of Contents

- [System Architecture](#-system-architecture)
- [Core Pillars & Working Functions](#-core-pillars--working-functions)
- [How Grounding Works (The Core Invariants)](#-how-grounding-works-the-core-invariants)
- [Architectural Deep-Dive & Engineering Q&A](#-architectural-deep-dive--engineering-qa)
  - [1. Deterministic Quote Verification & Failure Modes](#1-deterministic-quote-verification--failure-modes)
  - [2. Handling 150+ Page Documents & Streaming Concurrency](#2-handling-150-page-documents--streaming-concurrency)
  - [3. Word Tracked Changes Redlining (Part C Implementation)](#3-word-tracked-changes-redlining-part-c-implementation)
  - [4. Future Roadmap & What to Build Next](#4-future-roadmap--what-to-build-next)
- [Feature Flows & Visual Workflows](#-feature-flows--visual-workflows)
- [Technology Stack Breakdown](#-technology-stack-breakdown)
- [Running Locally](#-running-locally)
- [Configuration Reference](#-configuration-reference)
- [Production Status Tracker](#-production-status-tracker)
- [Known Limitations](#-known-limitations)
- [Project Directory Structure](#-project-directory-structure)
- [Deployment Guide](#-deployment-guide)

---

## 🏗️ System Architecture

```mermaid
flowchart LR
  subgraph Client["Frontend Client (Next.js 14 App Router)"]
    UI["Pages & Views<br/>/ (Library) · /chats · /compare · /redline · /documents/[id]"]
    PDFV["PDF Viewer (pdf.js)<br/>Pixel Bounding Box Overlay"]
    STREAM["NDJSON Event Consumer<br/>Streaming Status & Citations"]
  end

  subgraph Backend["FastAPI Application Server"]
    DOC_API["Documents API<br/>Streaming upload · sniff_type · page extract"]
    QA_API["QA API<br/>ask_stream · session persistence"]
    CMP_API["Comparison API<br/>clause segmentation · LIS alignment"]
    RDL_API["Redlining API<br/>propose · tracked_changes"]
    
    subgraph Engine["Grounding & Processing Core"]
      PIPE["QA Pipeline<br/>extract → verify → compose"]
      NORM["Text Normalizer<br/>keep · join · loose views + offset maps"]
      VERIF["Deterministic Verifier<br/>verify_in_text (pure)"]
      EXT["Document Extractors<br/>PyMuPDF (fitz) · python-docx (runs + tables)"]
      OOXML["OOXML Engine<br/>lxml run-splitter · w:ins / w:del"]
    end

    LLM["LLM Client<br/>Google Gemini / Offline MockClient"]
  end

  DB[("MySQL 8/9 Database<br/>SQLAlchemy 2.0 + Alembic Migrations")]
  FS[("Durable / Ephemeral Storage<br/>STORAGE_DIR (PDF/DOCX blobs)")]
  GEMINI[("Google Gemini API<br/>gemini-flash-lite-latest")]

  UI -->|"HTTPS / NDJSON"| DOC_API
  UI -->|"NDJSON Stream"| QA_API
  UI -->|"REST"| CMP_API
  UI -->|"REST / Binary Download"| RDL_API
  
  DOC_API --> EXT
  EXT --> DB
  EXT --> FS
  QA_API --> PIPE
  PIPE --> LLM --> GEMINI
  PIPE --> VERIF
  VERIF --> NORM
  VERIF --> DB
  RDL_API --> OOXML
  OOXML --> FS
```

All backend routes mount under the `/api` prefix (e.g., `/api/documents`, `/api/ask`, `/api/comparisons`, `/api/redlines`), while health checks are mounted at root `/health` and `/` with fast non-blocking startup semantics.

---

## 🧭 Core Pillars & Working Functions

Verbatim provides four integrated capabilities engineered specifically for legal professionals:

### 1. 📚 Document Library & Ingestion
- **Streaming Uploads:** Ingests PDF and DOCX files up to 80MB using bounded 1MB chunked streams to prevent server memory spikes.
- **Type Sniffing:** Inspects magic bytes (`%PDF-` for PDF, `PK\x03\x04` with zip structure for DOCX) before handing control to extractors, rejecting disguised file types.
- **Dual Durability:** Writes files to disk and mirrors original bytes in a MySQL `DocumentBlob` table to ensure document viewing survives ephemeral container restarts on platforms like Render.
- **Page-Aware Storage:** Deconstructs documents page-by-page into `DocumentPage` records, capturing text and spatial page numbers for citation coordinate mapping.

### 2. 💬 Grounded Question Answering (Q&A)
- **Extract → Verify → Compose Pipeline:** The LLM never provides coordinates or page numbers. It only outputs candidate quote strings. The server locates the quote, re-verifies it word-for-word, and filters out hallucinations.
- **Clickable Citations (`[Q1]`, `[Q2]`):** Every verified quote is rendered in the chat response with a clickable citation badge that opens the real document page with pixel-accurate bounding box highlights.
- **Honest Document Coverage:** Every answer includes a coverage audit (`read 8/8 chunks · 150 pp · full coverage`). If sections fail or are omitted, the system generates an explicit caveat warning rather than asserting a clause does not exist.
- **Multi-Document Support:** Cross-document queries cross-reference quotes against each document. Misattributed quotes trigger a strict `WRONG_DOCUMENT` failure instead of being incorrectly validated.

### 3. 🔀 Clause-Aware Contract Comparison
- **Structural Clause Segmentation:** Parses documents into discrete contractual clauses based on numbered legal headers, schedules, and indentations.
- **Monotonic Sequence Alignment:** Employs bigram-Dice lexical similarity combined with Longest Increasing Subsequence (LIS) algorithms to match clauses even when sections have moved.
- **Materiality Classification:** Ranks detected changes into four materiality tiers:
  - **HIGH:** Changes in liability caps, indemnities, payment amounts, termination rights, or governing law.
  - **MEDIUM:** Alterations in notice periods, cure windows, warranties, and audit rights.
  - **LOW:** Stylistic rewording, structural renumbering, or clarified language without legal shift.
  - **COSMETIC:** Punctuation adjustments, capitalization, and whitespace differences.

### 4. ✍️ Plain-English Tracked Changes Redlining
- **Natural Language Instructions:** Users write plain-English revision prompts (e.g., *"Increase the liability cap from AED 500,000 to AED 1,000,000 and extend the notice period from 30 to 60 days"*).
- **Deterministic Precondition Verification:** Verifies that the specified original value exists in the document text before making any LLM call. If missing, it immediately rejects the edit with an honest reason.
- **Full-Body Traversal:** Traverses both regular body paragraphs and all table cells (`w:p` inside `w:tc`), ensuring fee schedules and matrices can be safely redlined.
- **Native OOXML Generation:** Edits the underlying DOCX run tree using low-level `lxml` manipulations, splitting text runs and wrapping modifications in genuine `<w:del>` (with `<w:delText>`) and `<w:ins>` tags with author attribution and UTC timestamps.

---

## 🛡️ How Grounding Works (The Core Invariants)

In high-stakes legal review, standard RAG pipelines are hazardous because language models tend to paraphrase, drop caveats, or hallucinate page numbers. Verbatim enforces seven architectural invariants:

```mermaid
flowchart TD
  Q["User Question + Selected Document(s)"] --> CHK["Split Canonical Text into<br/>Paragraph-Aligned Chunks (<=12k chars)"]
  CHK --> EXT["Extract Phase (Parallel Bounded LLM Calls)<br/>Model returns candidate quote TEXT only<br/>(No offsets, no page numbers)"]
  EXT --> NORM["Text Normalization Engine<br/>Generate keep · join · loose views<br/>with exact canonical offset maps"]
  NORM --> VERIF{"Deterministic Verifier<br/>(Exact substring check against document)"}
  
  VERIF -->|Hit in Attributed Doc| VQ["Verified Quote<br/>Canonical [start, end) + Page Number(s)"]
  VERIF -->|Found in Other Doc| WD["WRONG_DOCUMENT Flag"]
  VERIF -->|No Substring Match| NF["NOT_FOUND Flag"]
  
  VQ --> REL["Relevance & Page Gate<br/>Filter by requested page / keywords"]
  REL --> COMP["Compose Phase (Single LLM Call)<br/>Receives ONLY verified quotes as evidence"]
  COMP --> CFILT["Streaming Citation Filter<br/>Drops any unverified [Q#] references"]
  CFILT --> OUT["Final Answer + [Q#] Badges + Coverage Metadata"]
  
  NF --> COV["Coverage Caveat Engine"]
  WD --> COV
  COV --> OUT
```

- **I-1 (Quote Authority):** The model returns candidate quote text only. It is never trusted for positions, character spans, or page numbers.
- **I-2 (Deterministic Offsets):** Offsets and page spans are derived solely on the server by locating the normalized quote in the canonical document.
- **I-3 (Verified Evidence Only):** The composition prompt receives only verified quotes. Unverified quotes are permanently stripped before generation.
- **I-4 (Conservative Matching):** Verification relies exclusively on exact substring matching across three normalized coordinate views. No fuzzy or embedding distance matching is allowed on the verification path.
- **I-5 (Honest Coverage):** If document processing is partial (due to timeouts, token caps, or unreadable pages), the system forbids claiming a clause is absent.
- **I-6 (Streaming Integrity):** A real-time token filter intercepts the output stream. Any hallucinated citation token whose ID is not verified is removed before delivery to the client.
- **I-7 (Document Attribution):** Quotes must verify in the document they are attributed to. If a quote is located in a different document, it is marked `WRONG_DOCUMENT` and rejected.

---

## 🔍 Architectural Deep-Dive & Engineering Q&A

### 1. Deterministic Quote Verification & Failure Modes

#### How It Works
The language model is only ever shown the text of the quote, never its location. A deterministic verifier checks that this exact text appears in the document attributed to the quote.

1. **Canonical Reconstruction:** Raw extracted text from `DocumentPage` records is joined into a unified canonical string with an accompanying page range index (`PageRange(page_number, start_offset, end_offset)`).
2. **Three Aligned Normalized Views:** To prevent extraction artifacts (e.g., smart quotes, line-break hyphenation, ligature expansion) from rejecting real quotes, the text normalizer (`app/services/text/normalize.py`) constructs three parallel views of the canonical text:
   - **`keep` View:** Applies Unicode NFKC normalization, converts smart quotes/dashes to ASCII equivalents, strips soft-hyphens/zero-width spaces, and collapses whitespace runs to single spaces. Every character maintains a direct index pointer back to its canonical source code point.
   - **`join` View:** Detects soft line-break hyphenation (e.g., `"termi-\nnation"`) and rejoins the word without the hyphen while maintaining original offset references.
   - **`loose` View:** Completely removes all whitespace characters to match instances where PDF text extractors accidentally glue words together or insert errant spaces.
3. **Pure Functional Verification:** `verify_in_text()` in `app/services/citations/verify_quote.py` checks the candidate quote against `keep` and `join` views first (`match_kind="exact"`). If neither matches, it falls back to the `loose` view (`match_kind="loose"`). If still unfound, it returns `NOT_FOUND`.
4. **Offset to Page Resolution:** When a match is found in a view, its start and end coordinates are translated via the view's offset map back into canonical offsets, which are mapped to physical page numbers via binary search on `PageRange`.

```python
# app/services/citations/verify_quote.py
def verify_in_text(quote: str, canonical: str, ranges: list[PageRange], chunk_hint=None) -> VerifyResult:
    q = normalize_str(quote)
    if len(q) < MIN_QUOTE_CHARS:
        return VerifyResult(False, q, fail_reason=TOO_SHORT)
    if len(q) > MAX_QUOTE_CHARS:
        return VerifyResult(False, q, fail_reason=TOO_LONG)

    # Ellipsis support: segments must appear in consecutive order
    segments = _split_ellipsis(q)
    if len(segments) > 1:
        return _verify_segments(segments, canonical, ranges, q)

    keep, join, loose = build_views(canonical)

    # Exact search over keep and join views
    for view in (keep, join):
        positions = [(j, q) for j in _find_all(view.text, q)]
        if positions:
            occ = _occurrences_from_positions(positions, view, ranges)
            return VerifyResult(True, q, match_kind="exact", occurrences=occ, primary=_pick_primary(occ, chunk_hint))

    # Loose fallback (whitespace-insensitive, no character fuzzing)
    ql = normalize_loose(q)
    if ql:
        positions = [(j, ql) for j in _find_all(loose.text, ql)]
        if positions:
            occ = _occurrences_from_positions(positions, loose, ranges)
            return VerifyResult(True, q, match_kind="loose", occurrences=occ, primary=_pick_primary(occ, chunk_hint))

    return VerifyResult(False, q, fail_reason=NOT_FOUND)
```

#### Where Verification Can Fail & How Errors Are Handled
- **Paraphrasing or Near-Matches (`NOT_FOUND`):** If an LLM paraphrases a legal clause rather than quoting it verbatim, the deterministic matcher rejects it. We are deliberately conservative about fuzzy matching: an ungrounded or modified quote returns `NOT_FOUND` rather than being wrongly accepted.
- **Cross-Document Confusion (`WRONG_DOCUMENT`):** In multi-document comparisons, an LLM might attribute a clause from Master Agreement B to Schedule A. In `verify_quote_multi()`, if a quote fails on its attributed document but verifies against another active document, it is flagged as `WRONG_DOCUMENT`.
- **Length Violations (`TOO_SHORT` / `TOO_LONG`):** Quotes shorter than 20 characters (`TOO_SHORT`) or longer than 2,000 characters (`TOO_LONG`) are rejected to avoid uninformative single words or entire pages being passed as single citations.
- **Scanned Image PDFs:** PDFs without an embedded text layer produce zero extractable characters. The system detects this immediately during upload/processing and reports it explicitly as a scanned document, rather than claiming clauses were "not found".

---

### 2. Handling 150+ Page Documents & Streaming Concurrency

#### Streaming Uploads with Enforced Limits
Large contracts (e.g., 150-page credit agreements or leases) are uploaded as 1MB streaming chunks with hard size caps in `app/api/documents.py`. This ensures the server never buffers an entire 80MB file in memory.

```python
# app/api/documents.py
total = 0
max_bytes = settings.max_file_size_bytes
with dest.open("wb") as out:
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            out.close()
            dest.unlink(missing_ok=True)
            raise HTTPException(400, f"File too large (max {settings.max_file_size_mb} MB).")
        out.write(chunk)
```

#### Bounded Parallel Extraction & Sequential Verification
- **12,000-Character Paragraph Chunks:** Instead of processing a 150-page contract as a single 150,000-character prompt (which degrades LLM attention and misses critical clauses), `app/services/qa/pipeline.py` segments the canonical text into 12k-character, paragraph-aligned windows.
- **Bounded Concurrency:** Extraction calls run concurrently across chunks using a `ThreadPoolExecutor` bounded by `LLM_MAX_CONCURRENCY` (default: 2 workers). This keeps API latency low while respecting provider rate limits.
- **Thread-Safe Sequential DB Verification:** While LLM extraction is parallelized across threads, quote verification against the database is executed sequentially. SQLAlchemy `Session` instances are not thread-safe; keeping verification sequential guarantees deterministic transaction isolation and prevents session corruption.
- **Coverage Auditing & Absence Safety:** The system tracks `chunks_total`, `chunks_read`, and `failed_chunks` for every document. If any chunk fails to extract (e.g., due to rate limits or timeouts), the answer includes a `DocumentCoverage` object with an explicit caveat warning. The system warns the user that the clause may exist in unread sections, rather than falsely asserting that the contract is silent on the issue.

---

### 3. Word Tracked Changes Redlining (Part C Implementation)

#### Why Tracked Changes Were Chosen
In legal workflows, sending counsel a "clean" revised Word document destroys the entire revision history and negotiation audit trail. Lawyers require native tracked changes that open in Microsoft Word with the author's name, revision timestamps, and native Accept/Reject controls.

#### End-to-End DOCX OOXML Implementation
Because higher-level libraries like `python-docx` lack native tracked change creation APIs, Verbatim operates directly on the underlying OpenXML DOM using `lxml` in `app/services/redlining/tracked_changes.py`:
1. **Paragraph Run Splitting:** Text within DOCX files is stored inside runs (`<w:r>`). If an edit spans only a portion of a run or crosses run boundaries, `_split_at()` cuts the run at the exact character offsets without breaking run styling properties (`<w:rPr>`).
2. **Native `<w:del>` & `<w:ins>` Insertion:** The targeted runs are converted into `<w:del>` elements containing `<w:delText>` with `xml:space="preserve"`. The replacement text is inserted as an adjacent `<w:ins>` element containing a new run that inherits the font, size, and styling of the original text. Both elements receive matching `w:id`, `w:author`, and `w:date` (UTC ISO-8601) attributes.
3. **Table Cell Traversal:** Unlike `document.paragraphs` (which only returns body-level paragraphs), `_iter_paragraphs()` traverses all `w:p` elements across the document body, including those nested within table cells (`w:tc`), ensuring fee tables and liability schedules are fully redlined.

```python
# app/services/redlining/tracked_changes.py
# 3. Build the <w:del> preserving formatting
del_el = parent.makeelement(qn("w:del"), {})
del_el.set(qn("w:id"), str(rev_id))
del_el.set(qn("w:author"), author)
del_el.set(qn("w:date"), date_str)
for r in covered:
    dr = copy.deepcopy(r)
    for t in dr.findall(qn("w:t")):
        t.tag = qn("w:delText")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    parent.remove(r)
    del_el.append(dr)

# 4. Build the <w:ins> with the replacement text, cloning run props
ins_el = parent.makeelement(qn("w:ins"), {})
ins_el.set(qn("w:id"), str(rev_id + 1))
ins_el.set(qn("w:author"), author)
ins_el.set(qn("w:date"), date_str)
ins_run = ins_el.makeelement(qn("w:r"), {})
src_rpr = covered[0].find(qn("w:rPr"))
if src_rpr is not None:
    ins_run.append(copy.deepcopy(src_rpr))
ins_t = ins_run.makeelement(qn("w:t"), {})
ins_t.text = replacement
ins_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
ins_run.append(ins_t)
ins_el.append(ins_run)
```

#### The Hardest Challenge: Ambiguous Repeated Values
The most difficult engineering hurdle in automated redlining is handling repeated values. For instance, the figure *"AED 500,000"* or a period of *"30 days"* might appear across five distinct clauses (e.g., fee schedule, liability cap, insurance threshold, payment term).

- **No First-Match Guessing:** Naive redliners replace the first occurrence found in the document, which can swap a fee schedule value when the user intended to alter the liability cap.
- **Deterministic Precondition Check:** If the instruction specifies an original value (e.g., *"Change liability cap from AED 500,000 to AED 1,000,000"*), `value_in_text()` checks whether *"AED 500,000"* exists in the document before any LLM call. If missing, it immediately rejects the edit with an informative message.
- **Surrounding Context Anchoring:** If a target appears more than once (`occ > 1`), `propose.py` checks whether the surrounding context uniquely anchors the edit (`count_occurrences(document, context) == 1`). If the model did not provide a context anchor, `_derive_unique_context()` extracts keywords from the instruction and locates the specific clause by concept.
- **Safe Rejection on Ambiguity:** If multiple clauses match equally and no unique anchor can be established, the system strictly refuses to guess. The edit is dropped and reported as `ambiguous` with the occurrence count, keeping legal redlines reliable and safe.

---

### 4. Future Roadmap & What to Build Next

1. **OCR Support for Scanned PDFs:** Integrate Tesseract or cloud document AI (e.g., Google Cloud Document AI) to extract text and layout coordinates from scanned image PDFs, matching the existing pixel-overlay highlighting engine.
2. **Clause-Level Insert & Delete Redlining:** Expand the redline engine beyond word/phrase substitutions to handle full paragraph insertion, whole clause deletions, and automated renumbering of subsequent sections.
3. **Durable Asynchronous Background Workers (Celery/RQ + Redis):** Replace in-process `ThreadPoolExecutor` instances with Redis-backed task queues for background extraction and document parsing, supporting job retries, dead-letter queues, and scalable worker pools.
4. **Hybrid / Vector Search as a Candidate Generator:** Add BM25 and vector embeddings (pgvector / Milvus / Qdrant) to quickly index and retrieve candidate chunks across 500+ page archives, while preserving deterministic substring verification as the gatekeeper of truth.
5. **Production Enterprise Multi-Tenancy:** Add OAuth2 / SAML authentication, role-based access control (RBAC), multi-tenant document isolation, and granular per-user rate limiting.
6. **Interactive Accept/Reject Web UI:** Build an in-browser Word redline review panel where legal teams can toggle proposed changes, preview diffs in real-time, and download the finalized `.docx`.

---

## 🎨 Feature Flows & Visual Workflows

### Contract Comparison Workflow

```mermaid
flowchart LR
  A["Document A (Baseline) + Document B (Revised)"] --> B["Clause Segmentation Engine<br/>Header patterns & indentation trees"]
  B --> C["Monotonic Sequence Alignment<br/>Bigram-Dice similarity + LIS dynamic programming"]
  C --> D["Materiality Classifier<br/>HIGH / MEDIUM / LOW / COSMETIC"]
  D --> E["Side-by-Side Diff Presentation + Conservative Executive Summary"]
```

### Word Tracked Changes Redlining Workflow

```mermaid
flowchart TD
  A["Plain-English Instruction"] --> B{"Deterministic Precondition Check<br/>Does expected original value exist in text?"}
  B -->|Absent| C["Drop Proposal<br/>Report 'original value not found'"]
  B -->|Present / Unspecified| D["LLM Extraction Call<br/>Propose minimal verbatim target & replacement"]
  D --> E["Verify Target in DOCX Run Tree<br/>(Body paragraphs AND table cells)"]
  E -->|Count = 1| F["Accept Proposal"]
  E -->|Count > 1| G{"Surrounding Context Verification<br/>Does unique anchor isolate one occurrence?"}
  G -->|Unique Anchor Found| F
  G -->|Ambiguous / Indistinguishable| H["Drop Proposal<br/>Report 'ambiguous repeated value'"]
  E -->|Count = 0| I["Drop Proposal<br/>Report 'target not found'"]
  F --> J["Split Text Runs at Exact Offsets<br/>Inject OpenXML <w:del> and <w:ins> Revisions"]
  J --> K["Downloadable .docx with Native Word Tracked Changes"]
```

---

## 💻 Technology Stack Breakdown

### Frontend
- **Framework:** Next.js 14 (React 18, App Router architecture)
- **Language:** TypeScript 5.x (Strict mode, clean build, 0 type errors)
- **Styling:** Tailwind CSS with responsive layout grids and accessible color palettes
- **PDF Viewing:** Mozilla `pdf.js` with custom SVG/Canvas overlay for pixel-accurate citation bounding boxes
- **Streaming Client:** Custom NDJSON streaming reader (`lib/api/client.ts`) supporting live typed events (`status`, `verified`, `unverified`, `token`, `done`, `error`)

### Backend
- **Framework:** FastAPI 0.115+ (ASGI, async route handlers, streaming responses)
- **Data Validation & Settings:** Pydantic v2 & `pydantic-settings`
- **Database ORM:** SQLAlchemy 2.0 with Alembic database migrations
- **Relational Database:** MySQL 8.0 / 9.0 (PyMySQL connector with connection pooling)
- **LLM Engine:** Google Gemini API (`gemini-flash-lite-latest`) with custom retry backoff and deterministic `MockClient` for 100% offline development
- **Document Extractors:**
  - `PyMuPDF` (`fitz`): High-speed PDF page extraction, layout coordinates, and metadata parsing
  - `python-docx` & `lxml`: Low-level OOXML run tree manipulation, OpenXML schema manipulation, and document generation

---

## 🚀 Running Locally

### Prerequisites
- **Python 3.12+** (tested on 3.12, 3.13, and 3.14)
- **Node.js 18+** & `npm`
- **MySQL 8.0+** running locally (or use the offline mock provider without a database setup)

### 1. Backend Setup

```bash
cd backend

# Create virtual environment and activate
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables (.env)
cp ../.env.example .env
# Set DATABASE_URL and GEMINI_API_KEY in .env

# Run migrations (automatically run on startup, or manually):
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```

#### Completely Offline Mode (No Gemini Key or External Network Required)
You can run the entire backend deterministically without a Google Gemini API key:

```bash
# Set LLM_PROVIDER to mock
export LLM_PROVIDER=mock  # On Windows PowerShell: $env:LLM_PROVIDER="mock"
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
# Application opens at http://localhost:3000
```

Configure `frontend/.env.local`:
```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Automated Test Suite

```bash
cd backend
pytest -q
# 233 passing unit and integration tests across 24 test modules
```

To run frontend type and build checks:
```bash
cd frontend
npm run typecheck
npm run build
```

---

## ⚙️ Configuration Reference

All backend configurations are managed via `app/core/config.py` using Pydantic Settings.

| Environment Variable | Default Value | Description |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://root:admin@localhost:3306/legal_contract_intelligence` | Database connection string. Automatically handles `mysql://` to `mysql+pymysql://`. |
| `DB_CONNECT_TIMEOUT` | `10` | Database connection timeout in seconds to prevent hanging on cold starts. |
| `GEMINI_API_KEY` | `""` | Google Gemini API key. Required for live AI extraction and composition. |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | Model version for extraction and composition prompts. |
| `LLM_PROVIDER` | `gemini` | Choose `gemini` for live models or `mock` for deterministic offline testing. |
| `LLM_MAX_CONCURRENCY` | `2` | Bounded thread pool concurrency for parallel document chunk extraction. |
| `STORAGE_DIR` | `backend/data` | Local directory for storing temporary uploads and generated DOCX redlines. |
| `MAX_FILE_SIZE_MB` | `80` | Maximum allowed file upload size. |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins for the frontend. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend build-time API base URL. |

---

## ✅ Production Status Tracker

| Component | Status | Details |
|---|---|---|
| **Document Ingestion** | Complete | 1MB chunked streaming, file extension sniffing, dual disk/MySQL persistence. |
| **Deterministic Verification** | Complete | 3-tier keep/join/loose views, exact canonical offset mappings, ellipsis support. |
| **Grounded Q&A** | Complete | Streaming NDJSON, parallel extraction, citation filters, coverage warnings. |
| **PDF Citation Highlights** | Complete | Real pixel bounding box coordinates rendered on canvas via `pdf.js`. |
| **Contract Comparison** | Complete | Clause segmentation, bigram-Dice similarity, LIS alignment, materiality tiers. |
| **Word Redlines (Tracked Changes)**| Complete | Low-level OOXML `<w:ins>` / `<w:del>` elements, author/date tracking, table traversal. |
| **Disambiguation Engine** | Complete | Source-value pre-check, surrounding context anchoring, ambiguous drop safety. |
| **Automated Test Coverage** | Complete | 233 backend unit/integration tests passing; zero TypeScript errors. |
| **Cloud Deployment** | Live | Deployed on Render with external MySQL backend and automated health probes. |

---

## ⚠️ Known Limitations

- **DOCX Coordinate Geometry:** The `/locate` endpoint generates exact pixel rectangles for PDF pages via PyMuPDF. Because Microsoft Word documents lack fixed pagination geometry until rendered by a layout engine, DOCX citations are highlighted by text and located page without pixel bounding boxes (`noGeometry: true`).
- **Provider Rate Limits:** Free-tier Gemini keys are subject to per-minute rate limits. The backend handles `429` and `503` codes with exponential backoff; if exhausted, the pipeline streams a clean typed error event while preserving all verified citations found up to that point.
- **Single-User Workspace:** The current deployment operates as a single-workspace system without per-user access control or authentication partitions.

---

## 📁 Project Directory Structure

```
backend/
├── app/
│   ├── api/                  # FastAPI router endpoints
│   │   ├── documents.py      # Streaming upload, sniff, page extraction
│   │   ├── qa.py             # ask_stream endpoint & NDJSON event formatting
│   │   ├── comparisons.py    # Multi-document clause comparison
│   │   └── redlines.py       # DOCX redline proposal & download
│   ├── core/
│   │   └── config.py         # Pydantic settings & environment configuration
│   ├── db/
│   │   └── session.py        # SQLAlchemy engine, SessionLocal & background migrations
│   ├── models/               # SQLAlchemy ORM models (Document, Page, Message, Quote, etc.)
│   ├── schemas/              # Pydantic schemas (CamelCase API request/response models)
│   └── services/
│       ├── ai/               # Gemini API wrapper, retry logic, mock client
│       ├── citations/        # Pure verifier (verify_quote.py), cache service, locate
│       ├── comparison/       # Clause segmentation, bigram-Dice similarity, LIS alignment
│       ├── extraction/       # PyMuPDF and python-docx parsing engines
│       ├── qa/               # QA pipeline, chunker, intent parser, coverage auditor
│       ├── redlining/        # Tracked changes (OOXML), proposal engine, disambiguation
│       └── text/             # Canonical text normalization (keep/join/loose) & offset maps
├── migrations/               # Alembic database migration revisions
├── tests/                    # 24 test suites containing 233 test cases
├── Dockerfile                # Production container specification
├── render.yaml               # Render infrastructure-as-code deployment blueprint
└── requirements.txt          # Python dependencies

frontend/
├── src/
│   ├── app/                  # Next.js 14 App Router routes (/chats, /compare, /redline, etc.)
│   ├── components/
│   │   ├── chat/             # Message stream, citation pills, coverage footer
│   │   ├── compare/          # Side-by-side clause diffs & materiality badges
│   │   ├── redline/          # Proposal cards, disambiguation warnings, DOCX downloader
│   │   ├── viewer/           # PDF viewer with pixel highlight overlay & DOCX viewer
│   │   └── library/          # Document upload dropzone & library table
│   └── lib/
│       ├── api/client.ts     # NDJSON streaming reader & API client
│       └── types.ts          # Shared TypeScript type definitions
├── package.json
└── tsconfig.json
```

---

## ☁️ Deployment Guide

Full step-by-step instructions for containerized deployment, Render web services, managed MySQL configurations, and Vercel hosting are documented in **[DEPLOYMENT.md](DEPLOYMENT.md)**. 

The live production demonstration is publicly accessible at: **[https://verbatim-demo.onrender.com](https://verbatim-demo.onrender.com)**.

---

*Independent architectural implementation engineered for rigorous contract intelligence, citation verification, and enterprise legal safety.*
