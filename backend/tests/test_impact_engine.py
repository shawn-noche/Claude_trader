"""
Impact engine tests — placeholder until step 3.
"""

import pytest
from backend.services.impact_engine import map_impacts
from backend.schemas.event import Event, EventType, Direction, Magnitude, TimeHorizon

DUMMY_EVENT = Event(
    event_type=EventType.EARNINGS,
    focal_entities=["NVDA"],
    direction=Direction.BULLISH,
    magnitude=Magnitude.HIGH,
    time_horizon=TimeHorizon.INTRADAY,
    economic_mechanism="Strong data center demand drives upward earnings revision cycle.",
    event_summary="NVIDIA beat Q4 estimates on data center GPU demand.",
    confidence=0.9,
)


@pytest.mark.asyncio
async def test_impact_engine_not_yet_implemented():
    with pytest.raises(NotImplementedError):
        await map_impacts(DUMMY_EVENT)
