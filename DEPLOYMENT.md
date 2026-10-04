# Deployment Guide — Legal Contract Intelligence

This document explains how to take the app from a working local project to a
live deployment. It is written for the stack actually in this repo:

| Layer | Technology | Recommended host |
|---|---|---|
| Frontend | Next.js 16 (App Router) / React 19 | **Vercel** |
| Backend API | FastAPI + Uvicorn (Python 3.12) | **Render** (Docker — image pins Python 3.12) |
| Database | MySQL 8/9 (SQLAlchemy + Alembic) | **External managed MySQL** (Render has no managed MySQL) |
| AI | Google Gemini (`google-genai`) | Google AI Studio API key |
| File storage | Local filesystem (`STORAGE_DIR`) | Render persistent disk (or object storage, see notes) |

```
Browser ──▶ Vercel (Next.js)  ──HTTPS/NDJSON──▶  Render (FastAPI /api/*)  ──▶  Managed MySQL
                                                     │
                                                     └──▶ Gemini API (answers) + STORAGE_DIR (uploads/redlines)
```

---

## 1. Prerequisites

- A Google Gemini API key ([aistudio.google.com](https://aistudio.google.com)).
- A managed **MySQL** database (any of: PlanetScale, Aiven for MySQL, Railway
  MySQL, TiDB Cloud, ClearDB, or your own MySQL host). Note the connection URL.
- Accounts on **Render** and **Vercel**, plus the GitHub repo
  (`https://github.com/VishalRajExe/verbatim-demo.git`).
- For the fully **offline demo** (no Gemini, no external DB cost) see §8.

---

## 2. Environment variables (single source of truth)

The backend reads everything from environment variables via
`backend/app/core/config.py` (pydantic-settings). A real `.env` file is
git-ignored; `backend/.env.example` and the root `.env.example` are safe
templates.

| Variable | Used by | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | backend | local MySQL | `mysql://…` is auto-normalised to `mysql+pymysql://…`. |
| `DB_CONNECT_TIMEOUT` | backend | `10` | Seconds to wait for the MySQL connect/AUTH handshake before failing fast (prevents an infinite startup hang). |
| `GEMINI_API_KEY` | backend | *(empty)* | Required for live answers. |
| `GEMINI_MODEL` | backend | `gemini-flash-lite-latest` | |
| `LLM_PROVIDER` | backend | `gemini` | `mock` = offline deterministic demo (no key). |
| `CORS_ORIGINS` | backend | `["http://localhost:3000"]` | JSON list; must include your frontend origin. |
| `STORAGE_DIR` | backend | `backend/data` | Writable dir for uploads + redlines. |
| `MAX_FILE_SIZE_MB` | backend | `80` | Upload cap. |
| `NEXT_PUBLIC_API_URL` | frontend | `http://localhost:8000` | **Build-time** base URL of the backend. |

The frontend derives its API base from `NEXT_PUBLIC_API_URL`
(`frontend/src/lib/api/client.ts`), falling back to `http://127.0.0.1:8000`.

---

## 3. Database (managed MySQL)

1. Provision a MySQL database and create a schema named
   `legal_contract_intelligence` (or whatever you use in the URL).
2. Copy the provider connection string into `DATABASE_URL`.
   - PlanetScale / ClearDB give `mysql://user:pass@host:port/db`.
   - **Aiven** gives `mysql://avnadmin:…@host:22308/defaultdb?ssl-mode=REQUIRED`.
   - The app automatically rewrites the scheme to `mysql+pymysql://` **and**
     strips JDBC-only TLS params like `ssl-mode=…` (which PyMySQL rejects with
     `unexpected keyword argument 'ssl-mode'`), translating them into a proper
     TLS connection. So you can paste your provider's string **as-is**.
   - To pin a CA instead of TLS-without-verification, use the real PyMySQL
     param `ssl_ca=/path/ca.pem` (kept untouched by the normaliser).
3. **You do not run migrations manually.** On every backend start the app calls
   Alembic (`run_migrations()` in the FastAPI lifespan), upgrading the schema to
   head. The first successful boot creates all tables.

> Render does **not** offer managed MySQL (only Postgres/Redis). Keep MySQL
> external. If you would rather use Render Postgres, that is a code change to
> the SQLAlchemy dialect/driver and is out of scope for this guide.

### ⚠️ The #1 deploy failure: unreachable database

The app runs migrations **during startup** (`run_migrations()` in the lifespan),
so it cannot boot — and Render's health check cannot pass — until it can reach
MySQL. If the deploy log stops at:

```
INFO app: Starting Legal Contract Intelligence backend...
INFO:     Waiting for application startup.
```

…and then stalls until **Timed Out**, the backend cannot connect to your
`DATABASE_URL`. This is a connectivity/config problem, not a code bug. Check, in
order:

1. **`DATABASE_URL` is set** on the Render service (not left at the localhost
   default) and points at your external MySQL.
2. **Render's egress IPs are allowlisted** by the DB provider. Render's free /
   starter instances use **shared, rotating outbound IPs** — many providers
   (PlanetScale, Aiven, etc.) block them by default. Either allowlist Render's
   published egress ranges, or set the DB to accept connections from any host
   (with a strong password + TLS).
3. **TLS is configured.** Most managed MySQL require SSL; append the provider's
   SSL params to the URL (e.g. `?ssl_mode=REQUIRED`).
4. **The DB is actually reachable** from outside its own network (not
   localhost-only, firewall open to 3306/3307).

The app now bounds the connect/AUTH handshake with `DB_CONNECT_TIMEOUT`
(default **10s**), so an unreachable DB fails fast with a clear
`Can't connect to MySQL server …` line in the deploy log instead of hanging for
15 minutes. Fix the connectivity above and redeploy.

---

## 4. Deploy the backend to Render

### Option A — Blueprint (recommended, reproducible)

`render.yaml` at the repo root defines the backend service.

1. Push this repo to GitHub and **New → Blueprint** on Render, selecting the repo.
2. Render detects `render.yaml`. Before applying, set the two `sync: false`
   secrets in the dashboard (they are never stored in git):
   - `DATABASE_URL` → your managed MySQL URL
   - `GEMINI_API_KEY` → your key
3. Edit `CORS_ORIGINS` to include your Vercel origin, e.g.
   `["https://your-app.vercel.app"]`.
4. Apply. The service **builds `backend/Dockerfile`** (base image
   `python:3.12-slim`), starts uvicorn on `0.0.0.0:$PORT`, and health-checks
   `/health`.
5. Your backend URL is `https://<service>.onrender.com`.

The Blueprint also mounts a **persistent disk** at `/var/data` and points
`STORAGE_DIR` there so uploads/redlines survive restarts (needs a paid instance;
see §6).

> **Why Docker, not Render's native Python?** Render's default interpreter is
> now **3.14**, and the pinned packages (`rapidfuzz`, `PyMuPDF`, `cryptography`,
> `lxml`) have no cp314 wheels — pip then compiles `rapidfuzz` from source and
> its build backend fails (`metadata-generation-failed ╰─> rapidfuzz`). The
> Dockerfile pins `python:3.12`, where every dependency installs from a prebuilt
> wheel, so the build is deterministic. The `PYTHON_VERSION` env pin is not
> reliably honoured by the native buildpack, which is why we build an image.

### Option B — Manual web service (Docker)

New → Web Service → connect repo → **Environment/Build: Docker** → **Dockerfile
Path: `backend/Dockerfile`** → **Context Path: `backend`** → add the env vars
above → set Health Check Path `/health`. (Avoid choosing Runtime: Python
here — it defaults to 3.14 and hits the wheel problem above.)

### Option C — Docker

`backend/Dockerfile` is provided (build context = `backend/`):

```bash
docker build -f backend/Dockerfile backend -t lci-backend
docker run -p 8000:8000 -e DATABASE_URL=... -e GEMINI_API_KEY=... \
  -e CORS_ORIGINS='["https://your-app.vercel.app"]' lci-backend
```

Use it on Render (Environment: Docker) or any container host (Fly.io, Railway,
Cloud Run). The image binds `0.0.0.0:$PORT` and runs migrations on startup.

---

## 5. Deploy the frontend to Vercel

1. Import the GitHub repo into Vercel. Set **Root Directory = `frontend`**.
2. Vercel auto-detects Next.js — **no `vercel.json` is required** for this app
   (there are no custom redirects/routes/headers to configure; framework
   detection handles build and start). Add one only if you later need such rules.
3. Add the environment variable:
   - `NEXT_PUBLIC_API_URL = https://<your-backend>.onrender.com`
   This is **inlined at build time**, so after changing it you must **redeploy**.
4. Deploy. You get `https://your-app.vercel.app`.
5. Go back to Render and make sure `CORS_ORIGINS` contains exactly that origin
   (scheme + host, no trailing slash), then redeploy/restart the backend if you
   change it.

> Local frontend dev uses `frontend/.env.local` with
> `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` (git-ignored).

---

## 6. Storage & persistence (important)

Uploaded documents and generated redline `.docx` files are written to
`STORAGE_DIR` on the local filesystem and referenced from the database.

- **Render:** the free filesystem is **ephemeral** — files are lost on every
  restart/redeploy, though the DB rows remain. Attach a **persistent disk**
  (as `render.yaml` does) and keep `STORAGE_DIR` pointed at it.
- **Scaling to multiple instances / serverless:** a shared disk is not enough.
  If you run more than one backend instance or move to a serverless host, swap
  the filesystem store for object storage (S3/GCS/R2). That is a code change
  beyond this guide; the current design assumes a single instance with a
  persistent volume.
- The database itself is external and always persistent.

---

## 7. Verify the deployment (smoke test)

```bash
# 1) Backend health (lightweight liveness probe)
curl https://<backend>.onrender.com/health
# -> {"status":"ok"}

# 2) Frontend loads
open https://your-app.vercel.app

# 3) Upload a PDF, ask "What is the liability cap?" -> answer + citations.
# 4) Click a citation -> viewer opens on the right page with a highlight.
# 5) Compare two docs; propose a redline; download the .docx.
```

If the browser can reach the page but API calls fail with CORS errors, the
frontend origin is missing from `CORS_ORIGINS`.

---

## 8. Offline / zero-cost demo mode

Set `LLM_PROVIDER=mock` on the backend. The guard, retrieval, verification,
comparison and redline logic run deterministically with **no Gemini calls and no
API key** — ideal for a cheap demo or CI. Reuse `docker-compose.yml` for a local
MySQL. The pre-Gemini query guard (empty/gibberish/off-topic/duplicate) works
identically in both providers because it is provider-independent.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend boots then crashes on DB | Wrong `DATABASE_URL` / SSL / host not allowlisted | Verify URL; add provider SSL params; allowlist Render egress IPs (PlanetScale). |
| Stuck at `Waiting for application startup` → **Timed Out** | Cannot reach MySQL (unset `DATABASE_URL`, egress IP blocked, or TLS mismatch) | See §3 "unreachable database"; startup now fails fast after `DB_CONNECT_TIMEOUT` (10s). |
| Build fails: `metadata-generation-failed ╰─> rapidfuzz` / `Extra keys present in "project"` | Render's native buildpack used **Python 3.14** (no cp314 wheels → source build) | Deploy via the **Docker** runtime (`render.yaml` now does); the image pins `python:3.12`. |
| `cryptography`/`PyMuPDF` build errors on deploy | Using an interpreter with no prebuilt wheels | Use Python 3.12 (as pinned) or the provided Dockerfile. |
| Frontend loads, API calls fail | `NEXT_PUBLIC_API_URL` wrong or not rebuilt | Set it and **redeploy** the frontend (build-time var). |
| CORS errors in console | Frontend origin not in `CORS_ORIGINS` | Add exact origin; restart backend. `CORS_ORIGINS` accepts a JSON array (`["https://a","https://b"]`) **or** a comma-separated list (`https://a,https://b`). |
| Uploaded file / redline download 404 after a while | Ephemeral filesystem wiped | Use a persistent disk / object storage (§6). |
| Streaming answer stalls or times out | Free-tier spin-down or proxy buffering | Use a paid plan for always-on; backend already sends `X-Accel-Buffering: no`. |
| "Bad gateway" briefly after deploy | Cold start / migrations running | Wait for `/health` to return `{"status":"ok"}`. |

---

## 10. Updating a live deployment

- **Backend:** push to `main`; Render auto-deploys (`autoDeployTrigger: commit`)
  and re-runs migrations on boot.
- **Frontend:** push; Vercel rebuilds. Remember `NEXT_PUBLIC_API_URL` is baked in
  at build time.
- Env-var changes on either host require a redeploy/restart to take effect.

---

## 11. Health endpoint & UptimeRobot keep-alive

### The `/health` endpoint

The backend exposes a single, lightweight **liveness** endpoint:

```
GET /health   →   200 OK   Content-Type: application/json
{ "status": "ok" }
```

It is intentionally minimal:

- **Public** — no authentication or authorization (the app has no auth layer;
  only CORS is configured, and `/health` needs no origin header to respond).
- **Cheap** — no MySQL query, no Gemini/API call, no filesystem scan, no PDF
  processing, no external request, no heavy computation. It returns instantly
  and does not modify application state.
- **Safe** — returns only `{"status":"ok"}`; no secrets, env values, DB
  credentials, host info, or stack traces.

It answers exactly one question: *"Is the backend process alive and able to
accept HTTP requests?"* It is **not** a dependency health-check — it will return
`ok` even if MySQL or Gemini is temporarily unreachable (those failures surface
on the real API routes, not here).

`render.yaml` sets `healthCheckPath: /health`, so Render gates each deploy on
this endpoint returning `200`.

### Render → UptimeRobot flow (do this AFTER deploying)

> ⚠️ Create the UptimeRobot monitor **only after** the Render backend has been
> deployed and its final public URL is known. Do not create it now.

1. Deploy the backend to Render (see §4) and wait until Render provides the
   public URL, e.g. `https://lci-backend.onrender.com`.
2. Open `https://<render-url>/health` in a browser or `curl` and confirm you get
   **HTTP 200** with body `{ "status": "ok" }`.
3. In UptimeRobot, **Add Monitor** → **HTTP(s)** with:
   - **Monitor Type:** HTTP(s)
   - **URL to monitor:** `https://YOUR-RENDER-BACKEND-URL/health`
   - **Method:** GET
   - **Monitoring interval:** 5 minutes
   - **Expected status code:** 200 (and optionally assert the keyword `"ok"`)
4. Save the monitor and confirm UptimeRobot reports **UP** (receiving 200s).

The monitor only checks that the backend is responding. Point it at `/health`
**only** — never at an expensive application API (uploads, `/api/ask`,
comparison, or redline routes), which would burn Gemini quota and do real work
on every poll.

> Note: a 5-minute UptimeRobot poll also acts as a gentle keep-alive that helps
> a paid Render instance stay warm. It does **not** prevent the free tier from
> spinning down between requests, and it is not a substitute for a paid plan if
> you need guaranteed always-on latency.

---

### What was added for deployment (this change)
- `render.yaml` — Render Blueprint for the backend (**Docker** runtime so the
  interpreter is pinned to 3.12; health check, persistent disk, secret-safe
  `sync:false` env vars).
- `backend/Dockerfile` + `backend/.dockerignore` — container image (the Render
  build now uses this; also works on Fly.io / Railway / Cloud Run).
- `.env.example` (root) — consolidated safe template.
- `backend/app/core/config.py` — normalises `mysql://` → `mysql+pymysql://` so
  managed-MySQL connection strings work unchanged (localhost default unaffected).
- `DEPLOYMENT.md` — this guide.

No runtime feature code, RAG pipeline, citations, comparison, redline or the
query guard were modified. `vercel.json` was intentionally **not** added because
Vercel auto-detects this standard Next.js app and there is nothing to override.
