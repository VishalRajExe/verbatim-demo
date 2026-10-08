"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, comparisons, qa, redlines
from app.core.config import get_settings
from app.db.session import run_migrations

settings = get_settings()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the server immediately so /health responds during cold-start.

    Migrations run in a daemon background thread so the lifespan yield is
    reached instantly.  The /health endpoint becomes reachable within a
    second of the process starting — before the MySQL handshake completes —
    which keeps UptimeRobot from timing out on free-tier cold starts.

    If migrations fail the error is logged; DB-dependent API routes will
    surface the failure naturally on their first call (same behaviour as
    before, just without blocking startup).
    """
    import threading

    logger.info("Starting Legal Contract Intelligence backend...")

    def _run_migrations_bg() -> None:
        try:
            run_migrations()
            logger.info("Database migrations applied.")
        except Exception:  # noqa: BLE001
            logger.exception("Migration failed (background thread); DB routes may error.")

    t = threading.Thread(target=_run_migrations_bg, daemon=True, name="migrations")
    t.start()

    logger.info("Backend ready — accepting requests while migrations run in background.")
    yield
    logger.info("Shutting down backend.")


app = FastAPI(
    title="Legal Contract Intelligence",
    description="Grounded Q&A, comparison, and tracked changes for legal contracts.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix=settings.api_prefix)
app.include_router(qa.router, prefix=settings.api_prefix)
app.include_router(comparisons.router, prefix=settings.api_prefix)
app.include_router(redlines.router, prefix=settings.api_prefix)


@app.get("/health", tags=["health"])
def health() -> dict:
    """Lightweight liveness probe: confirms the backend process is up and can
    serve HTTP. Intentionally performs NO database query, NO Gemini/API call,
    NO filesystem or heavy work, and exposes no secrets or internals. Used by
    the Render health check and UptimeRobot keep-alive monitoring."""
    return {"status": "ok"}
