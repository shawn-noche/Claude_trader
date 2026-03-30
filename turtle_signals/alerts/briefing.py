"""alerts/briefing.py — Generate the full daily morning briefing."""

from datetime import datetime

from config import INITIAL_CAPITAL
from risk.portfolio_limits import get_portfolio_status
from signals.turtle_signals import Signal
from trades.monitor import TradeAlert


def generate_briefing(
    entry_signals: list,
    exit_alerts: list,
    add_alerts: list,
    time_alerts: list,
    watchlist: list,
    open_trades: list,
    account_equity: float = INITIAL_CAPITAL,
) -> tuple[str, str]:
    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    market_str = "Pre-Market" if now.hour < 9 or (now.hour == 9 and now.minute < 30) else "Market Hours"

    portfolio = get_portfolio_status()
    total_exposure = sum(t["current_price"] * t["units"] for t in open_trades)
    total_open_pnl = sum(t.get("unrealized_pnl", 0) for t in open_trades)

    lines = []
    sep = lambda: lines.append("-" * 45)

    sep()
    lines.append("TURTLE TRADER - DAILY BRIEFING")
    lines.append(f"Date: {date_str} | {market_str}")
    sep()
    lines.append("")

    entry_sigs = [s for s in entry_signals if "entry" in s.signal_type and not s.filtered]
    filtered_sigs = [s for s in entry_signals if "entry" in s.signal_type and s.filtered]

    lines.append(f"NEW ENTRY SIGNALS ({len(entry_sigs)} signals - act today)")
    sep()
    if not entry_sigs:
        lines.append("  No new entry signals today.")
    else:
        for i, sig in enumerate(entry_sigs, 1):
            lines.extend(_fmt_entry_text(i, sig))
    lines.append("")

    if filtered_sigs:
        lines.append(f"FILTERED SIGNALS ({len(filtered_sigs)} - skipped by System 1 winner rule)")
        sep()
        for sig in filtered_sigs:
            direction = "LONG" if sig.signal_type == "entry_long" else "SHORT"
            lines.append(f"  {sig.ticker} - {direction} (System {sig.system}) - SKIPPED: previous S1 trade was a winner")
        lines.append("")

    lines.append(f"EXIT ALERTS ({len(exit_alerts)} trades to close)")
    sep()
    if not exit_alerts:
        lines.append("  No exit alerts - all positions look healthy.")
    else:
        for i, alert in enumerate(exit_alerts, 1):
            lines.extend(_fmt_exit_text(i, alert))
    lines.append("")

    lines.append(f"ADD-TO-POSITION ALERTS ({len(add_alerts)} pyramid opportunities)")
    sep()
    if not add_alerts:
        lines.append("  No pyramid add alerts today.")
    else:
        for i, alert in enumerate(add_alerts, 1):
            lines.extend(_fmt_add_text(i, alert))
    lines.append("")

    lines.append(f"TIME-BASED EXIT WARNINGS ({len(time_alerts)})")
    sep()
    if not time_alerts:
        lines.append("  No time-based warnings.")
    else:
        for i, alert in enumerate(time_alerts, 1):
            lines.extend(_fmt_time_text(i, alert))
    lines.append("")

    close_ones = [w for w in watchlist if _best_proximity(w) >= 0.85]
    lines.append(f"APPROACHING BREAKOUT - WATCH THESE ({len(close_ones)})")
    sep()
    if not close_ones:
        lines.append("  No tickers near breakout levels (>85% threshold).")
    else:
        for i, w in enumerate(close_ones[:10], 1):
            lines.extend(_fmt_watchlist_text(i, w))
    lines.append("")

    lines.append("PORTFOLIO SNAPSHOT")
    sep()
    lines.append(f"  Account Equity    : ${account_equity:,.2f}")
    lines.append(f"  Open Trades       : {len(open_trades)}")
    lines.append(f"  Open P&L          : ${total_open_pnl:+,.2f}")
    lines.append(f"  Total Units Held  : {portfolio.total_units} / {portfolio.max_total} max")
    lines.append(f"  Longs             : {portfolio.long_units} units | Shorts: {portfolio.short_units} units")
    lines.append(f"  Total Exposure    : ${total_exposure:,.2f} ({total_exposure / account_equity * 100:.1f}% of account)")
    lines.append(f"  Available Capital : ${account_equity - total_exposure:,.2f}")
    sep()

    plain_text = "\n".join(lines)

    # Markdown for Telegram
    md = []
    md.append("*TURTLE TRADER - DAILY BRIEFING*")
    md.append(f"{date_str} | {market_str}")
    md.append("")
    md.append(f"*NEW ENTRY SIGNALS ({len(entry_sigs)} - Act Today)*")
    if not entry_sigs:
        md.append("_No new entry signals today._")
    else:
        for i, sig in enumerate(entry_sigs, 1):
            md.extend(_fmt_entry_md(i, sig))
    md.append("")
    md.append(f"*EXIT ALERTS ({len(exit_alerts)} - Close These)*")
    if not exit_alerts:
        md.append("_No exit alerts._")
    else:
        for i, alert in enumerate(exit_alerts, 1):
            md.extend(_fmt_exit_md(i, alert))
    md.append("")
    md.append(f"*ADD-TO-POSITION ALERTS ({len(add_alerts)})*")
    if not add_alerts:
        md.append("_No pyramid add alerts._")
    else:
        for i, alert in enumerate(add_alerts, 1):
            md.extend(_fmt_add_md(i, alert))
    md.append("")
    md.append(f"*TIME-BASED EXIT WARNINGS ({len(time_alerts)})*")
    if not time_alerts:
        md.append("_No time-based warnings._")
    else:
        for i, alert in enumerate(time_alerts, 1):
            md.extend(_fmt_time_md(i, alert))
    md.append("")
    md.append(f"*APPROACHING BREAKOUT ({len(close_ones)})*")
    if not close_ones:
        md.append("_No tickers near breakout._")
    else:
        for i, w in enumerate(close_ones[:10], 1):
            md.extend(_fmt_watchlist_md(i, w))
    md.append("")
    md.append("*PORTFOLIO SNAPSHOT*")
    md.append(f"Account Equity    : `${account_equity:,.2f}`")
    md.append(f"Open Trades       : `{len(open_trades)}`")
    md.append(f"Open P&L          : `${total_open_pnl:+,.2f}`")
    md.append(f"Total Units       : `{portfolio.total_units} / {portfolio.max_total}`")
    md.append(f"Longs / Shorts    : `{portfolio.long_units} / {portfolio.short_units}`")
    md.append(f"Total Exposure    : `${total_exposure:,.2f}` ({total_exposure / account_equity * 100:.1f}%)")
    md.append(f"Available Capital : `${account_equity - total_exposure:,.2f}`")

    markdown = "\n".join(md)
    return plain_text, markdown


def _fmt_entry_text(idx, sig):
    direction = "BUY LONG" if sig.signal_type == "entry_long" else "SELL SHORT"
    lines = [
        f"{idx}. {sig.ticker} - {direction} (System {sig.system})",
        f"   Current Price : ${sig.price:.2f}",
        f"   Breakout Level: ${sig.breakout_level:.2f}",
        f"   Stop-Loss     : ${sig.stop_loss:.2f}  (2xATR ${sig.atr:.2f})",
        f"   Unit Size     : {sig.unit_size} shares",
        f"   Unit Alt 2%   : {sig.unit_size_2pct} shares  (aggressive variant)",
        f"   Total Cost    : ~${sig.total_cost:,.2f}",
        f"   Max Risk      : ${sig.max_risk_dollars:,.2f}  (1.0% of account)",
        f"   ATR (20-day)  : ${sig.atr:.2f}",
        f"   Reason        : {sig.reason}",
    ]
    for i, lvl in enumerate(sig.pyramid_levels, 1):
        lines.append(f"   Add Unit {i} at : ${lvl:.2f}")
    lines.append("")
    return lines


def _fmt_entry_md(idx, sig):
    direction = "BUY LONG" if sig.signal_type == "entry_long" else "SELL SHORT"
    lines = [
        f"*{idx}. {sig.ticker} - {direction} (System {sig.system})*",
        f"   Breakout: `${sig.breakout_level:.2f}` | Stop: `${sig.stop_loss:.2f}` | ATR: `${sig.atr:.2f}`",
        f"   Units: `{sig.unit_size}` | Cost: `~${sig.total_cost:,.2f}` | Risk: `${sig.max_risk_dollars:,.2f}`",
    ]
    for i, lvl in enumerate(sig.pyramid_levels, 1):
        lines.append(f"   Add Unit {i}: `${lvl:.2f}`")
    lines.append("")
    return lines


def _fmt_exit_text(idx, alert):
    return [
        f"{idx}. {alert.ticker} - EXIT {alert.direction.upper()}",
        f"   Your Entry    : ${alert.entry_price:.2f}  (opened {alert.days_open} days ago)",
        f"   Current Price : ${alert.current_price:.2f}",
        f"   Estimated P&L : ${alert.pnl_estimate:+,.2f}",
        "",
    ]


def _fmt_exit_md(idx, alert):
    return [
        f"*{idx}. {alert.ticker} - EXIT {alert.direction.upper()}*",
        f"   Entry: `${alert.entry_price:.2f}` | Current: `${alert.current_price:.2f}` | P&L: `${alert.pnl_estimate:+,.2f}`",
        "",
    ]


def _fmt_add_text(idx, alert):
    lines = [
        f"{idx}. {alert.ticker} - ADD UNIT",
        f"   Current Price : ${alert.current_price:.2f}",
        f"   Entry Price   : ${alert.entry_price:.2f}",
    ]
    if alert.new_stop:
        lines.append(f"   New Stop      : ${alert.new_stop:.2f}")
    lines.append("")
    return lines


def _fmt_add_md(idx, alert):
    lines = [f"*{idx}. {alert.ticker} - ADD UNIT*",
              f"   Price: `${alert.current_price:.2f}` | Entry: `${alert.entry_price:.2f}`"]
    if alert.new_stop:
        lines.append(f"   New Stop: `${alert.new_stop:.2f}`")
    lines.append("")
    return lines


def _fmt_time_text(idx, alert):
    change_pct = abs(alert.current_price - alert.entry_price) / alert.entry_price * 100
    return [
        f"{idx}. {alert.ticker} - CONSIDER EXITING ({alert.days_open} days open, only +{change_pct:.1f}% movement)",
        f"   Your Entry    : ${alert.entry_price:.2f}",
        f"   Current Price : ${alert.current_price:.2f}",
        f"   Action        : Consider closing - no trend has developed",
        "",
    ]


def _fmt_time_md(idx, alert):
    change_pct = abs(alert.current_price - alert.entry_price) / alert.entry_price * 100
    return [
        f"*{idx}. {alert.ticker}* - {alert.days_open} days, only +{change_pct:.1f}% move",
        f"   Entry: `${alert.entry_price:.2f}` | Now: `${alert.current_price:.2f}`",
        "",
    ]


def _fmt_watchlist_text(idx, w):
    prox = _best_proximity(w)
    if w.get("s2_long_proximity", 0) >= w.get("s1_long_proximity", 0):
        level = w.get("s2_long_level", 0)
        system = "System 2"
    else:
        level = w.get("s1_long_level", 0)
        system = "System 1"
    return [
        f"{idx}. {w['ticker']} - {prox * 100:.0f}% of the way to {system} breakout",
        f"   Current Price : ${w['current_price']:.2f}",
        f"   Breakout Level: ${level:.2f}  ATR: ${w['atr']:.2f}",
        "",
    ]


def _fmt_watchlist_md(idx, w):
    prox = _best_proximity(w)
    if w.get("s2_long_proximity", 0) >= w.get("s1_long_proximity", 0):
        level = w.get("s2_long_level", 0)
        system = "System 2"
    else:
        level = w.get("s1_long_level", 0)
        system = "System 1"
    return [
        f"*{idx}. {w['ticker']}* - `{prox * 100:.0f}%` to {system} breakout",
        f"   Price: `${w['current_price']:.2f}` | Target: `${level:.2f}` | ATR: `${w['atr']:.2f}`",
        "",
    ]


def _best_proximity(w: dict) -> float:
    return max(w.get("s1_long_proximity") or 0, w.get("s2_long_proximity") or 0)
