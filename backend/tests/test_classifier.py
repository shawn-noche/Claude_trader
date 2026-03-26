"""
Tests for the event classifier.

All LLM calls are mocked — no Anthropic API key required.
"""

import pytest
from unittest.mock import patch

from backend.schemas.article import Article
from backend.schemas.event import EventType, Direction, Magnitude, TimeHorizon
from backend.services.classifier import classify_event, ClassificationError, _parse_response

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DUMMY_ARTICLE = Article(
    url="https://example.com/article",
    title="NVIDIA Reports Record Q4 Revenue on Data Center Surge",
    text="NVIDIA reported record revenue of $22.1 billion for Q4, driven by data center GPU demand.",
    source_domain="example.com",
    char_count=88,
    extraction_method="trafilatura",
)

VALID_LLM_RESPONSE = """{
  "event_type": "earnings",
  "event_summary": "NVIDIA reported record Q4 revenue of $22.1 billion, exceeding analyst estimates by 12%. Data center revenue reached $18.4 billion, up 409% year over year, driven by H100 GPU demand from hyperscalers.",
  "focal_entities": ["NVDA"],
  "direction": "bullish",
  "magnitude": "high",
  "time_horizon": "intraday",
  "economic_mechanism": "Raises full-year earnings estimates across the AI GPU supply chain as data center demand exceeds prior guidance.",
  "confidence": 0.95
}"""

MARKDOWN_WRAPPED_RESPONSE = """```json
{
  "event_type": "supply_chain",
  "event_summary": "TSMC reported CoWoS advanced packaging capacity is constrained through Q3, limiting NVIDIA H100 shipment volumes.",
  "focal_entities": ["TSM", "NVDA"],
  "direction": "bearish",
  "magnitude": "medium",
  "time_horizon": "weeks",
  "economic_mechanism": "Reduces near-term NVIDIA GPU shipments as CoWoS bottleneck limits H100 output.",
  "confidence": 0.82
}
```"""


# ---------------------------------------------------------------------------
# _parse_response unit tests (no I/O)
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_valid_json_returns_event(self):
        event = _parse_response(VALID_LLM_RESPONSE)
        assert event.event_type == EventType.EARNINGS
        assert event.direction == Direction.BULLISH
        assert event.magnitude == Magnitude.HIGH
        assert event.time_horizon == TimeHorizon.INTRADAY
        assert "NVDA" in event.focal_entities
        assert event.confidence == pytest.approx(0.95)

    def test_strips_markdown_fences(self):
        event = _parse_response(MARKDOWN_WRAPPED_RESPONSE)
        assert event.event_type == EventType.SUPPLY_CHAIN
        assert event.direction == Direction.BEARISH
        assert "TSM" in event.focal_entities
        assert "NVDA" in event.focal_entities

    def test_unknown_event_type_falls_back_to_other(self):
        raw = '{"event_type": "alien_invasion", "event_summary": "x", "focal_entities": [], "direction": "neutral", "magnitude": "low", "time_horizon": "days", "economic_mechanism": "x", "confidence": 0.5}'
        event = _parse_response(raw)
        assert event.event_type == EventType.OTHER

    def test_unknown_direction_falls_back_to_neutral(self):
        raw = '{"event_type": "earnings", "event_summary": "x", "focal_entities": [], "direction": "sideways", "magnitude": "low", "time_horizon": "days", "economic_mechanism": "x", "confidence": 0.5}'
        event = _parse_response(raw)
        assert event.direction == Direction.NEUTRAL

    def test_unknown_magnitude_falls_back_to_low(self):
        raw = '{"event_type": "earnings", "event_summary": "x", "focal_entities": [], "direction": "bullish", "magnitude": "gigantic", "time_horizon": "days", "economic_mechanism": "x", "confidence": 0.5}'
        event = _parse_response(raw)
        assert event.magnitude == Magnitude.LOW

    def test_unknown_time_horizon_falls_back_to_weeks(self):
        raw = '{"event_type": "earnings", "event_summary": "x", "focal_entities": [], "direction": "bullish", "magnitude": "high", "time_horizon": "forever", "economic_mechanism": "x", "confidence": 0.5}'
        event = _parse_response(raw)
        assert event.time_horizon == TimeHorizon.WEEKS

    def test_confidence_clamped_to_zero_one(self):
        raw = '{"event_type": "earnings", "event_summary": "x", "focal_entities": [], "direction": "bullish", "magnitude": "high", "time_horizon": "days", "economic_mechanism": "x", "confidence": 1.5}'
        event = _parse_response(raw)
        assert event.confidence == pytest.approx(1.0)

    def test_missing_fields_use_safe_defaults(self):
        raw = '{"event_type": "earnings"}'
        event = _parse_response(raw)
        assert event.focal_entities == []
        assert event.direction == Direction.NEUTRAL
        assert event.magnitude == Magnitude.LOW
        assert event.time_horizon == TimeHorizon.WEEKS
        assert event.confidence == pytest.approx(0.5)
        assert event.event_summary == ""
        assert event.economic_mechanism == ""

    def test_invalid_json_raises_classification_error(self):
        with pytest.raises(ClassificationError, match="invalid JSON"):
            _parse_response("this is not json at all {{{")

    def test_json_array_raises_classification_error(self):
        with pytest.raises(ClassificationError, match="Expected a JSON object"):
            _parse_response("[1, 2, 3]")

    def test_focal_entities_string_coerced_to_list(self):
        raw = '{"event_type": "earnings", "event_summary": "x", "focal_entities": "NVDA", "direction": "bullish", "magnitude": "high", "time_horizon": "days", "economic_mechanism": "x", "confidence": 0.9}'
        event = _parse_response(raw)
        assert event.focal_entities == ["NVDA"]


# ---------------------------------------------------------------------------
# classify_event integration tests (LLM mocked)
# ---------------------------------------------------------------------------

class TestClassifyEvent:
    @pytest.mark.asyncio
    async def test_returns_typed_event(self):
        with patch("backend.services.classifier.llm_client.complete", return_value=VALID_LLM_RESPONSE):
            event = await classify_event(DUMMY_ARTICLE)

        assert event.event_type == EventType.EARNINGS
        assert event.direction == Direction.BULLISH
        assert event.magnitude == Magnitude.HIGH
        assert event.confidence > 0.9

    @pytest.mark.asyncio
    async def test_handles_markdown_wrapped_response(self):
        with patch("backend.services.classifier.llm_client.complete", return_value=MARKDOWN_WRAPPED_RESPONSE):
            event = await classify_event(DUMMY_ARTICLE)

        assert event.event_type == EventType.SUPPLY_CHAIN

    @pytest.mark.asyncio
    async def test_llm_failure_raises_classification_error(self):
        with patch(
            "backend.services.classifier.llm_client.complete",
            side_effect=Exception("API rate limit"),
        ):
            with pytest.raises(ClassificationError, match="LLM call failed"):
                await classify_event(DUMMY_ARTICLE)

    @pytest.mark.asyncio
    async def test_bad_json_raises_classification_error(self):
        with patch("backend.services.classifier.llm_client.complete", return_value="not json <<<"):
            with pytest.raises(ClassificationError):
                await classify_event(DUMMY_ARTICLE)
