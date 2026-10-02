"""Shared pytest fixtures. Tests run against the configured MySQL database."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    # Using the context manager runs the app lifespan (applies migrations).
    with TestClient(app) as c:
        yield c
