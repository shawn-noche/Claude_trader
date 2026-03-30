"""
risk/position_sizer.py — Turtle position sizing with full breakdown.

The Turtle formula:
  Unit Size = floor( (Account Equity × Risk_Percent) ÷ ATR )

Where ATR is the 20-day Wilder's ATR (the expected daily dollar move).
This ensures a 1 ATR adverse move costs exactly Risk_Percent of equity.
"""

import math
from dataclasses import dataclass

from config import (
    INITIAL_CAPITAL,
    RISK_PER_TRADE,
    MAX_RISK_PER_TRADE,
    STOP_ATR_MULTIPLIER,
    PYRAMID_STEP_ATR,
    MAX_PYRAMID_UNITS,
)


@dataclass
class SizingBreakdown:
    """Full position sizing calculation with human-readable explanation."""
    ticker: str
    direction: str                # 'long' or 'short'
    account_equity: float
    risk_pct: float               # e.g. 0.01 for 1%
    atr: float
    entry_price: float

    # Calculated values
    dollar_risk_budget: float     # equity × risk_pct
    stop_distance: float          # 2 × ATR (dollar distance to stop)
    unit_size: int                # floor(dollar_risk / ATR) = floor(dollar_risk / stop_per_share)
    unit_size_aggressive: int     # same at 2% risk
    total_cost: float             # unit_size × entry_price
    max_risk_dollars: float       # dollar_risk_budget (max loss on 1 unit)
    account_pct_exposed: float    # total_cost / equity (% of account used)
    stop_loss: float              # actual stop-loss price

    pyramid_levels: list[float]   # Price levels to add units
    pyramid_unit_sizes: list[int] # Unit sizes at each pyramid level (may differ)

    explanation: str              # Step-by-step human-readable breakdown


def calculate_position_size(
    ticker: str,
    direction: str,
    entry_price: float,
    atr: float,
    account_equity: float = INITIAL_CAPITAL,
    risk_pct: float = RISK_PER_TRADE,
) -> SizingBreakdown:
    """
    Calculate the full position size breakdown for a Turtle trade.

    Step-by-step:
    1. Determine dollar risk budget: equity × risk_pct
    2. Calculate ATR-based stop distance: 2 × ATR
    3. Unit size = floor(dollar_risk_budget / ATR)
       (Each unit risks approximately risk_pct of equity)
    4. Total cost = unit_size × entry_price
    5. Generate pyramid levels (every 0.5 ATR in our favor)

    Args:
        ticker:         Instrument symbol
        direction:      'long' or 'short'
        entry_price:    Breakout price (confirmed close)
        atr:            Current 20-day Wilder's ATR
        account_equity: Total account value
        risk_pct:       Fraction to risk per unit (default 1%)

    Returns:
        SizingBreakdown with all details.
    """
    # Step 1: Dollar risk budget
    dollar_risk_budget = account_equity * risk_pct

    # Step 2: Stop distance
    stop_distance = STOP_ATR_MULTIPLIER * atr

    # Step 3: Unit size (each unit's worst-case loss ≈ dollar_risk_budget)
    # If stop is hit, we lose: unit_size × stop_distance ≈ dollar_risk_budget
    unit_size = math.floor(dollar_risk_budget / atr) if atr > 0 else 0
    unit_aggressive = math.floor(account_equity * MAX_RISK_PER_TRADE / atr) if atr > 0 else 0

    # Step 4: Position cost and exposure
    total_cost = unit_size * entry_price
    account_pct_exposed = (total_cost / account_equity * 100) if account_equity > 0 else 0.0

    # Step 5: Stop-loss price
    if direction == "long":
        stop_loss = round(entry_price - stop_distance, 2)
    else:
        stop_loss = round(entry_price + stop_distance, 2)

    # Step 6: Pyramid levels (add 1 unit per 0.5 ATR in our favor)
    pyramid_levels = []
    pyramid_unit_sizes = []
    for i in range(1, MAX_PYRAMID_UNITS + 1):
        if direction == "long":
            add_price = round(entry_price + PYRAMID_STEP_ATR * i * atr, 2)
        else:
            add_price = round(entry_price - PYRAMID_STEP_ATR * i * atr, 2)
        pyramid_levels.append(add_price)
        # Recalculate unit size at pyramid add price (ATR should be similar)
        add_unit = math.floor(dollar_risk_budget / atr) if atr > 0 else 0
        pyramid_unit_sizes.append(add_unit)

    # Build human-readable explanation
    explanation = _build_explanation(
        ticker, direction, entry_price, atr, account_equity, risk_pct,
        dollar_risk_budget, stop_distance, unit_size, unit_aggressive,
        total_cost, stop_loss, account_pct_exposed, pyramid_levels,
    )

    return SizingBreakdown(
        ticker=ticker,
        direction=direction,
        account_equity=account_equity,
        risk_pct=risk_pct,
        atr=atr,
        entry_price=entry_price,
        dollar_risk_budget=round(dollar_risk_budget, 2),
        stop_distance=round(stop_distance, 2),
        unit_size=unit_size,
        unit_size_aggressive=unit_aggressive,
        total_cost=round(total_cost, 2),
        max_risk_dollars=round(dollar_risk_budget, 2),
        account_pct_exposed=round(account_pct_exposed, 2),
        stop_loss=stop_loss,
        pyramid_levels=pyramid_levels,
        pyramid_unit_sizes=pyramid_unit_sizes,
        explanation=explanation,
    )


