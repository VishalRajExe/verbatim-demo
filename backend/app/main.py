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
    logger.info("Starting Legal Contract Intelligence backend...")
    try:
        run_migrations()
        logger.info("Database migrations applied.")
    except Exception:  # noqa: BLE001
        logger.exception("Migration failed on startup.")
        raise
    logger.info("Backend ready.")
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


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "service": "legal-contract-intelligence"}
