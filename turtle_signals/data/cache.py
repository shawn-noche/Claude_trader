"""
data/cache.py — CSV-based cache for daily OHLCV data with a 24-hour TTL.

Avoids hammering Yahoo Finance on every script run. Each ticker is saved
as a CSV file in data/cache/. Files older than CACHE_TTL_HOURS are refreshed.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from config import DATA_DIR, CACHE_TTL_HOURS
from data.fetcher import fetch_ohlcv

logger = logging.getLogger(__name__)

DATA_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(ticker: str) -> Path:
    """Return the cache file path for a given ticker."""
    return DATA_DIR / f"{ticker.upper()}.csv"


def _is_stale(path: Path) -> bool:
    """Return True if the file does not exist or is older than the TTL."""
    if not path.exists():
        return True
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age > timedelta(hours=CACHE_TTL_HOURS)


def load_cached(ticker: str, days: int = 200) -> Optional[pd.DataFrame]:
    """
    Load OHLCV data for a ticker from cache.
    Fetches fresh data from yfinance if the cache is stale or missing.

    Returns a DataFrame or None on failure.
    """
    path = _cache_path(ticker)

    if _is_stale(path):
        logger.debug("Cache miss or stale for %s — fetching from yfinance.", ticker)
        df = fetch_ohlcv(ticker, days=days)
        if df is None or df.empty:
            return None
        # Persist to CSV
        df.to_csv(path)
        logger.debug("Cached %d rows for %s at %s", len(df), ticker, path)
        return df

    # Load from cache
    try:
        df = pd.read_csv(path, index_col="Date", parse_dates=True)
        # If cached data is shorter than requested, top it up
        if len(df) < days * 0.7:
            logger.debug("Cached data too short for %s — refreshing.", ticker)
            df = fetch_ohlcv(ticker, days=days)
            if df is not None:
                df.to_csv(path)
        logger.debug("Loaded %d rows for %s from cache.", len(df), ticker)
        return df
    except Exception as exc:
        logger.warning("Failed to read cache for %s: %s — re-fetching.", ticker, exc)
        df = fetch_ohlcv(ticker, days=days)
        if df is not None:
            df.to_csv(path)
        return df


def load_all(tickers: list[str], days: int = 200) -> dict[str, pd.DataFrame]:
    """
    Load OHLCV data for all tickers, using cache where possible.
    Returns a dict {ticker: DataFrame}.
    """
    result: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        df = load_cached(ticker, days=days)
        if df is not None and not df.empty:
            result[ticker] = df
        else:
            logger.warning("No data available for %s — skipped.", ticker)
    return result


def invalidate(ticker: str) -> None:
    """Force-delete the cache file for a ticker so it refreshes next load."""
    path = _cache_path(ticker)
    if path.exists():
        path.unlink()
        logger.debug("Invalidated cache for %s.", ticker)


def invalidate_all() -> None:
    """Delete all cached CSVs to force a full refresh."""
    for path in DATA_DIR.glob("*.csv"):
        path.unlink()
    logger.info("All cache files deleted.")
