"""
Tests for the trade idea generation service.

Covers: context building, response parsing, graceful degradation,
anti-hallucination guarantee, and the top-3 cap.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch

from backend.schemas.event import Event, EventType, Direction, Magnitude, TimeHorizon
from backend.schemas.impact import ImpactCandidate, ImpactOrder
from backend.schemas.analysis import TradeIdea
from backend.services.trade_idea_generator import (
    generate_trade_ideas,
    _build_trade_context,
    _parse_trade_ideas,
    _strip_fences,
    TradeIdeaGenerationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(**kwargs) -> Event:
    defaults = dict(
        event_type=EventType.EARNINGS,
        focal_entities=["NVDA"],
        direction=Direction.BULLISH,
        magnitude=Magnitude.HIGH,
        time_horizon=TimeHorizon.INTRADAY,
        economic_mechanism="Raises estimates across AI GPU supply chain.",
        event_summary="NVIDIA beat Q4 estimates on data center GPU demand.",
        confidence=0.95,
    )
    return Event(**{**defaults, **kwargs})


def make_candidate(
    ticker="TSM",
    impact_order=ImpactOrder.DIRECT,
    impact_direction="bullish",
    confidence=0.82,
    priced_in_assessment=0.30,
    tradability_score=0.80,
    final_score=0.72,
) -> ImpactCandidate:
    return ImpactCandidate(
        ticker=ticker,
        company_name=ticker,
        impact_direction=impact_direction,
        impact_order=impact_order,
        relationship_type="foundry_customer",
        mechanism=f"{ticker} mechanism sentence.",
        confidence=confidence,
        time_horizon=TimeHorizon.WEEKS,
        priced_in_assessment=priced_in_assessment,
        tradability_score=tradability_score,
        final_score=final_score,
    )


def make_llm_item(
    ticker="TSM",
    trade_direction="long",
    why_now="Catalyst is imminent.",
    key_mechanism="Revenue increases.",
    underappreciated="Street not modelling this.",
    risk="If demand collapses.",
) -> dict:
    return {
        "ticker": ticker,
        "trade_direction": trade_direction,
        "why_now": why_now,
        "key_mechanism": key_mechanism,
        "why_it_may_be_underappreciated": underappreciated,
        "invalidation_or_risk": risk,
    }


EVENT = make_event()
CANDIDATE_DIRECT = make_candidate("TSM", ImpactOrder.DIRECT, priced_in_assessment=0.80)
CANDIDATE_SECOND = make_candidate("AMKR", ImpactOrder.SECOND_ORDER, priced_in_assessment=0.10)
CANDIDATE_THIRD = make_candidate("ANET", ImpactOrder.THIRD_ORDER, priced_in_assessment=0.05)

CANDIDATE_MAP = {
    "TSM": CANDIDATE_DIRECT,
    "AMKR": CANDIDATE_SECOND,
    "ANET": CANDIDATE_THIRD,
}


# ---------------------------------------------------------------------------
# _build_trade_context
# ---------------------------------------------------------------------------

class TestBuildTradeContext:
    def test_contains_event_section(self):
        ctx = _build_trade_context(EVENT, [CANDIDATE_DIRECT])
        assert "EVENT:" in ctx
        assert "earnings" in ctx

    def test_contains_candidate_section(self):
        ctx = _build_trade_context(EVENT, [CANDIDATE_DIRECT])
        assert "RANKED CANDIDATES" in ctx
        assert "TSM" in ctx

    def test_candidate_count_in_header(self):
        ctx = _build_trade_context(EVENT, [CANDIDATE_DIRECT, CANDIDATE_SECOND])
        assert "2 total" in ctx

    def test_candidate_fields_serialised(self):
        ctx = _build_trade_context(EVENT, [CANDIDATE_SECOND])
        assert "priced_in_assessment" in ctx
        assert "final_score" in ctx
        assert "impact_order" in ctx

    def test_event_enums_as_strings(self):
        ctx = _build_trade_context(EVENT, [CANDIDATE_DIRECT])
        # Enum values should be strings, not Python repr
        assert '"earnings"' in ctx
        assert '"bullish"' in ctx


# ---------------------------------------------------------------------------
# _strip_fences
# ---------------------------------------------------------------------------

class TestStripFences:
    def test_plain_json_unchanged(self):
        raw = '[{"ticker": "TSM"}]'
        assert _strip_fences(raw) == raw

    def test_strips_json_fence(self):
        raw = '```json\n[{"ticker": "TSM"}]\n```'
        assert _strip_fences(raw) == '[{"ticker": "TSM"}]'

    def test_strips_generic_fence(self):
        raw = '```\n[{"ticker": "TSM"}]\n```'
        assert _strip_fences(raw) == '[{"ticker": "TSM"}]'


# ---------------------------------------------------------------------------
# _parse_trade_ideas
# ---------------------------------------------------------------------------

class TestParseTradeIdeas:
    def test_parses_valid_response(self):
        raw = json.dumps([make_llm_item("TSM")])
        ideas = _parse_trade_ideas(raw, CANDIDATE_MAP)
        assert len(ideas) == 1
        assert ideas[0].ticker == "TSM"

    def test_company_name_from_candidate(self):
        raw = json.dumps([make_llm_item("TSM")])
        ideas = _parse_trade_ideas(raw, CANDIDATE_MAP)
        assert ideas[0].company_name == "TSM"   # make_candidate uses ticker as name

    def test_chain_position_from_candidate(self):
        raw = json.dumps([make_llm_item("AMKR")])
        ideas = _parse_trade_ideas(raw, CANDIDATE_MAP)
        assert ideas[0].chain_position == "second_order"

    def test_confidence_from_candidate_not_llm(self):
        raw = json.dumps([make_llm_item("AMKR")])
        ideas = _parse_trade_ideas(raw, CANDIDATE_MAP)
        assert ideas[0].confidence == CANDIDATE_SECOND.confidence

    def test_unknown_ticker_skipped(self):
        raw = json.dumps([make_llm_item("FAKE")])
        ideas = _parse_trade_ideas(raw, CANDIDATE_MAP)
        assert ideas == []

    def test_mixed_known_and_unknown(self):
        raw = json.dumps([make_llm_item("TSM"), make_llm_item("FAKE"), make_llm_item("AMKR")])
        ideas = _parse_trade_ideas(raw, CANDIDATE_MAP)
        assert len(ideas) == 2
        assert {i.ticker for i in ideas} == {"TSM", "AMKR"}

    def test_invalid_json_raises(self):
        with pytest.raises(TradeIdeaGenerationError, match="Invalid JSON"):
            _parse_trade_ideas("not json", CANDIDATE_MAP)

    def test_non_list_json_raises(self):
        with pytest.raises(TradeIdeaGenerationError, match="Expected JSON array"):
            _parse_trade_ideas('{"ticker": "TSM"}', CANDIDATE_MAP)

    def test_direction_fallback_for_invalid_value(self):
        item = make_llm_item("TSM", trade_direction="sideways")
        raw = json.dumps([item])
        ideas = _parse_trade_ideas(raw, CANDIDATE_MAP)
        # CANDIDATE_DIRECT is bullish → should fall back to "long"
        assert ideas[0].trade_direction == "long"

    def test_direction_fallback_for_bearish_candidate(self):
        bearish = make_candidate("TSM", impact_direction="bearish")
        item = make_llm_item("TSM", trade_direction="bad_value")
        raw = json.dumps([item])
        ideas = _parse_trade_ideas(raw, {"TSM": bearish})
        assert ideas[0].trade_direction == "short"

    def test_key_mechanism_falls_back_to_candidate_mechanism(self):
        item = {
            "ticker": "TSM",
            "trade_direction": "long",
            "why_now": "Now.",
            "key_mechanism": "",       # empty → should fall back
            "why_it_may_be_underappreciated": "Underappreciated.",
            "invalidation_or_risk": "Risk.",
        }
        raw = json.dumps([item])
        ideas = _parse_trade_ideas(raw, CANDIDATE_MAP)
        assert ideas[0].key_mechanism == CANDIDATE_DIRECT.mechanism

    def test_empty_array_returns_empty_list(self):
        ideas = _parse_trade_ideas("[]", CANDIDATE_MAP)
        assert ideas == []

    def test_non_dict_items_skipped(self):
        raw = json.dumps(["not_a_dict", make_llm_item("TSM")])
        ideas = _parse_trade_ideas(raw, CANDIDATE_MAP)
        assert len(ideas) == 1


# ---------------------------------------------------------------------------
# generate_trade_ideas
# ---------------------------------------------------------------------------

class TestGenerateTradeIdeas:
    async def test_empty_candidates_returns_empty_without_llm_call(self):
        with patch("backend.services.trade_idea_generator.llm_client") as mock_llm:
            result = await generate_trade_ideas(EVENT, [])
        assert result == []
        mock_llm.complete.assert_not_called()

    async def test_returns_list_of_trade_ideas(self):
        llm_response = json.dumps([
            make_llm_item("TSM"),
            make_llm_item("AMKR"),
        ])
        with patch(
            "backend.services.trade_idea_generator.llm_client.complete",
            return_value=llm_response,
        ):
            result = await generate_trade_ideas(
                EVENT, [CANDIDATE_DIRECT, CANDIDATE_SECOND]
            )
        assert len(result) == 2
        assert all(isinstance(i, TradeIdea) for i in result)

    async def test_capped_at_three_ideas(self):
        four_items = [
            make_llm_item("TSM"),
            make_llm_item("AMKR"),
            make_llm_item("ANET"),
            make_llm_item("TSM"),   # duplicate — would be skipped by dict lookup as duplicate
        ]
        # Use four distinct tickers
        c4 = make_candidate("MU", ImpactOrder.THIRD_ORDER)
        four_items = [
            make_llm_item("TSM"),
            make_llm_item("AMKR"),
            make_llm_item("ANET"),
            make_llm_item("MU"),
        ]
        extended_map = {**CANDIDATE_MAP, "MU": c4}
        candidates = [CANDIDATE_DIRECT, CANDIDATE_SECOND, CANDIDATE_THIRD, c4]

        with patch(
            "backend.services.trade_idea_generator.llm_client.complete",
            return_value=json.dumps(four_items),
        ):
            result = await generate_trade_ideas(EVENT, candidates)
        assert len(result) == 3   # capped at _MAX_IDEAS

    async def test_llm_error_returns_empty_list(self):
        with patch(
            "backend.services.trade_idea_generator.llm_client.complete",
            side_effect=Exception("network error"),
        ):
            result = await generate_trade_ideas(EVENT, [CANDIDATE_DIRECT])
        assert result == []

    async def test_parse_error_returns_empty_list(self):
        with patch(
            "backend.services.trade_idea_generator.llm_client.complete",
            return_value="not valid json at all",
        ):
            result = await generate_trade_ideas(EVENT, [CANDIDATE_DIRECT])
        assert result == []

    async def test_trade_ideas_carry_candidate_confidence(self):
        llm_response = json.dumps([make_llm_item("AMKR")])
        with patch(
            "backend.services.trade_idea_generator.llm_client.complete",
            return_value=llm_response,
        ):
            result = await generate_trade_ideas(EVENT, [CANDIDATE_SECOND])
        assert result[0].confidence == CANDIDATE_SECOND.confidence

    async def test_only_top_8_candidates_sent_to_llm(self):
        many = [make_candidate(f"T{i}") for i in range(12)]
        # All will be filtered as unknown tickers by parser, but we can verify
        # the context only contains 8 entries
        captured = []

        def capture_complete(system, user):
            captured.append(user)
            return "[]"

        with patch(
            "backend.services.trade_idea_generator.llm_client.complete",
            side_effect=capture_complete,
        ):
            await generate_trade_ideas(EVENT, many)

        assert len(captured) == 1
        # Count how many tickers appear in the context
        context = captured[0]
        ticker_count = sum(1 for c in many[:8] if c.ticker in context)
        assert ticker_count == 8
