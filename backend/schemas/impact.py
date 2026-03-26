from enum import Enum
from pydantic import BaseModel
from .event import TimeHorizon


class ImpactOrder(str, Enum):
    DIRECT = "direct"               # focal entity itself, or mechanical 1-hop counterparty
    SECOND_ORDER = "second_order"   # one step removed — supplier's supplier, downstream integrator
    THIRD_ORDER = "third_order"     # structural read-through, 3+ hops, sector rotation


class ImpactCandidate(BaseModel):
    ticker: str
    company_name: str
    impact_direction: str           # "bullish" | "bearish" | "neutral"
    impact_order: ImpactOrder
    relationship_type: str          # KB relationship type linking this company to the event
    mechanism: str                  # one-sentence causal chain from event to this company's P&L
    confidence: float               # 0.0–1.0  (LLM certainty)
    time_horizon: TimeHorizon
    priced_in_assessment: float     # 0.0 = fresh surprise → 1.0 = fully priced in
    tradability_score: float        # 0.0–1.0  (liquidity, float, catalyst clarity)
    final_score: float              # computed by ranker; 0.0 until ranked
