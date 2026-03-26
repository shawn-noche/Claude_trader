"""
Hybrid impact mapping engine.

Flow:
  1. Resolve focal entities from the KB (article entities → KB company records)
  2. Build a constrained candidate universe via the ecosystem graph (max 2 hops)
  3. Serialise event + universe into a structured LLM context
  4. Call Claude; receive a JSON array of impact assessments
  5. Parse, validate, and coerce into typed ImpactCandidate objects
  6. Filter out low-confidence noise

The LLM reasons; the KB constrains. Candidates that aren't in the KB cannot appear
in the output — this is the core guarantee that prevents hallucinated tickers.
"""

import asyncio
import json
import logging
from pathlib import Path

from backend.schemas.event import Event, TimeHorizon
from backend.schemas.impact import ImpactCandidate, ImpactOrder
from backend.services import knowledge_base as kb
from backend.services import llm_client

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"
_MIN_CONFIDENCE = 0.40          # candidates below this are discarded
_MAX_CANDIDATES_RETURNED = 12   # cap to keep output focused

# Cached prompt strings
_PROMPTS: dict[str, str] = {}


class ImpactMappingError(Exception):
    """Raised when impact mapping fails unrecoverably."""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def map_impacts(event: Event) -> list[ImpactCandidate]:
    """
    Map the market event to a list of impact candidates.

    Returns an empty list (not an error) when no KB entities are resolved,
    so the pipeline can still return a partial FinalAnalysis.
    """
    focal_companies = kb.resolve_entities(event.focal_entities)

    if not focal_companies:
        logger.warning(
            "No KB entities resolved for focal_entities=%s; skipping impact mapping",
            event.focal_entities,
        )
        return []

    candidate_universe = _build_candidate_universe(focal_companies)
    logger.info(
        "Candidate universe: %d companies (%d focal + %d 1-hop + %d 2-hop)",
        len(candidate_universe),
        sum(1 for d in candidate_universe.values() if d["hop"] == 0),
        sum(1 for d in candidate_universe.values() if d["hop"] == 1),
        sum(1 for d in candidate_universe.values() if d["hop"] == 2),
    )

    system_prompt = _load_prompt("map_impacts.txt")
    user_prompt = _build_impact_context(event, focal_companies, candidate_universe)

    try:
        raw = await asyncio.to_thread(llm_client.complete, system_prompt, user_prompt)
    except Exception as exc:
        raise ImpactMappingError(f"LLM call failed: {exc}") from exc

    candidates = _parse_impact_response(raw, candidate_universe)

    before = len(candidates)
    candidates = [c for c in candidates if c.confidence >= _MIN_CONFIDENCE]
    if before != len(candidates):
        logger.info(
            "Filtered %d low-confidence candidates (threshold=%.2f)",
            before - len(candidates),
            _MIN_CONFIDENCE,
        )

    candidates = candidates[:_MAX_CANDIDATES_RETURNED]
    logger.info("Impact mapping complete: %d candidates returned", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Candidate universe builder
# ---------------------------------------------------------------------------

def _build_candidate_universe(focal_companies: list[dict]) -> dict[str, dict]:
    """
    Walk the KB graph up to 2 hops from focal entities.

    Returns a dict keyed by ticker. Each value is the company record augmented
    with:
      hop        — 0 (focal), 1 (direct), 2 (extended)
      connection — the KB relationship dict that connects it to the graph
      via        — ticker of the hop-1 company this was reached through (hop-2 only)
    """
    universe: dict[str, dict] = {}

    # Hop 0 — focal entities themselves
    for company in focal_companies:
        universe[company["ticker"]] = {**company, "hop": 0, "connection": None, "via": None}

    # Hop 1 — direct relationships to/from each focal entity
    for focal in focal_companies:
        focal_ticker = focal["ticker"]
        _add_relationship_targets(universe, focal_ticker, hop=1, via=None)

    # Hop 2 — relationships of hop-1 companies (one more step out)
    hop1_tickers = [t for t, d in universe.items() if d["hop"] == 1]
    for ticker in hop1_tickers:
        _add_relationship_targets(universe, ticker, hop=2, via=ticker)

    return universe


def _add_relationship_targets(
    universe: dict[str, dict],
    source_ticker: str,
    hop: int,
    via: str | None,
) -> None:
    """Add companies reachable from source_ticker (both directions) into universe."""
    all_rels = (
        kb.get_relationships(source_ticker)
        + kb.get_inbound_relationships(source_ticker)
    )
    for rel in all_rels:
        # The other end of this relationship
        other = rel["to"] if rel["from"].upper() == source_ticker.upper() else rel["from"]
        if other in universe:
            continue
        company = kb.get_company(other)
        if company:
            universe[other] = {**company, "hop": hop, "connection": rel, "via": via}


# ---------------------------------------------------------------------------
# LLM context builder
# ---------------------------------------------------------------------------

def _build_impact_context(
    event: Event,
    focal_companies: list[dict],
    candidate_universe: dict[str, dict],
) -> str:
    parts: list[str] = []

    # --- Event ---
    parts.append("EVENT:")
    parts.append(json.dumps(_event_to_dict(event), indent=2))
    parts.append("")

    # --- Focal companies ---
    parts.append("FOCAL COMPANIES (primary subjects of this event):")
    for c in focal_companies:
        parts.append(f"[{c['ticker']}] {c['name']}")
        parts.append(f"  Sector: {c.get('sub_sector') or c.get('sector', '')}")
        parts.append(f"  Roles: {', '.join(c.get('roles', []))}")
        desc = c.get("description", "")
        parts.append(f"  {desc[:140]}")
    parts.append("")

    # --- Direct ecosystem (hop 1) ---
    hop1 = [(t, d) for t, d in candidate_universe.items() if d["hop"] == 1]
    if hop1:
        parts.append(f"DIRECT ECOSYSTEM ({len(hop1)} companies, 1-hop from focal entities):")
        for ticker, data in sorted(hop1):
            _append_candidate_block(parts, ticker, data, show_via=False)
        parts.append("")

    # --- Extended ecosystem (hop 2) ---
    hop2 = [(t, d) for t, d in candidate_universe.items() if d["hop"] == 2]
    if hop2:
        parts.append(f"EXTENDED ECOSYSTEM ({len(hop2)} companies, 2-hops from focal entities):")
        for ticker, data in sorted(hop2):
            _append_candidate_block(parts, ticker, data, show_via=True)
        parts.append("")

    total = len(candidate_universe)
    parts.append(
        f"Assess the impact of this event on the {total} companies above. "
        "Use only these tickers. Return a JSON array."
    )
    return "\n".join(parts)


def _append_candidate_block(
    parts: list[str], ticker: str, data: dict, show_via: bool
) -> None:
    conn = data.get("connection")
    via = data.get("via")
    sub = data.get("sub_sector") or data.get("sector", "")
    parts.append(f"[{ticker}] {data['name']} | {sub}")
    if conn:
        strength = conn.get("strength", "")
        rel_str = f"  Link: {conn['from']} → {conn['to']} ({conn['type']}, {strength})"
        if show_via and via:
            rel_str += f"  [via {via}]"
        parts.append(rel_str)
        desc = conn.get("description", "")
        if desc:
            parts.append(f"  \"{desc[:130]}\"")


def _event_to_dict(event: Event) -> dict:
    """Serialise event enums to their string values for the LLM."""
    return {
        "event_type": event.event_type.value,
        "event_summary": event.event_summary,
        "focal_entities": event.focal_entities,
        "direction": event.direction.value,
        "magnitude": event.magnitude.value,
        "time_horizon": event.time_horizon.value,
        "economic_mechanism": event.economic_mechanism,
        "confidence": event.confidence,
    }


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_impact_response(
    raw: str,
    candidate_universe: dict[str, dict],
) -> list[ImpactCandidate]:
    cleaned = _strip_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ImpactMappingError(
            f"LLM returned invalid JSON: {exc}\nRaw (first 500): {raw[:500]}"
        ) from exc

    if not isinstance(data, list):
        raise ImpactMappingError(
            f"Expected JSON array from LLM, got {type(data).__name__}"
        )

    candidates: list[ImpactCandidate] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        ticker = str(item.get("ticker") or "").upper().strip()
        if not ticker:
            continue

        # Hard constraint: only accept tickers from the KB universe
        if ticker not in candidate_universe:
            logger.warning("LLM returned ticker %r not in candidate universe — skipped", ticker)
            continue

        company = kb.get_company(ticker)
        company_name = company["name"] if company else ticker

        try:
            candidate = ImpactCandidate(
                ticker=ticker,
                company_name=company_name,
                impact_direction=_coerce_direction(item.get("impact_direction")),
                impact_order=_coerce_impact_order(item.get("impact_order")),
                relationship_type=str(item.get("relationship_type") or "unknown"),
                mechanism=str(item.get("mechanism") or "").strip(),
                confidence=_coerce_float(item.get("confidence"), default=0.5),
                time_horizon=_coerce_time_horizon(item.get("time_horizon")),
                priced_in_assessment=_coerce_float(item.get("priced_in_assessment"), default=0.3),
                tradability_score=_coerce_float(item.get("tradability_score"), default=0.5),
                final_score=0.0,  # set by ranker
            )
            candidates.append(candidate)
        except Exception as exc:
            logger.warning("Could not parse impact item for %s: %s — skipped", ticker, exc)

    return candidates


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

def _coerce_direction(value) -> str:
    v = str(value or "").lower().strip()
    return v if v in ("bullish", "bearish", "neutral") else "neutral"


def _coerce_impact_order(value) -> ImpactOrder:
    v = str(value or "").lower().strip()
    try:
        return ImpactOrder(v)
    except ValueError:
        logger.warning("Unknown impact_order %r — defaulting to third_order", value)
        return ImpactOrder.THIRD_ORDER


def _coerce_time_horizon(value) -> TimeHorizon:
    v = str(value or "").lower().strip()
    try:
        return TimeHorizon(v)
    except ValueError:
        logger.warning("Unknown time_horizon %r — defaulting to weeks", value)
        return TimeHorizon.WEEKS


def _coerce_float(value, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


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
