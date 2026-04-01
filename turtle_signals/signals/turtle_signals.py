"""
signals/turtle_signals.py — Core Turtle Trading signal computation.

Implements Richard Dennis's original Turtle rules exactly:

SYSTEM 1 (Short-Term):
  Entry Long:  Close > 20-day highest high
  Entry Short: Close < 20-day lowest low
  Exit Long:   Close < 10-day lowest low
  Exit Short:  Close > 10-day highest high
  Filter:      Skip if previous System 1 signal was a winner

SYSTEM 2 (Long-Term):
  Entry Long:  Close > 55-day highest high
  Entry Short: Close < 55-day lowest low
  Exit Long:   Close < 20-day lowest low
  Exit Short:  Close > 20-day highest high
  Filter:      None — always take System 2 signals
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from config import (
    SYSTEM1_ENTRY, SYSTEM1_EXIT,
    SYSTEM2_ENTRY, SYSTEM2_EXIT,
    ATR_PERIOD, STOP_ATR_MULTIPLIER,
    PYRAMID_STEP_ATR, MAX_PYRAMID_UNITS,
    INITIAL_CAPITAL, RISK_PER_TRADE, MAX_RISK_PER_TRADE,
)
from signals.atr import wilder_atr, latest_atr


@dataclass
class Signal:
    """Represents a single trading signal for one ticker."""
    ticker: str
    date: str
    system: int                     # 1 or 2
    signal_type: str                # 'entry_long', 'entry_short', 'exit_long', 'exit_short'
    price: float                    # Current close price
    breakout_level: float           # The donchian channel level that was broken
    atr: float                      # ATR at signal time
    stop_loss: float                # Calculated stop-loss level
    unit_size: int                  # Recommended unit size at 1% risk
    unit_size_2pct: int             # Alternative at 2% risk
    risk_amount: float              # Dollar risk per unit (1%)
    total_cost: float               # Approximate total position cost
    max_risk_dollars: float         # Max dollar risk (1% of account)
    reason: str                     # Human-readable explanation
    pyramid_levels: list[float] = field(default_factory=list)  # Add-unit price levels
    days_in_previous_signal: Optional[int] = None
    filtered: bool = False          # True if System 1 winner-filter blocked it


def _donchian_high(series: pd.Series, period: int, offset: int = 1) -> float:
    """
    Highest high over the last `period` bars, ending `offset` bars ago.
    offset=1 means we exclude today (look at yesterday and before).
    This is the correct Turtle entry rule: break the PREVIOUS period's high.
    """
    window = series.iloc[-(period + offset): -offset] if offset > 0 else series.iloc[-period:]
    if len(window) < period:
        return float("nan")
    return float(window.max())


def _donchian_low(series: pd.Series, period: int, offset: int = 1) -> float:
    """
    Lowest low over the last `period` bars, ending `offset` bars ago.
    """
    window = series.iloc[-(period + offset): -offset] if offset > 0 else series.iloc[-period:]
    if len(window) < period:
        return float("nan")
    return float(window.min())


def compute_signals(
    ticker: str,
    df: pd.DataFrame,
    account_equity: float = INITIAL_CAPITAL,
    risk_pct: float = RISK_PER_TRADE,
    prev_s1_was_winner: bool = False,
) -> list[Signal]:
    """
    Compute all active signals for a ticker given its price history.

    Args:
        ticker:              Ticker symbol
        df:                  OHLCV DataFrame (at least 120 days)
        account_equity:      Current account equity for position sizing
        risk_pct:            Risk fraction per unit (default 1%)
        prev_s1_was_winner:  True = System 1 winner filter active, skip entry

    Returns:
        List of Signal objects (may be empty if no signals today).
    """
    if len(df) < SYSTEM2_ENTRY + 10:
        return []

    # Compute Wilder's ATR for the full history
    atr_series = wilder_atr(df, ATR_PERIOD)
    current_atr = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else 0.0

    if current_atr <= 0:
        return []

    current_close = float(df["Close"].iloc[-1])
    today_str = str(df.index[-1].date())

    signals: list[Signal] = []

    # ─── SYSTEM 1 SIGNALS ────────────────────────────────────────────────────
    # Entry: break the 20-day high/low (measured from yesterday back 20 days)
    s1_high = _donchian_high(df["High"], SYSTEM1_ENTRY, offset=1)
    s1_low = _donchian_low(df["Low"], SYSTEM1_ENTRY, offset=1)
    # Exit: break the 10-day high/low
    s1_exit_low = _donchian_low(df["Low"], SYSTEM1_EXIT, offset=0)   # today inclusive
    s1_exit_high = _donchian_high(df["High"], SYSTEM1_EXIT, offset=0)

    # System 1 Entry Long: today's close breaks above the 20-day highest high
    if current_close > s1_high and not pd.isna(s1_high):
        stop = current_close - STOP_ATR_MULTIPLIER * current_atr
        unit = _calc_unit_size(account_equity, risk_pct, current_atr)
        unit_2pct = _calc_unit_size(account_equity, MAX_RISK_PER_TRADE, current_atr)
        risk_amt = current_atr * STOP_ATR_MULTIPLIER
        pyramid = _pyramid_levels(current_close, current_atr, "long")
        sig = Signal(
            ticker=ticker,
            date=today_str,
            system=1,
            signal_type="entry_long",
            price=current_close,
            breakout_level=s1_high,
            atr=current_atr,
            stop_loss=round(stop, 2),
            unit_size=unit,
            unit_size_2pct=unit_2pct,
            risk_amount=round(risk_amt, 2),
            total_cost=round(unit * current_close, 2),
            max_risk_dollars=round(account_equity * risk_pct, 2),
            reason=(
                f"Price closed above {SYSTEM1_ENTRY}-day high of ${s1_high:.2f} "
                f"(System 1 breakout)"
            ),
            pyramid_levels=pyramid,
            filtered=prev_s1_was_winner,   # mark but still include in list
        )
        signals.append(sig)

    # System 1 Entry Short: today's close breaks below the 20-day lowest low
    if current_close < s1_low and not pd.isna(s1_low):
        stop = current_close + STOP_ATR_MULTIPLIER * current_atr
        unit = _calc_unit_size(account_equity, risk_pct, current_atr)
        unit_2pct = _calc_unit_size(account_equity, MAX_RISK_PER_TRADE, current_atr)
        risk_amt = current_atr * STOP_ATR_MULTIPLIER
        pyramid = _pyramid_levels(current_close, current_atr, "short")
        sig = Signal(
            ticker=ticker,
            date=today_str,
            system=1,
            signal_type="entry_short",
            price=current_close,
            breakout_level=s1_low,
            atr=current_atr,
            stop_loss=round(stop, 2),
            unit_size=unit,
            unit_size_2pct=unit_2pct,
            risk_amount=round(risk_amt, 2),
            total_cost=round(unit * current_close, 2),
            max_risk_dollars=round(account_equity * risk_pct, 2),
            reason=(
                f"Price closed below {SYSTEM1_ENTRY}-day low of ${s1_low:.2f} "
                f"(System 1 breakout)"
            ),
            pyramid_levels=pyramid,
            filtered=prev_s1_was_winner,
        )
        signals.append(sig)

    # System 1 Exit Long: close breaks below the 10-day lowest low
    if current_close < s1_exit_low and not pd.isna(s1_exit_low):
        signals.append(Signal(
            ticker=ticker,
            date=today_str,
            system=1,
            signal_type="exit_long",
            price=current_close,
            breakout_level=s1_exit_low,
            atr=current_atr,
            stop_loss=0.0,
            unit_size=0,
            unit_size_2pct=0,
            risk_amount=0.0,
            total_cost=0.0,
            max_risk_dollars=0.0,
            reason=(
                f"Price broke below {SYSTEM1_EXIT}-day low of ${s1_exit_low:.2f} "
                f"(System 1 exit trigger)"
            ),
        ))

    # System 1 Exit Short: close breaks above the 10-day highest high
    if current_close > s1_exit_high and not pd.isna(s1_exit_high):
        signals.append(Signal(
            ticker=ticker,
            date=today_str,
            system=1,
            signal_type="exit_short",
            price=current_close,
            breakout_level=s1_exit_high,
            atr=current_atr,
            stop_loss=0.0,
            unit_size=0,
            unit_size_2pct=0,
            risk_amount=0.0,
            total_cost=0.0,
            max_risk_dollars=0.0,
            reason=(
                f"Price broke above {SYSTEM1_EXIT}-day high of ${s1_exit_high:.2f} "
                f"(System 1 short exit trigger)"
            ),
        ))

    # ─── SYSTEM 2 SIGNALS ────────────────────────────────────────────────────
    # Entry: break the 55-day high/low
    s2_high = _donchian_high(df["High"], SYSTEM2_ENTRY, offset=1)
    s2_low = _donchian_low(df["Low"], SYSTEM2_ENTRY, offset=1)
    # Exit: break the 20-day high/low
    s2_exit_low = _donchian_low(df["Low"], SYSTEM2_EXIT, offset=0)
    s2_exit_high = _donchian_high(df["High"], SYSTEM2_EXIT, offset=0)

    # System 2 Entry Long: today's close breaks above the 55-day highest high
    if current_close > s2_high and not pd.isna(s2_high):
        stop = current_close - STOP_ATR_MULTIPLIER * current_atr
        unit = _calc_unit_size(account_equity, risk_pct, current_atr)
        unit_2pct = _calc_unit_size(account_equity, MAX_RISK_PER_TRADE, current_atr)
        risk_amt = current_atr * STOP_ATR_MULTIPLIER
        pyramid = _pyramid_levels(current_close, current_atr, "long")
        # Count how many days since the last time price was at this high
        days_since = _days_since_last_high(df["High"], SYSTEM2_ENTRY)
        signals.append(Signal(
            ticker=ticker,
            date=today_str,
            system=2,
            signal_type="entry_long",
            price=current_close,
            breakout_level=s2_high,
            atr=current_atr,
            stop_loss=round(stop, 2),
            unit_size=unit,
            unit_size_2pct=unit_2pct,
            risk_amount=round(risk_amt, 2),
            total_cost=round(unit * current_close, 2),
            max_risk_dollars=round(account_equity * risk_pct, 2),
            reason=(
                f"Price closed above {SYSTEM2_ENTRY}-day high of ${s2_high:.2f} "
                f"for the first time in {days_since} days (System 2 breakout)"
            ),
            pyramid_levels=pyramid,
        ))

    # System 2 Entry Short: today's close breaks below the 55-day lowest low
    if current_close < s2_low and not pd.isna(s2_low):
        stop = current_close + STOP_ATR_MULTIPLIER * current_atr
        unit = _calc_unit_size(account_equity, risk_pct, current_atr)
        unit_2pct = _calc_unit_size(account_equity, MAX_RISK_PER_TRADE, current_atr)
        risk_amt = current_atr * STOP_ATR_MULTIPLIER
        pyramid = _pyramid_levels(current_close, current_atr, "short")
        days_since = _days_since_last_low(df["Low"], SYSTEM2_ENTRY)
        signals.append(Signal(
            ticker=ticker,
            date=today_str,
            system=2,
            signal_type="entry_short",
            price=current_close,
            breakout_level=s2_low,
            atr=current_atr,
            stop_loss=round(stop, 2),
            unit_size=unit,
            unit_size_2pct=unit_2pct,
            risk_amount=round(risk_amt, 2),
            total_cost=round(unit * current_close, 2),
            max_risk_dollars=round(account_equity * risk_pct, 2),
            reason=(
                f"Price closed below {SYSTEM2_ENTRY}-day low of ${s2_low:.2f} "
                f"for the first time in {days_since} days (System 2 breakout)"
            ),
            pyramid_levels=pyramid,
        ))

    # System 2 Exit Long: close breaks below the 20-day lowest low
    if current_close < s2_exit_low and not pd.isna(s2_exit_low):
        signals.append(Signal(
            ticker=ticker,
            date=today_str,
            system=2,
            signal_type="exit_long",
            price=current_close,
            breakout_level=s2_exit_low,
            atr=current_atr,
            stop_loss=0.0,
            unit_size=0,
            unit_size_2pct=0,
            risk_amount=0.0,
            total_cost=0.0,
            max_risk_dollars=0.0,
            reason=(
                f"Price broke below {SYSTEM2_EXIT}-day low of ${s2_exit_low:.2f} "
                f"(System 2 exit trigger)"
            ),
        ))

    # System 2 Exit Short: close breaks above the 20-day highest high
    if current_close > s2_exit_high and not pd.isna(s2_exit_high):
        signals.append(Signal(
            ticker=ticker,
            date=today_str,
            system=2,
            signal_type="exit_short",
            price=current_close,
            breakout_level=s2_exit_high,
            atr=current_atr,
            stop_loss=0.0,
            unit_size=0,
            unit_size_2pct=0,
            risk_amount=0.0,
            total_cost=0.0,
            max_risk_dollars=0.0,
            reason=(
                f"Price broke above {SYSTEM2_EXIT}-day high of ${s2_exit_high:.2f} "
                f"(System 2 short exit trigger)"
            ),
        ))

    return signals


def compute_watchlist_proximity(
    ticker: str,
    df: pd.DataFrame,
) -> dict:
    """
    Calculate how close the current price is to System 1 and System 2
    breakout levels. Used for the "Approaching Breakout" watchlist.

    Returns a dict with proximity percentages and level details.
    """
    if len(df) < SYSTEM2_ENTRY + 10:
        return {}

    current_close = float(df["Close"].iloc[-1])
    current_atr = latest_atr(df, ATR_PERIOD)

    s1_high = _donchian_high(df["High"], SYSTEM1_ENTRY, offset=1)
    s1_low = _donchian_low(df["Low"], SYSTEM1_ENTRY, offset=1)
    s2_high = _donchian_high(df["High"], SYSTEM2_ENTRY, offset=1)
    s2_low = _donchian_low(df["Low"], SYSTEM2_ENTRY, offset=1)

    def _proximity_to_high(price: float, level: float) -> float:
        """What fraction of the gap to the breakout has been covered from below?"""
        if pd.isna(level) or level <= 0:
            return 0.0
        # Look at lowest low over last 20 days as the "start" of the move
        recent_low = float(df["Low"].iloc[-SYSTEM1_ENTRY:].min())
        total_range = level - recent_low
        if total_range <= 0:
            return 1.0
        covered = price - recent_low
        return min(max(covered / total_range, 0.0), 1.0)

    def _proximity_to_low(price: float, level: float) -> float:
        """What fraction of the gap to the downside breakout has been covered?"""
        if pd.isna(level) or level <= 0:
            return 0.0
        recent_high = float(df["High"].iloc[-SYSTEM1_ENTRY:].max())
        total_range = recent_high - level
        if total_range <= 0:
            return 1.0
        covered = recent_high - price
        return min(max(covered / total_range, 0.0), 1.0)

    return {
        "ticker": ticker,
        "current_price": current_close,
        "atr": current_atr,
        # System 1 long breakout
        "s1_long_level": round(s1_high, 2) if not pd.isna(s1_high) else None,
        "s1_long_pct_away": round((s1_high - current_close) / current_close * 100, 2)
            if not pd.isna(s1_high) else None,
        "s1_long_proximity": round(_proximity_to_high(current_close, s1_high), 4)
            if not pd.isna(s1_high) else None,
        # System 1 short breakout
        "s1_short_level": round(s1_low, 2) if not pd.isna(s1_low) else None,
        "s1_short_pct_away": round((current_close - s1_low) / current_close * 100, 2)
            if not pd.isna(s1_low) else None,
        # System 2 long breakout
        "s2_long_level": round(s2_high, 2) if not pd.isna(s2_high) else None,
        "s2_long_pct_away": round((s2_high - current_close) / current_close * 100, 2)
            if not pd.isna(s2_high) else None,
        "s2_long_proximity": round(_proximity_to_high(current_close, s2_high), 4)
            if not pd.isna(s2_high) else None,
        # System 2 short breakout
        "s2_short_level": round(s2_low, 2) if not pd.isna(s2_low) else None,
        "s2_short_pct_away": round((current_close - s2_low) / current_close * 100, 2)
            if not pd.isna(s2_low) else None,
        # Potential stop if breakout fires
        "potential_stop_long": round(s2_high - STOP_ATR_MULTIPLIER * current_atr, 2)
            if not pd.isna(s2_high) else None,
        "potential_stop_short": round(s2_low + STOP_ATR_MULTIPLIER * current_atr, 2)
            if not pd.isna(s2_low) else None,
    }


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _calc_unit_size(equity: float, risk_pct: float, atr: float) -> int:
    """
    Turtle position sizing formula:
      Unit Size = floor( (Account Equity × Risk_Percent) ÷ ATR )

    The ATR represents the expected daily move (dollar risk per share).
    Dividing total dollar risk by ATR gives the number of shares we can
    hold while limiting our risk to risk_pct of equity.
    """
    if atr <= 0:
        return 0
    dollar_risk = equity * risk_pct   # e.g. $1,000 at 1% of $100k
    return int(dollar_risk / atr)


def _pyramid_levels(
    entry_price: float,
    atr: float,
    direction: str,
) -> list[float]:
    """
    Generate the price levels at which to add pyramid units.
    Each add is triggered when price moves 0.5 × ATR in our favor.
    Maximum MAX_PYRAMID_UNITS additional units.
    """
    levels = []
    for i in range(1, MAX_PYRAMID_UNITS + 1):
        step = PYRAMID_STEP_ATR * i * atr
        if direction == "long":
            levels.append(round(entry_price + step, 2))
        else:
            levels.append(round(entry_price - step, 2))
    return levels


def _days_since_last_high(highs: pd.Series, period: int) -> int:
    """Return how many bars since the series was last at its current max."""
    if len(highs) < period:
        return period
    rolling_max = highs.iloc[-(period + 30):].max()
    # Walk back to find when it was last at this level
    for i in range(len(highs) - 2, max(len(highs) - period - 30, 0), -1):
        if highs.iloc[i] >= rolling_max:
            return len(highs) - 1 - i
    return period


def _days_since_last_low(lows: pd.Series, period: int) -> int:
    """Return how many bars since the series was last at its current min."""
    if len(lows) < period:
        return period
    rolling_min = lows.iloc[-(period + 30):].min()
    for i in range(len(lows) - 2, max(len(lows) - period - 30, 0), -1):
        if lows.iloc[i] <= rolling_min:
            return len(lows) - 1 - i
    return period
