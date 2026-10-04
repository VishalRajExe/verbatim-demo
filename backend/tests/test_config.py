"""Regression tests for environment-driven Settings parsing.

These lock the deployment-critical normalisation that previously crashed the
backend on Render: a comma-separated CORS_ORIGINS must not raise a pydantic
SettingsError, and managed-MySQL URLs must normalise to the PyMySQL driver.
"""
from __future__ import annotations

import pytest

from app.core.config import Settings


def _settings(**kw):
    # Bypass any on-disk .env so tests are hermetic.
    return Settings(_env_file=None, **kw)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("http://localhost:3000,https://a.vercel.app",
         ["http://localhost:3000", "https://a.vercel.app"]),
        ('["http://x","https://y"]', ["http://x", "https://y"]),
        ("https://single.dev", ["https://single.dev"]),
        ("  a , b  ,  ", ["a", "b"]),
        ("", []),
    ],
)
def test_cors_origins_accepts_csv_and_json(raw, expected):
    assert _settings(cors_origins=raw).cors_origins == expected


def test_cors_origins_via_env_source_does_not_crash(monkeypatch):
    # The real Render failure: value arrives via EnvSettingsSource, which used
    # to JSON-decode and raise before any validator could run.
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://app.vercel.app")
    parsed = Settings(_env_file=None).cors_origins
    assert parsed == ["http://localhost:3000", "https://app.vercel.app"]


def test_cors_origins_default(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert _settings().cors_origins == ["http://localhost:3000"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        (".PDF,.docx", {".pdf", ".docx"}),
        ('[".pdf",".txt"]', {".pdf", ".txt"}),
    ],
)
def test_allowed_extensions_parsing(raw, expected):
    assert _settings(allowed_extensions=raw).allowed_extensions == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("mysql://u:p@h:3306/db?ssl_mode=REQUIRED",
         "mysql+pymysql://u:p@h:3306/db?ssl_mode=REQUIRED"),
        ("mariadb://u:p@h/db", "mysql+pymysql://u:p@h/db"),
        ("mysql+pymysql://u:p@h/db", "mysql+pymysql://u:p@h/db"),
    ],
)
def test_database_url_normalisation(raw, expected):
    assert _settings(database_url=raw).database_url == expected
