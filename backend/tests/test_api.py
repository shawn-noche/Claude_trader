"""
Tests for POST /api/v1/analyze and GET /api/v1/health.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.article import Article
from backend.schemas.event import Event, EventType, Direction, Magnitude, TimeHorizon
from backend.services.ingestion import IngestionError
from backend.services.classifier import ClassificationError

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

MOCK_EVENT = Event(
    event_type=EventType.EARNINGS,
    focal_entities=["NVDA"],
    direction=Direction.BULLISH,
    magnitude=Magnitude.HIGH,
    time_horizon=TimeHorizon.INTRADAY,
    economic_mechanism="Raises full-year estimates across the AI GPU supply chain.",
    event_summary="NVIDIA beat Q4 estimates on strong data center GPU demand.",
    confidence=0.95,
)


class TestHealth:
    def test_health_returns_200(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestAnalyze:
    def test_valid_url_returns_200_with_article_and_event(self):
        with (
            patch("backend.api.routes.fetch_article", new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event", new_callable=AsyncMock, return_value=MOCK_EVENT),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["article"]["title"] == "NVIDIA Reports Record Revenue"
        assert body["event"]["event_type"] == "earnings"
        assert body["event"]["direction"] == "bullish"
        assert body["event"]["time_horizon"] == "intraday"
        assert body["candidates"] == []
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

    def test_classification_error_returns_422(self):
        with (
            patch("backend.api.routes.fetch_article", new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch(
                "backend.api.routes.classify_event",
                new_callable=AsyncMock,
                side_effect=ClassificationError("LLM call failed"),
            ),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.status_code == 422
        assert "Classification error" in resp.json()["detail"]

    def test_non_http_scheme_rejected(self):
        resp = client.post("/api/v1/analyze", json={"url": "ftp://example.com/file"})
        assert resp.status_code == 422

    def test_response_contains_all_required_fields(self):
        with (
            patch("backend.api.routes.fetch_article", new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event", new_callable=AsyncMock, return_value=MOCK_EVENT),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        body = resp.json()
        for field in ("request_id", "analyzed_at", "article", "event", "candidates", "duration_seconds"):
            assert field in body, f"Missing field: {field}"
