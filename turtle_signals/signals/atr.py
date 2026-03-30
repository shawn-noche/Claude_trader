"""
signals/atr.py — Wilder's Average True Range (ATR) calculation.

The original Turtle Traders used Wilder's smoothing (not simple average).
Wilder's ATR = previous ATR × (n-1)/n + current TR × 1/n
which is equivalent to an exponentially-weighted moving average with
alpha = 1/n.

Reference: J. Welles Wilder, "New Concepts in Technical Trading Systems" (1978)
"""

import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    """
    Calculate daily True Range for each bar.

    True Range = max of:
      (a) High - Low          (today's intraday range)
      (b) |High - Prev Close| (gap up scenario)
      (c) |Low  - Prev Close| (gap down scenario)
    """
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr


def wilder_atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Compute Wilder's smoothed ATR.

    Wilder's method seeds the first ATR value as the simple average of the
    first `period` True Range values, then applies the smoothing formula:
        ATR_t = ATR_{t-1} * (period - 1) / period + TR_t / period

    Args:
        df:     DataFrame with High, Low, Close columns.
        period: Smoothing period (default 20 per Turtle system rules).

    Returns:
        Series of ATR values, indexed like df.
    """
    tr = true_range(df)
    atr = pd.Series(index=df.index, dtype=float)

    # Seed: first ATR = simple mean of first `period` true range values
    if len(tr) < period:
        return atr  # Not enough data

    atr.iloc[period - 1] = tr.iloc[:period].mean()

    # Wilder's smoothing: exponentially-weighted with alpha = 1/period
    alpha = 1.0 / period
    for i in range(period, len(tr)):
        atr.iloc[i] = atr.iloc[i - 1] * (1 - alpha) + tr.iloc[i] * alpha

    return atr


def latest_atr(df: pd.DataFrame, period: int = 20) -> float:
    """
    Return the most recent ATR value as a plain float.
    Returns 0.0 if insufficient data.
    """
    atr_series = wilder_atr(df, period)
    valid = atr_series.dropna()
    if valid.empty:
        return 0.0
    return float(valid.iloc[-1])
