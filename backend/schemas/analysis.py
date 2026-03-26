from pydantic import BaseModel
from datetime import datetime
from .article import Article
from .event import Event
from .impact import ImpactCandidate


class FinalAnalysis(BaseModel):
    request_id: str
    analyzed_at: datetime
    article: Article
    event: Event | None = None
    candidates: list[ImpactCandidate] = []
    top_trade_idea: str | None = None   # narrative from LLM (step 3 — not yet built)
    duration_seconds: float
