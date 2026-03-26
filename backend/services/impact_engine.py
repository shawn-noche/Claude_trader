"""
Impact engine — stub.

Will be fully implemented in step 3.
"""

from backend.schemas.event import Event
from backend.schemas.impact import ImpactCandidate


async def map_impacts(event: Event) -> list[ImpactCandidate]:
    raise NotImplementedError("impact_engine not yet implemented — coming in step 3")
