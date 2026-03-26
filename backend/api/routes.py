import time
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.schemas.article import ArticleRequest
from backend.schemas.analysis import FinalAnalysis
from backend.services.ingestion import fetch_article, IngestionError
from backend.services.classifier import classify_event, ClassificationError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=FinalAnalysis, status_code=200)
async def analyze(request: ArticleRequest) -> FinalAnalysis:
    """
    Full analysis pipeline.

    Step 1: ingest article  (complete)
    Step 2: classify event  (complete)
    Step 3: impact mapping  (stub — coming next)
    Step 4: ranking         (stub — coming next)
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

    # Steps 3–4 — impact mapping and ranking (stubs, coming in step 3)
    # candidates = await map_impacts(event)
    # candidates = rank(candidates)

    duration = round(time.perf_counter() - start, 3)
    logger.info("analyze done request_id=%s duration=%.3fs", request_id, duration)

    return FinalAnalysis(
        request_id=request_id,
        analyzed_at=datetime.now(timezone.utc),
        article=article,
        event=event,
        candidates=[],
        top_trade_idea=None,
        duration_seconds=duration,
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
