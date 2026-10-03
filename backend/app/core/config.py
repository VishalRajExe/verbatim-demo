"""Application configuration via pydantic-settings.

Single source of truth for environment-derived settings. Loads from backend/.env.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── Paths ───
    base_dir: Path = Path(__file__).resolve().parents[2]
    storage_dir: Path = base_dir / "data"

    # ─── Database ───
    database_url: str = (
        "mysql+pymysql://root:admin@localhost:3306/legal_contract_intelligence"
    )

    # ─── AI (Gemini) ───
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"
    gemini_base_url: str = ""
    llm_provider: str = "gemini"          # "gemini" | "mock"
    llm_max_concurrency: int = 2

    # ─── Upload / processing ───
    max_file_size_mb: int = 80
    allowed_extensions: set[str] = {".pdf", ".docx"}
    chunk_size_words: int = 200
    chunk_overlap_words: int = 40
    chunk_max_chars: int = 96000          # ~24k tokens of canonical text per extract call

    # ─── Server ───
    cors_origins: list[str] = ["http://localhost:3000"]
    api_prefix: str = "/api"

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def _norm_exts(cls, v):
        if isinstance(v, str):
            return {e.strip().lower() for e in v.split(",") if e.strip()}
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def _norm_db_url(cls, v):
        # Managed MySQL providers (PlanetScale / Aiven / Railway / ClearDB) hand
        # out plain "mysql://" URLs, but SQLAlchemy needs the PyMySQL driver
        # scheme this app is built around. Normalise the common variants so a
        # provider connection string works unchanged; leave anything already
        # dialect-qualified (e.g. mysql+pymysql://) exactly as given.
        if isinstance(v, str):
            v = v.strip()
            for scheme in ("mysql://", "mysql2://", "mariadb://"):
                if v.startswith(scheme):
                    return "mysql+pymysql://" + v[len(scheme):]
        return v

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    return s
