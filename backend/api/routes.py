import time
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.schemas.article import ArticleRequest
from backend.schemas.analysis import FinalAnalysis, ImpactBuckets
from backend.schemas.impact import ImpactCandidate
from backend.services.ingestion import fetch_article, IngestionError
from backend.services.classifier import classify_event, ClassificationError
from backend.services.impact_engine import map_impacts, ImpactMappingError
from backend.services.ranker import rank
from backend.services.trade_idea_generator import generate_trade_ideas

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=FinalAnalysis, status_code=200)
async def analyze(request: ArticleRequest) -> FinalAnalysis:
    """
    Full analysis pipeline.

    Step 1: ingest article           (complete)
    Step 2: classify event           (complete)
    Step 3: map impacts via KB       (complete)
    Step 4: rank candidates          (complete)
    Step 5: build impact buckets     (complete)
    Step 6: generate top trade ideas (complete)
    """
    request_id = str(uuid.uuid4())
    start = time.perf_counter()
    url = str(request.url)

    logger.info("analyze start request_id=%s url=%s", request_id, url)

    # Step 1 — ingest
    try:
        article = await fetch_article(url)
    except IngestionError as exc:
        logger.warning("Ingestion failed request_id=%s: %s", request_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))

    # Step 2 — classify
    try:
        event = await classify_event(article)
    except ClassificationError as exc:
        logger.warning("Classification failed request_id=%s: %s", request_id, exc)
        raise HTTPException(status_code=422, detail=f"Classification error: {exc}")

    # Step 3 — impact mapping (graceful degradation: errors → empty candidates)
    try:
        candidates = await map_impacts(event)
    except ImpactMappingError as exc:
        logger.warning("Impact mapping failed request_id=%s: %s", request_id, exc)
        candidates = []

    # Step 4 — rank
    candidates = rank(candidates, event.magnitude)

    # Step 5 — bucket by direction × order
    impact_buckets = _build_impact_buckets(candidates)

    # Step 6 — generate trade ideas (graceful degradation: errors/empty → [])
    try:
        top_trade_ideas = await generate_trade_ideas(event, candidates)
    except Exception as exc:
        logger.warning("Trade idea generation failed request_id=%s: %s", request_id, exc)
        top_trade_ideas = []

    duration = round(time.perf_counter() - start, 3)
    logger.info(
        "analyze done request_id=%s duration=%.3fs candidates=%d ideas=%d",
        request_id, duration, len(candidates), len(top_trade_ideas),
    )

    return FinalAnalysis(
        request_id=request_id,
        analyzed_at=datetime.now(timezone.utc),
        article=article,
        event=event,
        impact_buckets=impact_buckets,
        candidates=candidates,
        top_trade_ideas=top_trade_ideas,
        duration_seconds=duration,
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_impact_buckets(candidates: list[ImpactCandidate]) -> ImpactBuckets:
    """Split ranked candidates into (order × direction) buckets. Neutral candidates excluded."""
    buckets: dict[str, list[ImpactCandidate]] = {
        "direct_beneficiaries": [],
        "second_order_beneficiaries": [],
        "third_order_beneficiaries": [],
        "direct_losers": [],
        "second_order_losers": [],
        "third_order_losers": [],
    }

    for c in candidates:
        if c.impact_direction == "neutral":
            continue
        suffix = "beneficiaries" if c.impact_direction == "bullish" else "losers"
        key = f"{c.impact_order.value}_{suffix}"
        if key in buckets:
            buckets[key].append(c)

    return ImpactBuckets(**buckets)
