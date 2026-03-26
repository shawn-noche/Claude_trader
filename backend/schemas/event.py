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


class Event(BaseModel):
    event_type: EventType
    focal_entities: list[str]          # ticker symbols or company names
    direction: Direction
    magnitude: Magnitude
    economic_mechanism: str            # one-sentence causal summary
    summary: str                       # 2–3 sentence event summary
    confidence: float                  # 0.0–1.0
