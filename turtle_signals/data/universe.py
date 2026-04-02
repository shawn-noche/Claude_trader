"""
data/universe.py — Download and cache the Russell 2000 component ticker list.

Pulls the IWM (iShares Russell 2000 ETF) holdings CSV from iShares, which
is updated daily and freely available. Caches locally for 7 days.
"""

import logging
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "cache" / "russell2000_tickers.txt"
CACHE_MAX_AGE_DAYS = 7

IWM_URL = (
    "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
)


def get_universe_tickers(universe: str = "russell2000") -> list[str]:
    """Return tickers for the requested universe."""
    if universe == "russell2000":
        return get_russell2000_tickers()
    return []


def get_russell2000_tickers() -> list[str]:
    """Return the current Russell 2000 component tickers, cached locally."""
    if _cache_is_fresh():
        tickers = _load_cache()
        logger.info("Loaded %d Russell 2000 tickers from cache.", len(tickers))
        return tickers

    logger.info("Downloading Russell 2000 components from iShares IWM...")
    tickers = _download_iwm_holdings()

    if tickers:
        _save_cache(tickers)
        logger.info("Cached %d Russell 2000 tickers.", len(tickers))
        return tickers

    # Fall back to stale cache rather than returning nothing
    if CACHE_FILE.exists():
        logger.warning("Download failed — using stale cached tickers.")
        return _load_cache()

    logger.error("Could not obtain Russell 2000 ticker list.")
    return []


def _cache_is_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
    return age < timedelta(days=CACHE_MAX_AGE_DAYS)


def _load_cache() -> list[str]:
    return [t.strip() for t in CACHE_FILE.read_text().splitlines() if t.strip()]


def _save_cache(tickers: list[str]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text("\n".join(tickers))


def _download_iwm_holdings() -> list[str]:
    """Download IWM holdings CSV from iShares and extract equity tickers."""
    try:
        resp = requests.get(
            IWM_URL,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        resp.raise_for_status()

        lines = resp.text.splitlines()

        # iShares CSV has metadata rows at the top — find the header row
        data_start = 0
        for i, line in enumerate(lines):
            if "Ticker" in line and "Name" in line:
                data_start = i
                break

        df = pd.read_csv(StringIO("\n".join(lines[data_start:])), on_bad_lines="skip")

        if "Ticker" not in df.columns:
            logger.error(
                "Unexpected IWM CSV format — columns: %s", df.columns.tolist()
            )
            return []

        tickers = (
            df["Ticker"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
            .tolist()
        )

        # Keep only real equity tickers (letters only, 1-5 chars, no cash rows)
        tickers = [
            t for t in tickers
            if t
            and t not in {"-", "CASH", "USD", "N/A", "NAN", "XTSLA"}
            and 1 <= len(t) <= 5
            and t.replace(".", "").isalpha()
        ]

        return tickers

    except Exception as exc:
        logger.error("Failed to download IWM holdings: %s", exc)
        return []
