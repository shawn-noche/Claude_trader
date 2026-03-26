"""
Deterministic candidate scoring and ranking.

No LLM calls. Pure arithmetic so the formula is auditable and easy to tune.

Score components (weights sum to 1.0):
  order_score      0.30  — directness to the event source
  confidence       0.35  — LLM certainty about the impact
  tradability      0.20  — liquidity, float, catalyst clarity
  priced_in_factor 0.15  — penalty for already-discounted information

The raw weighted sum is then multiplied by a magnitude multiplier so that
a CRITICAL event produces higher absolute scores than a LOW event across the
board, reflecting the larger total opportunity set.

Final scores are clamped to [0.0, 1.0] and rounded to 4 decimal places.
"""

from backend.schemas.event import Magnitude
from backend.schemas.impact import ImpactCandidate, ImpactOrder

# ---------------------------------------------------------------------------
# Tunable weights  (must sum to 1.0)
# ---------------------------------------------------------------------------
_W_ORDER       = 0.30
_W_CONFIDENCE  = 0.35
_W_TRADABILITY = 0.20
_W_PRICED_IN   = 0.15

# Per-order base scores
_ORDER_SCORE: dict[str, float] = {
    ImpactOrder.DIRECT.value:       1.00,
    ImpactOrder.SECOND_ORDER.value: 0.65,
    ImpactOrder.THIRD_ORDER.value:  0.35,
}

# Event magnitude multiplier applied to the entire score
_MAGNITUDE_MULT: dict[str, float] = {
    Magnitude.LOW.value:      0.70,
    Magnitude.MEDIUM.value:   0.85,
    Magnitude.HIGH.value:     1.00,
    Magnitude.CRITICAL.value: 1.15,
}


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def rank(
    candidates: list[ImpactCandidate],
    event_magnitude: Magnitude,
) -> list[ImpactCandidate]:
    """
    Score every candidate and return them sorted by final_score descending.

    Returns a new list; the input objects are not mutated.
    """
    scored = [_score(c, event_magnitude) for c in candidates]
    return sorted(scored, key=lambda c: c.final_score, reverse=True)


def score_candidate(
    candidate: ImpactCandidate,
    event_magnitude: Magnitude,
) -> ImpactCandidate:
    """Score a single candidate. Exposed for testing."""
    return _score(candidate, event_magnitude)


# ---------------------------------------------------------------------------
# Internal scoring
# ---------------------------------------------------------------------------

def _score(candidate: ImpactCandidate, magnitude: Magnitude) -> ImpactCandidate:
    order_score = _ORDER_SCORE.get(candidate.impact_order.value, 0.35)
    priced_in_factor = 1.0 - (0.70 * candidate.priced_in_assessment)
    magnitude_mult = _MAGNITUDE_MULT.get(magnitude.value, 1.0)

    raw = (
        _W_ORDER       * order_score
        + _W_CONFIDENCE  * candidate.confidence
        + _W_TRADABILITY * candidate.tradability_score
        + _W_PRICED_IN   * priced_in_factor
    ) * magnitude_mult

    final = round(min(1.0, max(0.0, raw)), 4)
    return candidate.model_copy(update={"final_score": final})
