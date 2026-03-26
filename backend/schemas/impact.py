from enum import Enum
from pydantic import BaseModel


class ImpactLayer(str, Enum):
    DIRECT = "direct"           # focal company or direct customer/supplier
    SECOND_ORDER = "second_order"   # one hop away in supply chain / ecosystem
    THIRD_ORDER = "third_order"     # two hops away or competitive read-through


class ImpactCandidate(BaseModel):
    ticker: str
    company_name: str
    layer: ImpactLayer
    direction: str                  # "bullish" | "bearish" | "neutral"
    rationale: str                  # causal chain explanation
    confidence: float               # 0.0–1.0
    sensitivity: float              # how exposed is this company: 0.0–1.0
    priced_in_likelihood: float     # how much is already in the price: 0.0–1.0
    tradability_score: float        # options liquidity, float, catalyst clarity: 0.0–1.0
    final_score: float              # computed by ranker
