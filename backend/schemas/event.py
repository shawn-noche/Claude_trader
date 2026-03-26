from enum import Enum
from pydantic import BaseModel


class EventType(str, Enum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    PRODUCT_LAUNCH = "product_launch"
    SUPPLY_CHAIN = "supply_chain"
    REGULATORY = "regulatory"
    MA = "ma"  # mergers & acquisitions
    GEOPOLITICAL = "geopolitical"
    MACRO = "macro"
    PARTNERSHIP = "partnership"
    PERSONNEL = "personnel"
    OTHER = "other"


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class Magnitude(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TimeHorizon(str, Enum):
    INTRADAY = "intraday"   # same-day price reaction
    DAYS = "days"           # 1–5 trading days
    WEEKS = "weeks"         # 1–4 weeks
    MONTHS = "months"       # 1–3 months
    LONG_TERM = "long_term" # 3+ months / structural


class Event(BaseModel):
    event_type: EventType
    focal_entities: list[str]       # ticker symbols or company names
    direction: Direction
    magnitude: Magnitude
    time_horizon: TimeHorizon
    economic_mechanism: str         # one-sentence causal chain, starts with a verb
    event_summary: str              # 2–3 sentence summary of the market event
    confidence: float               # 0.0–1.0
