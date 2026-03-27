from pydantic import BaseModel
from datetime import datetime
from .article import Article
from .event import Event
from .impact import ImpactCandidate


class TradeIdea(BaseModel):
    ticker: str
    company_name: str
    trade_direction: str              # "long" | "short"
    chain_position: str               # "direct" | "second_order" | "third_order"
    why_now: str                      # timing or near-term catalyst that makes this actionable
    key_mechanism: str                # exact revenue/cost/volume line that changes
    why_it_may_be_underappreciated: str   # reason the street may not have modelled this
    confidence: float                 # carried from the source ImpactCandidate
    invalidation_or_risk: str         # single condition that kills the thesis


class ImpactBuckets(BaseModel):
    """
    Candidates organised by (order × direction).
    Neutral-direction candidates are excluded — they belong in the flat ranked list.
    """
    direct_beneficiaries: list[ImpactCandidate] = []
    second_order_beneficiaries: list[ImpactCandidate] = []
    third_order_beneficiaries: list[ImpactCandidate] = []
    direct_losers: list[ImpactCandidate] = []
    second_order_losers: list[ImpactCandidate] = []
    third_order_losers: list[ImpactCandidate] = []


class FinalAnalysis(BaseModel):
    request_id: str
    analyzed_at: datetime
    article: Article
    event: Event | None = None
    impact_buckets: ImpactBuckets = ImpactBuckets()   # categorised by direction and order
    candidates: list[ImpactCandidate] = []            # all ranked candidates, flat
    top_trade_ideas: list[TradeIdea] = []             # up to 3 structured LLM-generated ideas
    duration_seconds: float
