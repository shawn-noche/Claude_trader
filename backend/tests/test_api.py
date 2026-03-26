"""
Tests for POST /api/v1/analyze and GET /api/v1/health.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.article import Article
from backend.services.ingestion import IngestionError

# Use synchronous TestClient (simpler for route-level tests)
client = TestClient(app, raise_server_exceptions=False)


MOCK_ARTICLE = Article(
    url="https://example.com/article",
    title="NVIDIA Reports Record Revenue",
    text="NVIDIA reported record revenue of $22.1 billion for Q4.",
    author="Jane Doe",
    published_date=None,
    source_domain="example.com",
    char_count=57,
    extraction_method="trafilatura",
)


class TestHealth:
    def test_health_returns_200(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestAnalyze:
    def test_valid_url_returns_200(self):
        with patch(
            "backend.api.routes.fetch_article",
            new_callable=AsyncMock,
            return_value=MOCK_ARTICLE,
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["article"]["title"] == "NVIDIA Reports Record Revenue"
        assert body["candidates"] == []
        assert body["event"] is None
        assert "request_id" in body
        assert "duration_seconds" in body

    def test_invalid_url_returns_422(self):
        resp = client.post("/api/v1/analyze", json={"url": "not-a-url"})
        assert resp.status_code == 422

    def test_missing_url_field_returns_422(self):
        resp = client.post("/api/v1/analyze", json={})
        assert resp.status_code == 422

    def test_ingestion_error_returns_422(self):
        with patch(
            "backend.api.routes.fetch_article",
            new_callable=AsyncMock,
            side_effect=IngestionError("fetch failed"),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.status_code == 422
        assert "fetch failed" in resp.json()["detail"]

    def test_non_http_scheme_rejected(self):
        resp = client.post("/api/v1/analyze", json={"url": "ftp://example.com/file"})
        assert resp.status_code == 422
