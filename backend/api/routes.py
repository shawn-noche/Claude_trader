import time
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.schemas.article import ArticleRequest, Article
from backend.schemas.analysis import FinalAnalysis
from backend.services.ingestion import fetch_article, IngestionError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=FinalAnalysis, status_code=200)
async def analyze(request: ArticleRequest) -> FinalAnalysis:
    """
    Full analysis pipeline.

    Currently implements step 1 (ingestion only).
    Classifier, impact engine, and ranker are stubs — will be wired in step 2/3.
    """
    request_id = str(uuid.uuid4())
    start = time.perf_counter()
    url = str(request.url)

    logger.info("analyze request_id=%s url=%s", request_id, url)

    # Step 1 — ingest
    try:
        article = await fetch_article(url)
    except IngestionError as exc:
        logger.warning("Ingestion failed request_id=%s: %s", request_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))

    # Steps 2–4 are stubs for now
    # event = await classify_event(article)
    # candidates = await map_impacts(event)
    # candidates = rank(candidates)

    duration = round(time.perf_counter() - start, 3)
    logger.info("analyze done request_id=%s duration=%.3fs", request_id, duration)

    # Return a partial analysis (event/candidates/top_trade_idea are None until later steps)
    return FinalAnalysis(
        request_id=request_id,
        analyzed_at=datetime.now(timezone.utc),
        article=article,
        event=None,        # type: ignore[arg-type]
        candidates=[],
        top_trade_idea=None,
        duration_seconds=duration,
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
