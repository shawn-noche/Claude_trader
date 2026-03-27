"""
Top trade idea generation layer.

Takes the classified event + top-ranked candidates and uses an LLM to produce
up to 3 structured TradeIdea objects. Each idea is pinned to a specific candidate
ticker from the ranked list — the same anti-hallucination guarantee used in the
impact engine applies here.

Gracefully returns an empty list on LLM failure, parse error, or empty input.
"""

import asyncio
import json
import logging
from pathlib import Path

from backend.schemas.event import Event
from backend.schemas.impact import ImpactCandidate
from backend.schemas.analysis import TradeIdea
from backend.services import llm_client

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"
_MAX_IDEAS = 3
_MAX_INPUT_CANDIDATES = 8   # feed only the top N to keep the prompt focused

_PROMPTS: dict[str, str] = {}


class TradeIdeaGenerationError(Exception):
    """Raised internally when generation fails unrecoverably."""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def generate_trade_ideas(
    event: Event,
    ranked_candidates: list[ImpactCandidate],
) -> list[TradeIdea]:
    """
    Generate up to 3 structured trade ideas from the ranked candidate list.

    Returns an empty list (never raises) when candidates are empty, the LLM
    call fails, or the response cannot be parsed.
    """
    if not ranked_candidates:
        return []

    candidate_map = {c.ticker: c for c in ranked_candidates}
    top = ranked_candidates[:_MAX_INPUT_CANDIDATES]

    system_prompt = _load_prompt("trade_ideas.txt")
    user_prompt = _build_trade_context(event, top)

    try:
        raw = await asyncio.to_thread(llm_client.complete, system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("Trade idea LLM call failed: %s — returning empty list", exc)
        return []

    try:
        ideas = _parse_trade_ideas(raw, candidate_map)
    except TradeIdeaGenerationError as exc:
        logger.warning("Trade idea parse failed: %s — returning empty list", exc)
        return []

    ideas = ideas[:_MAX_IDEAS]
    logger.info("Trade idea generation complete: %d ideas", len(ideas))
    return ideas


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_trade_context(event: Event, candidates: list[ImpactCandidate]) -> str:
    event_dict = {
        "event_type": event.event_type.value,
        "event_summary": event.event_summary,
        "focal_entities": event.focal_entities,
        "direction": event.direction.value,
        "magnitude": event.magnitude.value,
        "time_horizon": event.time_horizon.value,
        "economic_mechanism": event.economic_mechanism,
    }

    candidate_dicts = [
        {
            "ticker": c.ticker,
            "company_name": c.company_name,
            "impact_direction": c.impact_direction,
            "impact_order": c.impact_order.value,
            "relationship_type": c.relationship_type,
            "mechanism": c.mechanism,
            "confidence": c.confidence,
            "priced_in_assessment": c.priced_in_assessment,
            "tradability_score": c.tradability_score,
            "final_score": c.final_score,
        }
        for c in candidates
    ]

    parts = [
        "EVENT:",
        json.dumps(event_dict, indent=2),
        "",
        f"RANKED CANDIDATES ({len(candidates)} total, sorted by final_score descending):",
        json.dumps(candidate_dicts, indent=2),
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_trade_ideas(
    raw: str,
    candidate_map: dict[str, ImpactCandidate],
) -> list[TradeIdea]:
    cleaned = _strip_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise TradeIdeaGenerationError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise TradeIdeaGenerationError(f"Expected JSON array, got {type(data).__name__}")

    ideas: list[TradeIdea] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        ticker = str(item.get("ticker") or "").upper().strip()
        if not ticker:
            continue

        # Anti-hallucination: only accept tickers that were in the candidate list
        candidate = candidate_map.get(ticker)
        if candidate is None:
            logger.warning("Trade idea returned unknown ticker %r — skipped", ticker)
            continue

        direction = str(item.get("trade_direction") or "").lower().strip()
        if direction not in ("long", "short"):
            direction = "long" if candidate.impact_direction == "bullish" else "short"

        try:
            idea = TradeIdea(
                ticker=ticker,
                company_name=candidate.company_name,
                trade_direction=direction,
                chain_position=candidate.impact_order.value,
                why_now=str(item.get("why_now") or "").strip(),
                key_mechanism=str(
                    item.get("key_mechanism") or candidate.mechanism
                ).strip(),
                why_it_may_be_underappreciated=str(
                    item.get("why_it_may_be_underappreciated") or ""
                ).strip(),
                confidence=candidate.confidence,
                invalidation_or_risk=str(
                    item.get("invalidation_or_risk") or ""
                ).strip(),
            )
            ideas.append(idea)
        except Exception as exc:
            logger.warning(
                "Could not build TradeIdea for %s: %s — skipped", ticker, exc
            )

    return ideas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
    return "\n".join(lines[1:end])


def _load_prompt(filename: str) -> str:
    if filename not in _PROMPTS:
        _PROMPTS[filename] = (_PROMPT_DIR / filename).read_text(encoding="utf-8")
    return _PROMPTS[filename]
