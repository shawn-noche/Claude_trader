"""
data/fetcher.py — Fetch OHLCV price data from yfinance.

No API key needed. Uses free Yahoo Finance data via yfinance.
Returns clean pandas DataFrames with standard column names.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_ohlcv(
    ticker: str,
    days: int = 200,
    end_date: Optional[datetime] = None,
) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV data for a single ticker from Yahoo Finance.

    Args:
        ticker:   Ticker symbol (e.g. "GLD")
        days:     Number of calendar days of history to fetch (default 200)
        end_date: Optional end date for historical fetches (default: today)

    Returns:
        DataFrame with columns [Open, High, Low, Close, Volume] and
        a DatetimeIndex, or None if the fetch fails.
    """
    if end_date is None:
        end_date = datetime.today()

    start_date = end_date - timedelta(days=days)

    try:
        raw = yf.download(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,   # adjust prices for splits/dividends
        )
    except Exception as exc:
        logger.error("yfinance download failed for %s: %s", ticker, exc)
        return None

    if raw is None or raw.empty:
        logger.warning("No data returned for %s", ticker)
        return None

    # Flatten MultiIndex columns that yfinance sometimes produces
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    # Keep only the standard OHLCV columns we need
    cols_needed = ["Open", "High", "Low", "Close", "Volume"]
    available = [c for c in cols_needed if c in raw.columns]
    df = raw[available].copy()
    df.index.name = "Date"

    # Drop any rows with NaN close prices
    df = df.dropna(subset=["Close"])

    logger.debug("Fetched %d rows for %s", len(df), ticker)
    return df


def fetch_multiple(
    tickers: list[str],
    days: int = 200,
    end_date: Optional[datetime] = None,
) -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV data for multiple tickers. Returns a dict {ticker: DataFrame}.
    Tickers that fail are omitted from the result.
    """
    results: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        df = fetch_ohlcv(ticker, days=days, end_date=end_date)
        if df is not None and not df.empty:
            results[ticker] = df
        else:
            logger.warning("Skipping %s — no data available.", ticker)
    return results


def get_current_price(ticker: str) -> Optional[float]:
    """
    Return the latest closing price for a ticker.
    Used for real-time monitoring of open trades.
    """
    df = fetch_ohlcv(ticker, days=5)
    if df is None or df.empty:
        return None
    return float(df["Close"].iloc[-1])
