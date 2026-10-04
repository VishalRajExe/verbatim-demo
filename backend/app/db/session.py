"""SQLAlchemy engine, session factory and declarative base."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def db_connect_args(url: str) -> dict:
    """Driver-specific connect args. For MySQL we bound the connect/AUTH
    handshake so an unreachable host raises quickly instead of hanging startup.
    Other backends (e.g. SQLite in tests) get no extra args."""
    if url.startswith("mysql"):
        return {"connect_timeout": settings.db_connect_timeout}
    return {}


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
    connect_args=db_connect_args(settings.database_url),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Apply Alembic migrations programmatically (used on startup)."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini = backend_dir / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")
