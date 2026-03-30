"""
signals/filters.py — System 1 Winner-Filter logic.

Original Turtle Rule: Do NOT take a System 1 entry signal if the
PREVIOUS System 1 signal for that ticker was a winner.

Rationale: This filter prevents chasing a trend that has already been
captured once. If the last S1 trade was profitable, it suggests a trend
is maturing — wait for the next fresh breakout.

System 2 has NO filter — always take every System 2 signal.
"""

import logging
from typing import Optional

from trades.database import get_db

logger = logging.getLogger(__name__)


def was_previous_s1_signal_winner(ticker: str) -> bool:
    """
    Check the database for the most recently CLOSED System 1 trade on
    this ticker and determine whether it was a winner (positive P&L).

    Returns:
        True  → previous S1 trade was profitable → SKIP this new S1 entry
        False → previous S1 trade was a loss, or no prior S1 trade exists
                → TAKE this entry signal
    """
    db = get_db()
    try:
        row = db.execute(
            """
            SELECT pnl
            FROM my_trades
            WHERE ticker = ?
              AND system = 1
              AND status = 'closed'
            ORDER BY exit_date DESC
            LIMIT 1
            """,
            (ticker,),
        ).fetchone()
    except Exception as exc:
        logger.warning("Filter DB query failed for %s: %s", ticker, exc)
        return False
    finally:
        db.close()

    if row is None:
        # No prior System 1 trade on record → take the signal
        return False

    pnl = row["pnl"]
    if pnl is None:
        return False

    return float(pnl) > 0   # True if the last S1 trade made money


def apply_s1_filter(ticker: str, signal_type: str) -> bool:
    """
    Decide whether to SKIP a System 1 entry signal.

    Args:
        ticker:      The instrument ticker.
        signal_type: 'entry_long' or 'entry_short'.

    Returns:
        True  → signal is filtered out (skip it)
        False → signal is valid (take it)
    """
    # Only filter entry signals, never exit signals
    if "entry" not in signal_type:
        return False

    filtered = was_previous_s1_signal_winner(ticker)
    if filtered:
        logger.info(
            "[%s] System 1 entry FILTERED — previous S1 trade was a winner.",
            ticker,
        )
    return filtered


def get_filter_status(tickers: list[str]) -> dict[str, bool]:
    """
    Return the filter status (should_skip) for all tickers at once.
    Useful for the dashboard to show which tickers have the filter active.
    """
    return {ticker: apply_s1_filter(ticker, "entry_long") for ticker in tickers}
