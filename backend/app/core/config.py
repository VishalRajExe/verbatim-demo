"""Application configuration via pydantic-settings.

Single source of truth for environment-derived settings. Loads from backend/.env.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    # Bound the TCP/AUTH handshake so an unreachable managed-MySQL host fails
    # fast with a clear error instead of hanging the whole app startup (which on
    # Render otherwise stalls until the 15-minute deploy timeout).
    db_connect_timeout: int = 10
    # Derived from database_url's query string in _normalise_db below (Aiven /
    # PlanetScale JDBC-style TLS hints are translated into driver-compatible
    # connect args rather than passed through verbatim, which PyMySQL rejects).
    db_ssl_enabled: bool = False

    # ─── AI (Gemini) ───
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"
    gemini_base_url: str = ""
    llm_provider: str = "gemini"          # "gemini" | "mock"
    llm_max_concurrency: int = 2

    # ─── Upload / processing ───
    max_file_size_mb: int = 80
    allowed_extensions: Annotated[set[str], NoDecode] = {".pdf", ".docx"}
    chunk_size_words: int = 200
    chunk_overlap_words: int = 40
    chunk_max_chars: int = 96000          # ~24k tokens of canonical text per extract call

    # ─── Server ───
    # NoDecode stops pydantic-settings from JSON-decoding the raw env value (which
    # crashes on a comma-separated CORS_ORIGINS); _parse_seq below handles it.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    api_prefix: str = "/api"

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @staticmethod
    def _parse_seq(v, cast=str):
        # Accept a real list/set (defaults, tests) or a string in either JSON
        # array form ('["a","b"]') or comma/space separated form ('a,b'). This
        # keeps deployment env vars forgiving across providers.
        if isinstance(v, (list, set, tuple, frozenset)):
            return [cast(x) for x in v]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("["):
                try:
                    return [cast(x) for x in json.loads(s)]
                except (ValueError, TypeError):
                    pass
            return [cast(p.strip()) for p in s.replace("\n", ",").split(",") if p.strip()]
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _norm_cors(cls, v):
        return cls._parse_seq(v)

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def _norm_exts(cls, v):
        return {e.strip().lower() for e in cls._parse_seq(v)}

    @model_validator(mode="after")
    def _normalise_db(self):
        # Managed MySQL providers hand out connection strings that SQLAlchemy's
        # PyMySQL driver cannot use verbatim:
        #   • plain "mysql://" / "mariadb://" schemes (need the +pymysql driver),
        #   • JDBC-style TLS params such as "?ssl-mode=REQUIRED" (Aiven) that are
        #     NOT valid PyMySQL kwargs and crash connect() with
        #     "unexpected keyword argument 'ssl-mode'".
        # Normalise both so a provider Service URI pasted as-is just works:
        # rewrite the scheme, strip the JDBC-only params, and translate an SSL
        # request into driver-compatible connect args (via db_ssl_enabled). Any
        # genuinely-supported PyMySQL param (e.g. ssl_ca=/path/ca.pem) is kept.
        url = self.database_url.strip()
        for scheme in ("mysql://", "mysql2://", "mariadb://"):
            if url.startswith(scheme):
                url = "mysql+pymysql://" + url[len(scheme):]
                break
        if url.startswith("mysql"):
            parts = urlsplit(url)
            kept: list[tuple[str, str]] = []
            ssl_requested = False
            for k, v in parse_qsl(parts.query, keep_blank_values=True):
                lk = k.lower()
                if lk in ("ssl-mode", "ssl_mode", "sslmode"):
                    ssl_requested = ssl_requested or v.upper() not in (
                        "DISABLED", "FALSE", "NO", "0", "")
                    continue
                if lk in ("require_ssl", "requiressl", "use_ssl", "usessl"):
                    ssl_requested = ssl_requested or v.lower() in (
                        "true", "1", "yes", "required")
                    continue
                kept.append((k, v))
            url = urlunsplit(
                (parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment)
            )
            self.db_ssl_enabled = self.db_ssl_enabled or ssl_requested
        self.database_url = url
        return self

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    return s
