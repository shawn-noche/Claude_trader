import time
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.schemas.article import ArticleRequest
from backend.schemas.analysis import FinalAnalysis
from backend.services.ingestion import fetch_article, IngestionError
from backend.services.classifier import classify_event, ClassificationError
from backend.services.impact_engine import map_impacts, ImpactMappingError
from backend.services.ranker import rank

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=FinalAnalysis, status_code=200)
async def analyze(request: ArticleRequest) -> FinalAnalysis:
    """
    Full analysis pipeline.

    Step 1: ingest article       (complete)
    Step 2: classify event       (complete)
    Step 3: map impacts via KB   (complete)
    Step 4: rank candidates      (complete)
    Step 5: trade idea narrative (simple version — full LLM narrative in next step)
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

    # Step 5 — top trade idea (simple summary; full LLM narrative comes next step)
    top_trade_idea = _build_simple_trade_idea(candidates)

    duration = round(time.perf_counter() - start, 3)
    logger.info(
        "analyze done request_id=%s duration=%.3fs candidates=%d",
        request_id, duration, len(candidates),
    )

    return FinalAnalysis(
        request_id=request_id,
        analyzed_at=datetime.now(timezone.utc),
        article=article,
        event=event,
        candidates=candidates,
        top_trade_idea=top_trade_idea,
        duration_seconds=duration,
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_simple_trade_idea(candidates: list) -> str | None:
    """
    Build a one-line trade idea from the top-ranked non-obvious candidate.

    Skips direct/focal candidates when a higher-order play is available.
    Full LLM narrative (trade_ideas.txt) is wired in the next implementation step.
    """
    if not candidates:
        return None

    # Prefer the first second/third-order candidate over the top direct hit
    non_obvious = next(
        (c for c in candidates if c.impact_order.value != "direct"),
        candidates[0],  # fall back to best overall if all are direct
    )

    direction_word = "Long" if non_obvious.impact_direction == "bullish" else "Short"
    order_label = non_obvious.impact_order.value.replace("_", "-")
    return (
        f"{direction_word} {non_obvious.ticker} ({non_obvious.company_name}) — "
        f"{order_label} play, score={non_obvious.final_score:.3f}: "
        f"{non_obvious.mechanism}"
    )
