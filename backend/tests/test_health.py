"""Tests for the lightweight /health liveness endpoint.

These assert the endpoint is public, fast, dependency-free, and returns exactly
the small JSON body Render's health check and UptimeRobot expect.
"""
from __future__ import annotations


def test_health_returns_200_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"status": "ok"}


def test_health_is_get_only(client):
    # Other verbs must not be handled by the liveness route.
    assert client.post("/health").status_code in (404, 405)


def test_health_requires_no_auth(client):
    # No Authorization header present -> still 200 (endpoint is public).
    resp = client.get("/health", headers={})
    assert resp.status_code == 200


def test_no_duplicate_api_health_path(client):
    # The endpoint was converted to /health, not duplicated alongside the old
    # /api/health path.
    assert client.get("/api/health").status_code == 404


def test_health_exposes_no_internals(client):
    body = client.get("/health").json()
    # Only the liveness flag: no service name, env, DB, or host details.
    assert set(body.keys()) == {"status"}


def test_health_supports_head(client):
    # Uptime monitors (e.g. UptimeRobot) default to HEAD requests
    resp = client.head("/health")
    assert resp.status_code == 200


def test_root_returns_200_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_root_supports_head(client):
    resp = client.head("/")
    assert resp.status_code == 200