def recalculate_stop_after_pyramid(
    units_held: list[tuple[float, float]],
    direction: str,
) -> float:
    """
    After adding a pyramid unit, the stop-loss moves to protect the latest entry.
    New stop = latest entry ± (2 × ATR of latest entry).
    """
    if not units_held:
        return 0.0
    latest_price, latest_atr = units_held[-1]
    if direction == "long":
        return round(latest_price - STOP_ATR_MULTIPLIER * latest_atr, 2)
    else:
        return round(latest_price + STOP_ATR_MULTIPLIER * latest_atr, 2)


def _build_explanation(
    ticker, direction, entry_price, atr, equity, risk_pct,
    dollar_risk, stop_dist, unit_size, unit_aggressive,
    total_cost, stop_loss, pct_exposed, pyramid_levels,
) -> str:
    dir_word = "LONG" if direction == "long" else "SHORT"
    stop_word = "below" if direction == "long" else "above"
    lines = [
        f"Position Sizing Breakdown — {ticker} {dir_word}",
        "=" * 50,
        f"Step 1 | Account Equity        : ${equity:,.2f}",
        f"       | Risk per Trade (%)     : {risk_pct * 100:.1f}%",
        f"       | Dollar Risk Budget     : ${dollar_risk:,.2f}",
        f"         (${equity:,.0f} × {risk_pct * 100:.1f}% = ${dollar_risk:,.2f})",
        "",
        f"Step 2 | 20-day ATR             : ${atr:.2f}",
        f"       | Stop Multiplier        : {STOP_ATR_MULTIPLIER}×",
        f"       | Stop Distance          : ${stop_dist:.2f}",
        f"         ({STOP_ATR_MULTIPLIER} × ${atr:.2f} = ${stop_dist:.2f})",
        "",
        f"Step 3 | Unit Size Formula      : floor(${dollar_risk:,.2f} ÷ ${atr:.2f})",
        f"       | Unit Size @ 1% risk    : {unit_size} shares",
        f"       | Unit Size @ 2% risk    : {unit_aggressive} shares  (aggressive)",
        "",
        f"Step 4 | Entry Price            : ${entry_price:.2f}",
        f"       | Stop-Loss              : ${stop_loss:.2f}  ({STOP_ATR_MULTIPLIER}×ATR {stop_word} entry)",
        f"       | Total Position Cost    : ${total_cost:,.2f}",
        f"       | % of Account Exposed   : {pct_exposed:.1f}%",
        f"       | Max Loss if Stop Hit   : ${dollar_risk:,.2f}  ({risk_pct * 100:.1f}% of account)",
        "",
        f"Step 5 | Pyramid Add Levels:",
    ]
    for i, lvl in enumerate(pyramid_levels, 1):
        lines.append(f"       | Unit {i + 1} at ${lvl:.2f}  (add when price hits this level)")
    return "\n".join(lines)
