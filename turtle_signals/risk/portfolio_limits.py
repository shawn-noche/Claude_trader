""" 
risk/portfolio_limits.py — Track open units and enforce Turtle portfolio limits.

Original Turtle Rules:
  - Max 4 units per single instrument
  - Max 12 total units across all positions
  - Max 6 units in same direction (long or short)
"""

import logging
from dataclasses import dataclass

from trades.database import get_db
from config import (
    MAX_UNITS_PER_INSTRUMENT,
    MAX_UNITS_TOTAL,
    MAX_UNITS_SAME_DIRECTION,
)

logger = logging.getLogger(__name__)


@dataclass
class PortfolioStatus:
    """Current state of the portfolio from a Turtle limits perspective."""
    total_units: int
    long_units: int
    short_units: int
    units_by_ticker: dict[str, int]
    max_total: int
    max_per_instrument: int
    max_same_direction: int

    @property
    def available_units(self) -> int:
        return max(0, self.max_total - self.total_units)

    @property
    def at_total_limit(self) -> bool:
        return self.total_units >= self.max_total

    def can_add_unit(self, ticker: str, direction: str) -> tuple[bool, str]:
        """
        Check if we can add one more unit to a given ticker.
        Returns (allowed: bool, reason: str).
        """
        ticker_units = self.units_by_ticker.get(ticker, 0)

        if self.total_units >= self.max_total:
            return False, f"Portfolio at max total units ({self.max_total})"

        if ticker_units >= self.max_per_instrument:
            return False, (
                f"{ticker} already at max units ({self.max_per_instrument}) "
                f"for a single instrument"
            )

        same_dir = self.long_units if direction == "long" else self.short_units
        if same_dir >= self.max_same_direction:
            return False, (
                f"Max {self.max_same_direction} units in same direction reached "
                f"({'longs' if direction == 'long' else 'shorts'})"
            )

        return True, "OK"


def get_portfolio_status() -> PortfolioStatus:
    """
    Query the database for all open trades and compute current unit counts.
    """
    db = get_db()
    try:
        rows = db.execute(
            """
            SELECT ticker, direction, current_units
            FROM my_trades
            WHERE status = 'open'
            """,
        ).fetchall()
    except Exception as exc:
        logger.warning("Could not query open trades: %s", exc)
        rows = []
    finally:
        db.close()

    units_by_ticker: dict[str, int] = {}
    long_units = 0
    short_units = 0

    for row in rows:
        ticker = row["ticker"]
        direction = row["direction"]
        units = row["current_units"] or 1

        units_by_ticker[ticker] = units_by_ticker.get(ticker, 0) + units

        if direction == "long":
            long_units += units
        else:
            short_units += units

    total_units = long_units + short_units

    return PortfolioStatus(
        total_units=total_units,
        long_units=long_units,
        short_units=short_units,
        units_by_ticker=units_by_ticker,
        max_total=MAX_UNITS_TOTAL,
        max_per_instrument=MAX_UNITS_PER_INSTRUMENT,
        max_same_direction=MAX_UNITS_SAME_DIRECTION,
    )


def check_entry_allowed(ticker: str, direction: str) -> tuple[bool, str]:
    """
    Main entry point to check if taking a new position is allowed.

    Args:
        ticker:    Instrument to trade.
        direction: 'long' or 'short'

    Returns:
        (allowed: bool, reason: str)
    """
    status = get_portfolio_status()
    return status.can_add_unit(ticker, direction)


def summarize_limits(status: PortfolioStatus) -> str:
    """Return a short human-readable summary of current portfolio limits."""
    lines = [
        f"Total Units  : {status.total_units} / {status.max_total}",
        f"Longs        : {status.long_units} / {status.max_same_direction}",
        f"Shorts       : {status.short_units} / {status.max_same_direction}",
        f"Available    : {status.available_units} units remaining",
    ]
    if status.units_by_ticker:
        lines.append("By Ticker    :")
        for t, u in sorted(status.units_by_ticker.items()):
            limit_warn = " \u2190 AT MAX" if u >= status.max_per_instrument else ""
            lines.append(f"  {t:<8} {u} / {status.max_per_instrument}{limit_warn}")
    return "\n".join(lines)
