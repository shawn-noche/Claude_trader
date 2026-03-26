"""
Tests for POST /api/v1/analyze and GET /api/v1/health.
Covers the full ingestion → classify → impact → rank pipeline with mocked services.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.article import Article
from backend.schemas.event import Event, EventType, Direction, Magnitude, TimeHorizon
from backend.schemas.impact import ImpactCandidate, ImpactOrder
from backend.services.ingestion import IngestionError
from backend.services.classifier import ClassificationError
from backend.services.impact_engine import ImpactMappingError

client = TestClient(app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Shared mock objects
# ---------------------------------------------------------------------------

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

MOCK_CANDIDATE = ImpactCandidate(
    ticker="TSM",
    company_name="TSMC",
    impact_direction="bullish",
    impact_order=ImpactOrder.DIRECT,
    relationship_type="foundry_customer",
    mechanism="Higher GPU orders drive incremental N4/N3 wafer starts at TSMC.",
    confidence=0.82,
    time_horizon=TimeHorizon.WEEKS,
    priced_in_assessment=0.35,
    tradability_score=0.80,
    final_score=0.0,
)

MOCK_CANDIDATE_RANKED = MOCK_CANDIDATE.model_copy(update={"final_score": 0.712})

MOCK_SECOND_ORDER_CANDIDATE = ImpactCandidate(
    ticker="SMCI",
    company_name="Super Micro Computer",
    impact_direction="bullish",
    impact_order=ImpactOrder.SECOND_ORDER,
    relationship_type="component_supplier_to",
    mechanism="More GPU supply enables SMCI to ship more AI server racks.",
    confidence=0.74,
    time_horizon=TimeHorizon.WEEKS,
    priced_in_assessment=0.25,
    tradability_score=0.85,
    final_score=0.0,
)

MOCK_SECOND_ORDER_RANKED = MOCK_SECOND_ORDER_CANDIDATE.model_copy(update={"final_score": 0.680})


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Full pipeline: ingestion + classification + impact + ranking
# ---------------------------------------------------------------------------

class TestAnalyzeFullPipeline:
    def _patch_all(self, candidates=None):
        if candidates is None:
            candidates = [MOCK_CANDIDATE_RANKED, MOCK_SECOND_ORDER_RANKED]
        return [
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock, return_value=candidates),
            # rank is deterministic — let it run for real, but seed with scored candidates
        ]

    def test_200_with_full_analysis(self):
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock,
                  return_value=[MOCK_CANDIDATE_RANKED, MOCK_SECOND_ORDER_RANKED]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["article"]["title"] == "NVIDIA Reports Record Revenue"
        assert body["event"]["event_type"] == "earnings"
        assert body["event"]["time_horizon"] == "intraday"
        assert len(body["candidates"]) == 2
        assert body["candidates"][0]["ticker"] == "TSM"
        assert "top_trade_idea" in body

    def test_candidates_have_all_required_fields(self):
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock, return_value=[MOCK_CANDIDATE_RANKED]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        candidate = resp.json()["candidates"][0]
        for field in (
            "ticker", "company_name", "impact_direction", "impact_order",
            "relationship_type", "mechanism", "confidence", "time_horizon",
            "priced_in_assessment", "tradability_score", "final_score",
        ):
            assert field in candidate, f"Missing field: {field}"

    def test_top_trade_idea_prefers_non_obvious_candidate(self):
        """second-order candidate should be surfaced in top_trade_idea over direct."""
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock,
                  return_value=[MOCK_CANDIDATE_RANKED, MOCK_SECOND_ORDER_RANKED]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        idea = resp.json()["top_trade_idea"]
        assert idea is not None
        assert "SMCI" in idea    # second-order preferred over TSM direct

    def test_top_trade_idea_is_none_when_no_candidates(self):
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock, return_value=[]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.json()["top_trade_idea"] is None
        assert resp.json()["candidates"] == []

    def test_impact_mapping_error_returns_partial_analysis(self):
        """Impact mapping failure is non-fatal — returns 200 with empty candidates."""
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock,
                  side_effect=ImpactMappingError("LLM call failed")),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["candidates"] == []
        assert body["event"] is not None   # event was still classified


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestAnalyzeErrors:
    def test_invalid_url_returns_422(self):
        resp = client.post("/api/v1/analyze", json={"url": "not-a-url"})
        assert resp.status_code == 422

    def test_missing_url_returns_422(self):
        resp = client.post("/api/v1/analyze", json={})
        assert resp.status_code == 422

    def test_ftp_scheme_rejected(self):
        resp = client.post("/api/v1/analyze", json={"url": "ftp://example.com/file"})
        assert resp.status_code == 422

    def test_ingestion_error_returns_422(self):
        with patch("backend.api.routes.fetch_article",
                   new_callable=AsyncMock,
                   side_effect=IngestionError("DNS failure")):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/a"})
        assert resp.status_code == 422
        assert "DNS failure" in resp.json()["detail"]

    def test_classification_error_returns_422(self):
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock,
                  side_effect=ClassificationError("bad LLM output")),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/a"})
        assert resp.status_code == 422
        assert "Classification error" in resp.json()["detail"]

    def test_response_envelope_always_present(self):
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock, return_value=[]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/a"})
        body = resp.json()
        for field in ("request_id", "analyzed_at", "article", "event",
                      "candidates", "top_trade_idea", "duration_seconds"):
            assert field in body, f"Missing field: {field}"
