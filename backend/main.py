import logging
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.api.routes import router

logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(
    title="Event-to-Trade Engine",
    version="0.1.0",
    description="Causal reasoning engine that maps financial news to trade candidates.",
)

app.include_router(router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).exception("Unhandled error on %s", request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )
