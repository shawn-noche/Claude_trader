"""trades/monitor.py — Monitor open trades for exit conditions."""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from config import (
    SYSTEM1_MAX_DAYS, SYSTEM2_MAX_DAYS,
    TIME_EXIT_THRESHOLD, PYRAMID_STEP_ATR, MAX_PYRAMID_UNITS,
)
from data.fetcher import get_current_price
from trades.database import get_open_trades, get_db
from signals.atr import latest_atr

logger = logging.getLogger(__name__)


@dataclass
class TradeAlert:
    trade_id: int
    ticker: str
    direction: str
    alert_type: str
    urgency: str
    current_price: float
    entry_price: float
    units: int
    entry_date: str
    days_open: int
    message: str
    pnl_estimate: float
    new_stop: Optional[float] = None


def monitor_all_trades(price_data: dict | None = None) -> list[TradeAlert]:
    open_trades = get_open_trades()
    if not open_trades:
        return []

    alerts: list[TradeAlert] = []
    today = date.today()

    for trade in open_trades:
        trade_id = trade["id"]
        ticker = trade["ticker"]
        direction = trade["direction"]
        entry_price = float(trade["entry_price"])
        stop_loss = float(trade["stop_loss"])
        units = trade["units"]
        current_units = trade["current_units"] or 1
        entry_date_str = trade["entry_date"]
        system = trade["system"]

        try:
            entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
            days_open = (today - entry_date).days
        except ValueError:
            days_open = 0

        if price_data and ticker in price_data:
            df = price_data[ticker]
            current_price = float(df["Close"].iloc[-1])
        else:
            current_price = get_current_price(ticker)
            if current_price is None:
                logger.warning("Could not get price for %s", ticker)
                continue

        if direction == "long":
            pnl = (current_price - entry_price) * units
        else:
            pnl = (entry_price - current_price) * units

        base_kwargs = dict(
            trade_id=trade_id,
            ticker=ticker,
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            units=units,
            entry_date=entry_date_str,
            days_open=days_open,
            pnl_estimate=round(pnl, 2),
        )

        stop_breached = (
            (direction == "long" and current_price <= stop_loss) or
            (direction == "short" and current_price >= stop_loss)
        )
        if stop_breached:
            alerts.append(TradeAlert(
                **base_kwargs,
                alert_type="stop_loss",
                urgency="urgent",
                message=(
                    f"STOP-LOSS HIT - {ticker} {direction.upper()}\n"
                    f"   Your stop: ${stop_loss:.2f} | Current: ${current_price:.2f}\n"
                    f"   EXIT IMMEDIATELY - estimated loss: ${pnl:,.2f}"
                ),
            ))
            continue

        exit_signal = _check_exit_signal(ticker, direction, system, current_price, price_data)
        if exit_signal:
            alerts.append(TradeAlert(
                **base_kwargs,
                alert_type="exit_signal",
                urgency="normal",
                message=(
                    f"EXIT SIGNAL - {ticker} {direction.upper()} (System {system})\n"
                    f"   {exit_signal}\n"
                    f"   Entry: ${entry_price:.2f} | Current: ${current_price:.2f} | "
                    f"Est P&L: ${pnl:+,.2f}"
                ),
            ))

        max_days = SYSTEM1_MAX_DAYS if system == 1 else SYSTEM2_MAX_DAYS
        price_change_pct = abs(current_price - entry_price) / entry_price

        if days_open >= max_days and price_change_pct < TIME_EXIT_THRESHOLD:
            alerts.append(TradeAlert(
                **base_kwargs,
                alert_type="time_exit",
                urgency="normal",
                message=(
                    f"TIME EXIT WARNING - {ticker} {direction.upper()}\n"
                    f"   {days_open} days open, only {price_change_pct * 100:.2f}% movement\n"
                    f"   System {system} limit: {max_days} days with <{TIME_EXIT_THRESHOLD * 100:.1f}% move"
                ),
            ))

        pyramid_alert = _check_pyramid(
            ticker, direction, entry_price, current_price, current_units, price_data,
        )
        if pyramid_alert:
            alerts.append(TradeAlert(
                **base_kwargs,
                alert_type="pyramid",
                urgency="info",
                new_stop=pyramid_alert.get("new_stop"),
                message=(
                    f"ADD UNIT - {ticker} {direction.upper()} (Unit {current_units + 1})\n"
                    f"   Pyramid trigger at ${pyramid_alert['trigger_price']:.2f} reached\n"
                    f"   New stop after add: ${pyramid_alert['new_stop']:.2f}"
                ),
            ))

    priority = {"urgent": 0, "normal": 1, "info": 2}
    alerts.sort(key=lambda a: priority.get(a.urgency, 3))
    return alerts


def _check_exit_signal(
    ticker: str, direction: str, system: int,
    current_price: float, price_data: dict | None,
) -> Optional[str]:
    if price_data is None or ticker not in price_data:
        return None
    df = price_data[ticker]
    exit_period = 10 if system == 1 else 20
    if len(df) < exit_period:
        return None
    if direction == "long":
        exit_low = float(df["Low"].iloc[-exit_period:].min())
        if current_price < exit_low:
            return f"Price ${current_price:.2f} broke below {exit_period}-day lowest low of ${exit_low:.2f}"
    else:
        exit_high = float(df["High"].iloc[-exit_period:].max())
        if current_price > exit_high:
            return f"Price ${current_price:.2f} broke above {exit_period}-day highest high of ${exit_high:.2f}"
    return None


def _check_pyramid(
    ticker: str, direction: str, entry_price: float,
    current_price: float, current_units: int, price_data: dict | None,
) -> Optional[dict]:
    if current_units >= MAX_PYRAMID_UNITS:
        return None
    if price_data is None or ticker not in price_data:
        return None
    df = price_data[ticker]
    atr = latest_atr(df)
    if atr <= 0:
        return None
    step = PYRAMID_STEP_ATR * current_units * atr
    if direction == "long":
        trigger = entry_price + step
        if current_price >= trigger:
            return {"trigger_price": round(trigger, 2), "new_stop": round(current_price - 2 * atr, 2), "unit_size": 1}
    else:
        trigger = entry_price - step
        if current_price <= trigger:
            return {"trigger_price": round(trigger, 2), "new_stop": round(current_price + 2 * atr, 2), "unit_size": 1}
    return None


def get_open_trade_summary(price_data: dict | None = None) -> list[dict]:
    open_trades = get_open_trades()
    results = []
    today = date.today()
    for trade in open_trades:
        ticker = trade["ticker"]
        entry_price = float(trade["entry_price"])
        units = trade["units"]
        direction = trade["direction"]
        if price_data and ticker in price_data:
            current_price = float(price_data[ticker]["Close"].iloc[-1])
        else:
            current_price = get_current_price(ticker) or entry_price
        if direction == "long":
            pnl = (current_price - entry_price) * units
        else:
            pnl = (entry_price - current_price) * units
        try:
            entry_date = datetime.strptime(trade["entry_date"], "%Y-%m-%d").date()
            days_open = (today - entry_date).days
        except ValueError:
            days_open = 0
        results.append({
            "id": trade["id"], "ticker": ticker, "direction": direction,
            "system": trade["system"], "entry_date": trade["entry_date"],
            "entry_price": entry_price, "units": units,
            "current_units": trade["current_units"], "stop_loss": float(trade["stop_loss"]),
            "current_price": current_price, "unrealized_pnl": round(pnl, 2),
            "days_open": days_open, "status": trade["status"], "notes": trade["notes"],
        })
    return results
