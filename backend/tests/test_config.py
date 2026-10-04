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
        ("mysql://u:p@h:3306/db", "mysql+pymysql://u:p@h:3306/db"),
        ("mariadb://u:p@h/db", "mysql+pymysql://u:p@h/db"),
        ("mysql+pymysql://u:p@h/db", "mysql+pymysql://u:p@h/db"),
    ],
)
def test_database_url_normalisation(raw, expected):
    assert _settings(database_url=raw).database_url == expected


def test_db_connect_args_bounds_mysql_only():
    from app.db.session import db_connect_args
    from app.core.config import get_settings

    t = get_settings().db_connect_timeout
    assert db_connect_args("mysql+pymysql://u@h/db") == {"connect_timeout": t}
    assert db_connect_args("mysql://u@h/db") == {"connect_timeout": t}
    assert db_connect_args("sqlite:///test.db") == {}
    assert db_connect_args("postgresql+psycopg://u@h/db") == {}


def test_db_connect_args_enables_tls_when_requested(monkeypatch):
    import app.db.session as sess

    monkeypatch.setattr(sess.settings, "db_ssl_enabled", True)
    args = sess.db_connect_args("mysql+pymysql://u@h/db")
    assert args["connect_timeout"] == sess.settings.db_connect_timeout
    assert args["ssl"] == {"ca": None}


@pytest.mark.parametrize(
    "raw,expected_url,expected_ssl",
    [
        # Aiven's JDBC-style URI: scheme rewritten, invalid ssl-mode dropped, TLS flagged.
        ("mysql://avnadmin:p@ss@host:22308/defaultdb?ssl-mode=REQUIRED",
         "mysql+pymysql://avnadmin:p@ss@host:22308/defaultdb", True),
        # Explicitly disabled -> no TLS requested.
        ("mysql+pymysql://u:p@h/db?ssl_mode=DISABLED",
         "mysql+pymysql://u:p@h/db", False),
        # Unrelated params are preserved while the bad one is stripped.
        ("mysql://u:p@h/db?charset=utf8mb4&ssl-mode=REQUIRED",
         "mysql+pymysql://u:p@h/db?charset=utf8mb4", True),
        # A real PyMySQL param (ssl_ca) is left untouched and does not set the flag.
        ("mysql://u:p@h/db?ssl_ca=/etc/ca.pem",
         "mysql+pymysql://u:p@h/db", False),
    ],
)
def test_database_url_aiven_normalisation(raw, expected_url, expected_ssl):
    s = _settings(database_url=raw)
    # Compare without the ssl_ca value (urlencode percent-encodes the path; the
    # driver decodes it back, so only assert the key survives for that case).
    if "ssl_ca" in raw:
        assert s.database_url.startswith(expected_url.split("?")[0] + "?ssl_ca=")
        assert "ssl-mode" not in s.database_url
    else:
        assert s.database_url == expected_url
    assert s.db_ssl_enabled is expected_ssl


def test_database_url_ssl_mode_never_reaches_pymysql_kwargs():
    # The regression: passing the URI through must not leave 'ssl-mode' anywhere
    # in the final URL query (that kwarg is what crashed connect()).
    s = _settings(database_url="mysql://u:p@h:3306/db?ssl-mode=REQUIRED")
    assert "ssl-mode" not in s.database_url and "ssl_mode" not in s.database_url
