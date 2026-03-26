"""
Event classification service — stub.

Will be fully implemented in the next step.
Exposes classify_event() so the route can import it without breaking.
"""

from backend.schemas.article import Article
from backend.schemas.event import Event


async def classify_event(article: Article) -> Event:
    raise NotImplementedError("classifier not yet implemented — coming in step 2")
