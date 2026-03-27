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
from backend.schemas.analysis import TradeIdea
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

MOCK_TRADE_IDEA = TradeIdea(
    ticker="SMCI",
    company_name="Super Micro Computer",
    trade_direction="long",
    chain_position="second_order",
    why_now="NVDA supply unlock enables SMCI to fulfil backlogged AI server orders this quarter.",
    key_mechanism="Each incremental H100 rack adds ~$25K in SMCI integration and assembly revenue.",
    why_it_may_be_underappreciated="Sell-side models assume flat rack mix; GPU availability enables a higher-margin build.",
    confidence=0.74,
    invalidation_or_risk="Hyperscalers delay rack deployments pending power infrastructure readiness.",
)


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
    def _patch_all(self, candidates=None, ideas=None):
        if candidates is None:
            candidates = [MOCK_CANDIDATE_RANKED, MOCK_SECOND_ORDER_RANKED]
        if ideas is None:
            ideas = [MOCK_TRADE_IDEA]
        return [
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock, return_value=candidates),
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, return_value=ideas),
            # rank is deterministic — let it run for real
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
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, return_value=[MOCK_TRADE_IDEA]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["article"]["title"] == "NVIDIA Reports Record Revenue"
        assert body["event"]["event_type"] == "earnings"
        assert body["event"]["time_horizon"] == "intraday"
        assert len(body["candidates"]) == 2
        assert body["candidates"][0]["ticker"] == "TSM"
        assert "top_trade_ideas" in body
        assert "impact_buckets" in body

    def test_candidates_have_all_required_fields(self):
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock, return_value=[MOCK_CANDIDATE_RANKED]),
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, return_value=[]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        candidate = resp.json()["candidates"][0]
        for field in (
            "ticker", "company_name", "impact_direction", "impact_order",
            "relationship_type", "mechanism", "confidence", "time_horizon",
            "priced_in_assessment", "tradability_score", "final_score",
        ):
            assert field in candidate, f"Missing field: {field}"

    def test_top_trade_ideas_surfaced_in_response(self):
        """Generator output is passed through to top_trade_ideas in the response."""
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock,
                  return_value=[MOCK_CANDIDATE_RANKED, MOCK_SECOND_ORDER_RANKED]),
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, return_value=[MOCK_TRADE_IDEA]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        ideas = resp.json()["top_trade_ideas"]
        assert len(ideas) == 1
        assert ideas[0]["ticker"] == "SMCI"
        assert ideas[0]["chain_position"] == "second_order"

    def test_top_trade_ideas_empty_when_no_candidates(self):
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock, return_value=[]),
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, return_value=[]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.json()["top_trade_ideas"] == []
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
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, return_value=[]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["candidates"] == []
        assert body["event"] is not None   # event was still classified

    def test_trade_idea_generation_failure_returns_partial_analysis(self):
        """Trade idea generation failure is non-fatal — returns 200 with empty ideas."""
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock,
                  return_value=[MOCK_CANDIDATE_RANKED]),
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, side_effect=Exception("LLM error")),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["candidates"] != []    # candidates still present
        assert body["top_trade_ideas"] == []

    def test_impact_buckets_categorise_candidates_correctly(self):
        """Bullish candidates land in *_beneficiaries; bearish in *_losers."""
        bearish = MOCK_CANDIDATE_RANKED.model_copy(update={
            "impact_direction": "bearish",
            "impact_order": ImpactOrder.SECOND_ORDER,
        })
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock,
                  return_value=[MOCK_CANDIDATE_RANKED, bearish]),
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, return_value=[]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        buckets = resp.json()["impact_buckets"]
        assert len(buckets["direct_beneficiaries"]) == 1
        assert buckets["direct_beneficiaries"][0]["ticker"] == "TSM"
        assert len(buckets["second_order_losers"]) == 1

    def test_top_trade_ideas_have_all_required_fields(self):
        with (
            patch("backend.api.routes.fetch_article",
                  new_callable=AsyncMock, return_value=MOCK_ARTICLE),
            patch("backend.api.routes.classify_event",
                  new_callable=AsyncMock, return_value=MOCK_EVENT),
            patch("backend.api.routes.map_impacts",
                  new_callable=AsyncMock, return_value=[MOCK_CANDIDATE_RANKED]),
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, return_value=[MOCK_TRADE_IDEA]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/article"})

        idea = resp.json()["top_trade_ideas"][0]
        for field in (
            "ticker", "company_name", "trade_direction", "chain_position",
            "why_now", "key_mechanism", "why_it_may_be_underappreciated",
            "confidence", "invalidation_or_risk",
        ):
            assert field in idea, f"Missing field: {field}"


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
            patch("backend.api.routes.generate_trade_ideas",
                  new_callable=AsyncMock, return_value=[]),
        ):
            resp = client.post("/api/v1/analyze", json={"url": "https://example.com/a"})
        body = resp.json()
        for field in ("request_id", "analyzed_at", "article", "event",
                      "candidates", "top_trade_ideas", "impact_buckets", "duration_seconds"):
            assert field in body, f"Missing field: {field}"
