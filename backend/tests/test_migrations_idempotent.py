"""Regression: a drifted database must self-heal, not crash every startup.

MySQL auto-commits DDL, so if a process is killed between `ALTER TABLE ...
ADD COLUMN` and alembic's version-row UPDATE, the column exists while
alembic_version still points at the previous revision. Every later startup
then re-runs the ALTER and dies with "Duplicate column name", which used to
break the dev server boot and the whole pytest session at once. The fix made
the migration idempotent; these tests pin that behaviour.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine, run_migrations

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def _version_num() -> str:
    with engine.begin() as conn:
        return conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()


def test_migrations_are_idempotent_when_rerun() -> None:
    """Re-running upgrade on an already-migrated database is a no-op."""
    cfg = _alembic_config()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    run_migrations()
    assert _version_num() == head
    run_migrations()  # must not raise (e.g. Duplicate column)
    assert _version_num() == head


def test_drifted_database_self_heals_on_startup() -> None:
    """Rewinding the version pointer while keeping the column (the exact drift
    observed in this project's dev database) must recover on next startup."""
    cfg = _alembic_config()
    sd = ScriptDirectory.from_config(cfg)
    head = sd.get_current_head()
    prev = sd.get_revision(head).down_revision
    assert prev, "head revision must have a parent for this scenario"

    run_migrations()  # baseline: schema fully at head (column present)
    command.stamp(cfg, prev)  # simulate the half-applied state
    assert _version_num() == prev
    try:
        run_migrations()  # must NOT crash with "Duplicate column name"
        assert _version_num() == head
    finally:
        # Leave the shared dev database exactly as we found it.
        if _version_num() != head:
            command.stamp(cfg, head)
