"""
Classifier tests — placeholder until step 2.
"""

import pytest
from backend.services.classifier import classify_event
from backend.schemas.article import Article

DUMMY_ARTICLE = Article(
    url="https://example.com/article",
    title="NVIDIA Q4 Earnings",
    text="NVIDIA reported strong Q4 results.",
    source_domain="example.com",
    char_count=36,
    extraction_method="trafilatura",
)


@pytest.mark.asyncio
async def test_classifier_not_yet_implemented():
    with pytest.raises(NotImplementedError):
        await classify_event(DUMMY_ARTICLE)
