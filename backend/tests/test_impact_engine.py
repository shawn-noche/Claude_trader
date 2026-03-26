"""
Tests for the impact engine.

All LLM calls are mocked. The KB loads from real JSON files.
"""

import json
import pytest
from unittest.mock import patch

from backend.schemas.event import Event, EventType, Direction, Magnitude, TimeHorizon
from backend.schemas.impact import ImpactOrder
from backend.services import knowledge_base as kb
from backend.services.impact_engine import (
    map_impacts,
    ImpactMappingError,
    _build_candidate_universe,
    _parse_impact_response,
    _strip_fences,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

NVDA_EVENT = Event(
    event_type=EventType.EARNINGS,
    focal_entities=["NVDA"],
    direction=Direction.BULLISH,
    magnitude=Magnitude.HIGH,
    time_horizon=TimeHorizon.INTRADAY,
    economic_mechanism="Raises full-year estimates across the AI GPU supply chain.",
    event_summary="NVIDIA beat Q4 estimates on record data center GPU demand.",
    confidence=0.95,
)

UNKNOWN_EVENT = Event(
    event_type=EventType.EARNINGS,
    focal_entities=["ZZZZZ_UNKNOWN"],
    direction=Direction.BULLISH,
    magnitude=Magnitude.HIGH,
    time_horizon=TimeHorizon.INTRADAY,
    economic_mechanism="Unknown company reports results.",
    event_summary="Unknown company beat estimates.",
    confidence=0.9,
)

# Minimal valid LLM response for NVDA
VALID_LLM_RESPONSE = json.dumps([
    {
        "ticker": "TSM",
        "impact_direction": "bullish",
        "impact_order": "direct",
        "relationship_type": "foundry_customer",
        "mechanism": "Higher NVDA GPU orders drive incremental N4/N3 wafer starts at TSMC.",
        "confidence": 0.82,
        "time_horizon": "weeks",
        "priced_in_assessment": 0.45,
        "tradability_score": 0.80,
    },
    {
        "ticker": "HXSCL",
        "impact_direction": "bullish",
        "impact_order": "direct",
        "relationship_type": "memory_customer",
        "mechanism": "Record NVDA GPU shipments require more HBM3E allocation from SK Hynix.",
        "confidence": 0.78,
        "time_horizon": "weeks",
        "priced_in_assessment": 0.35,
        "tradability_score": 0.60,
    },
    {
        "ticker": "SMCI",
        "impact_direction": "bullish",
        "impact_order": "second_order",
        "relationship_type": "component_supplier_to",
        "mechanism": "NVDA GPU supply increase enables SMCI to ship more AI server racks.",
        "confidence": 0.74,
        "time_horizon": "weeks",
        "priced_in_assessment": 0.30,
        "tradability_score": 0.85,
    },
])

HALLUCINATED_TICKER_RESPONSE = json.dumps([
    {
        "ticker": "FAKE_TICKER",
        "impact_direction": "bullish",
        "impact_order": "direct",
        "relationship_type": "foundry_customer",
        "mechanism": "Some mechanism.",
        "confidence": 0.80,
        "time_horizon": "days",
        "priced_in_assessment": 0.2,
        "tradability_score": 0.7,
    }
])

LOW_CONFIDENCE_RESPONSE = json.dumps([
    {
        "ticker": "TSM",
        "impact_direction": "bullish",
        "impact_order": "direct",
        "relationship_type": "foundry_customer",
        "mechanism": "Speculative link to NVDA earnings.",
        "confidence": 0.20,   # below threshold
        "time_horizon": "months",
        "priced_in_assessment": 0.5,
        "tradability_score": 0.5,
    }
])


# ---------------------------------------------------------------------------
# _build_candidate_universe
# ---------------------------------------------------------------------------

class TestBuildCandidateUniverse:
    def test_includes_focal_as_hop0(self):
        nvda = kb.get_company("NVDA")
        universe = _build_candidate_universe([nvda])
        assert "NVDA" in universe
        assert universe["NVDA"]["hop"] == 0

    def test_includes_direct_suppliers_as_hop1(self):
        nvda = kb.get_company("NVDA")
        universe = _build_candidate_universe([nvda])
        # TSM is a foundry_customer target of NVDA → should appear at hop 1
        assert "TSM" in universe
        assert universe["TSM"]["hop"] == 1

    def test_includes_direct_customers_as_hop1(self):
        nvda = kb.get_company("NVDA")
        universe = _build_candidate_universe([nvda])
        # MSFT → NVDA (major_customer) means MSFT is inbound to NVDA → hop 1
        assert "MSFT" in universe
        assert universe["MSFT"]["hop"] == 1

    def test_includes_extended_companies_as_hop2(self):
        nvda = kb.get_company("NVDA")
        universe = _build_candidate_universe([nvda])
        # ASML supplies equipment to TSM (hop1) → ASML should be hop 2
        assert "ASML" in universe
        assert universe["ASML"]["hop"] == 2

    def test_no_duplicate_tickers(self):
        nvda = kb.get_company("NVDA")
        universe = _build_candidate_universe([nvda])
        assert len(universe) == len(set(universe.keys()))

    def test_connection_set_for_hop1(self):
        nvda = kb.get_company("NVDA")
        universe = _build_candidate_universe([nvda])
        assert universe["TSM"]["connection"] is not None
        assert universe["TSM"]["connection"]["type"] == "foundry_customer"

    def test_via_set_for_hop2(self):
        nvda = kb.get_company("NVDA")
        universe = _build_candidate_universe([nvda])
        # ASML's 'via' should be TSM (the hop-1 bridge)
        assert universe["ASML"]["via"] is not None


# ---------------------------------------------------------------------------
# _parse_impact_response
# ---------------------------------------------------------------------------

class TestParseImpactResponse:
    def setup_method(self):
        nvda = kb.get_company("NVDA")
        self.universe = _build_candidate_universe([nvda])

    def test_valid_response_returns_candidates(self):
        candidates = _parse_impact_response(VALID_LLM_RESPONSE, self.universe)
        assert len(candidates) == 3
        tickers = [c.ticker for c in candidates]
        assert "TSM" in tickers
        assert "HXSCL" in tickers
        assert "SMCI" in tickers

    def test_fields_correctly_parsed(self):
        candidates = _parse_impact_response(VALID_LLM_RESPONSE, self.universe)
        tsm = next(c for c in candidates if c.ticker == "TSM")
        assert tsm.impact_direction == "bullish"
        assert tsm.impact_order == ImpactOrder.DIRECT
        assert tsm.relationship_type == "foundry_customer"
        assert tsm.confidence == pytest.approx(0.82)
        assert tsm.priced_in_assessment == pytest.approx(0.45)
        assert tsm.tradability_score == pytest.approx(0.80)
        assert tsm.final_score == pytest.approx(0.0)   # not yet ranked

    def test_company_name_resolved_from_kb(self):
        candidates = _parse_impact_response(VALID_LLM_RESPONSE, self.universe)
        tsm = next(c for c in candidates if c.ticker == "TSM")
        assert tsm.company_name == "TSMC"

    def test_hallucinated_ticker_is_excluded(self):
        candidates = _parse_impact_response(HALLUCINATED_TICKER_RESPONSE, self.universe)
        assert len(candidates) == 0

    def test_invalid_json_raises(self):
        with pytest.raises(ImpactMappingError, match="invalid JSON"):
            _parse_impact_response("definitely not json {{{", self.universe)

    def test_json_object_instead_of_array_raises(self):
        with pytest.raises(ImpactMappingError, match="Expected JSON array"):
            _parse_impact_response('{"ticker": "TSM"}', self.universe)

    def test_strips_markdown_fences(self):
        fenced = "```json\n" + VALID_LLM_RESPONSE + "\n```"
        candidates = _parse_impact_response(fenced, self.universe)
        assert len(candidates) == 3

    def test_missing_ticker_item_skipped(self):
        raw = json.dumps([{"impact_direction": "bullish", "confidence": 0.8}])
        candidates = _parse_impact_response(raw, self.universe)
        assert candidates == []

    def test_unknown_impact_order_defaults_to_third_order(self):
        raw = json.dumps([{
            "ticker": "TSM", "impact_direction": "bullish",
            "impact_order": "completely_made_up",
            "relationship_type": "x", "mechanism": "x",
            "confidence": 0.7, "time_horizon": "weeks",
            "priced_in_assessment": 0.3, "tradability_score": 0.6,
        }])
        candidates = _parse_impact_response(raw, self.universe)
        assert candidates[0].impact_order == ImpactOrder.THIRD_ORDER

    def test_confidence_clamped_to_one(self):
        raw = json.dumps([{
            "ticker": "TSM", "impact_direction": "bullish",
            "impact_order": "direct", "relationship_type": "foundry_customer",
            "mechanism": "x", "confidence": 2.5,
            "time_horizon": "days", "priced_in_assessment": 0.1,
            "tradability_score": 0.8,
        }])
        candidates = _parse_impact_response(raw, self.universe)
        assert candidates[0].confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Confidence filtering
# ---------------------------------------------------------------------------

class TestConfidenceFiltering:
    def setup_method(self):
        nvda = kb.get_company("NVDA")
        self.universe = _build_candidate_universe([nvda])

    def test_low_confidence_candidates_excluded(self):
        """Confidence 0.20 is below the 0.40 threshold — should be filtered."""
        with patch("backend.services.impact_engine.llm_client.complete",
                   return_value=LOW_CONFIDENCE_RESPONSE):
            import asyncio
            candidates = asyncio.get_event_loop().run_until_complete(
                map_impacts(NVDA_EVENT)
            )
        assert len(candidates) == 0


# ---------------------------------------------------------------------------
# map_impacts integration (LLM mocked)
# ---------------------------------------------------------------------------

class TestMapImpacts:
    @pytest.mark.asyncio
    async def test_returns_candidates_for_known_entity(self):
        with patch("backend.services.impact_engine.llm_client.complete",
                   return_value=VALID_LLM_RESPONSE):
            candidates = await map_impacts(NVDA_EVENT)
        assert len(candidates) == 3

    @pytest.mark.asyncio
    async def test_unknown_focal_entity_returns_empty(self):
        candidates = await map_impacts(UNKNOWN_EVENT)
        assert candidates == []

    @pytest.mark.asyncio
    async def test_llm_failure_raises_impact_mapping_error(self):
        with patch("backend.services.impact_engine.llm_client.complete",
                   side_effect=Exception("timeout")):
            with pytest.raises(ImpactMappingError, match="LLM call failed"):
                await map_impacts(NVDA_EVENT)

    @pytest.mark.asyncio
    async def test_final_score_is_zero_before_ranking(self):
        with patch("backend.services.impact_engine.llm_client.complete",
                   return_value=VALID_LLM_RESPONSE):
            candidates = await map_impacts(NVDA_EVENT)
        assert all(c.final_score == 0.0 for c in candidates)

    @pytest.mark.asyncio
    async def test_hallucinated_ticker_excluded_end_to_end(self):
        with patch("backend.services.impact_engine.llm_client.complete",
                   return_value=HALLUCINATED_TICKER_RESPONSE):
            candidates = await map_impacts(NVDA_EVENT)
        assert candidates == []


# ---------------------------------------------------------------------------
# _strip_fences helper
# ---------------------------------------------------------------------------

class TestStripFences:
    def test_no_fences_unchanged(self):
        assert _strip_fences('["a"]') == '["a"]'

    def test_json_fences_stripped(self):
        assert _strip_fences('```json\n["a"]\n```') == '["a"]'

    def test_plain_fences_stripped(self):
        assert _strip_fences('```\n["a"]\n```') == '["a"]'

    def test_leading_whitespace_stripped(self):
        assert _strip_fences('  ["a"]  ') == '["a"]'
